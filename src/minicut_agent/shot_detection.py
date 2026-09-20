from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from .v42_1b2 import CandidateRange, V42OneB2Plan

PTS_TIME_RE = re.compile(r"\bpts_time:(-?\d+(?:\.\d+)?)")
DEFAULT_SCENE_THRESHOLD = 0.30
DEFAULT_MIN_SHOT_MS = 300


@dataclass(slots=True)
class ShotSegment:
    start_ms: int
    end_ms: int
    candidate_start_ms: int
    candidate_end_ms: int
    location: str | None = None
    label: str = ""

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def representative_times_ms(self) -> list[int]:
        """Sparse local frame times for the next evidence-building stage."""
        if self.end_ms <= self.start_ms:
            return [self.start_ms]

        duration = self.end_ms - self.start_ms
        edge = min(250, max(0, duration // 10))
        points = [
            self.start_ms + edge,
            self.start_ms + duration // 2,
            self.end_ms - edge,
        ]
        result: list[int] = []
        for value in points:
            value = min(max(value, self.start_ms), max(self.start_ms, self.end_ms - 1))
            if value not in result:
                result.append(value)
        return result

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShotSegment":
        return cls(
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            candidate_start_ms=int(data["candidate_start_ms"]),
            candidate_end_ms=int(data["candidate_end_ms"]),
            location=(
                None if data.get("location") in (None, "") else str(data["location"])
            ),
            label=str(data.get("label", "")),
        )


@dataclass
class CandidateShotAnalysis:
    start_ms: int
    end_ms: int
    location: str | None = None
    label: str = ""
    shots: list[ShotSegment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "location": self.location,
            "label": self.label,
            "shots": [shot.to_dict() for shot in self.shots],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateShotAnalysis":
        return cls(
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            location=(
                None if data.get("location") in (None, "") else str(data["location"])
            ),
            label=str(data.get("label", "")),
            shots=[
                ShotSegment.from_dict(item)
                for item in list(data.get("shots") or [])
            ],
        )


@dataclass
class UnitShotAnalysis:
    unit_id: str
    source: str
    scene_threshold: float
    min_shot_ms: int
    candidates: list[CandidateShotAnalysis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def shot_count(self) -> int:
        return sum(len(item.shots) for item in self.candidates)

    def summary(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "candidate_ranges": len(self.candidates),
            "shots": self.shot_count,
            "scene_threshold": self.scene_threshold,
            "min_shot_ms": self.min_shot_ms,
            "warnings": len(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "unit_id": self.unit_id,
            "source": self.source,
            "scene_threshold": self.scene_threshold,
            "min_shot_ms": self.min_shot_ms,
            "candidates": [item.to_dict() for item in self.candidates],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnitShotAnalysis":
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("Schema shot analysis tidak didukung.")
        return cls(
            unit_id=str(data["unit_id"]),
            source=str(data["source"]),
            scene_threshold=float(data.get("scene_threshold", DEFAULT_SCENE_THRESHOLD)),
            min_shot_ms=int(data.get("min_shot_ms", DEFAULT_MIN_SHOT_MS)),
            candidates=[
                CandidateShotAnalysis.from_dict(item)
                for item in list(data.get("candidates") or [])
            ],
            warnings=[str(item) for item in list(data.get("warnings") or [])],
        )


RunCallable = Callable[..., subprocess.CompletedProcess[str]]


class FFmpegShotDetector:
    """Local camera/shot boundary detector restricted to one candidate range."""

    def __init__(
        self,
        *,
        ffmpeg_path: str | None = None,
        scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
        min_shot_ms: int = DEFAULT_MIN_SHOT_MS,
        timeout_seconds: float = 180.0,
        runner: RunCallable = subprocess.run,
    ):
        threshold = float(scene_threshold)
        if not 0.0 < threshold < 1.0:
            raise ValueError("scene_threshold harus di antara 0 dan 1.")
        minimum = int(min_shot_ms)
        if minimum < 0:
            raise ValueError("min_shot_ms tidak boleh negatif.")

        self.ffmpeg_path = ffmpeg_path
        self.scene_threshold = threshold
        self.min_shot_ms = minimum
        self.timeout_seconds = float(timeout_seconds)
        self.runner = runner

    def detect(
        self,
        source: str | Path,
        candidate: CandidateRange,
    ) -> CandidateShotAnalysis:
        source_path = str(source)
        if candidate.end_ms <= candidate.start_ms:
            raise ValueError("Rentang kandidat 1B2 tidak valid.")

        executable = self.ffmpeg_path or find_ffmpeg()
        command = self.build_command(executable, source_path, candidate)

        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Deteksi shot melewati batas waktu {self.timeout_seconds:g} detik."
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"FFmpeg tidak dapat dijalankan: {exc}") from exc

        if int(completed.returncode) != 0:
            error = (completed.stderr or completed.stdout or "").strip()
            if len(error) > 700:
                error = error[-700:]
            raise RuntimeError(
                "FFmpeg gagal menganalisis candidate range."
                + (f" {error}" if error else "")
            )

        offsets_ms = parse_showinfo_offsets_ms(completed.stderr or "")
        shots = build_shots(
            candidate,
            offsets_ms,
            min_shot_ms=self.min_shot_ms,
        )
        return CandidateShotAnalysis(
            start_ms=candidate.start_ms,
            end_ms=candidate.end_ms,
            location=candidate.location,
            label=candidate.label,
            shots=shots,
        )

    def build_command(
        self,
        executable: str,
        source: str,
        candidate: CandidateRange,
    ) -> list[str]:
        start_seconds = candidate.start_ms / 1000.0
        duration_seconds = (candidate.end_ms - candidate.start_ms) / 1000.0
        # setpts before select guarantees showinfo pts_time is relative to the
        # candidate start even when input seeking preserves original PTS.
        filtergraph = (
            "setpts=PTS-STARTPTS,"
            f"select='gt(scene,{self.scene_threshold:.4f})',"
            "showinfo"
        )
        return [
            executable,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "info",
            "-ss",
            f"{start_seconds:.3f}",
            "-i",
            source,
            "-t",
            f"{duration_seconds:.3f}",
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            filtergraph,
            "-fps_mode",
            "vfr",
            "-f",
            "null",
            "-",
        ]


def parse_showinfo_offsets_ms(stderr: str) -> list[int]:
    values: list[int] = []
    for match in PTS_TIME_RE.finditer(stderr):
        seconds = float(match.group(1))
        if seconds < 0:
            continue
        milliseconds = int(round(seconds * 1000))
        if milliseconds not in values:
            values.append(milliseconds)
    values.sort()
    return values


def build_shots(
    candidate: CandidateRange,
    cut_offsets_ms: Sequence[int],
    *,
    min_shot_ms: int = DEFAULT_MIN_SHOT_MS,
) -> list[ShotSegment]:
    start = int(candidate.start_ms)
    end = int(candidate.end_ms)
    if end <= start:
        raise ValueError("Rentang kandidat 1B2 tidak valid.")

    minimum = max(0, int(min_shot_ms))
    duration = end - start
    boundaries = [start]

    for offset in sorted({max(0, int(item)) for item in cut_offsets_ms}):
        if offset <= 0 or offset >= duration:
            continue
        absolute = start + offset
        if absolute - boundaries[-1] < minimum:
            continue
        if end - absolute < minimum:
            continue
        boundaries.append(absolute)

    boundaries.append(end)
    shots: list[ShotSegment] = []
    for left, right in zip(boundaries, boundaries[1:]):
        if right <= left:
            continue
        shots.append(
            ShotSegment(
                start_ms=left,
                end_ms=right,
                candidate_start_ms=start,
                candidate_end_ms=end,
                location=candidate.location,
                label=candidate.label,
            )
        )
    return shots


def candidate_ranges_for_unit(
    plan: V42OneB2Plan,
    unit_id: str,
) -> tuple[list[CandidateRange], list[str]]:
    key = str(unit_id).upper()
    unit = plan.units.get(key)
    if unit is None:
        raise KeyError(f"Unit 1B2 tidak ditemukan: {key}")

    if unit.candidate_ranges:
        return list(unit.candidate_ranges), []

    if unit.block_id and unit.block_id in plan.blocks:
        fallback = list(plan.blocks[unit.block_id].candidate_ranges)
        if fallback:
            return fallback, [
                f"{key} tidak memiliki candidate range khusus; memakai kandidat blok {unit.block_id}."
            ]

    return [], [f"{key} tidak memiliki candidate range yang dapat dianalisis."]


def analyze_unit_candidates(
    plan: V42OneB2Plan,
    unit_id: str,
    source: str | Path,
    *,
    detector: FFmpegShotDetector | None = None,
) -> UnitShotAnalysis:
    detector = detector or FFmpegShotDetector()
    candidates, warnings = candidate_ranges_for_unit(plan, unit_id)
    result = UnitShotAnalysis(
        unit_id=str(unit_id).upper(),
        source=str(source),
        scene_threshold=detector.scene_threshold,
        min_shot_ms=detector.min_shot_ms,
        warnings=list(warnings),
    )

    for candidate in candidates:
        result.candidates.append(detector.detect(source, candidate))
    return result


def find_ffmpeg() -> str:
    override = os.environ.get("MINICUT_FFMPEG")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_dir / "ffmpeg.exe",
            executable_dir / "ffmpeg",
            executable_dir / "bin" / "ffmpeg.exe",
            executable_dir / "bin" / "ffmpeg",
            Path.cwd() / "ffmpeg.exe",
            Path.cwd() / "ffmpeg",
            Path.cwd() / "bin" / "ffmpeg.exe",
            Path.cwd() / "bin" / "ffmpeg",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    raise FileNotFoundError(
        "FFmpeg tidak ditemukan. Pasang FFmpeg di PATH atau set MINICUT_FFMPEG."
    )
