from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QWidget

from .timeline_model import TimelineDocument


class TimelineView(QWidget):
    seekRequested = Signal(int)
    clipSelected = Signal(str)
    clipMoveRequested = Signal(str, str, int)
    clipTrimRequested = Signal(str, str, int)

    HEADER_WIDTH = 76
    RULER_HEIGHT = 28
    TRACK_HEIGHT = 48
    SNAP_MS = 100
    TRIM_HANDLE_PX = 7

    def __init__(self, document: TimelineDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.playhead_ms = 0
        self.pixels_per_second = 82.0
        self.selected_clip_id: str | None = None
        self._drag_clip_id: str | None = None
        self._drag_offset_x = 0
        self._drag_mode: str | None = None
        self._press_pos: QPoint | None = None
        self.setMinimumHeight(self.RULER_HEIGHT + len(document.tracks) * self.TRACK_HEIGHT + 12)
        self.setMouseTracking(True)

    def set_document(self, document: TimelineDocument) -> None:
        self.document = document
        self.setMinimumHeight(self.RULER_HEIGHT + len(document.tracks) * self.TRACK_HEIGHT + 12)
        self.update()

    def clear_selection(self) -> None:
        self.selected_clip_id = None
        self._drag_clip_id = None
        self._drag_mode = None
        self.update()

    def set_playhead(self, milliseconds: int) -> None:
        self.playhead_ms = max(0, int(milliseconds))
        self.update()

    def set_zoom(self, pixels_per_second: float) -> None:
        self.pixels_per_second = min(320.0, max(24.0, float(pixels_per_second)))
        self.update()

    def _time_to_x(self, milliseconds: int) -> int:
        return self.HEADER_WIDTH + int((milliseconds / 1000.0) * self.pixels_per_second)

    def _x_to_time(self, x: int) -> int:
        return max(0, int(((x - self.HEADER_WIDTH) / self.pixels_per_second) * 1000.0))

    def _track_at_y(self, y: int) -> str | None:
        if y < self.RULER_HEIGHT:
            return None
        row = (y - self.RULER_HEIGHT) // self.TRACK_HEIGHT
        if 0 <= row < len(self.document.tracks):
            return self.document.tracks[row].id
        return None

    def _clip_rect(self, clip) -> QRect:
        row = next((i for i, track in enumerate(self.document.tracks) if track.id == clip.track_id), 0)
        y = self.RULER_HEIGHT + row * self.TRACK_HEIGHT + 5
        x = self._time_to_x(clip.timeline_start_ms)
        width = max(10, self._time_to_x(clip.timeline_end_ms) - x)
        return QRect(x, y, width, self.TRACK_HEIGHT - 10)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#17191f"))

        painter.fillRect(0, 0, self.width(), self.RULER_HEIGHT, QColor("#20232b"))
        painter.fillRect(0, self.RULER_HEIGHT, self.HEADER_WIDTH, self.height(), QColor("#1f2229"))

        track_font = QFont(self.font())
        track_font.setBold(True)
        painter.setFont(track_font)

        for index, track in enumerate(self.document.tracks):
            y = self.RULER_HEIGHT + index * self.TRACK_HEIGHT
            painter.fillRect(
                self.HEADER_WIDTH,
                y,
                self.width() - self.HEADER_WIDTH,
                self.TRACK_HEIGHT,
                QColor("#191c22" if index % 2 == 0 else "#1c1f26"),
            )
            painter.setPen(QColor("#343943"))
            painter.drawLine(0, y + self.TRACK_HEIGHT, self.width(), y + self.TRACK_HEIGHT)
            painter.setPen(QColor("#c8ccd6"))
            painter.drawText(
                QRect(8, y, self.HEADER_WIDTH - 16, self.TRACK_HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                track.name,
            )

        painter.setFont(self.font())
        visible_seconds = max(1, int((self.width() - self.HEADER_WIDTH) / self.pixels_per_second) + 2)
        for second in range(0, visible_seconds + 1):
            x = self.HEADER_WIDTH + int(second * self.pixels_per_second)
            painter.setPen(QColor("#555b66"))
            painter.drawLine(x, self.RULER_HEIGHT - 8, x, self.RULER_HEIGHT)
            painter.setPen(QColor("#a8adb7"))
            painter.drawText(x + 4, 17, f"{second // 60:02d}:{second % 60:02d}")

        for clip in self.document.clips:
            rect = self._clip_rect(clip)
            if clip.track_id.startswith("V"):
                fill = QColor("#3d68b2")
            elif clip.track_id.startswith("A"):
                fill = QColor("#3b8a6b")
            else:
                fill = QColor("#9b6a36")
            if clip.id == self.selected_clip_id:
                fill = fill.lighter(125)
            painter.fillRect(rect, fill)
            painter.setPen(QPen(QColor("#d7dae0"), 1))
            painter.drawRect(rect)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                rect.adjusted(7, 0, -5, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                clip.label,
            )
            if clip.id == self.selected_clip_id:
                painter.fillRect(
                    QRect(rect.left(), rect.top(), self.TRIM_HANDLE_PX, rect.height()),
                    QColor("#f1f3f7"),
                )
                painter.fillRect(
                    QRect(
                        rect.right() - self.TRIM_HANDLE_PX + 1,
                        rect.top(),
                        self.TRIM_HANDLE_PX,
                        rect.height(),
                    ),
                    QColor("#f1f3f7"),
                )

        x = self._time_to_x(self.playhead_ms)
        painter.setPen(QPen(QColor("#f04f5f"), 2))
        painter.drawLine(x, 0, x, self.height())
        painter.setBrush(QColor("#f04f5f"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygon([QPoint(x - 5, 0), QPoint(x + 5, 0), QPoint(x, 8)]))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        pos = event.position().toPoint()
        self._press_pos = pos
        for clip in reversed(self.document.clips):
            rect = self._clip_rect(clip)
            if rect.contains(pos):
                self.selected_clip_id = clip.id
                self._drag_clip_id = clip.id
                self._drag_offset_x = pos.x() - rect.x()
                if pos.x() - rect.left() <= self.TRIM_HANDLE_PX:
                    self._drag_mode = "trim-left"
                elif rect.right() - pos.x() <= self.TRIM_HANDLE_PX:
                    self._drag_mode = "trim-right"
                else:
                    self._drag_mode = "move"
                self.clipSelected.emit(clip.id)
                self.update()
                return

        self._drag_clip_id = None
        self._drag_mode = None
        if pos.x() >= self.HEADER_WIDTH:
            milliseconds = self._x_to_time(pos.x())
            self.set_playhead(milliseconds)
            self.seekRequested.emit(milliseconds)
            self.selected_clip_id = None
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or not self._drag_clip_id:
            self._drag_clip_id = None
            return super().mouseReleaseEvent(event)

        pos = event.position().toPoint()
        if self._press_pos is not None and (pos - self._press_pos).manhattanLength() >= 4:
            clip = self.document.clip(self._drag_clip_id)
            if self._drag_mode in {"trim-left", "trim-right"}:
                raw_time = self._x_to_time(pos.x())
                snapped_time = int(round(raw_time / self.SNAP_MS) * self.SNAP_MS)
                edge = "left" if self._drag_mode == "trim-left" else "right"
                self.clipTrimRequested.emit(clip.id, edge, max(0, snapped_time))
            else:
                target_track = self._track_at_y(pos.y()) or clip.track_id
                raw_start = self._x_to_time(pos.x() - self._drag_offset_x)
                snapped_start = int(round(raw_start / self.SNAP_MS) * self.SNAP_MS)
                self.clipMoveRequested.emit(clip.id, target_track, max(0, snapped_start))

        self._drag_clip_id = None
        self._drag_mode = None
        self._press_pos = None
