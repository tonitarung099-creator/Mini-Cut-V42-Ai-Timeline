from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .shot_detection import ShotSegment, UnitShotAnalysis, find_ffmpeg

SRT_TIME_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)


@dataclass(slots=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str
    index: int | None = None

    def overlaps(self, start_ms: int, end_ms: int) -> bool:
        return self.start_ms < int(end_ms) and self.end_ms > int(start_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubtitleCue":
        return cls(
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            text=str(data.get("text", "")),
            index=(None if data.get("index") is None else int(data["index"])),
        )


@dataclass(slots=True)
class FrameEvidence:
    timestamp_ms: int
    path: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrameEvidence":
        return cls(
            timestamp_ms=int(data["timestamp_ms"]),
            path=str(data["path"]),
            size_bytes=int(data.get("size_bytes", 0)),
        )


@dataclass(slots=True)
class ShotEvidence:
    start_ms: int
    end_ms: int
    candidate_start_ms: int
    candidate_end_ms: int
    location: str | None = None
    label: str = ""
    frames: list[FrameEvidence] = field(default_factory=list)
    subtitles: list[SubtitleCue] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "candidate_start_ms": self.candidate_start_ms,
            "candidate_end_ms": self.candidate_end_ms,
            "location": self.location,
            "label": self.label,
            "frames": [item.to_dict() for item in self.frames],
            "subtitles": [item.to_dict() for item in self.subtitles],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShotEvidence":
        return cls(
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            candidate_start_ms=int(data["candidate_start_ms"]),
            candidate_end_ms=int(data["candidate_end_ms"]),
            location=(
                None if data.get("location") in (None, "") else str(data["location"])
            ),
            label=str(data.get("label", "")),
            frames=[
                FrameEvidence.from_dict(item)
                for item in list(data.get("frames") or [])
            ],
            subtitles=[
                SubtitleCue.from_dict(item)
                for item in list(data.get("subtitles") or [])
            ],
        )


@dataclass
class UnitEvidencePacket:
    unit_id: str
    source: str
    source_fingerprint: str
    one_b2_source_sha256: str = ""
    srt_path: str | None = None
    srt_sha256: str | None = None
    shots: list[ShotEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def frame_count(self) -> int:
        return sum(len(shot.frames) for shot in self.shots)

    @property
    def subtitle_cue_count(self) -> int:
        seen: set[tuple[int, int, str]] = set()
        for shot in self.shots:
            for cue in shot.subtitles:
                seen.add((cue.start_ms, cue.end_ms, cue.text))
        return len(seen)

    @property
    def image_bytes(self) -> int:
        return sum(frame.size_bytes for shot in self.shots for frame in shot.frames)

    @property
    def subtitle_chars(self) -> int:
        seen: set[tuple[int, int, str]] = set()
        total = 0
        for shot in self.shots:
            for cue in shot.subtitles:
                key = (cue.start_ms, cue.end_ms, cue.text)
                if key in seen:
                    continue
                seen.add(key)
                total += len(cue.text)
        return total

    def summary(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "shots": len(self.shots),
            "frames": self.frame_count,
            "subtitle_cues": self.subtitle_cue_count,
            "subtitle_chars": self.subtitle_chars,
            "image_bytes": self.image_bytes,
            "warnings": len(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "unit_id": self.unit_id,
            "source": self.source,
            "source_fingerprint": self.source_fingerprint,
            "one_b2_source_sha256": self.one_b2_source_sha256,
            "srt_path": self.srt_path,
            "srt_sha256": self.srt_sha256,
            "shots": [shot.to_dict() for shot in self.shots],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnitEvidencePacket":
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("Schema evidence packet tidak didukung.")
        return cls(
            unit_id=str(data["unit_id"]),
            source=str(data["source"]),
            source_fingerprint=str(data.get("source_fingerprint", "")),
            one_b2_source_sha256=str(data.get("one_b2_source_sha256", "")),
            srt_path=(
                None if data.get("srt_path") in (None, "") else str(data["srt_path"])
            ),
            srt_sha256=(
                None
                if data.get("srt_sha256") in (None, "")
                else str(data["srt_sha256"])
            ),
            shots=[
                ShotEvidence.from_dict(item)
                for item in list(data.get("shots") or [])
            ],
            warnings=[str(item) for item in list(data.get("warnings") or [])],
        )


RunCallable = Callable[..., subprocess.CompletedProcess[str]]


class SparseFrameExtractor:
    """Extract tiny local visual evidence at selected absolute timestamps."""

    def __init__(
        self,
        *,
        ffmpeg_path: str | None = None,
        max_width: int = 640,
        jpeg_quality: int = 4,
        timeout_seconds: float = 60.0,
        runner: RunCallable = subprocess.run,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.max_width = int(max_width)
        self.jpeg_quality = int(jpeg_quality)
        self.timeout_seconds = float(timeout_seconds)
        self.runner = runner
        if self.max_width < 64:
            raise ValueError("max_width terlalu kecil.")
        if not 2 <= self.jpeg_quality <= 31:
            raise ValueError("jpeg_quality FFmpeg harus 2..31.")

    def extract(
        self,
        source: str | Path,
        timestamp_ms: int,
        target: str | Path,
    ) -> FrameEvidence:
        source_path = str(source)
        output = Path(target)
        output.parent.mkdir(parents=True, exist_ok=True)

        if output.is_file() and output.stat().st_size > 0:
            return FrameEvidence(
                timestamp_ms=int(timestamp_ms),
                path=str(output),
                size_bytes=output.stat().st_size,
            )

        executable = self.ffmpeg_path or find_ffmpeg()
        command = self.build_command(
            executable,
            source_path,
            int(timestamp_ms),
            str(output),
        )
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
                f"Ekstraksi frame melewati {self.timeout_seconds:g} detik."
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"FFmpeg frame extractor gagal dijalankan: {exc}") from exc

        if int(completed.returncode) != 0:
            error = (completed.stderr or completed.stdout or "").strip()
            if len(error) > 700:
                error = error[-700:]
            raise RuntimeError(
                "FFmpeg gagal mengekstrak frame."
                + (f" {error}" if error else "")
            )
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("FFmpeg selesai tetapi file frame tidak terbentuk.")

        return FrameEvidence(
            timestamp_ms=int(timestamp_ms),
            path=str(output),
            size_bytes=output.stat().st_size,
        )

    def build_command(
        self,
        executable: str,
        source: str,
        timestamp_ms: int,
        output: str,
    ) -> list[str]:
        seconds = max(0, int(timestamp_ms)) / 1000.0
        scale = f"scale='min({self.max_width},iw)':-2"
        return [
            executable,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            source,
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-frames:v",
            "1",
            "-vf",
            scale,
            "-q:v",
            str(self.jpeg_quality),
            "-y",
            output,
        ]


def load_srt(path: str | Path) -> tuple[list[SubtitleCue], str]:
    source = Path(path).expanduser()
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text = _decode_subtitle_bytes(raw)
    return parse_srt(text), digest


def parse_srt(text: str) -> list[SubtitleCue]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = re.split(r"\n\s*\n", normalized)
    cues: list[SubtitleCue] = []

    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue

        timing_index = next(
            (index for index, line in enumerate(lines) if SRT_TIME_RE.search(line)),
            None,
        )
        if timing_index is None:
            continue

        match = SRT_TIME_RE.search(lines[timing_index])
        if match is None:
            continue

        start_ms = parse_srt_timestamp(match.group("start"))
        end_ms = parse_srt_timestamp(match.group("end"))
        if end_ms <= start_ms:
            continue

        cue_index: int | None = None
        if timing_index > 0:
            token = lines[0].strip()
            if token.isdigit():
                cue_index = int(token)

        body = "\n".join(
            line.strip() for line in lines[timing_index + 1 :] if line.strip()
        ).strip()
        if not body:
            continue

        cues.append(
            SubtitleCue(
                start_ms=start_ms,
                end_ms=end_ms,
                text=body,
                index=cue_index,
            )
        )

    cues.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.index or 0))
    return cues


def parse_srt_timestamp(value: str) -> int:
    token = str(value).strip().replace(".", ",")
    parts = token.split(":")
    if len(parts) != 3:
        raise ValueError(f"Timestamp SRT tidak valid: {value}")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds_ms = parts[2].split(",", 1)
    seconds = int(seconds_ms[0])
    millis = int((seconds_ms[1] if len(seconds_ms) > 1 else "0").ljust(3, "0")[:3])
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"Timestamp SRT tidak valid: {value}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def overlapping_cues(
    cues: Iterable[SubtitleCue],
    start_ms: int,
    end_ms: int,
) -> list[SubtitleCue]:
    return [
        cue
        for cue in cues
        if cue.overlaps(int(start_ms), int(end_ms))
    ]


def default_evidence_cache_root() -> Path:
    override = os.environ.get("MINICUT_EVIDENCE_CACHE")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return base / "MiniCutV42" / "evidence"
    return Path.home() / ".minicut-v42" / "evidence"


def source_fingerprint(path: str | Path) -> str:
    source = Path(path).expanduser()
    try:
        stat = source.stat()
        material = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        material = str(source.absolute())
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:24]


def suggest_srt_for_video(source: str | Path) -> Path | None:
    video = Path(source).expanduser()
    candidates = [
        video.with_suffix(".srt"),
        video.with_name(video.stem + ".id.srt"),
        video.with_name(video.stem + ".ID.srt"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_unit_evidence(
    analysis: UnitShotAnalysis,
    *,
    one_b2_source_sha256: str = "",
    srt_path: str | Path | None = None,
    extractor: SparseFrameExtractor | None = None,
    cache_root: str | Path | None = None,
) -> UnitEvidencePacket:
    extractor = extractor or SparseFrameExtractor()
    fingerprint = source_fingerprint(analysis.source)
    cache = Path(cache_root) if cache_root is not None else default_evidence_cache_root()
    unit_cache = cache / fingerprint / analysis.unit_id

    cues: list[SubtitleCue] = []
    srt_digest: str | None = None
    actual_srt: str | None = None
    warnings = list(analysis.warnings)

    resolved_srt: Path | None = None
    if srt_path is not None:
        resolved_srt = Path(srt_path).expanduser()
    else:
        resolved_srt = suggest_srt_for_video(analysis.source)

    if resolved_srt is not None and resolved_srt.is_file():
        cues, srt_digest = load_srt(resolved_srt)
        actual_srt = str(resolved_srt)
        if not cues:
            warnings.append("SRT terbaca tetapi tidak menghasilkan cue subtitle.")
    else:
        warnings.append("Film SRT belum tersedia; evidence dibuat tanpa konteks subtitle.")

    packet = UnitEvidencePacket(
        unit_id=analysis.unit_id,
        source=analysis.source,
        source_fingerprint=fingerprint,
        one_b2_source_sha256=one_b2_source_sha256,
        srt_path=actual_srt,
        srt_sha256=srt_digest,
        warnings=warnings,
    )

    shot_index = 0
    for candidate in analysis.candidates:
        for shot in candidate.shots:
            shot_index += 1
            frame_items: list[FrameEvidence] = []
            for sample_index, timestamp_ms in enumerate(
                shot.representative_times_ms(),
                start=1,
            ):
                target = unit_cache / (
                    f"shot-{shot_index:04d}-sample-{sample_index}-"
                    f"{timestamp_ms:012d}.jpg"
                )
                frame_items.append(
                    extractor.extract(analysis.source, timestamp_ms, target)
                )

            packet.shots.append(
                ShotEvidence(
                    start_ms=shot.start_ms,
                    end_ms=shot.end_ms,
                    candidate_start_ms=shot.candidate_start_ms,
                    candidate_end_ms=shot.candidate_end_ms,
                    location=shot.location,
                    label=shot.label,
                    frames=frame_items,
                    subtitles=overlapping_cues(cues, shot.start_ms, shot.end_ms),
                )
            )

    if not packet.shots:
        warnings.append("Shot analysis tidak berisi shot untuk dibuat evidence.")
    return packet


def compact_packet_for_model(
    packet: UnitEvidencePacket,
    *,
    include_frame_paths: bool = True,
) -> dict[str, Any]:
    """JSON-safe compact metadata; image bytes are attached separately by the provider."""
    shots: list[dict[str, Any]] = []
    for index, shot in enumerate(packet.shots, start=1):
        frame_data = []
        for frame in shot.frames:
            item: dict[str, Any] = {"timestamp_ms": frame.timestamp_ms}
            if include_frame_paths:
                item["path"] = frame.path
            frame_data.append(item)

        shots.append(
            {
                "shot_index": index,
                "start_ms": shot.start_ms,
                "end_ms": shot.end_ms,
                "location": shot.location,
                "label": shot.label,
                "frames": frame_data,
                "subtitles": [
                    {
                        "start_ms": cue.start_ms,
                        "end_ms": cue.end_ms,
                        "text": cue.text,
                    }
                    for cue in shot.subtitles
                ],
            }
        )

    return {
        "unit_id": packet.unit_id,
        "source_fingerprint": packet.source_fingerprint,
        "one_b2_source_sha256": packet.one_b2_source_sha256,
        "srt_sha256": packet.srt_sha256,
        "summary": packet.summary(),
        "shots": shots,
        "warnings": list(packet.warnings),
    }


def _decode_subtitle_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
