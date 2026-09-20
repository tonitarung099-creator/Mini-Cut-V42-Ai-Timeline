from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from .timeline_history import TimelineHistory
from .timeline_model import TimelineDocument


class TimelineToolRegistry:
    """Validated command surface shared by the UI and future AI agents.

    The registry owns mutation boundaries and revision numbers. AI callers can
    send expected_revision to reject stale plans instead of silently editing a
    timeline that changed after reasoning.
    """

    def __init__(self, document: TimelineDocument, history: TimelineHistory):
        if history.document is not document:
            raise ValueError("TimelineHistory harus menggunakan document yang sama.")
        self.document = document
        self.history = history
        self.revision = 0
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "insert_clip": self._insert_clip,
            "move_clip": self._move_clip,
            "trim_clip": self._trim_clip,
            "split_clip": self._split_clip,
            "delete_clip": self._delete_clip,
            "set_speed": self._set_speed,
            "set_clip_mute": self._set_clip_mute,
            "set_clip_lock": self._set_clip_lock,
            "set_track_lock": self._set_track_lock,
            "set_track_visibility": self._set_track_visibility,
            "set_track_mute": self._set_track_mute,
        }

    @property
    def tool_names(self) -> tuple[str, ...]:
        return (
            "get_state",
            *self._handlers.keys(),
            "undo",
            "redo",
        )

    def state(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "duration_ms": self.document.duration_ms,
            "tracks": [asdict(track) for track in self.document.tracks],
            "clips": [asdict(clip) for clip in self.document.clips],
            "can_undo": self.history.can_undo,
            "can_redo": self.history.can_redo,
        }

    def execute(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        if tool == "get_state":
            return self._ok(tool, self.state())

        stale = self._check_revision(args.pop("expected_revision", None))
        if stale is not None:
            return stale

        if tool == "undo":
            if not self.history.undo():
                return self._error(tool, "nothing_to_undo", "Tidak ada perubahan untuk di-undo.")
            self.revision += 1
            return self._ok(tool, self.state())

        if tool == "redo":
            if not self.history.redo():
                return self._error(tool, "nothing_to_redo", "Tidak ada perubahan untuk di-redo.")
            self.revision += 1
            return self._ok(tool, self.state())

        handler = self._handlers.get(tool)
        if handler is None:
            return self._error(tool, "unknown_tool", f"Tool tidak dikenal: {tool}")

        self.history.checkpoint()
        try:
            result = handler(args)
        except (KeyError, TypeError, ValueError) as exc:
            self.history.rollback_checkpoint()
            return self._error(tool, "validation_error", str(exc))

        self.history.commit_checkpoint()
        self.revision += 1
        return self._ok(tool, self._serialize_result(result))

    def execute_batch(
        self,
        actions: list[dict[str, Any]],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        stale = self._check_revision(expected_revision)
        if stale is not None:
            stale["tool"] = "batch"
            return stale
        if not actions:
            return self._error("batch", "empty_batch", "Batch tidak boleh kosong.")

        self.history.checkpoint()
        results: list[dict[str, Any]] = []
        try:
            for index, action in enumerate(actions):
                if not isinstance(action, dict):
                    raise ValueError(f"Action #{index} harus berupa object.")
                tool = str(action.get("tool", ""))
                if tool not in self._handlers:
                    raise ValueError(f"Tool batch tidak diizinkan: {tool}")
                args = dict(action.get("args") or {})
                if "expected_revision" in args:
                    raise ValueError("expected_revision hanya boleh diberikan pada level batch.")
                result = self._handlers[tool](args)
                results.append(
                    {
                        "tool": tool,
                        "result": self._serialize_result(result),
                    }
                )
        except (KeyError, TypeError, ValueError) as exc:
            self.history.rollback_checkpoint()
            return self._error("batch", "validation_error", str(exc))

        self.history.commit_checkpoint()
        self.revision += 1
        return self._ok(
            "batch",
            {
                "actions": results,
                "state": self.state(),
            },
        )

    def _check_revision(self, expected_revision: Any) -> dict[str, Any] | None:
        if expected_revision is None:
            return None
        try:
            expected = int(expected_revision)
        except (TypeError, ValueError):
            return self._error(
                "revision",
                "invalid_revision",
                "expected_revision harus berupa integer.",
            )
        if expected != self.revision:
            return self._error(
                "revision",
                "stale_revision",
                f"Timeline berubah: expected {expected}, current {self.revision}.",
            )
        return None

    def _insert_clip(self, args: dict[str, Any]):
        return self.document.insert_clip(
            source=args["source"],
            track_id=str(args["track_id"]),
            source_in_ms=int(args["source_in_ms"]),
            source_out_ms=int(args["source_out_ms"]),
            timeline_start_ms=int(args["timeline_start_ms"]),
            speed=float(args.get("speed", 1.0)),
            muted=bool(args.get("muted", False)),
            group_id=args.get("group_id"),
            label=str(args.get("label", "")),
            clip_id=args.get("clip_id"),
        )

    def _move_clip(self, args: dict[str, Any]):
        return self.document.move_linked(
            str(args["clip_id"]),
            timeline_start_ms=int(args["timeline_start_ms"]),
            track_id=args.get("track_id"),
        )

    def _trim_clip(self, args: dict[str, Any]):
        return self.document.trim_linked(
            str(args["clip_id"]),
            edge=str(args["edge"]),
            timeline_ms=int(args["timeline_ms"]),
        )

    def _split_clip(self, args: dict[str, Any]):
        return self.document.split_linked_at(
            str(args["clip_id"]),
            int(args["timeline_ms"]),
        )

    def _delete_clip(self, args: dict[str, Any]):
        return self.document.remove_linked(str(args["clip_id"]))

    def _set_speed(self, args: dict[str, Any]):
        return self.document.set_linked_speed(
            str(args["clip_id"]),
            float(args["speed"]),
        )

    def _set_clip_mute(self, args: dict[str, Any]):
        return self.document.set_clip_muted(
            str(args["clip_id"]),
            bool(args["muted"]),
        )

    def _set_clip_lock(self, args: dict[str, Any]):
        return self.document.set_clip_locked(
            str(args["clip_id"]),
            bool(args["locked"]),
        )

    def _set_track_lock(self, args: dict[str, Any]):
        return self.document.set_track_locked(
            str(args["track_id"]),
            bool(args["locked"]),
        )

    def _set_track_visibility(self, args: dict[str, Any]):
        return self.document.set_track_visible(
            str(args["track_id"]),
            bool(args["visible"]),
        )

    def _set_track_mute(self, args: dict[str, Any]):
        return self.document.set_track_muted(
            str(args["track_id"]),
            bool(args["muted"]),
        )

    @staticmethod
    def _serialize_result(value: Any) -> Any:
        if isinstance(value, list):
            return [TimelineToolRegistry._serialize_result(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        return value

    def _ok(self, tool: str, result: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "tool": tool,
            "revision": self.revision,
            "result": result,
        }

    def _error(self, tool: str, code: str, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "tool": tool,
            "revision": self.revision,
            "error": {
                "code": code,
                "message": message,
            },
        }
