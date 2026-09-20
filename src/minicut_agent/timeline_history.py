from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .timeline_model import TimelineClip, TimelineDocument, TimelineTrack


@dataclass
class _Snapshot:
    tracks: list[TimelineTrack]
    clips: list[TimelineClip]


class TimelineHistory:
    """Small deterministic undo/redo history around one TimelineDocument.

    The document object itself is preserved so UI and future AI tools can keep a
    stable reference to the same timeline source of truth.
    """

    def __init__(self, document: TimelineDocument, max_depth: int = 100):
        self.document = document
        self.max_depth = max(1, int(max_depth))
        self._undo: list[_Snapshot] = []
        self._redo: list[_Snapshot] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def checkpoint(self) -> None:
        self._undo.append(self._snapshot())
        if len(self._undo) > self.max_depth:
            del self._undo[0]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    def _snapshot(self) -> _Snapshot:
        return _Snapshot(deepcopy(self.document.tracks), deepcopy(self.document.clips))

    def _restore(self, snapshot: _Snapshot) -> None:
        self.document.tracks[:] = deepcopy(snapshot.tracks)
        self.document.clips[:] = deepcopy(snapshot.clips)
