from __future__ import annotations

from typing import Any

from .evidence_packets import UnitEvidencePacket
from .gemini_client import GeminiUnitVerification
from .timeline_model import TimelineClip, TimelineDocument
from .v42_1b2 import V42OneB2Plan
from .v42_prompt3_fit import Prompt3Candidate, Prompt3FitError, fit_prompt3_visuals
from .v42_verified_plan import V42PlanBuildError, select_verified_ranges


class Prompt3RevisionError(ValueError):
    pass


def build_prompt3_visual_replacement_plan(
    *,
    plan: V42OneB2Plan,
    packet: UnitEvidencePacket,
    verification: GeminiUnitVerification,
    document: TimelineDocument,
    clip_id: str,
    expected_revision: int,
) -> dict[str, Any]:
    try:
        selected = document.clip(str(clip_id))
    except KeyError as exc:
        raise Prompt3RevisionError("Clip visual yang dipilih tidak ditemukan.") from exc

    if selected.track_id != "V2" or selected.origin not in {
        "prompt3_visual",
        "prompt3_visual_revision",
    }:
        raise Prompt3RevisionError(
            "Target revisi harus clip visual Prompt 3 pada track V2."
        )
    if not selected.unit_id:
        raise Prompt3RevisionError("Clip Prompt 3 tidak memiliki unit N.")
    unit_id = selected.unit_id.upper()
    unit = plan.units.get(unit_id)
    if unit is None or unit.kind != "narration":
        raise Prompt3RevisionError(f"Unit clip bukan narasi V42 yang valid: {unit_id}.")
    if selected.locked or document.track(selected.track_id).locked:
        raise Prompt3RevisionError("Clip/track visual yang dipilih sedang dikunci.")
    if packet.unit_id != unit_id or verification.unit_id != unit_id:
        raise Prompt3RevisionError(
            "Evidence/Gemini yang aktif tidak cocok dengan unit clip terpilih."
        )

    siblings = sorted(
        [
            clip
            for clip in document.clips
            if clip.unit_id == unit_id
            and clip.track_id == "V2"
            and clip.origin in {"prompt3_visual", "prompt3_visual_revision"}
        ],
        key=lambda clip: (clip.timeline_start_ms, clip.id),
    )
    try:
        selected_index = next(
            index for index, clip in enumerate(siblings) if clip.id == selected.id
        )
    except StopIteration as exc:
        raise Prompt3RevisionError("Clip terpilih tidak ditemukan di region N.") from exc

    previous = siblings[selected_index - 1] if selected_index > 0 else None
    following = (
        siblings[selected_index + 1]
        if selected_index + 1 < len(siblings)
        else None
    )
    lower_source = previous.source_out_ms if previous is not None else -1
    upper_source = following.source_in_ms if following is not None else 10**18

    if (
        previous is not None
        and previous.source_out_ms > selected.source_in_ms
    ) or (
        following is not None
        and selected.source_out_ms > following.source_in_ms
    ):
        raise Prompt3RevisionError(
            "Urutan sumber clip N saat ini tidak kronologis; revisi otomatis dihentikan."
        )

    try:
        verified = select_verified_ranges(packet, verification)
    except V42PlanBuildError as exc:
        raise Prompt3RevisionError(str(exc)) from exc

    occupied = [
        clip
        for clip in document.clips
        if clip.id != selected.id
        and clip.source == packet.source
        and document.track(clip.track_id).kind == "video"
    ]

    alternatives = []
    for item in verified:
        if _overlaps(
            item.start_ms,
            item.end_ms,
            selected.source_in_ms,
            selected.source_out_ms,
        ):
            continue
        if item.start_ms < lower_source or item.end_ms > upper_source:
            continue
        if any(
            _overlaps(
                item.start_ms,
                item.end_ms,
                clip.source_in_ms,
                clip.source_out_ms,
            )
            for clip in occupied
        ):
            continue
        alternatives.append(
            Prompt3Candidate(
                shot_index=item.shot_index,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                confidence=item.confidence,
                reason=item.reason,
                decision=item.decision,
            )
        )

    if not alternatives:
        raise Prompt3RevisionError(
            "PERLU REVISI — tidak ada kandidat Gemini lain yang aman di antara "
            "visual sebelum dan sesudah clip terpilih."
        )

    target_duration = selected.timeline_duration_ms
    try:
        fitted = fit_prompt3_visuals(
            alternatives,
            target_duration_ms=target_duration,
        )
    except Prompt3FitError as exc:
        raise Prompt3RevisionError(str(exc)) from exc

    actions: list[dict[str, Any]] = [
        {
            "tool": "delete_clip",
            "args": {"clip_id": selected.id},
        }
    ]
    cursor = selected.timeline_start_ms
    for piece in fitted.pieces:
        actions.append(
            {
                "tool": "insert_clip",
                "args": {
                    "source": packet.source,
                    "track_id": "V2",
                    "source_in_ms": piece.source_in_ms,
                    "source_out_ms": piece.source_out_ms,
                    "timeline_start_ms": cursor,
                    "speed": piece.speed,
                    "muted": True,
                    "group_id": (
                        f"v42-{unit_id}-revision-"
                        f"{piece.shot_index:04d}-{selected.id[:8]}"
                    ),
                    "label": (
                        f"{unit_id} · revisi visual · shot {piece.shot_index}"
                    ),
                    "unit_id": unit_id,
                    "block_id": unit.block_id,
                    "origin": "prompt3_visual_revision",
                },
            }
        )
        cursor += piece.timeline_duration_ms

    if cursor != selected.timeline_end_ms:
        raise Prompt3RevisionError(
            "PERLU REVISI — visual pengganti tidak mempertahankan durasi clip lama."
        )

    warning_text = (
        " Peringatan: " + " ".join(fitted.warnings)
        if fitted.warnings
        else ""
    )
    return {
        "title": f"Ganti satu visual {unit_id}",
        "expected_revision": int(expected_revision),
        "block_id": unit.block_id,
        "unit_id": unit_id,
        "created_by": "prompt3-visual-revision",
        "explanation": (
            f"Hanya clip {selected.id[:8]} pada {selected.timeline_start_ms / 1000:.3f}s–"
            f"{selected.timeline_end_ms / 1000:.3f}s yang diganti. "
            f"Durasi region lokal tetap {target_duration / 1000:.3f}s; "
            f"{len(fitted.pieces)} clip pengganti tetap kronologis, muted, "
            "speed <=0,50×, dan tidak mengubah clip N/J lain."
            + warning_text
        ),
        "actions": actions,
    }


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return int(start_a) < int(end_b) and int(end_a) > int(start_b)
