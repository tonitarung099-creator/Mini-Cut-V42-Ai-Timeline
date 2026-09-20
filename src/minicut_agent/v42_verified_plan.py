from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ai_plan import MAX_PLAN_ACTIONS
from .evidence_packets import ShotEvidence, UnitEvidencePacket
from .gemini_client import GeminiShotDecision, GeminiUnitVerification
from .timeline_model import TimelineDocument, TimelineClip
from .v42_1b2 import V42OneB2Plan, V42UnitSpec
from .v42_prompt3_fit import (
    Prompt3Candidate,
    Prompt3FitError,
    fit_prompt3_visuals,
)
from .v42_regions import (
    V42RegionError,
    build_reflow_actions,
    compute_region_layout,
)


class V42PlanBuildError(ValueError):
    pass


@dataclass(slots=True)
class SelectedSourceRange:
    shot_index: int
    start_ms: int
    end_ms: int
    confidence: float
    reason: str
    decision: str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


def build_verified_timeline_plan(
    *,
    plan: V42OneB2Plan,
    packet: UnitEvidencePacket,
    verification: GeminiUnitVerification,
    document: TimelineDocument,
    expected_revision: int,
    timeline_start_ms: int | None = None,
    narration_target_duration_ms: int | None = None,
) -> dict[str, Any]:
    unit = _resolve_unit(plan, packet, verification)
    _validate_target_tracks(document, unit)
    _ensure_unit_not_already_placed(document, unit)

    selections = select_verified_ranges(packet, verification)
    if not selections:
        raise V42PlanBuildError(
            f"Gemini tidak memilih visual yang dapat dipakai untuk {unit.id}."
        )

    _reject_conflicts_with_existing_v42(
        document,
        packet.source,
        unit.id,
        selections,
    )

    prompt3_fit = None
    if unit.kind == "narration" and narration_target_duration_ms is not None:
        try:
            prompt3_fit = fit_prompt3_visuals(
                [
                    Prompt3Candidate(
                        shot_index=item.shot_index,
                        start_ms=item.start_ms,
                        end_ms=item.end_ms,
                        confidence=item.confidence,
                        reason=item.reason,
                        decision=item.decision,
                    )
                    for item in selections
                ],
                target_duration_ms=int(narration_target_duration_ms),
            )
        except Prompt3FitError as exc:
            raise V42PlanBuildError(str(exc)) from exc
        total_duration = prompt3_fit.target_duration_ms
    else:
        total_duration = sum(item.duration_ms for item in selections)

    reflow_actions: list[dict[str, Any]] = []
    region_note = ""

    if timeline_start_ms is None:
        layout = compute_region_layout(
            plan,
            document,
            duration_overrides={unit.id: total_duration},
        )
        try:
            region = layout.region(unit.id)
            reflow_actions = build_reflow_actions(
                document,
                layout,
                exclude_unit_ids={unit.id},
            )
        except (KeyError, V42RegionError) as exc:
            raise V42PlanBuildError(str(exc)) from exc
        start = region.start_ms
        region_note = (
            f" Posisi mengikuti Urutan Tayang region #{region.order_index}; "
            f"{len(reflow_actions)} action reflow diperlukan."
        )
    else:
        start = int(timeline_start_ms)
        region_note = " Posisi timeline diberikan eksplisit tanpa reflow region."

    if start < 0:
        raise V42PlanBuildError("timeline_start_ms tidak boleh negatif.")

    actions: list[dict[str, Any]] = list(reflow_actions)
    cursor = start

    if unit.kind == "narration" and prompt3_fit is not None:
        for piece in prompt3_fit.pieces:
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
                        "group_id": f"v42-{unit.id}-{piece.shot_index:04d}",
                        "label": (
                            f"{unit.id} · visual Prompt 3 · "
                            f"shot {piece.shot_index}"
                        ),
                        "unit_id": unit.id,
                        "block_id": unit.block_id,
                        "origin": "prompt3_visual",
                    },
                }
            )
            cursor += piece.timeline_duration_ms
    else:
        for selection in selections:
            if unit.kind == "narration":
                actions.append(
                    {
                        "tool": "insert_clip",
                        "args": {
                            "source": packet.source,
                            "track_id": "V2",
                            "source_in_ms": selection.start_ms,
                            "source_out_ms": selection.end_ms,
                            "timeline_start_ms": cursor,
                            "speed": 1.0,
                            "muted": True,
                            "group_id": f"v42-{unit.id}-{selection.shot_index:04d}",
                            "label": f"{unit.id} · visual · shot {selection.shot_index}",
                            "unit_id": unit.id,
                            "block_id": unit.block_id,
                            "origin": "gemini_verified",
                        },
                    }
                )
            elif unit.kind == "anchor":
                group_id = f"v42-{unit.id}-{selection.shot_index:04d}"
                common = {
                    "source": packet.source,
                    "source_in_ms": selection.start_ms,
                    "source_out_ms": selection.end_ms,
                    "timeline_start_ms": cursor,
                    "speed": 1.0,
                    "group_id": group_id,
                    "unit_id": unit.id,
                    "block_id": unit.block_id,
                    "origin": "gemini_verified",
                }
                actions.extend(
                    [
                        {
                            "tool": "insert_clip",
                            "args": {
                                **common,
                                "track_id": "V1",
                                "muted": False,
                                "label": f"{unit.id} · jangkar · shot {selection.shot_index}",
                            },
                        },
                        {
                            "tool": "insert_clip",
                            "args": {
                                **common,
                                "track_id": "A1",
                                "muted": False,
                                "label": f"{unit.id} · audio jangkar · shot {selection.shot_index}",
                            },
                        },
                    ]
                )
            else:
                raise V42PlanBuildError(
                    f"Unit {unit.id} berjenis {unit.kind!r}; converter saat ini hanya N/J."
                )

            cursor += selection.duration_ms

    if len(actions) > MAX_PLAN_ACTIONS:
        raise V42PlanBuildError(
            f"Plan {unit.id} membutuhkan {len(actions)} action; "
            f"batas satu plan adalah {MAX_PLAN_ACTIONS}."
        )

    kept = sum(1 for item in verification.decisions if item.decision == "keep")
    trimmed = sum(1 for item in verification.decisions if item.decision == "trim")
    rejected = sum(1 for item in verification.decisions if item.decision == "reject")
    return {
        "title": f"Susun visual terverifikasi {unit.id}",
        "expected_revision": int(expected_revision),
        "block_id": unit.block_id,
        "unit_id": unit.id,
        "created_by": (
            "prompt3-visual-fit"
            if unit.kind == "narration" and prompt3_fit is not None
            else "gemini-verification"
        ),
        "explanation": (
            f"Gemini memverifikasi {len(verification.decisions)} shot: "
            f"{kept} keep, {trimmed} trim, {rejected} reject. "
            f"Setelah validasi lokal, {len(selections)} rentang sumber "
            f"({total_duration / 1000:.2f} detik) akan ditempatkan mulai "
            f"{start / 1000:.3f}s."
            f"{region_note} "
            + (
                (
                    "Prompt 3 memakai V2 tanpa audio film; durasi visual tepat "
                    f"{prompt3_fit.timeline_duration_ms / 1000:.3f}s mengikuti A2, "
                    f"speed {prompt3_fit.min_speed:.3f}×–"
                    f"{prompt3_fit.max_speed:.3f}× (maksimum 0,50×), "
                    f"{len(prompt3_fit.pieces)} potongan minimal 2,00s"
                    + (
                        "; peringatan: " + " ".join(prompt3_fit.warnings)
                        if prompt3_fit.warnings
                        else ""
                    )
                    + "."
                )
                if unit.kind == "narration" and prompt3_fit is not None
                else (
                    "Unit narasi memakai V2 tanpa audio film."
                    if unit.kind == "narration"
                    else "Unit jangkar memakai pasangan V1+A1 pada speed 1×."
                )
            )
        ),
        "actions": actions,
    }


def select_verified_ranges(
    packet: UnitEvidencePacket,
    verification: GeminiUnitVerification,
) -> list[SelectedSourceRange]:
    if verification.unit_id != packet.unit_id:
        raise V42PlanBuildError(
            f"Unit Gemini {verification.unit_id} berbeda dari evidence {packet.unit_id}."
        )

    decisions = verification.decisions
    if len(decisions) != len(packet.shots):
        raise V42PlanBuildError(
            "Gemini verification tidak memiliki satu keputusan untuk setiap shot evidence."
        )

    by_index: dict[int, GeminiShotDecision] = {}
    for decision in decisions:
        index = int(decision.shot_index)
        if index < 1 or index > len(packet.shots):
            raise V42PlanBuildError(f"Shot index Gemini di luar evidence: {index}.")
        if index in by_index:
            raise V42PlanBuildError(f"Shot index Gemini duplikat: {index}.")
        by_index[index] = decision

    if set(by_index) != set(range(1, len(packet.shots) + 1)):
        raise V42PlanBuildError(
            "Gemini verification tidak lengkap untuk seluruh shot evidence."
        )

    raw: list[SelectedSourceRange] = []
    for index in range(1, len(packet.shots) + 1):
        shot = packet.shots[index - 1]
        decision = by_index[index]
        if decision.decision == "reject":
            continue

        start, end = _decision_bounds(decision, shot)
        raw.append(
            SelectedSourceRange(
                shot_index=index,
                start_ms=start,
                end_ms=end,
                confidence=float(decision.confidence),
                reason=decision.reason,
                decision=decision.decision,
            )
        )

    return _deduplicate_overlaps(raw)


def _resolve_unit(
    plan: V42OneB2Plan,
    packet: UnitEvidencePacket,
    verification: GeminiUnitVerification,
) -> V42UnitSpec:
    if packet.one_b2_source_sha256 and plan.source_sha256:
        if packet.one_b2_source_sha256 != plan.source_sha256:
            raise V42PlanBuildError(
                "Evidence dibuat dari 1B2 yang berbeda; buat evidence ulang."
            )
    if packet.unit_id != verification.unit_id:
        raise V42PlanBuildError("Unit evidence dan Gemini verification berbeda.")
    unit = plan.units.get(packet.unit_id)
    if unit is None:
        raise V42PlanBuildError(f"Unit tidak ditemukan di 1B2: {packet.unit_id}.")
    if unit.kind not in {"narration", "anchor"}:
        raise V42PlanBuildError(
            f"Unit {unit.id} berjenis {unit.kind!r}; hanya N/J yang didukung."
        )
    return unit


def _validate_target_tracks(document: TimelineDocument, unit: V42UnitSpec) -> None:
    track_ids = ["V2"] if unit.kind == "narration" else ["V1", "A1"]
    for track_id in track_ids:
        try:
            track = document.track(track_id)
        except KeyError as exc:
            raise V42PlanBuildError(f"Track wajib tidak tersedia: {track_id}.") from exc
        if track.locked:
            raise V42PlanBuildError(
                f"Track {track_id} sedang dikunci; AI plan tidak dibuat."
            )


def _ensure_unit_not_already_placed(
    document: TimelineDocument,
    unit: V42UnitSpec,
) -> None:
    owned = [clip for clip in document.clips if clip.unit_id == unit.id]
    if unit.kind == "narration":
        # A2 narration audio belongs to the same N unit and is expected to be
        # installed before Prompt 3 visuals. Only existing N visual clips block
        # a new visual plan.
        owned = [
            clip
            for clip in owned
            if document.track(clip.track_id).kind == "video"
        ]
    if not owned:
        return
    locked = any(clip.locked or document.track(clip.track_id).locked for clip in owned)
    suffix = " dan ada clip yang dikunci" if locked else ""
    raise V42PlanBuildError(
        f"Unit {unit.id} sudah memiliki {len(owned)} clip visual di timeline{suffix}. "
        "Gunakan workflow revisi/replace agar hasil lama tidak terduplikasi."
    )


def _decision_bounds(
    decision: GeminiShotDecision,
    shot: ShotEvidence,
) -> tuple[int, int]:
    if decision.decision == "keep":
        start, end = shot.start_ms, shot.end_ms
    elif decision.decision == "trim":
        if decision.trim_start_ms is None or decision.trim_end_ms is None:
            raise V42PlanBuildError(
                f"Trim shot {decision.shot_index} tidak memiliki batas lengkap."
            )
        start, end = int(decision.trim_start_ms), int(decision.trim_end_ms)
    else:
        raise V42PlanBuildError(
            f"Decision shot {decision.shot_index} tidak valid: {decision.decision!r}."
        )

    if not shot.start_ms <= start < end <= shot.end_ms:
        raise V42PlanBuildError(
            f"Rentang shot {decision.shot_index} keluar dari evidence "
            f"{shot.start_ms}..{shot.end_ms}."
        )
    return start, end


def _deduplicate_overlaps(
    selections: list[SelectedSourceRange],
) -> list[SelectedSourceRange]:
    if not selections:
        return []

    # Prefer the higher-confidence decision when two selected evidence shots
    # describe overlapping source time. A tie keeps the earlier shot index.
    ranked = sorted(
        selections,
        key=lambda item: (-item.confidence, item.shot_index),
    )
    chosen: list[SelectedSourceRange] = []
    for item in ranked:
        if any(_overlaps(item.start_ms, item.end_ms, other.start_ms, other.end_ms) for other in chosen):
            continue
        chosen.append(item)

    return sorted(chosen, key=lambda item: (item.start_ms, item.end_ms, item.shot_index))


def _reject_conflicts_with_existing_v42(
    document: TimelineDocument,
    source: str,
    unit_id: str,
    selections: list[SelectedSourceRange],
) -> None:
    existing = [
        clip
        for clip in document.clips
        if clip.source == source
        and clip.unit_id not in (None, "", unit_id)
        and document.track(clip.track_id).kind == "video"
    ]
    for selected in selections:
        for clip in existing:
            if _overlaps(
                selected.start_ms,
                selected.end_ms,
                clip.source_in_ms,
                clip.source_out_ms,
            ):
                raise V42PlanBuildError(
                    f"Visual {selected.start_ms}..{selected.end_ms} ms untuk {unit_id} "
                    f"bertabrakan dengan sumber milik {clip.unit_id}."
                )


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return int(start_a) < int(end_b) and int(end_a) > int(start_b)
