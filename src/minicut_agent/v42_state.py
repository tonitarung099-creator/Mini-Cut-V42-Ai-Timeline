from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

VALID_UNIT_STATUSES = {
    "pending",
    "working",
    "locked",
    "needs_revision",
}


@dataclass
class V42WorkflowState:
    """Durable orchestration state independent from any Gemini session."""

    active_block: str | None = None
    active_unit: str | None = None
    units: dict[str, dict[str, Any]] = field(default_factory=dict)
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)

    def set_unit_status(
        self,
        unit_id: str,
        status: str,
        *,
        block_id: str | None = None,
        timeline_revision: int | None = None,
        note: str = "",
    ) -> None:
        unit_id = str(unit_id).strip()
        if not unit_id:
            raise ValueError("unit_id tidak boleh kosong.")
        if status not in VALID_UNIT_STATUSES:
            raise ValueError(f"Status unit tidak valid: {status}")
        if timeline_revision is not None and int(timeline_revision) < 0:
            raise ValueError("timeline_revision tidak boleh negatif.")

        entry = dict(self.units.get(unit_id, {}))
        entry["status"] = status
        if block_id is not None:
            entry["block_id"] = str(block_id)
        if timeline_revision is not None:
            entry["timeline_revision"] = int(timeline_revision)
        if note:
            entry["note"] = str(note)
        self.units[unit_id] = entry

    def record_checkpoint(
        self,
        checkpoint_id: str,
        *,
        timeline_revision: int,
        block_id: str | None = None,
        unit_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        checkpoint_id = str(checkpoint_id).strip()
        if not checkpoint_id:
            raise ValueError("checkpoint_id tidak boleh kosong.")
        if int(timeline_revision) < 0:
            raise ValueError("timeline_revision tidak boleh negatif.")

        entry: dict[str, Any] = {
            "timeline_revision": int(timeline_revision),
        }
        if block_id is not None:
            entry["block_id"] = str(block_id)
        if unit_id is not None:
            entry["unit_id"] = str(unit_id)
        if payload:
            entry["payload"] = deepcopy(payload)
        self.checkpoints[checkpoint_id] = entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "active_block": self.active_block,
            "active_unit": self.active_unit,
            "units": deepcopy(self.units),
            "checkpoints": deepcopy(self.checkpoints),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "V42WorkflowState":
        if not data:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("Workflow V42 harus berupa object.")
        schema = data.get("schema_version", 1)
        if schema != 1:
            raise ValueError(f"Schema workflow V42 tidak didukung: {schema!r}.")

        units = data.get("units", {})
        checkpoints = data.get("checkpoints", {})
        if not isinstance(units, dict) or not isinstance(checkpoints, dict):
            raise ValueError("units dan checkpoints workflow harus berupa object.")

        state = cls(
            active_block=(
                None if data.get("active_block") in (None, "") else str(data["active_block"])
            ),
            active_unit=(
                None if data.get("active_unit") in (None, "") else str(data["active_unit"])
            ),
            units=deepcopy(units),
            checkpoints=deepcopy(checkpoints),
        )
        for unit_id, entry in state.units.items():
            if not isinstance(entry, dict):
                raise ValueError(f"State unit {unit_id} harus berupa object.")
            status = entry.get("status", "pending")
            if status not in VALID_UNIT_STATUSES:
                raise ValueError(f"Status unit {unit_id} tidak valid: {status}")
        return state
