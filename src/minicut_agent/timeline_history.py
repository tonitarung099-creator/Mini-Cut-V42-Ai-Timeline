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
        self._redo_before_checkpoint: list[_Snapshot] | None = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def checkpoint(self) -> None:
        if self._redo_before_checkpoint is not None:
            raise RuntimeError("Checkpoint sebelumnya belum di-commit atau di-rollback.")
        self._redo_before_checkpoint = deepcopy(self._redo)
        self._undo.append(self._snapshot())
        if len(self._undo) > self.max_depth:
            del self._undo[0]
        self._redo.clear()

    def commit_checkpoint(self) -> None:
        """Finalize a successful mutation and discard the redo backup."""
        if self._redo_before_checkpoint is None:
            raise RuntimeError("Tidak ada checkpoint aktif.")
        self._redo_before_checkpoint = None

    def cancel_checkpoint(self) -> bool:
        """Discard an unused checkpoint and restore the previous redo chain."""
        if not self._undo or self._redo_before_checkpoint is None:
            return False
        self._undo.pop()
        self._redo[:] = deepcopy(self._redo_before_checkpoint)
        self._redo_before_checkpoint = None
        return True

    def rollback_checkpoint(self) -> bool:
        """Restore a failed mutation and the exact redo chain from before it."""
        if not self._undo or self._redo_before_checkpoint is None:
            return False
        snapshot = self._undo.pop()
        redo_backup = self._redo_before_checkpoint
        self._redo_before_checkpoint = None
        self._restore(snapshot)
        self._redo[:] = deepcopy(redo_backup)
        return True

    def undo(self) -> bool:
        if self._redo_before_checkpoint is not None:
            raise RuntimeError("Tidak boleh undo saat checkpoint transaksi masih aktif.")
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if self._redo_before_checkpoint is not None:
            raise RuntimeError("Tidak boleh redo saat checkpoint transaksi masih aktif.")
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
