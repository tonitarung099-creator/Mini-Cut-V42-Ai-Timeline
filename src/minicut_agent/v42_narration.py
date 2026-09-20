from __future__ import annotations

import hashlib
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .evidence_packets import SubtitleCue, load_srt
from .shot_detection import find_ffmpeg
from .v42_1b2 import V42OneB2Plan
from .v42_regions import display_sequence

FINAL_SECTION_RE = re.compile(
    r"NASKAH\s+BERSIH\s+FINAL\s*[—–-]?\s*SUMBER\s+AUDIO\s+NARASI",
    re.IGNORECASE,
)
UNIT_LINE_RE = re.compile(
    r"^\s*(?:[#>*_-]+\s*)?(?P<id>[NJD]-\d{3,})\b"
    r"(?:\s*[:—–-]\s*(?P<tail>.*))?$",
    re.IGNORECASE,
)
NARRATION_ID_RE = re.compile(r"\b(N-\d{3,})\b", re.IGNORECASE)
SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


class NarrationMappingError(ValueError):
    pass


@dataclass(slots=True)
class NarrationScriptUnit:
    unit_id: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NarrationScript:
    source_path: str
    source_sha256: str
    units: dict[str, NarrationScriptUnit] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "units": {
                key: value.to_dict() for key, value in sorted(self.units.items())
            },
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NarrationScript":
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("Schema narration script tidak didukung.")
        return cls(
            source_path=str(data.get("source_path", "")),
            source_sha256=str(data.get("source_sha256", "")),
            units={
                str(key): NarrationScriptUnit(
                    unit_id=str(value["unit_id"]),
                    text=str(value["text"]),
                )
                for key, value in dict(data.get("units") or {}).items()
            },
            warnings=[str(item) for item in list(data.get("warnings") or [])],
        )


@dataclass(slots=True)
class NarrationCueMapping:
    unit_id: str
    text: str
    cue_indexes: list[int]
    core_start_ms: int
    core_end_ms: int
    similarity: float
    method: str

    @property
    def core_duration_ms(self) -> int:
        return max(0, self.core_end_ms - self.core_start_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SilenceInterval:
    start_ms: int
    end_ms: int


@dataclass(slots=True)
class NarrationAudioTiming:
    unit_id: str
    source_in_ms: int
    source_out_ms: int
    core_start_ms: int
    core_end_ms: int
    pre_padding_ms: int
    post_padding_ms: int
    mapping_similarity: float
    mapping_method: str
    boundary_method: str
    warning: str = ""

    @property
    def duration_ms(self) -> int:
        return max(0, self.source_out_ms - self.source_in_ms)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration_ms"] = self.duration_ms
        return data


@dataclass
class NarrationTimingSet:
    audio_path: str
    audio_fingerprint: str
    narration_srt_path: str
    narration_srt_sha256: str
    script_sha256: str
    timings: dict[str, NarrationAudioTiming] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def duration_overrides(self) -> dict[str, int]:
        return {
            unit_id: timing.duration_ms
            for unit_id, timing in self.timings.items()
            if timing.duration_ms > 0
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "audio_path": self.audio_path,
            "audio_fingerprint": self.audio_fingerprint,
            "narration_srt_path": self.narration_srt_path,
            "narration_srt_sha256": self.narration_srt_sha256,
            "script_sha256": self.script_sha256,
            "timings": {
                key: value.to_dict() for key, value in sorted(self.timings.items())
            },
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NarrationTimingSet":
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("Schema narration timing tidak didukung.")
        timings: dict[str, NarrationAudioTiming] = {}
        for key, raw in dict(data.get("timings") or {}).items():
            timings[str(key)] = NarrationAudioTiming(
                unit_id=str(raw["unit_id"]),
                source_in_ms=int(raw["source_in_ms"]),
                source_out_ms=int(raw["source_out_ms"]),
                core_start_ms=int(raw["core_start_ms"]),
                core_end_ms=int(raw["core_end_ms"]),
                pre_padding_ms=int(raw.get("pre_padding_ms", 0)),
                post_padding_ms=int(raw.get("post_padding_ms", 0)),
                mapping_similarity=float(raw.get("mapping_similarity", 0.0)),
                mapping_method=str(raw.get("mapping_method", "")),
                boundary_method=str(raw.get("boundary_method", "")),
                warning=str(raw.get("warning", "")),
            )
        return cls(
            audio_path=str(data["audio_path"]),
            audio_fingerprint=str(data.get("audio_fingerprint", "")),
            narration_srt_path=str(data.get("narration_srt_path", "")),
            narration_srt_sha256=str(data.get("narration_srt_sha256", "")),
            script_sha256=str(data.get("script_sha256", "")),
            timings=timings,
            warnings=[str(item) for item in list(data.get("warnings") or [])],
        )


RunCallable = Callable[..., subprocess.CompletedProcess[str]]


class FFmpegSilenceDetector:
    def __init__(
        self,
        *,
        ffmpeg_path: str | None = None,
        noise_db: float = -40.0,
        minimum_silence_seconds: float = 0.08,
        timeout_seconds: float = 60.0,
        runner: RunCallable = subprocess.run,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.noise_db = float(noise_db)
        self.minimum_silence_seconds = float(minimum_silence_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.runner = runner

    def detect(
        self,
        audio_path: str | Path,
        start_ms: int,
        end_ms: int,
    ) -> list[SilenceInterval]:
        start_ms = max(0, int(start_ms))
        end_ms = int(end_ms)
        if end_ms <= start_ms:
            return []

        executable = self.ffmpeg_path or find_ffmpeg()
        command = self.build_command(
            executable,
            str(audio_path),
            start_ms,
            end_ms,
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
            raise RuntimeError("Waveform silence analysis timeout.") from exc
        except OSError as exc:
            raise RuntimeError(f"FFmpeg waveform analysis gagal: {exc}") from exc

        if int(completed.returncode) != 0:
            error = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                "FFmpeg gagal menganalisis waveform."
                + (f" {error[-700:]}" if error else "")
            )
        return parse_silencedetect(
            completed.stderr or "",
            window_start_ms=start_ms,
            window_end_ms=end_ms,
        )

    def build_command(
        self,
        executable: str,
        audio_path: str,
        start_ms: int,
        end_ms: int,
    ) -> list[str]:
        duration_ms = end_ms - start_ms
        return [
            executable,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "info",
            "-ss",
            f"{start_ms / 1000:.3f}",
            "-i",
            audio_path,
            "-t",
            f"{duration_ms / 1000:.3f}",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            (
                f"silencedetect=noise={self.noise_db:g}dB:"
                f"d={self.minimum_silence_seconds:g}"
            ),
            "-f",
            "null",
            "-",
        ]


def load_narration_script(path: str | Path) -> NarrationScript:
    source = Path(path).expanduser()
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if source.suffix.lower() == ".docx":
        text = _docx_text(source)
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    script = parse_narration_script_text(text)
    script.source_path = str(source)
    script.source_sha256 = digest
    return script


def parse_narration_script_text(text: str) -> NarrationScript:
    lines = [
        line.strip()
        for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    section_indexes = [
        index for index, line in enumerate(lines) if FINAL_SECTION_RE.search(line)
    ]
    if not section_indexes:
        raise NarrationMappingError(
            "Bagian 'NASKAH BERSIH FINAL — SUMBER AUDIO NARASI' tidak ditemukan."
        )
    # Prompt 1B1 requires the final section to be at the bottom; take the last
    # occurrence to avoid accidentally parsing earlier technical references.
    body = lines[section_indexes[-1] + 1 :]

    units: dict[str, NarrationScriptUnit] = {}
    warnings: list[str] = []
    active_id: str | None = None
    active_lines: list[str] = []

    def flush() -> None:
        nonlocal active_id, active_lines
        if active_id is None:
            active_lines = []
            return
        text_value = _clean_script_text(active_lines)
        if text_value:
            if active_id in units:
                warnings.append(f"{active_id} muncul lebih dari sekali; teks digabung.")
                merged = (units[active_id].text + " " + text_value).strip()
                units[active_id] = NarrationScriptUnit(active_id, merged)
            else:
                units[active_id] = NarrationScriptUnit(active_id, text_value)
        else:
            warnings.append(f"{active_id} tidak memiliki teks narasi.")
        active_id = None
        active_lines = []

    for line in body:
        match = UNIT_LINE_RE.match(line)
        if match:
            unit_id = match.group("id").upper()
            flush()
            if unit_id.startswith("N-"):
                active_id = unit_id
                tail = (match.group("tail") or "").strip()
                if tail:
                    active_lines.append(tail)
            # D/J markers terminate an N block but are not narration text.
            continue

        if active_id is None:
            continue
        if not line:
            continue
        if _looks_like_heading(line):
            flush()
            continue
        active_lines.append(line)
    flush()

    if not units:
        raise NarrationMappingError(
            "Bagian final ditemukan tetapi tidak ada unit N-xxx yang dapat dibaca."
        )

    return NarrationScript(
        source_path="",
        source_sha256="",
        units=units,
        warnings=warnings,
    )


def map_narration_cues(
    script: NarrationScript,
    cues: Sequence[SubtitleCue],
    plan: V42OneB2Plan,
    *,
    minimum_similarity: float = 0.46,
) -> list[NarrationCueMapping]:
    ordered_ids = [
        unit_id
        for unit_id in display_sequence(plan)
        if unit_id.startswith("N-") and unit_id in script.units
    ]
    missing = [
        unit_id
        for unit_id in display_sequence(plan)
        if unit_id.startswith("N-") and unit_id not in script.units
    ]
    if missing:
        raise NarrationMappingError(
            "Teks final Prompt 1B1 tidak memiliki unit: " + ", ".join(missing)
        )
    if not ordered_ids:
        raise NarrationMappingError("Tidak ada unit N yang dapat dipetakan.")
    if not cues:
        raise NarrationMappingError("SRT narasi tidak memiliki cue.")

    explicit = _map_explicit_ids(ordered_ids, script, cues)
    if explicit is not None:
        return explicit

    mapped = _map_monotonic_text(ordered_ids, script, cues)
    weak = [item for item in mapped if item.similarity < minimum_similarity]
    if weak:
        details = ", ".join(
            f"{item.unit_id}={item.similarity:.2f}" for item in weak
        )
        raise NarrationMappingError(
            "Pencocokan teks SRT narasi terlalu lemah untuk dikunci: "
            + details
            + ". Gunakan SRT yang benar atau tambahkan label N-xxx."
        )
    return mapped


def build_narration_timings(
    *,
    script: NarrationScript,
    plan: V42OneB2Plan,
    narration_srt_path: str | Path,
    audio_path: str | Path,
    detector: FFmpegSilenceDetector | None = None,
    before_padding_ms: int = 250,
    after_padding_ms: int = 350,
    search_margin_ms: int = 1200,
) -> NarrationTimingSet:
    cues, srt_sha = load_srt(narration_srt_path)
    mappings = map_narration_cues(script, cues, plan)
    detector = detector or FFmpegSilenceDetector()

    result = NarrationTimingSet(
        audio_path=str(audio_path),
        audio_fingerprint=_file_fingerprint(audio_path),
        narration_srt_path=str(narration_srt_path),
        narration_srt_sha256=srt_sha,
        script_sha256=script.source_sha256,
    )

    for index, mapping in enumerate(mappings):
        previous_end = mappings[index - 1].core_end_ms if index > 0 else 0
        next_start = (
            mappings[index + 1].core_start_ms
            if index + 1 < len(mappings)
            else mapping.core_end_ms + search_margin_ms
        )
        lower_bound = (
            max(0, (previous_end + mapping.core_start_ms) // 2)
            if index > 0
            else 0
        )
        upper_bound = (
            max(mapping.core_end_ms, (mapping.core_end_ms + next_start) // 2)
            if index + 1 < len(mappings)
            else mapping.core_end_ms + search_margin_ms
        )
        window_start = max(
            lower_bound,
            mapping.core_start_ms - search_margin_ms,
        )
        window_end = min(
            upper_bound,
            mapping.core_end_ms + search_margin_ms,
        )
        if window_end <= window_start:
            window_end = mapping.core_end_ms + max(after_padding_ms, 100)

        intervals = detector.detect(audio_path, window_start, window_end)
        timing = refine_safe_padding(
            mapping,
            intervals,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            before_padding_ms=before_padding_ms,
            after_padding_ms=after_padding_ms,
        )
        result.timings[mapping.unit_id] = timing
        if timing.warning:
            result.warnings.append(f"{mapping.unit_id}: {timing.warning}")

    return result


def refine_safe_padding(
    mapping: NarrationCueMapping,
    silences: Sequence[SilenceInterval],
    *,
    lower_bound: int,
    upper_bound: int,
    before_padding_ms: int = 250,
    after_padding_ms: int = 350,
) -> NarrationAudioTiming:
    lower_bound = max(0, int(lower_bound))
    upper_bound = max(int(upper_bound), mapping.core_end_ms)

    before = [
        silence
        for silence in silences
        if silence.start_ms < mapping.core_start_ms
        and silence.end_ms <= mapping.core_start_ms + 180
    ]
    after = [
        silence
        for silence in silences
        if silence.end_ms > mapping.core_end_ms
        and silence.start_ms >= mapping.core_end_ms - 180
    ]

    warning_parts: list[str] = []
    if before:
        nearest_before = max(before, key=lambda item: item.end_ms)
        source_in = max(
            lower_bound,
            nearest_before.start_ms,
            nearest_before.end_ms - int(before_padding_ms),
        )
        pre_method = "waveform-silence"
    else:
        source_in = max(lower_bound, mapping.core_start_ms - int(before_padding_ms))
        pre_method = "srt-fallback"
        warning_parts.append("silence sebelum ucapan tidak terdeteksi; padding fallback")

    if after:
        nearest_after = min(after, key=lambda item: item.start_ms)
        source_out = min(
            upper_bound,
            nearest_after.end_ms,
            nearest_after.start_ms + int(after_padding_ms),
        )
        post_method = "waveform-silence"
    else:
        source_out = min(upper_bound, mapping.core_end_ms + int(after_padding_ms))
        post_method = "srt-fallback"
        warning_parts.append("silence sesudah ucapan tidak terdeteksi; padding fallback")

    source_in = min(source_in, mapping.core_start_ms)
    source_out = max(source_out, mapping.core_end_ms)
    if source_out <= source_in:
        raise NarrationMappingError(
            f"Batas audio {mapping.unit_id} tidak valid setelah safe padding."
        )

    return NarrationAudioTiming(
        unit_id=mapping.unit_id,
        source_in_ms=source_in,
        source_out_ms=source_out,
        core_start_ms=mapping.core_start_ms,
        core_end_ms=mapping.core_end_ms,
        pre_padding_ms=max(0, mapping.core_start_ms - source_in),
        post_padding_ms=max(0, source_out - mapping.core_end_ms),
        mapping_similarity=mapping.similarity,
        mapping_method=mapping.method,
        boundary_method=f"{pre_method}/{post_method}",
        warning="; ".join(warning_parts),
    )


def parse_silencedetect(
    stderr: str,
    *,
    window_start_ms: int,
    window_end_ms: int,
) -> list[SilenceInterval]:
    events: list[tuple[str, int]] = []
    for line in str(stderr).splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            value = int(round(float(start_match.group(1)) * 1000))
            events.append(("start", window_start_ms + value))
        end_match = SILENCE_END_RE.search(line)
        if end_match:
            value = int(round(float(end_match.group(1)) * 1000))
            events.append(("end", window_start_ms + value))

    intervals: list[SilenceInterval] = []
    pending: int | None = None
    for kind, value in events:
        value = max(window_start_ms, min(value, window_end_ms))
        if kind == "start":
            pending = value
        elif pending is not None and value > pending:
            intervals.append(SilenceInterval(pending, value))
            pending = None

    if pending is not None and window_end_ms > pending:
        intervals.append(SilenceInterval(pending, window_end_ms))
    return intervals


def narration_duration_overrides(
    timing_set: NarrationTimingSet | None,
) -> dict[str, int]:
    return {} if timing_set is None else timing_set.duration_overrides()


def _map_explicit_ids(
    ordered_ids: Sequence[str],
    script: NarrationScript,
    cues: Sequence[SubtitleCue],
) -> list[NarrationCueMapping] | None:
    groups: dict[str, list[int]] = {unit_id: [] for unit_id in ordered_ids}
    found_any = False
    for index, cue in enumerate(cues):
        ids = [item.upper() for item in NARRATION_ID_RE.findall(cue.text)]
        ids = [item for item in ids if item in groups]
        if len(ids) == 1:
            groups[ids[0]].append(index)
            found_any = True
    if not found_any:
        return None
    if any(not groups[unit_id] for unit_id in ordered_ids):
        return None

    result: list[NarrationCueMapping] = []
    previous_end = -1
    for unit_id in ordered_ids:
        indexes = groups[unit_id]
        if indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise NarrationMappingError(
                f"Cue berlabel {unit_id} tidak kontigu di SRT narasi."
            )
        selected = [cues[index] for index in indexes]
        start = selected[0].start_ms
        end = selected[-1].end_ms
        if start < previous_end:
            raise NarrationMappingError(
                f"Urutan cue berlabel {unit_id} tidak kronologis."
            )
        text = " ".join(_strip_narration_id(cue.text) for cue in selected).strip()
        similarity = _similarity(script.units[unit_id].text, text)
        result.append(
            NarrationCueMapping(
                unit_id=unit_id,
                text=script.units[unit_id].text,
                cue_indexes=[
                    cue.index if cue.index is not None else index + 1
                    for index, cue in zip(indexes, selected)
                ],
                core_start_ms=start,
                core_end_ms=end,
                similarity=similarity,
                method="explicit-id",
            )
        )
        previous_end = end
    return result


def _map_monotonic_text(
    ordered_ids: Sequence[str],
    script: NarrationScript,
    cues: Sequence[SubtitleCue],
) -> list[NarrationCueMapping]:
    unit_count = len(ordered_ids)
    cue_count = len(cues)
    if cue_count < unit_count:
        raise NarrationMappingError(
            f"SRT narasi hanya memiliki {cue_count} cue untuk {unit_count} unit N."
        )

    max_group = max(1, min(20, cue_count - unit_count + 1))
    neg = -10**9
    dp = [[neg] * (cue_count + 1) for _ in range(unit_count + 1)]
    back: list[list[int | None]] = [
        [None] * (cue_count + 1) for _ in range(unit_count + 1)
    ]
    dp[0][0] = 0.0

    for u in range(1, unit_count + 1):
        target = script.units[ordered_ids[u - 1]].text
        min_end = u
        max_end = cue_count - (unit_count - u)
        for end in range(min_end, max_end + 1):
            start_min = max(u - 1, end - max_group)
            for start in range(start_min, end):
                if dp[u - 1][start] <= neg / 2:
                    continue
                candidate = " ".join(cue.text for cue in cues[start:end])
                score = _similarity(target, candidate)
                # Slight penalty for giant groups keeps ambiguous SRT from being
                # swallowed by a single unit when textual fit is similar.
                score_adjusted = score - max(0, (end - start) - 6) * 0.01
                total = dp[u - 1][start] + score_adjusted
                if total > dp[u][end]:
                    dp[u][end] = total
                    back[u][end] = start

    if back[unit_count][cue_count] is None:
        raise NarrationMappingError("SRT narasi tidak dapat dipetakan secara monoton.")

    groups: list[tuple[int, int]] = []
    end = cue_count
    for u in range(unit_count, 0, -1):
        start = back[u][end]
        if start is None:
            raise NarrationMappingError("Backtracking mapping SRT gagal.")
        groups.append((start, end))
        end = start
    groups.reverse()

    result: list[NarrationCueMapping] = []
    for unit_id, (start, end) in zip(ordered_ids, groups):
        selected = cues[start:end]
        candidate = " ".join(cue.text for cue in selected)
        result.append(
            NarrationCueMapping(
                unit_id=unit_id,
                text=script.units[unit_id].text,
                cue_indexes=[
                    cue.index if cue.index is not None else index + 1
                    for index, cue in enumerate(selected, start=start)
                ],
                core_start_ms=selected[0].start_ms,
                core_end_ms=selected[-1].end_ms,
                similarity=_similarity(script.units[unit_id].text, candidate),
                method="monotonic-text",
            )
        )
    return result


def _similarity(left: str, right: str) -> float:
    a = _normalize_text(left)
    b = _normalize_text(_strip_narration_id(right))
    if not a or not b:
        return 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return max(0.0, min(1.0, sequence * 0.72 + overlap * 0.28))


def _normalize_text(value: str) -> str:
    text = str(value).lower()
    text = NARRATION_ID_RE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _strip_narration_id(value: str) -> str:
    return re.sub(r"\bN-\d{3,}\b\s*[:—–-]?", " ", str(value), flags=re.IGNORECASE)


def _clean_script_text(lines: Iterable[str]) -> str:
    text = " ".join(str(line).strip() for line in lines if str(line).strip())
    text = re.sub(r"\s+", " ", text).strip()
    # Strip common prose labels but keep the user's actual narration words.
    text = re.sub(
        r"^(?:narasi(?:\s+final)?|teks(?:\s+narasi)?|voice\s*over)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def _looks_like_heading(line: str) -> bool:
    clean = str(line).strip()
    if len(clean) > 120:
        return False
    upper = clean.upper().strip("#*_ ")
    return (
        upper.startswith("LAMPIRAN ")
        or upper.startswith("BAGIAN ")
        or upper in {"STATUS", "CATATAN", "AUDIT"}
    )


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise NarrationMappingError("DOCX Prompt 1B1 tidak valid.") from exc
    root = ET.fromstring(raw)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        chunks = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        value = "".join(chunks).strip()
        if value:
            paragraphs.append(value)
    return "\n".join(paragraphs)


def _file_fingerprint(path: str | Path) -> str:
    source = Path(path).expanduser()
    stat = source.stat()
    material = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:24]
