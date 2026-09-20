from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer, QUrl
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

from .timeline_history import TimelineHistory
from .timeline_model import TimelineDocument
from .timeline_view import TimelineView

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


class MiniCutMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 900)
        self.setAcceptDrops(True)

        self.document = TimelineDocument.default()
        self.history = TimelineHistory(self.document)
        self.media_durations: dict[str, int] = {}
        self.current_media: str | None = None

        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        self._build_actions()
        self._build_toolbar()
        self._build_workspace()
        self._build_ai_dock()
        self._connect_player()
        self._refresh_edit_actions()

        self.statusBar().showMessage("Siap · timeline manual aktif")
        self.setStyleSheet(STYLE)

    def _build_actions(self):
        self.action_import = QAction("Import", self)
        self.action_import.setShortcut(QKeySequence.StandardKey.Open)
        self.action_import.triggered.connect(self.import_media)

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

    def _build_toolbar(self):
        bar = QToolBar("Main", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        for action in (
            self.action_import,
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

    def _build_ai_dock(self):
        dock = QDockWidget("AI Agent", self)
        dock.setObjectName("AIAgentDock")
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.ai_status = QLabel("Idle · Agent belum diaktifkan")
        self.ai_status.setObjectName("StatusPill")
        self.ai_unit = QLabel("Unit V42: —")
        self.ai_input = QPlainTextEdit()
        self.ai_input.setPlaceholderText(
            "Nanti kamu bisa menulis: “Kerjakan B-001”, “Cari visual lain untuk N-007”, dll."
        )
        self.ai_input.setMaximumHeight(110)
        self.ai_run = QPushButton("Jalankan AI")
        self.ai_run.setEnabled(False)
        layout.addWidget(self.ai_status)
        layout.addWidget(self.ai_unit)
        layout.addWidget(self.ai_input)
        layout.addWidget(self.ai_run)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _connect_player(self):
        self.player.positionChanged.connect(self._player_position)
        self.player.durationChanged.connect(self._player_duration)
        self.player.playbackStateChanged.connect(self._playback_state_changed)

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
        self.current_media = path
        self.player.setSource(QUrl.fromLocalFile(path))
        self.statusBar().showMessage(f"Preview: {Path(path).name}")

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

        self.history.checkpoint()
        group_id = "media-" + uuid4().hex[:10]
        start = self.document.next_free_time("V1")
        self.document.insert_clip(
            source=path,
            track_id="V1",
            source_in_ms=0,
            source_out_ms=duration,
            timeline_start_ms=start,
            group_id=group_id,
            label=Path(path).name,
        )
        self.document.insert_clip(
            source=path,
            track_id="A1",
            source_in_ms=0,
            source_out_ms=duration,
            timeline_start_ms=start,
            group_id=group_id,
            label=Path(path).name + " · audio",
        )
        self._timeline_changed(f"Ditambahkan ke timeline: {Path(path).name}")

    def split_selected_clip(self):
        clip_id = self.timeline.selected_clip_id
        if not clip_id:
            return
        try:
            self.history.checkpoint()
            self.document.split_linked_at(clip_id, self.timeline.playhead_ms)
        except (ValueError, KeyError) as exc:
            # Discard no-op checkpoint by undoing it without exposing it to the user.
            self.history.undo()
            self.history._redo.clear()
            self.statusBar().showMessage(str(exc))
            self._refresh_edit_actions()
            return
        self.timeline.clear_selection()
        self._clear_inspector()
        self._timeline_changed("Split berhasil pada playhead.")

    def delete_selected_clip(self):
        clip_id = self.timeline.selected_clip_id
        if not clip_id:
            return
        try:
            self.history.checkpoint()
            removed = self.document.remove_linked(clip_id)
        except (ValueError, KeyError) as exc:
            self.history.undo()
            self.history._redo.clear()
            self.statusBar().showMessage(str(exc))
            self._refresh_edit_actions()
            return
        self.timeline.clear_selection()
        self._clear_inspector()
        self._timeline_changed(f"{len(removed)} linked clip dihapus.")

    def _move_clip_requested(self, clip_id: str, track_id: str, timeline_start_ms: int):
        try:
            self.history.checkpoint()
            self.document.move_linked(
                clip_id,
                track_id=track_id,
                timeline_start_ms=timeline_start_ms,
            )
        except (ValueError, KeyError) as exc:
            self.history.undo()
            self.history._redo.clear()
            self.statusBar().showMessage(str(exc))
            self._refresh_edit_actions()
            return
        self._clip_selected(clip_id)
        self._timeline_changed("Clip digeser.")

    def undo_timeline(self):
        if self.history.undo():
            self.timeline.clear_selection()
            self._clear_inspector()
            self._timeline_changed("Undo.")
        else:
            self._refresh_edit_actions()

    def redo_timeline(self):
        if self.history.redo():
            self.timeline.clear_selection()
            self._clear_inspector()
            self._timeline_changed("Redo.")
        else:
            self._refresh_edit_actions()

    def _timeline_changed(self, message: str = ""):
        self.timeline.update()
        self.timeline_status.setText(f"{len(self.document.clips)} clip")
        self.action_export.setEnabled(bool(self.document.clips))
        self._refresh_edit_actions()
        if message:
            self.statusBar().showMessage(message)

    def _refresh_edit_actions(self):
        selected = bool(getattr(self, "timeline", None) and self.timeline.selected_clip_id)
        self.action_split.setEnabled(selected)
        self.action_delete.setEnabled(selected)
        self.action_undo.setEnabled(self.history.can_undo)
        self.action_redo.setEnabled(self.history.can_redo)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _player_duration(self, duration: int):
        if self.current_media:
            self.media_durations[self.current_media] = int(duration)
        self._update_time_label(self.player.position(), duration)

    def _player_position(self, position: int):
        self.timeline.set_playhead(position)
        self._update_time_label(position, self.player.duration())

    def _playback_state_changed(self, state):
        self.play_button.setText(
            "⏸ Pause"
            if state == QMediaPlayer.PlaybackState.PlayingState
            else "▶ Play"
        )

    def _timeline_seek(self, milliseconds: int):
        if self.current_media:
            self.player.setPosition(milliseconds)

    def _clip_selected(self, clip_id: str):
        clip = self.document.clip(clip_id)
        self.inspector_source.setText(Path(clip.source).name)
        self.inspector_track.setText(clip.track_id)
        self.inspector_in.setText(self._clock(clip.source_in_ms))
        self.inspector_out.setText(self._clock(clip.source_out_ms))
        self.inspector_speed.setText(f"{clip.speed:.2f}×")
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
        self.statusBar().showMessage("SELF TEST PASS")


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    window = MiniCutMainWindow()
    window.show()
    if "--self-test" in argv:
        QTimer.singleShot(80, window.run_self_test)
        QTimer.singleShot(250, app.quit)
    return app.exec()
