from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QElapsedTimer, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .ai_plan import TimelinePlanManager
from .bridge import BridgeRouter, LocalTimelineBridge, QtBridgeDispatcher
from .project_store import apply_project, load_project, save_project as save_project_file
from .shot_detection import UnitShotAnalysis, analyze_unit_candidates
from .timeline_history import TimelineHistory
from .timeline_model import TimelineDocument
from .timeline_tools import TimelineToolRegistry
from .timeline_view import TimelineView
from .v42_1b2 import V42OneB2Plan, load_1b2
from .v42_state import V42WorkflowState

APP_TITLE = "MiniCut V42 AI Timeline"

STYLE = """
QMainWindow, QWidget { background: #17191f; color: #e5e7eb; font-size: 12px; }
QToolBar { background: #20232b; border: 0; spacing: 6px; padding: 5px; }
QPushButton { background: #2a2e37; border: 1px solid #3a3f49; border-radius: 5px; padding: 7px 12px; }
QPushButton:hover { background: #343945; }
QPushButton:disabled { color: #6f7480; background: #23262d; }
QListWidget, QPlainTextEdit { background: #121419; border: 1px solid #2e333d; border-radius: 4px; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background: #315d9a; }
QDockWidget::title { background: #20232b; padding: 8px; }
QSlider::groove:horizontal { height: 4px; background: #383d47; }
QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius: 6px; background: #e7e9ee; }
#PanelTitle { font-size: 13px; font-weight: 600; padding: 4px 0 8px 0; }
#PreviewFrame { background: #090a0d; border: 1px solid #2e333d; }
#InspectorValue { color: #b9bec8; }
#StatusPill { background: #252a33; border-radius: 9px; padding: 3px 8px; }
"""


class ShotDetectionWorker(QThread):
    resultReady = Signal(object)
    errorRaised = Signal(str)

    def __init__(
        self,
        plan: V42OneB2Plan,
        unit_id: str,
        source: str,
        parent=None,
    ):
        super().__init__(parent)
        self.plan = plan
        self.unit_id = unit_id
        self.source = source

    def run(self):
        try:
            result = analyze_unit_candidates(
                self.plan,
                self.unit_id,
                self.source,
            )
        except Exception as exc:
            self.errorRaised.emit(str(exc))
            return
        self.resultReady.emit(result)


class MiniCutMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 900)
        self.setAcceptDrops(True)

        self.document = TimelineDocument.default()
        self.history = TimelineHistory(self.document)
        self.tools = TimelineToolRegistry(self.document, self.history)
        self.plan_manager = TimelinePlanManager(
            self.tools,
            action_validator=self._validate_ai_plan_action,
        )
        self.media_durations: dict[str, int] = {}
        self.current_media: str | None = None
        self.project_path: Path | None = None
        self.workflow_state = V42WorkflowState()
        self.v42_1b2_plan: V42OneB2Plan | None = None
        self._shot_worker: ShotDetectionWorker | None = None
        self._loading_project = False

        # Preview has two contexts: source-bin preview and composed timeline preview.
        self.preview_mode = "source"
        self.preview_clip_id: str | None = None
        self._timeline_playing = False
        self._timeline_clock = QElapsedTimer()
        self._timeline_timer = QTimer(self)
        self._timeline_timer.setInterval(33)
        self._timeline_timer.timeout.connect(self._timeline_tick)

        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_workspace()
        self._build_ai_dock()
        self._connect_player()
        self._refresh_edit_actions()

        self.bridge_router = None
        self.bridge_dispatcher = None
        self.local_bridge = None
        self._start_local_bridge()

        self.statusBar().showMessage("Siap · timeline manual + bridge lokal aktif")
        self.setStyleSheet(STYLE)

    def _build_actions(self):
        self.action_open_project = QAction("Open Project", self)
        self.action_open_project.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open_project.triggered.connect(self.open_project)

        self.action_save_project = QAction("Save", self)
        self.action_save_project.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save_project.triggered.connect(self.save_project)

        self.action_save_project_as = QAction("Save As", self)
        self.action_save_project_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.action_save_project_as.triggered.connect(self.save_project_as)

        self.action_import = QAction("Import Media", self)
        self.action_import.setShortcut(QKeySequence("Ctrl+I"))
        self.action_import.triggered.connect(self.import_media)

        self.action_import_1b2 = QAction("Import 1B2 Plan", self)
        self.action_import_1b2.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.action_import_1b2.triggered.connect(self.import_1b2_plan)

        self.action_add_timeline = QAction("Add to Timeline", self)
        self.action_add_timeline.setEnabled(False)
        self.action_add_timeline.triggered.connect(self.add_selected_to_timeline)

        self.action_split = QAction("Split", self)
        self.action_split.setShortcut(QKeySequence("Ctrl+B"))
        self.action_split.triggered.connect(self.split_selected_clip)

        self.action_delete = QAction("Delete", self)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.action_delete.triggered.connect(self.delete_selected_clip)

        self.action_undo = QAction("Undo", self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_undo.triggered.connect(self.undo_timeline)

        self.action_redo = QAction("Redo", self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.action_redo.triggered.connect(self.redo_timeline)

        self.action_export = QAction("Export", self)
        self.action_export.setEnabled(False)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.action_open_project)
        file_menu.addAction(self.action_import)
        file_menu.addAction(self.action_import_1b2)
        file_menu.addSeparator()
        file_menu.addAction(self.action_save_project)
        file_menu.addAction(self.action_save_project_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_split)
        edit_menu.addAction(self.action_delete)

    def _build_toolbar(self):
        bar = QToolBar("Main", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        for action in (
            self.action_open_project,
            self.action_save_project,
            self.action_import,
            self.action_import_1b2,
            self.action_add_timeline,
            self.action_split,
            self.action_delete,
            self.action_undo,
            self.action_redo,
        ):
            bar.addAction(action)
        bar.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        bar.addAction(self.action_export)

    def _panel(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        label = QLabel(title)
        label.setObjectName("PanelTitle")
        layout.addWidget(label)
        return widget, layout

    def _build_workspace(self):
        media_panel, media_layout = self._panel("Media / Project")
        self.media_list = QListWidget()
        self.media_list.itemSelectionChanged.connect(self._media_selection_changed)
        self.media_list.itemDoubleClicked.connect(lambda _: self.add_selected_to_timeline())
        media_layout.addWidget(self.media_list, 1)
        media_buttons = QHBoxLayout()
        import_button = QPushButton("Import Media")
        import_button.clicked.connect(self.import_media)
        add_button = QPushButton("Tambah ke Timeline")
        add_button.clicked.connect(self.add_selected_to_timeline)
        media_buttons.addWidget(import_button)
        media_buttons.addWidget(add_button)
        media_layout.addLayout(media_buttons)

        preview_panel, preview_layout = self._panel("Preview")
        self.video = QVideoWidget()
        self.video.setObjectName("PreviewFrame")
        self.video.setMinimumSize(520, 290)
        self.player.setVideoOutput(self.video)
        preview_layout.addWidget(self.video, 1)

        transport = QHBoxLayout()
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.timeline_zoom = QSlider(Qt.Orientation.Horizontal)
        self.timeline_zoom.setRange(24, 220)
        self.timeline_zoom.setValue(82)
        transport.addWidget(self.play_button)
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        transport.addWidget(QLabel("Timeline Zoom"))
        transport.addWidget(self.timeline_zoom)
        preview_layout.addLayout(transport)

        inspector_panel, inspector_layout = self._panel("Inspector")
        self.inspector_form = QFormLayout()
        self.inspector_source = QLabel("—")
        self.inspector_track = QLabel("—")
        self.inspector_in = QLabel("—")
        self.inspector_out = QLabel("—")
        self.inspector_speed = QLabel("—")
        for label in (
            self.inspector_source,
            self.inspector_track,
            self.inspector_in,
            self.inspector_out,
            self.inspector_speed,
        ):
            label.setObjectName("InspectorValue")
        self.inspector_form.addRow("Source", self.inspector_source)
        self.inspector_form.addRow("Track", self.inspector_track)
        self.inspector_form.addRow("In", self.inspector_in)
        self.inspector_form.addRow("Out", self.inspector_out)
        self.inspector_form.addRow("Speed", self.inspector_speed)
        inspector_layout.addLayout(self.inspector_form)
        inspector_layout.addStretch(1)

        upper = QSplitter(Qt.Orientation.Horizontal)
        upper.addWidget(media_panel)
        upper.addWidget(preview_panel)
        upper.addWidget(inspector_panel)
        upper.setStretchFactor(0, 1)
        upper.setStretchFactor(1, 4)
        upper.setStretchFactor(2, 1)
        upper.setSizes([270, 850, 260])

        timeline_container = QWidget()
        timeline_layout = QVBoxLayout(timeline_container)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_head = QHBoxLayout()
        timeline_title = QLabel("Timeline")
        timeline_title.setObjectName("PanelTitle")
        self.timeline_status = QLabel("0 clip")
        self.timeline_status.setObjectName("StatusPill")
        timeline_head.addWidget(timeline_title)
        timeline_head.addStretch(1)
        timeline_head.addWidget(self.timeline_status)
        timeline_layout.addLayout(timeline_head)
        self.timeline = TimelineView(self.document)
        timeline_layout.addWidget(self.timeline)

        root = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(upper)
        root.addWidget(timeline_container)
        root.setStretchFactor(0, 3)
        root.setStretchFactor(1, 2)
        root.setSizes([540, 330])
        self.setCentralWidget(root)

        self.timeline_zoom.valueChanged.connect(self.timeline.set_zoom)
        self.timeline.seekRequested.connect(self._timeline_seek)
        self.timeline.clipSelected.connect(self._clip_selected)
        self.timeline.clipMoveRequested.connect(self._move_clip_requested)
        self.timeline.clipTrimRequested.connect(self._trim_clip_requested)
        self.timeline.trackControlRequested.connect(self._track_control_requested)

    def _build_ai_dock(self):
        dock = QDockWidget("AI Agent", self)
        dock.setObjectName("AIAgentDock")
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.ai_status = QLabel("Idle · Agent belum diaktifkan")
        self.ai_status.setObjectName("StatusPill")
        self.ai_unit = QLabel("Unit V42: —")
        self.ai_1b2_status = QLabel("1B2: belum dimuat")
        self.ai_1b2_status.setObjectName("StatusPill")
        self.ai_import_1b2 = QPushButton("Import 1B2")
        self.ai_import_1b2.clicked.connect(self.import_1b2_plan)
        self.ai_shot_status = QLabel("Shot lokal: belum dianalisis")
        self.ai_shot_status.setObjectName("StatusPill")
        self.ai_detect_shots = QPushButton("Pecah Kandidat per Kamera")
        self.ai_detect_shots.setEnabled(False)
        self.ai_detect_shots.clicked.connect(self._analyze_next_1b2_unit)

        self.ai_input = QPlainTextEdit()
        self.ai_input.setPlaceholderText(
            "Nanti: “Kerjakan B-001”, “Cari visual lain untuk N-007”, dll."
        )
        self.ai_input.setMaximumHeight(90)

        self.ai_plan_view = QPlainTextEdit()
        self.ai_plan_view.setReadOnly(True)
        self.ai_plan_view.setPlaceholderText(
            "Belum ada AI plan. Plan dari MCP/Gemini akan muncul di sini sebelum timeline berubah."
        )
        self.ai_plan_view.setMinimumHeight(160)

        plan_buttons = QHBoxLayout()
        self.ai_apply_plan = QPushButton("Apply Plan")
        self.ai_apply_plan.setEnabled(False)
        self.ai_apply_plan.clicked.connect(self._apply_ai_plan)
        self.ai_cancel_plan = QPushButton("Cancel Plan")
        self.ai_cancel_plan.setEnabled(False)
        self.ai_cancel_plan.clicked.connect(self._cancel_ai_plan)
        plan_buttons.addWidget(self.ai_apply_plan)
        plan_buttons.addWidget(self.ai_cancel_plan)

        self.ai_run = QPushButton("Jalankan AI")
        self.ai_run.setEnabled(False)

        layout.addWidget(self.ai_status)
        layout.addWidget(self.ai_unit)
        layout.addWidget(self.ai_1b2_status)
        layout.addWidget(self.ai_import_1b2)
        layout.addWidget(self.ai_shot_status)
        layout.addWidget(self.ai_detect_shots)
        layout.addWidget(self.ai_input)
        layout.addWidget(QLabel("AI Plan / Review"))
        layout.addWidget(self.ai_plan_view)
        layout.addLayout(plan_buttons)
        layout.addWidget(self.ai_run)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._refresh_ai_plan()

    def import_1b2_plan(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import V42 1B2 Plan",
            "",
            "V42 1B2 (*.json *.docx *.txt);;JSON (*.json);;Word (*.docx);;Text (*.txt);;All Files (*)",
        )
        if not filename:
            return

        try:
            plan = load_1b2(filename)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.statusBar().showMessage(f"Gagal membaca 1B2: {exc}")
            return

        if not plan.units:
            self.statusBar().showMessage(
                "1B2 terbaca tetapi tidak ada unit N/J/D yang dapat digunakan."
            )
            return

        self.v42_1b2_plan = plan

        # Preserve existing meaningful progress when re-importing an updated 1B2.
        for unit in plan.units.values():
            if unit.kind not in {"narration", "anchor"}:
                continue
            existing = self.workflow_state.units.get(unit.id)
            if isinstance(existing, dict) and existing.get("status") in {
                "working",
                "locked",
                "needs_revision",
            }:
                continue
            self.workflow_state.set_unit_status(
                unit.id,
                "pending",
                block_id=unit.block_id,
                timeline_revision=self.tools.revision,
            )

        next_unit = self._next_1b2_unit_id()
        if next_unit is not None:
            unit = plan.units[next_unit]
            self.workflow_state.active_unit = next_unit
            self.workflow_state.active_block = unit.block_id

        self.record_v42_checkpoint(
            "1b2-import",
            block_id=self.workflow_state.active_block,
            unit_id=self.workflow_state.active_unit,
            payload={
                "plan": plan.to_dict(),
                "summary": plan.summary(),
            },
        )
        self._refresh_1b2_status()
        self._refresh_shot_status()

        summary = plan.summary()
        message = (
            f"1B2 dimuat · {summary['blocks']} blok · {summary['units']} unit · "
            f"{summary['candidate_ranges']} rentang kandidat"
        )
        if plan.warnings:
            message += f" · {len(plan.warnings)} peringatan"
        self.statusBar().showMessage(message)

    def _restore_1b2_plan_from_workflow(self):
        self.v42_1b2_plan = None
        checkpoint = self.workflow_state.checkpoints.get("1b2-import")
        if not isinstance(checkpoint, dict):
            self._refresh_1b2_status()
            return

        payload = checkpoint.get("payload")
        if not isinstance(payload, dict):
            self._refresh_1b2_status()
            return

        raw_plan = payload.get("plan")
        if not isinstance(raw_plan, dict):
            self._refresh_1b2_status()
            return

        try:
            self.v42_1b2_plan = V42OneB2Plan.from_dict(raw_plan)
        except (KeyError, TypeError, ValueError):
            self.v42_1b2_plan = None
        self._refresh_1b2_status()
        self._refresh_shot_status()

    def _next_1b2_unit_id(self) -> str | None:
        plan = self.v42_1b2_plan
        if plan is None:
            return None

        for item in plan.work_queue:
            unit_id = str(item).strip().upper()
            unit = plan.units.get(unit_id)
            if unit is None or unit.kind not in {"narration", "anchor"}:
                continue
            status = self.workflow_state.units.get(unit_id, {}).get("status", "pending")
            if status != "locked":
                return unit_id

        for unit in plan.units.values():
            if unit.kind in {"narration", "anchor"}:
                status = self.workflow_state.units.get(unit.id, {}).get(
                    "status", "pending"
                )
                if status != "locked":
                    return unit.id
        return None

    def _refresh_1b2_status(self):
        if not hasattr(self, "ai_1b2_status"):
            return
        plan = self.v42_1b2_plan
        if plan is None:
            self.ai_1b2_status.setText("1B2: belum dimuat")
            return

        summary = plan.summary()
        next_unit = self._next_1b2_unit_id() or "selesai"
        kinds = summary["unit_kinds"]
        self.ai_1b2_status.setText(
            "1B2 · "
            f"{summary['blocks']} blok · "
            f"{kinds.get('narration', 0)} N · "
            f"{kinds.get('anchor', 0)} J · "
            f"{summary['candidate_ranges']} kandidat · "
            f"berikutnya {next_unit}"
        )
        self._refresh_shot_status()

    def _analysis_source_path(self) -> str | None:
        selected = self.media_list.selectedItems()
        if selected:
            source = selected[0].data(Qt.ItemDataRole.UserRole)
            if source:
                return str(source)

        sources = sorted(self._allowed_bridge_sources())
        if len(sources) == 1:
            return sources[0]
        return None

    def _shot_unit_id(self) -> str | None:
        plan = self.v42_1b2_plan
        if plan is None:
            return None

        active = self.workflow_state.active_unit
        if active and active in plan.units:
            unit = plan.units[active]
            if unit.kind in {"narration", "anchor"}:
                status = self.workflow_state.units.get(active, {}).get(
                    "status", "pending"
                )
                if status != "locked":
                    return active
        return self._next_1b2_unit_id()

    def _analyze_next_1b2_unit(self):
        if self._shot_worker is not None:
            self.statusBar().showMessage("Deteksi shot lokal masih berjalan.")
            return

        plan = self.v42_1b2_plan
        if plan is None:
            self.statusBar().showMessage("Import 1B2 terlebih dahulu.")
            return

        unit_id = self._shot_unit_id()
        if unit_id is None:
            self.statusBar().showMessage("Tidak ada unit N/J 1B2 yang menunggu analisis.")
            return

        source = self._analysis_source_path()
        if source is None:
            self.statusBar().showMessage(
                "Pilih film sumber di Media Bin. Jika hanya ada satu media, MiniCut akan memilih otomatis."
            )
            return
        if not Path(source).is_file():
            self.statusBar().showMessage(f"Film sumber tidak ditemukan: {source}")
            return

        self.workflow_state.active_unit = unit_id
        unit = plan.units[unit_id]
        if unit.block_id:
            self.workflow_state.active_block = unit.block_id

        worker = ShotDetectionWorker(plan, unit_id, source, parent=self)
        worker.resultReady.connect(self._shot_analysis_ready)
        worker.errorRaised.connect(self._shot_analysis_error)
        worker.finished.connect(self._shot_worker_finished)
        self._shot_worker = worker

        self.ai_detect_shots.setEnabled(False)
        self.ai_shot_status.setText(f"Shot lokal: menganalisis {unit_id}…")
        self.statusBar().showMessage(
            f"Deteksi pergantian kamera lokal untuk {unit_id}…"
        )
        worker.start()

    def _shot_analysis_ready(self, result: UnitShotAnalysis):
        plan = self.v42_1b2_plan
        if plan is None:
            return

        unit = plan.units.get(result.unit_id)
        block_id = unit.block_id if unit is not None else None
        self.workflow_state.active_unit = result.unit_id
        if block_id:
            self.workflow_state.active_block = block_id

        self.workflow_state.set_unit_status(
            result.unit_id,
            "working",
            block_id=block_id,
            timeline_revision=self.tools.revision,
            note=(
                f"Candidate 1B2 dipecah lokal menjadi {result.shot_count} shot."
            ),
        )
        self.record_v42_checkpoint(
            f"shots-{result.unit_id}",
            block_id=block_id,
            unit_id=result.unit_id,
            payload={
                "analysis": result.to_dict(),
                "one_b2_source_sha256": plan.source_sha256,
            },
        )
        self._refresh_shot_status()
        summary = result.summary()
        self.statusBar().showMessage(
            f"{result.unit_id}: {summary['candidate_ranges']} candidate range → "
            f"{summary['shots']} shot lokal."
        )

    def _shot_analysis_error(self, message: str):
        self.ai_shot_status.setText("Shot lokal: gagal")
        self.statusBar().showMessage(f"Deteksi shot gagal: {message}")

    def _shot_worker_finished(self):
        worker = self._shot_worker
        self._shot_worker = None
        if worker is not None:
            worker.deleteLater()
        self._refresh_shot_status()

    def _shot_checkpoint_analysis(
        self,
        unit_id: str | None,
    ) -> UnitShotAnalysis | None:
        if not unit_id:
            return None
        checkpoint = self.workflow_state.checkpoints.get(f"shots-{unit_id}")
        if not isinstance(checkpoint, dict):
            return None
        payload = checkpoint.get("payload")
        if not isinstance(payload, dict):
            return None
        raw = payload.get("analysis")
        if not isinstance(raw, dict):
            return None
        try:
            return UnitShotAnalysis.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            return None

    def _refresh_shot_status(self):
        if not hasattr(self, "ai_shot_status"):
            return

        running = self._shot_worker is not None
        unit_id = self._shot_unit_id()
        analysis = self._shot_checkpoint_analysis(unit_id)
        if running:
            self.ai_detect_shots.setEnabled(False)
            return

        self.ai_detect_shots.setEnabled(
            self.v42_1b2_plan is not None and unit_id is not None
        )
        if unit_id is None:
            self.ai_shot_status.setText("Shot lokal: belum ada unit aktif")
        elif analysis is None:
            self.ai_shot_status.setText(f"Shot lokal {unit_id}: belum dianalisis")
        else:
            summary = analysis.summary()
            self.ai_shot_status.setText(
                f"Shot lokal {unit_id}: "
                f"{summary['candidate_ranges']} kandidat → {summary['shots']} shot"
            )

    def _start_local_bridge(self):
        try:
            self.bridge_router = BridgeRouter(
                self.tools,
                state_provider=self._bridge_state,
                seek_handler=self._bridge_seek,
                allowed_sources_provider=self._allowed_bridge_sources,
                mutation_callback=self._bridge_mutation,
                plan_manager=self.plan_manager,
                plan_callback=self._refresh_ai_plan,
            )
            self.bridge_dispatcher = QtBridgeDispatcher(
                self.bridge_router,
                parent=self,
            )
            self.local_bridge = LocalTimelineBridge(self.bridge_dispatcher)
            url = self.local_bridge.start()
            self.ai_status.setText(f"Bridge lokal aktif · {url} · AI cloud belum terhubung")
        except Exception as exc:
            self.local_bridge = None
            self.ai_status.setText("Bridge lokal gagal aktif")
            self.statusBar().showMessage(f"Bridge lokal gagal: {exc}")

    def _validate_ai_plan_action(self, tool: str, args: dict) -> str | None:
        if tool != "insert_clip":
            return None
        source = str(args.get("source", ""))
        if not source or source not in self._allowed_bridge_sources():
            return "AI hanya boleh memasukkan media yang sudah di-import ke proyek."
        return None

    def _refresh_ai_plan(self):
        if not hasattr(self, "ai_plan_view"):
            return

        plan = self.plan_manager.pending
        if plan is None:
            self.ai_plan_view.clear()
            self.ai_unit.setText("Unit V42: —")
            self.ai_apply_plan.setEnabled(False)
            self.ai_cancel_plan.setEnabled(False)
            if hasattr(self, "ai_status"):
                self.ai_status.setText(
                    f"Local timeline tools ready · rev {self.tools.revision}"
                )
            return

        stale = plan.expected_revision != self.tools.revision
        header = [
            f"{'[STALE] ' if stale else ''}{plan.title}",
            f"Plan ID: {plan.id}",
            f"Expected revision: {plan.expected_revision}",
            f"Current revision: {self.tools.revision}",
        ]
        if plan.explanation:
            header.extend(["", plan.explanation])
        header.append("")
        header.append(f"Actions ({len(plan.actions)}):")
        for index, action in enumerate(plan.actions, start=1):
            args_text = json.dumps(
                action.get("args", {}),
                ensure_ascii=False,
                sort_keys=True,
            )
            header.append(f"{index}. {action['tool']} {args_text}")

        self.ai_plan_view.setPlainText("\n".join(header))
        unit = plan.unit_id or "—"
        if plan.block_id:
            unit = f"{plan.block_id} / {unit}"
        self.ai_unit.setText(f"Unit V42: {unit}")
        self.ai_apply_plan.setEnabled(not stale)
        self.ai_cancel_plan.setEnabled(True)
        self.ai_status.setText(
            "AI plan stale · Cancel dan buat ulang"
            if stale
            else "AI plan menunggu review · belum mengubah timeline"
        )

    def _apply_ai_plan(self):
        plan = self.plan_manager.pending
        if plan is None:
            self._refresh_ai_plan()
            return

        result = self.plan_manager.apply()
        if not result.get("ok"):
            message = str(
                result.get("error", {}).get("message", "AI plan gagal diterapkan.")
            )
            self.statusBar().showMessage(message)
            self._refresh_ai_plan()
            return

        applied = result["plan"]
        unit_id = applied.get("unit_id")
        block_id = applied.get("block_id")
        if unit_id:
            self.workflow_state.active_unit = str(unit_id)
            if block_id:
                self.workflow_state.active_block = str(block_id)
            self.workflow_state.set_unit_status(
                str(unit_id),
                "working",
                block_id=(None if not block_id else str(block_id)),
                timeline_revision=self.tools.revision,
                note=f"AI plan diterapkan: {applied.get('title', '')}",
            )
            self.record_v42_checkpoint(
                f"plan-{applied['id']}",
                block_id=(None if not block_id else str(block_id)),
                unit_id=str(unit_id),
                payload={
                    "title": applied.get("title", ""),
                    "action_count": len(applied.get("actions", [])),
                },
            )

        self.timeline.clear_selection()
        self._clear_inspector()
        self._timeline_changed(
            f"AI plan diterapkan · rev {self.tools.revision}"
        )
        self._refresh_ai_plan()

    def _cancel_ai_plan(self):
        result = self.plan_manager.cancel()
        if result.get("ok"):
            self.statusBar().showMessage("AI plan dibatalkan. Timeline tidak berubah.")
        else:
            self.statusBar().showMessage(
                str(result.get("error", {}).get("message", "Tidak ada plan."))
            )
        self._refresh_ai_plan()

    def _allowed_bridge_sources(self) -> set[str]:
        sources = {clip.source for clip in self.document.clips}
        for index in range(self.media_list.count()):
            path = self.media_list.item(index).data(Qt.ItemDataRole.UserRole)
            if path:
                sources.add(str(path))
        return sources

    def _bridge_state(self) -> dict:
        return {
            "playhead_ms": self.timeline.playhead_ms,
            "preview_mode": self.preview_mode,
            "project_path": str(self.project_path) if self.project_path else None,
            "workflow": self.workflow_state.to_dict(),
            "one_b2": (
                None
                if self.v42_1b2_plan is None
                else {
                    "summary": self.v42_1b2_plan.summary(),
                    "work_queue": list(self.v42_1b2_plan.work_queue),
                    "source_sha256": self.v42_1b2_plan.source_sha256,
                    "active_unit": self._shot_unit_id(),
                    "shot_summary": (
                        None
                        if self._shot_checkpoint_analysis(self._shot_unit_id()) is None
                        else self._shot_checkpoint_analysis(
                            self._shot_unit_id()
                        ).summary()
                    ),
                }
            ),
            "imported_sources": sorted(self._allowed_bridge_sources()),
        }

    def _bridge_seek(self, milliseconds: int) -> dict:
        target = max(0, min(int(milliseconds), self.document.duration_ms))
        self.timeline.set_playhead(target)
        self._timeline_seek(target)
        return {"playhead_ms": target}

    def _bridge_mutation(self):
        selected = self.timeline.selected_clip_id
        if selected:
            try:
                self.document.clip(selected)
            except KeyError:
                self.timeline.clear_selection()
                self._clear_inspector()
        self._timeline_changed("Timeline diperbarui lewat AI/MCP lokal.")

    def shutdown(self):
        bridge = getattr(self, "local_bridge", None)
        if bridge is not None:
            bridge.stop()
            self.local_bridge = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _connect_player(self):
        self.player.positionChanged.connect(self._player_position)
        self.player.durationChanged.connect(self._player_duration)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)

    def _project_media_entries(self) -> list[dict]:
        entries: list[dict] = []
        seen: set[str] = set()
        for index in range(self.media_list.count()):
            source = self.media_list.item(index).data(Qt.ItemDataRole.UserRole)
            if not source:
                continue
            source = str(source)
            if source in seen:
                continue
            seen.add(source)
            entries.append(
                {
                    "source": source,
                    "duration_ms": int(self.media_durations.get(source, 0)),
                }
            )
        for clip in self.document.clips:
            if clip.source and clip.source not in seen:
                seen.add(clip.source)
                entries.append(
                    {
                        "source": clip.source,
                        "duration_ms": int(self.media_durations.get(clip.source, 0)),
                    }
                )
        return entries

    def save_project(self):
        if self.project_path is None:
            return self.save_project_as()
        return self._save_project_to(self.project_path)

    def save_project_as(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save MiniCut Project",
            str(self.project_path or Path.home() / "project.mcutv42.json"),
            "MiniCut V42 Project (*.mcutv42.json);;JSON (*.json)",
        )
        if not filename:
            return False
        path = Path(filename)
        if not path.name.lower().endswith(".json"):
            path = path.with_name(path.name + ".mcutv42.json")
        self.project_path = path
        return self._save_project_to(path)

    def _save_project_to(self, path: Path, *, silent: bool = False) -> bool:
        try:
            saved = save_project_file(
                path,
                self.document,
                revision=self.tools.revision,
                playhead_ms=self.timeline.playhead_ms,
                media=self._project_media_entries(),
                workflow=self.workflow_state.to_dict(),
            )
            self.project_path = saved
            if not silent:
                self.statusBar().showMessage(f"Project disimpan: {saved.name}")
            return True
        except (OSError, ValueError, TypeError) as exc:
            if not silent:
                self.statusBar().showMessage(f"Gagal menyimpan project: {exc}")
            return False

    def _autosave_project(self):
        if self._loading_project or self.project_path is None:
            return
        self._save_project_to(self.project_path, silent=True)

    def open_project(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open MiniCut Project",
            "",
            "MiniCut V42 Project (*.mcutv42.json *.json);;All Files (*)",
        )
        if not filename:
            return

        self._stop_timeline_playback()
        try:
            snapshot = load_project(filename)
            workflow = V42WorkflowState.from_dict(snapshot.workflow)
        except (OSError, ValueError, TypeError) as exc:
            self.statusBar().showMessage(f"Gagal membuka project: {exc}")
            return

        self._loading_project = True
        try:
            if self.plan_manager.pending is not None:
                self.plan_manager.cancel()
            apply_project(
                snapshot,
                document=self.document,
                history=self.history,
                registry=self.tools,
            )
            self.workflow_state = workflow
            self._restore_1b2_plan_from_workflow()
            self.project_path = Path(filename)

            self.media_list.clear()
            self.media_durations.clear()
            for entry in snapshot.media:
                source = str(entry["source"])
                item = QListWidgetItem(Path(source).name)
                item.setToolTip(source)
                item.setData(Qt.ItemDataRole.UserRole, source)
                self.media_list.addItem(item)
                self.media_durations[source] = int(entry.get("duration_ms", 0))

            # Ensure timeline-only sources also remain discoverable in the media bin.
            known = {
                str(self.media_list.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(self.media_list.count())
            }
            for clip in self.document.clips:
                if not clip.source or clip.source in known:
                    continue
                known.add(clip.source)
                item = QListWidgetItem(Path(clip.source).name)
                item.setToolTip(clip.source)
                item.setData(Qt.ItemDataRole.UserRole, clip.source)
                self.media_list.addItem(item)

            self.current_media = None
            self.preview_mode = "timeline"
            self.preview_clip_id = None
            self.timeline.set_document(self.document)
            target = min(snapshot.playhead_ms, self.document.duration_ms)
            self.timeline.set_playhead(target)
            self.timeline.clear_selection()
            self._clear_inspector()
            self._timeline_changed()
            self._sync_timeline_preview(target, autoplay=False, force_seek=True)
            self._refresh_ai_plan()

            if snapshot.missing_sources:
                self.statusBar().showMessage(
                    f"Project dibuka · {len(snapshot.missing_sources)} media belum ditemukan."
                )
            else:
                self.statusBar().showMessage(f"Project dibuka: {self.project_path.name}")
        finally:
            self._loading_project = False

    def record_v42_checkpoint(
        self,
        checkpoint_id: str,
        *,
        block_id: str | None = None,
        unit_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.workflow_state.record_checkpoint(
            checkpoint_id,
            timeline_revision=self.tools.revision,
            block_id=block_id,
            unit_id=unit_id,
            payload=payload,
        )
        self._autosave_project()

    def import_media(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Media",
            "",
            "Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All Files (*)",
        )
        for filename in files:
            if any(
                self.media_list.item(i).data(Qt.ItemDataRole.UserRole) == filename
                for i in range(self.media_list.count())
            ):
                continue
            item = QListWidgetItem(Path(filename).name)
            item.setToolTip(filename)
            item.setData(Qt.ItemDataRole.UserRole, filename)
            self.media_list.addItem(item)
        if files and not self.current_media:
            self.media_list.setCurrentRow(self.media_list.count() - len(files))

    def _media_selection_changed(self):
        items = self.media_list.selectedItems()
        enabled = bool(items)
        self.action_add_timeline.setEnabled(enabled)
        if not items:
            return
        path = str(items[0].data(Qt.ItemDataRole.UserRole))
        self._stop_timeline_playback()
        self.preview_mode = "source"
        self.preview_clip_id = None
        self.current_media = path
        self.player.setPlaybackRate(1.0)
        self.audio_output.setMuted(False)
        self.player.setSource(QUrl.fromLocalFile(path))
        self._update_play_button()
        self.statusBar().showMessage(f"Source preview: {Path(path).name}")

    def add_selected_to_timeline(self):
        items = self.media_list.selectedItems()
        if not items:
            return
        path = str(items[0].data(Qt.ItemDataRole.UserRole))
        duration = int(self.media_durations.get(path, 0))
        if duration <= 0:
            self.statusBar().showMessage(
                "Durasi media belum siap. Tunggu preview selesai membaca file."
            )
            return

        group_id = "media-" + uuid4().hex[:10]
        start = self.document.next_free_time("V1")
        result = self.tools.execute_batch(
            [
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": path,
                        "track_id": "V1",
                        "source_in_ms": 0,
                        "source_out_ms": duration,
                        "timeline_start_ms": start,
                        "group_id": group_id,
                        "label": Path(path).name,
                    },
                },
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": path,
                        "track_id": "A1",
                        "source_in_ms": 0,
                        "source_out_ms": duration,
                        "timeline_start_ms": start,
                        "group_id": group_id,
                        "label": Path(path).name + " · audio",
                    },
                },
            ],
            expected_revision=self.tools.revision,
        )
        if not result["ok"]:
            self.statusBar().showMessage(self._tool_error_message(result))
            return
        self._timeline_changed(f"Ditambahkan ke timeline: {Path(path).name}")

    def split_selected_clip(self):
        clip_id = self.timeline.selected_clip_id
        if not clip_id:
            return
        result = self.tools.execute(
            "split_clip",
            {
                "clip_id": clip_id,
                "timeline_ms": self.timeline.playhead_ms,
                "expected_revision": self.tools.revision,
            },
        )
        if not result["ok"]:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()
            return
        self.timeline.clear_selection()
        self._clear_inspector()
        self._timeline_changed("Split berhasil pada playhead.")

    def delete_selected_clip(self):
        clip_id = self.timeline.selected_clip_id
        if not clip_id:
            return
        result = self.tools.execute(
            "delete_clip",
            {
                "clip_id": clip_id,
                "expected_revision": self.tools.revision,
            },
        )
        if not result["ok"]:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()
            return
        removed = result["result"]
        self.timeline.clear_selection()
        self._clear_inspector()
        self._timeline_changed(f"{len(removed)} linked clip dihapus.")

    def _move_clip_requested(self, clip_id: str, track_id: str, timeline_start_ms: int):
        result = self.tools.execute(
            "move_clip",
            {
                "clip_id": clip_id,
                "track_id": track_id,
                "timeline_start_ms": timeline_start_ms,
                "expected_revision": self.tools.revision,
            },
        )
        if not result["ok"]:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()
            return
        self._clip_selected(clip_id)
        self._timeline_changed("Clip digeser.")

    def _trim_clip_requested(self, clip_id: str, edge: str, timeline_ms: int):
        result = self.tools.execute(
            "trim_clip",
            {
                "clip_id": clip_id,
                "edge": edge,
                "timeline_ms": timeline_ms,
                "expected_revision": self.tools.revision,
            },
        )
        if not result["ok"]:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()
            return

        self._clip_selected(clip_id)
        side = "kiri" if edge == "left" else "kanan"
        self._timeline_changed(f"Trim {side} berhasil.")

    def _track_control_requested(self, track_id: str, control: str):
        track = self.document.track(track_id)
        if control == "lock":
            state = not track.locked
            tool = "set_track_lock"
            args = {"track_id": track_id, "locked": state}
            message = f"{track_id} {'dikunci' if state else 'dibuka'}."
        elif control == "visibility":
            state = not track.visible
            tool = "set_track_visibility"
            args = {"track_id": track_id, "visible": state}
            message = f"{track_id} {'ditampilkan' if state else 'disembunyikan'}."
        elif control == "mute":
            state = not track.muted
            tool = "set_track_mute"
            args = {"track_id": track_id, "muted": state}
            message = f"{track_id} {'mute' if state else 'audio aktif'}."
        else:
            self.statusBar().showMessage(f"Kontrol track tidak dikenal: {control}")
            return

        args["expected_revision"] = self.tools.revision
        result = self.tools.execute(tool, args)
        if not result["ok"]:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()
            return
        self._timeline_changed(message)

    def undo_timeline(self):
        result = self.tools.execute(
            "undo",
            {"expected_revision": self.tools.revision},
        )
        if result["ok"]:
            self.timeline.clear_selection()
            self._clear_inspector()
            self._timeline_changed("Undo.")
        else:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()

    def redo_timeline(self):
        result = self.tools.execute(
            "redo",
            {"expected_revision": self.tools.revision},
        )
        if result["ok"]:
            self.timeline.clear_selection()
            self._clear_inspector()
            self._timeline_changed("Redo.")
        else:
            self.statusBar().showMessage(self._tool_error_message(result))
            self._refresh_edit_actions()

    def _timeline_changed(self, message: str = ""):
        self.timeline.update()
        self.timeline_status.setText(f"{len(self.document.clips)} clip")
        self.action_export.setEnabled(bool(self.document.clips))
        self._refresh_edit_actions()
        if self.preview_mode == "timeline":
            self._sync_timeline_preview(
                self.timeline.playhead_ms,
                autoplay=self._timeline_playing,
                force_seek=True,
            )
        self._autosave_project()
        if message:
            self.statusBar().showMessage(message)

    def _refresh_edit_actions(self):
        selected = bool(getattr(self, "timeline", None) and self.timeline.selected_clip_id)
        self.action_split.setEnabled(selected)
        self.action_delete.setEnabled(selected)
        self.action_undo.setEnabled(self.history.can_undo)
        self.action_redo.setEnabled(self.history.can_redo)
        if hasattr(self, "ai_status"):
            self._refresh_ai_plan()

    @staticmethod
    def _tool_error_message(result: dict) -> str:
        return str(result.get("error", {}).get("message", "Timeline tool gagal."))

    def toggle_play(self):
        if self.preview_mode == "timeline":
            if self._timeline_playing:
                self._stop_timeline_playback()
            else:
                self._start_timeline_playback()
            return

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _start_timeline_playback(self):
        if self.document.duration_ms <= 0:
            self.statusBar().showMessage("Timeline masih kosong.")
            return

        self.preview_mode = "timeline"
        if self.timeline.playhead_ms >= self.document.duration_ms:
            self.timeline.set_playhead(0)

        self._timeline_playing = True
        self._timeline_clock.restart()
        self._timeline_timer.start()
        self._sync_timeline_preview(
            self.timeline.playhead_ms,
            autoplay=True,
            force_seek=True,
        )
        self._update_play_button()

    def _stop_timeline_playback(self):
        self._timeline_timer.stop()
        self._timeline_playing = False
        self.player.pause()
        self._update_play_button()

    def _timeline_tick(self):
        if not self._timeline_playing:
            return

        elapsed_ms = max(1, self._timeline_clock.restart())
        next_ms = self.timeline.playhead_ms + elapsed_ms
        if next_ms >= self.document.duration_ms:
            self.timeline.set_playhead(self.document.duration_ms)
            self._update_timeline_time_label()
            self._sync_timeline_preview(
                self.document.duration_ms,
                autoplay=False,
                force_seek=False,
            )
            self._stop_timeline_playback()
            return

        self.timeline.set_playhead(next_ms)
        self._update_timeline_time_label()
        self._sync_timeline_preview(
            next_ms,
            autoplay=True,
            force_seek=False,
        )

    def _sync_timeline_preview(
        self,
        timeline_ms: int,
        *,
        autoplay: bool,
        force_seek: bool,
    ):
        clip = self.document.video_clip_at(timeline_ms)
        if clip is None:
            if self.preview_clip_id is not None or not self.player.source().isEmpty():
                self.player.pause()
                self.player.setSource(QUrl())
            self.preview_clip_id = None
            self.audio_output.setMuted(False)
            self._update_timeline_time_label()
            return

        expected_source_ms = clip.source_position_at(timeline_ms)
        current_source = self.player.source().toLocalFile()
        source_changed = current_source != clip.source or self.preview_clip_id != clip.id

        self.preview_clip_id = clip.id
        self.player.setPlaybackRate(clip.speed)
        self.audio_output.setMuted(
            self.document.audio_muted_for_video_clip(clip.id, timeline_ms)
        )

        if source_changed:
            self.player.setSource(QUrl.fromLocalFile(clip.source))
            self.player.setPosition(expected_source_ms)
        elif force_seek or abs(self.player.position() - expected_source_ms) > 250:
            self.player.setPosition(expected_source_ms)

        if autoplay:
            self.player.play()
        else:
            self.player.pause()

        self._update_timeline_time_label()

    def _player_duration(self, duration: int):
        source_path = self.player.source().toLocalFile()
        if source_path:
            self.media_durations[source_path] = int(duration)

        if self.preview_mode == "timeline":
            self._update_timeline_time_label()
        else:
            self._update_time_label(self.player.position(), duration)

    def _player_position(self, position: int):
        if self.preview_mode == "timeline":
            # The timeline clock owns the playhead; QMediaPlayer only renders
            # the resolved source segment.
            return
        self._update_time_label(position, self.player.duration())

    def _media_status_changed(self, status):
        if self.preview_mode != "timeline" or self.preview_clip_id is None:
            return
        if status not in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            return

        try:
            clip = self.document.clip(self.preview_clip_id)
            if not clip.covers_timeline_time(self.timeline.playhead_ms):
                return
            self.player.setPlaybackRate(clip.speed)
            self.player.setPosition(
                clip.source_position_at(self.timeline.playhead_ms)
            )
            if self._timeline_playing:
                self.player.play()
        except (KeyError, ValueError):
            return

    def _playback_state_changed(self, state):
        self._update_play_button()

    def _update_play_button(self):
        if self.preview_mode == "timeline":
            playing = self._timeline_playing
        else:
            playing = (
                self.player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState
            )
        self.play_button.setText("⏸ Pause" if playing else "▶ Play")

    def _timeline_seek(self, milliseconds: int):
        self.preview_mode = "timeline"
        if self._timeline_playing:
            self._timeline_clock.restart()
        self._sync_timeline_preview(
            milliseconds,
            autoplay=self._timeline_playing,
            force_seek=True,
        )
        self._update_play_button()

    def _update_timeline_time_label(self):
        self.time_label.setText(
            f"{self._clock(self.timeline.playhead_ms)} / "
            f"{self._clock(self.document.duration_ms)}"
        )

    def _clip_selected(self, clip_id: str):
        self.preview_mode = "timeline"
        clip = self.document.clip(clip_id)
        self.inspector_source.setText(Path(clip.source).name)
        self.inspector_track.setText(clip.track_id)
        self.inspector_in.setText(self._clock(clip.source_in_ms))
        self.inspector_out.setText(self._clock(clip.source_out_ms))
        self.inspector_speed.setText(f"{clip.speed:.2f}×")
        self._sync_timeline_preview(
            self.timeline.playhead_ms,
            autoplay=self._timeline_playing,
            force_seek=False,
        )
        self._update_play_button()
        self._refresh_edit_actions()

    def _clear_inspector(self):
        for label in (
            self.inspector_source,
            self.inspector_track,
            self.inspector_in,
            self.inspector_out,
            self.inspector_speed,
        ):
            label.setText("—")

    def _update_time_label(self, position: int, duration: int):
        self.time_label.setText(f"{self._clock(position)} / {self._clock(duration)}")

    @staticmethod
    def _clock(milliseconds: int) -> str:
        total_seconds = max(0, int(milliseconds)) // 1000
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.media_list.addItem(item)

    def run_self_test(self):
        assert self.timeline.document is self.document
        assert len(self.document.tracks) == 5
        assert self.media_list is not None
        assert self.video is not None
        assert self.findChild(QDockWidget, "AIAgentDock") is not None
        assert self.history.document is self.document
        assert self.tools.document is self.document
        assert self.plan_manager.registry is self.tools
        assert "trim_clip" in self.tools.tool_names
        assert self.local_bridge is not None
        assert self.local_bridge.running
        assert self.local_bridge.url.startswith("http://127.0.0.1:")
        assert isinstance(self.workflow_state, V42WorkflowState)
        assert self.v42_1b2_plan is None
        assert self.ai_1b2_status is not None
        assert self.ai_shot_status is not None
        assert self.ai_detect_shots is not None
        assert self._timeline_timer.interval() == 33
        self.statusBar().showMessage("SELF TEST PASS")


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    window = MiniCutMainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    if "--self-test" in argv:
        QTimer.singleShot(80, window.run_self_test)
        QTimer.singleShot(250, app.quit)
    return app.exec()
