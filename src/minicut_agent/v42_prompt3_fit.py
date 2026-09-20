from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Sequence

PROMPT3_MAX_SPEED = 0.50
PROMPT3_MIN_PIECE_MS = 2000
PROMPT3_VERY_SLOW_WARNING = 0.25


class Prompt3FitError(ValueError):
    pass


@dataclass(slots=True)
class Prompt3Candidate:
    shot_index: int
    start_ms: int
    end_ms: int
    confidence: float
    reason: str = ""
    decision: str = "keep"

    @property
    def source_duration_ms(self) -> int:
        return max(0, int(self.end_ms) - int(self.start_ms))

    @property
    def minimum_timeline_duration_ms(self) -> int:
        # 0.50x is the maximum allowed narration visual speed, so a source
        # range needs at least twice its source duration on the timeline.
        return max(
            PROMPT3_MIN_PIECE_MS,
            int(round(self.source_duration_ms / PROMPT3_MAX_SPEED)),
        )


@dataclass(slots=True)
class Prompt3VisualPiece:
    shot_index: int
    source_in_ms: int
    source_out_ms: int
    timeline_duration_ms: int
    speed: float
    confidence: float
    reason: str
    decision: str

    @property
    def source_duration_ms(self) -> int:
        return max(0, self.source_out_ms - self.source_in_ms)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Prompt3FitResult:
    target_duration_ms: int
    pieces: list[Prompt3VisualPiece] = field(default_factory=list)
    omitted_shot_indexes: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def timeline_duration_ms(self) -> int:
        return sum(piece.timeline_duration_ms for piece in self.pieces)

    @property
    def min_speed(self) -> float:
        return min((piece.speed for piece in self.pieces), default=0.0)

    @property
    def max_speed(self) -> float:
        return max((piece.speed for piece in self.pieces), default=0.0)

    def summary(self) -> dict:
        return {
            "target_duration_ms": self.target_duration_ms,
            "timeline_duration_ms": self.timeline_duration_ms,
            "pieces": len(self.pieces),
            "omitted": len(self.omitted_shot_indexes),
            "min_speed": self.min_speed,
            "max_speed": self.max_speed,
            "warnings": len(self.warnings),
        }


def fit_prompt3_visuals(
    candidates: Sequence[Prompt3Candidate],
    *,
    target_duration_ms: int,
) -> Prompt3FitResult:
    target = int(target_duration_ms)
    if target < PROMPT3_MIN_PIECE_MS:
        raise Prompt3FitError(
            "PERLU REVISI — DURASI N DI BAWAH MINIMUM 2 DETIK"
        )
    if not candidates:
        raise Prompt3FitError(
            "PERLU REVISI — tidak ada visual terverifikasi untuk menutup narasi."
        )

    ordered = sorted(
        (
            Prompt3Candidate(
                shot_index=int(item.shot_index),
                start_ms=int(item.start_ms),
                end_ms=int(item.end_ms),
                confidence=float(item.confidence),
                reason=str(item.reason),
                decision=str(item.decision),
            )
            for item in candidates
        ),
        key=lambda item: (item.start_ms, item.end_ms, item.shot_index),
    )
    _validate_chronology(ordered)

    usable = [item for item in ordered if item.source_duration_ms > 0]
    if not usable:
        raise Prompt3FitError(
            "PERLU REVISI — semua rentang visual terverifikasi berdurasi nol."
        )

    required_all = sum(item.minimum_timeline_duration_ms for item in usable)
    if required_all <= target:
        chosen = usable
    else:
        chosen = _choose_subset(usable, target)

    if not chosen:
        shortest = min(item.minimum_timeline_duration_ms for item in usable)
        raise Prompt3FitError(
            "PERLU REVISI — kandidat visual yang dipilih Gemini tidak dapat "
            f"masuk ke durasi N {target / 1000:.3f}s dengan batas speed "
            f"maksimum 0,50× dan minimum 2,00s per potongan. "
            f"Kebutuhan minimum satu kandidat saat ini {shortest / 1000:.3f}s; "
            "jalankan verifikasi Gemini ulang agar trim/reject mengikuti durasi A2."
        )

    minimums = [item.minimum_timeline_duration_ms for item in chosen]
    minimum_total = sum(minimums)
    if minimum_total > target:
        raise Prompt3FitError(
            "PERLU REVISI — kombinasi visual terpilih masih melebihi durasi N "
            "pada speed maksimum 0,50×."
        )

    allocations = _distribute_duration(
        chosen,
        minimums,
        target - minimum_total,
    )
    pieces: list[Prompt3VisualPiece] = []
    warnings: list[str] = []

    for item, timeline_duration in zip(chosen, allocations):
        speed = item.source_duration_ms / timeline_duration
        if speed <= 0 or speed > PROMPT3_MAX_SPEED + 1e-9:
            raise Prompt3FitError(
                f"PERLU REVISI — speed hasil fit shot {item.shot_index} "
                f"tidak valid: {speed:.6f}×."
            )
        if timeline_duration < PROMPT3_MIN_PIECE_MS:
            raise Prompt3FitError(
                f"PERLU REVISI — shot {item.shot_index} di bawah minimum 2,00 detik."
            )

        pieces.append(
            Prompt3VisualPiece(
                shot_index=item.shot_index,
                source_in_ms=item.start_ms,
                source_out_ms=item.end_ms,
                timeline_duration_ms=int(timeline_duration),
                speed=float(speed),
                confidence=item.confidence,
                reason=item.reason,
                decision=item.decision,
            )
        )
        if speed < PROMPT3_VERY_SLOW_WARNING:
            warnings.append(
                f"Shot {item.shot_index} membutuhkan {speed:.3f}×; "
                "audit naturalness/optical-flow/freeze diperlukan."
            )

    omitted = [
        item.shot_index
        for item in usable
        if item.shot_index not in {piece.shot_index for piece in pieces}
    ]
    if omitted:
        warnings.append(
            "Kandidat yang tidak dipakai karena durasi A2: "
            + ", ".join(str(index) for index in omitted)
            + "."
        )

    result = Prompt3FitResult(
        target_duration_ms=target,
        pieces=pieces,
        omitted_shot_indexes=omitted,
        warnings=warnings,
    )
    if result.timeline_duration_ms != target:
        raise Prompt3FitError(
            "PERLU REVISI — fitter tidak menghasilkan durasi visual yang sama "
            "dengan audio narasi."
        )
    return result


def _choose_subset(
    candidates: Sequence[Prompt3Candidate],
    target_duration_ms: int,
) -> list[Prompt3Candidate]:
    # Gemini has already made the semantic keep/trim/reject decision. If all
    # selected ranges cannot coexist under the V42 duration rules, keep the
    # strongest candidates that individually fit, then restore source order.
    ranked = sorted(
        candidates,
        key=lambda item: (
            -item.confidence,
            0 if item.decision == "trim" else 1,
            item.start_ms,
            item.shot_index,
        ),
    )
    chosen: list[Prompt3Candidate] = []
    used = 0
    for item in ranked:
        required = item.minimum_timeline_duration_ms
        if used + required > target_duration_ms:
            continue
        chosen.append(item)
        used += required

    return sorted(
        chosen,
        key=lambda item: (item.start_ms, item.end_ms, item.shot_index),
    )


def _distribute_duration(
    candidates: Sequence[Prompt3Candidate],
    minimums: Sequence[int],
    extra_ms: int,
) -> list[int]:
    allocations = [int(value) for value in minimums]
    extra = int(extra_ms)
    if extra <= 0:
        return allocations

    weights = [max(1, item.source_duration_ms) for item in candidates]
    weight_total = sum(weights)
    raw_shares = [extra * weight / weight_total for weight in weights]
    whole = [int(value) for value in raw_shares]
    for index, value in enumerate(whole):
        allocations[index] += value

    remainder = extra - sum(whole)
    order = sorted(
        range(len(candidates)),
        key=lambda index: (
            -(raw_shares[index] - whole[index]),
            candidates[index].shot_index,
        ),
    )
    for index in order[:remainder]:
        allocations[index] += 1
    return allocations


def _validate_chronology(candidates: Sequence[Prompt3Candidate]) -> None:
    previous_start = -1
    previous_end = -1
    for item in candidates:
        if item.end_ms <= item.start_ms:
            raise Prompt3FitError(
                f"PERLU REVISI — rentang shot {item.shot_index} tidak valid."
            )
        if item.start_ms < previous_start:
            raise Prompt3FitError(
                "PERLU REVISI — urutan visual kembali ke timestamp sumber lebih awal."
            )
        if previous_end >= 0 and item.start_ms < previous_end:
            raise Prompt3FitError(
                "PERLU REVISI — rentang visual saling overlap setelah verifikasi."
            )
        previous_start = item.start_ms
        previous_end = item.end_ms
