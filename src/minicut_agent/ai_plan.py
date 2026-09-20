from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .timeline_tools import TimelineToolRegistry

MAX_PLAN_ACTIONS = 200


@dataclass(slots=True)
class TimelinePlan:
    id: str
    title: str
    expected_revision: int
    actions: list[dict[str, Any]]
    explanation: str = ""
    block_id: str | None = None
    unit_id: str | None = None
    created_by: str = "ai"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "expected_revision": self.expected_revision,
            "actions": deepcopy(self.actions),
            "explanation": self.explanation,
            "block_id": self.block_id,
            "unit_id": self.unit_id,
            "created_by": self.created_by,
        }


class TimelinePlanManager:
    """Holds one reviewable AI edit plan without mutating the timeline."""

    def __init__(self, registry: TimelineToolRegistry):
        self.registry = registry
        self.pending: TimelinePlan | None = None

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.pending is not None:
            return self._error(
                "pending_plan_exists",
                "Masih ada AI plan yang menunggu Apply atau Cancel.",
            )
        try:
            plan = self._parse_plan(payload)
        except (TypeError, ValueError, KeyError) as exc:
            return self._error("invalid_plan", str(exc))

        if plan.expected_revision != self.registry.revision:
            return self._error(
                "stale_revision",
                (
                    "Timeline berubah sebelum plan diajukan: "
                    f"expected {plan.expected_revision}, current {self.registry.revision}."
                ),
            )

        self.pending = plan
        return self._ok("propose_plan", plan.to_dict())

    def get_pending(self) -> dict[str, Any]:
        return self._ok(
            "get_pending_plan",
            None if self.pending is None else self.pending.to_dict(),
        )

    def cancel(self) -> dict[str, Any]:
        if self.pending is None:
            return self._error("no_pending_plan", "Tidak ada AI plan yang menunggu.")
        plan = self.pending
        self.pending = None
        return self._ok("cancel_plan", plan.to_dict())

    def apply(self) -> dict[str, Any]:
        if self.pending is None:
            return self._error("no_pending_plan", "Tidak ada AI plan yang menunggu.")

        plan = self.pending
        result = self.registry.execute_batch(
            deepcopy(plan.actions),
            expected_revision=plan.expected_revision,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "command": "apply_plan",
                "plan": plan.to_dict(),
                "registry_result": result,
                "error": result.get(
                    "error",
                    {"code": "apply_failed", "message": "AI plan gagal diterapkan."},
                ),
            }

        self.pending = None
        return {
            "ok": True,
            "command": "apply_plan",
            "plan": plan.to_dict(),
            "revision": self.registry.revision,
            "registry_result": result,
        }

    def _parse_plan(self, payload: dict[str, Any]) -> TimelinePlan:
        if not isinstance(payload, dict):
            raise ValueError("Plan harus berupa object.")

        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("title tidak boleh kosong.")

        try:
            expected_revision = int(payload["expected_revision"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("expected_revision wajib berupa integer.") from exc
        if expected_revision < 0:
            raise ValueError("expected_revision tidak boleh negatif.")

        actions = payload.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError("actions harus berupa array yang tidak kosong.")
        if len(actions) > MAX_PLAN_ACTIONS:
            raise ValueError(
                f"Satu AI plan maksimal {MAX_PLAN_ACTIONS} action."
            )

        allowed = set(self.registry.mutation_tool_names)
        normalized: list[dict[str, Any]] = []
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                raise ValueError(f"Action #{index} harus berupa object.")
            tool = str(action.get("tool", "")).strip()
            if tool not in allowed:
                raise ValueError(f"Tool action #{index} tidak diizinkan: {tool}")
            args = action.get("args", {})
            if not isinstance(args, dict):
                raise ValueError(f"args action #{index} harus berupa object.")
            if "expected_revision" in args:
                raise ValueError(
                    "expected_revision hanya boleh berada di level plan."
                )
            normalized.append({"tool": tool, "args": deepcopy(args)})

        plan_id = str(payload.get("id", "")).strip() or uuid4().hex
        return TimelinePlan(
            id=plan_id,
            title=title,
            expected_revision=expected_revision,
            actions=normalized,
            explanation=str(payload.get("explanation", "")).strip(),
            block_id=(
                None
                if payload.get("block_id") in (None, "")
                else str(payload.get("block_id"))
            ),
            unit_id=(
                None
                if payload.get("unit_id") in (None, "")
                else str(payload.get("unit_id"))
            ),
            created_by=str(payload.get("created_by", "ai")).strip() or "ai",
        )

    def _ok(self, command: str, result: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "command": command,
            "revision": self.registry.revision,
            "result": result,
        }

    def _error(self, code: str, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "command": "plan",
            "revision": self.registry.revision,
            "error": {"code": code, "message": message},
        }
