from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .timeline_model import TimelineClip, TimelineDocument
from .v42_1b2 import V42OneB2Plan, V42UnitSpec, parse_timestamp


class V42RegionError(ValueError):
    pass


@dataclass(slots=True)
class V42TimelineRegion:
    unit_id: str
    block_id: str | None
    order_index: int
    start_ms: int
    duration_ms: int
    duration_source: str
    materialized: bool

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["end_ms"] = self.end_ms
        return data


@dataclass
class V42RegionLayout:
    base_start_ms: int
    regions: list[V42TimelineRegion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def end_ms(self) -> int:
        return max(
            [self.base_start_ms, *(region.end_ms for region in self.regions)]
        )

    def region(self, unit_id: str) -> V42TimelineRegion:
        key = str(unit_id).upper()
        for region in self.regions:
            if region.unit_id == key:
                return region
        raise KeyError(f"Region V42 tidak ditemukan: {key}")

    def summary(self) -> dict[str, Any]:
        return {
            "base_start_ms": self.base_start_ms,
            "end_ms": self.end_ms,
            "regions": len(self.regions),
            "materialized": sum(1 for item in self.regions if item.materialized),
            "provisional": sum(1 for item in self.regions if not item.materialized),
            "warnings": len(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "base_start_ms": self.base_start_ms,
            "regions": [item.to_dict() for item in self.regions],
            "warnings": list(self.warnings),
        }


def display_sequence(plan: V42OneB2Plan) -> list[str]:
    """Return N/J units in final display order, independent from work order."""
    ordered: list[str] = []
    seen: set[str] = set()

    for block_id in sorted(plan.blocks, key=_natural_id_key):
        block = plan.blocks[block_id]
        candidates = list(block.display_order)
        if not candidates:
            explicit = [
                unit
                for unit in plan.units.values()
                if unit.block_id == block.id and unit.display_order is not None
            ]
            explicit.sort(
                key=lambda unit: (
                    unit.display_order if unit.display_order is not None else 10**9,
                    _natural_id_key(unit.id),
                )
            )
            candidates = [unit.id for unit in explicit]
        if not candidates:
            candidates = list(block.unit_ids)

        for unit_id in candidates:
            key = str(unit_id).upper()
            unit = plan.units.get(key)
            if unit is None or unit.kind not in {"narration", "anchor"}:
                continue
            if key not in seen:
                seen.add(key)
                ordered.append(key)

    leftovers = [
        unit
        for unit in plan.units.values()
        if unit.kind in {"narration", "anchor"} and unit.id not in seen
    ]
    leftovers.sort(
        key=lambda unit: (
            _natural_id_key(unit.block_id or "B-999999"),
            unit.display_order if unit.display_order is not None else 10**9,
            _natural_id_key(unit.id),
        )
    )
    ordered.extend(unit.id for unit in leftovers)
    return ordered


def compute_region_layout(
    plan: V42OneB2Plan,
    document: TimelineDocument,
    *,
    duration_overrides: Mapping[str, int] | None = None,
) -> V42RegionLayout:
    overrides = {
        str(key).upper(): max(0, int(value))
        for key, value in dict(duration_overrides or {}).items()
    }
    base = _manual_base_end(document)
    layout = V42RegionLayout(base_start_ms=base)
    cursor = base

    for order_index, unit_id in enumerate(display_sequence(plan), start=1):
        unit = plan.units[unit_id]
        owned = clips_for_unit(document, unit_id)
        materialized = bool(owned)

        if unit_id in overrides:
            duration = overrides[unit_id]
            duration_source = "override"
        elif owned:
            duration = _owned_span_duration(owned)
            duration_source = "timeline"
        else:
            inferred = infer_unit_duration_ms(unit)
            duration = inferred or 0
            duration_source = "1b2-field" if inferred else "unknown"
            if duration <= 0:
                layout.warnings.append(
                    f"{unit_id} belum memiliki durasi; region sementara 0 ms."
                )

        layout.regions.append(
            V42TimelineRegion(
                unit_id=unit_id,
                block_id=unit.block_id,
                order_index=order_index,
                start_ms=cursor,
                duration_ms=duration,
                duration_source=duration_source,
                materialized=materialized,
            )
        )
        cursor += duration

    return layout


def build_reflow_actions(
    document: TimelineDocument,
    layout: V42RegionLayout,
    *,
    exclude_unit_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    excluded = {str(item).upper() for item in exclude_unit_ids}
    actions: list[dict[str, Any]] = []

    for region in layout.regions:
        if region.unit_id in excluded:
            continue
        owned = clips_for_unit(document, region.unit_id)
        if not owned:
            continue

        current_start = min(clip.timeline_start_ms for clip in owned)
        delta = region.start_ms - current_start
        if delta == 0:
            continue

        if any(
            clip.locked or document.track(clip.track_id).locked
            for clip in owned
        ):
            raise V42RegionError(
                f"Unit {region.unit_id} perlu digeser {delta} ms "
                "tetapi memiliki clip/track yang dikunci."
            )

        for representative in _move_representatives(document, owned):
            actions.append(
                {
                    "tool": "move_clip",
                    "args": {
                        "clip_id": representative.id,
                        "timeline_start_ms": representative.timeline_start_ms + delta,
                    },
                }
            )

    return actions


def clips_for_unit(
    document: TimelineDocument,
    unit_id: str,
) -> list[TimelineClip]:
    key = str(unit_id).upper()
    return [
        clip
        for clip in document.clips
        if (clip.unit_id or "").upper() == key
    ]


def infer_unit_duration_ms(unit: V42UnitSpec) -> int | None:
    """Conservatively read explicit duration-like fields from imported 1B2."""
    for raw_key, raw_value in unit.fields.items():
        key = _normalize_key(raw_key)
        if "durasi" not in key and "duration" not in key:
            continue
        parsed = _parse_duration_value(raw_value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _manual_base_end(document: TimelineDocument) -> int:
    unowned = [
        clip.timeline_end_ms
        for clip in document.clips
        if not clip.unit_id
    ]
    return max(unowned, default=0)


def _owned_span_duration(clips: list[TimelineClip]) -> int:
    start = min(clip.timeline_start_ms for clip in clips)
    end = max(clip.timeline_end_ms for clip in clips)
    return max(0, end - start)


def _move_representatives(
    document: TimelineDocument,
    clips: list[TimelineClip],
) -> list[TimelineClip]:
    by_group: dict[str, list[TimelineClip]] = {}
    ungrouped: list[TimelineClip] = []
    for clip in clips:
        if clip.group_id:
            by_group.setdefault(clip.group_id, []).append(clip)
        else:
            ungrouped.append(clip)

    representatives: list[TimelineClip] = list(ungrouped)
    for group in by_group.values():
        group.sort(
            key=lambda clip: (
                0 if document.track(clip.track_id).kind == "video" else 1,
                clip.timeline_start_ms,
                clip.id,
            )
        )
        representatives.append(group[0])

    representatives.sort(key=lambda clip: (clip.timeline_start_ms, clip.id))
    return representatives


def _parse_duration_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        if number <= 0:
            return None
        # Bare numeric duration fields in planning documents are conventionally seconds.
        return int(round(number * 1000))

    text = str(value).strip().lower().replace(",", ".")
    if not text:
        return None

    ms_match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*ms\s*", text)
    if ms_match:
        return int(round(float(ms_match.group(1))))

    sec_match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds|detik)\s*",
        text,
    )
    if sec_match:
        return int(round(float(sec_match.group(1)) * 1000))

    if re.fullmatch(r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,3})?", text):
        try:
            return parse_timestamp(text)
        except ValueError:
            return None

    return None


def _normalize_key(value: Any) -> str:
    text = str(value).lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _natural_id_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", str(value).upper())
    return tuple(int(part) if part.isdigit() else part for part in parts)
