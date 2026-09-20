from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

UNIT_RE = re.compile(r"\b([NJD]-\d{3,})\b", re.IGNORECASE)
BLOCK_RE = re.compile(r"\b(B-\d{3,})\b", re.IGNORECASE)
AUDIT_RE = re.compile(r"\bAudit\s+(B-\d{3,})\b", re.IGNORECASE)
BLOCK_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(B-\d{3,})\s*(?:[-—–:]\s*)?(.*)$",
    re.IGNORECASE,
)
NUMBERED_WORK_RE = re.compile(
    r"^\s*\d+\s*[.)-]\s*((?:[NJ]-\d{3,})|(?:Audit\s+B-\d{3,}))\b",
    re.IGNORECASE,
)
TIME_TOKEN = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"
RANGE_RE = re.compile(
    rf"(?P<start>{TIME_TOKEN})\s*(?:-->|→|[-–—]|\bs/?d\b|\bhingga\b|\bto\b)\s*(?P<end>{TIME_TOKEN})",
    re.IGNORECASE,
)


@dataclass(slots=True)
class CandidateRange:
    start_ms: int
    end_ms: int
    source_text: str = ""
    label: str = ""
    location: str | None = None

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateRange":
        return cls(
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            source_text=str(data.get("source_text", "")),
            label=str(data.get("label", "")),
            location=(
                None
                if data.get("location") in (None, "")
                else str(data.get("location"))
            ),
        )


@dataclass
class V42UnitSpec:
    id: str
    kind: str
    block_id: str | None = None
    display_order: int | None = None
    work_order: int | None = None
    candidate_ranges: list[CandidateRange] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "block_id": self.block_id,
            "display_order": self.display_order,
            "work_order": self.work_order,
            "candidate_ranges": [item.to_dict() for item in self.candidate_ranges],
            "fields": self.fields,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "V42UnitSpec":
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind") or _unit_kind(str(data["id"]))),
            block_id=(
                None if data.get("block_id") in (None, "") else str(data["block_id"])
            ),
            display_order=(
                None if data.get("display_order") is None else int(data["display_order"])
            ),
            work_order=(
                None if data.get("work_order") is None else int(data["work_order"])
            ),
            candidate_ranges=[
                CandidateRange.from_dict(item)
                for item in list(data.get("candidate_ranges") or [])
            ],
            fields=dict(data.get("fields") or {}),
        )


@dataclass
class V42BlockSpec:
    id: str
    title: str = ""
    unit_ids: list[str] = field(default_factory=list)
    display_order: list[str] = field(default_factory=list)
    work_order: list[str] = field(default_factory=list)
    candidate_ranges: list[CandidateRange] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "unit_ids": list(self.unit_ids),
            "display_order": list(self.display_order),
            "work_order": list(self.work_order),
            "candidate_ranges": [item.to_dict() for item in self.candidate_ranges],
            "fields": self.fields,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "V42BlockSpec":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            unit_ids=[str(item) for item in list(data.get("unit_ids") or [])],
            display_order=[str(item) for item in list(data.get("display_order") or [])],
            work_order=[str(item) for item in list(data.get("work_order") or [])],
            candidate_ranges=[
                CandidateRange.from_dict(item)
                for item in list(data.get("candidate_ranges") or [])
            ],
            fields=dict(data.get("fields") or {}),
        )


@dataclass
class V42OneB2Plan:
    source_path: str
    source_sha256: str
    blocks: dict[str, V42BlockSpec] = field(default_factory=dict)
    units: dict[str, V42UnitSpec] = field(default_factory=dict)
    work_queue: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def candidate_range_count(self) -> int:
        return sum(len(unit.candidate_ranges) for unit in self.units.values()) + sum(
            len(block.candidate_ranges) for block in self.blocks.values()
        )

    def summary(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for unit in self.units.values():
            kinds[unit.kind] = kinds.get(unit.kind, 0) + 1
        return {
            "blocks": len(self.blocks),
            "units": len(self.units),
            "unit_kinds": kinds,
            "work_items": len(self.work_queue),
            "candidate_ranges": self.candidate_range_count,
            "warnings": len(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "blocks": {
                key: value.to_dict() for key, value in sorted(self.blocks.items())
            },
            "units": {
                key: value.to_dict() for key, value in sorted(self.units.items())
            },
            "work_queue": list(self.work_queue),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "V42OneB2Plan":
        if not isinstance(data, dict):
            raise ValueError("Data 1B2 harus berupa object.")
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("Schema data 1B2 tidak didukung.")
        return cls(
            source_path=str(data.get("source_path", "")),
            source_sha256=str(data.get("source_sha256", "")),
            blocks={
                str(key): V42BlockSpec.from_dict(value)
                for key, value in dict(data.get("blocks") or {}).items()
            },
            units={
                str(key): V42UnitSpec.from_dict(value)
                for key, value in dict(data.get("units") or {}).items()
            },
            work_queue=[str(item) for item in list(data.get("work_queue") or [])],
            warnings=[str(item) for item in list(data.get("warnings") or [])],
        )


def load_1b2(path: str | Path) -> V42OneB2Plan:
    source = Path(path).expanduser()
    raw_bytes = source.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    suffix = source.suffix.lower()

    if suffix == ".json":
        raw = json.loads(raw_bytes.decode("utf-8-sig"))
        plan = parse_registration_json(raw)
    elif suffix == ".docx":
        plan = parse_1b2_text(_docx_text(source))
    else:
        text = raw_bytes.decode("utf-8-sig", errors="replace")
        plan = parse_1b2_text(text)

    plan.source_path = str(source)
    plan.source_sha256 = digest
    _finalize_plan(plan)
    return plan


def parse_registration_json(raw: Any) -> V42OneB2Plan:
    records = _registration_records(raw)
    plan = V42OneB2Plan(source_path="", source_sha256="")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            plan.warnings.append(f"Registrasi #{index + 1} bukan object.")
            continue
        normalized = {_key(k): v for k, v in record.items()}
        unit_id = _first_unit_id(normalized.get("unit"))
        block_id = _first_block_id(normalized.get("blok") or normalized.get("block"))

        if not unit_id:
            # Some exports use the ID as an explicit id field.
            unit_id = _first_unit_id(normalized.get("id"))
        if not unit_id:
            plan.warnings.append(f"Registrasi #{index + 1} tidak memiliki Unit N/J/D.")
            continue

        unit = _ensure_unit(plan, unit_id, block_id)
        if block_id:
            block = _ensure_block(plan, block_id)
            _append_unique(block.unit_ids, unit_id)

        unit.fields.update({str(k): v for k, v in record.items()})

        display_value = normalized.get("urutan tayang")
        work_value = normalized.get("urutan pengerjaan")
        unit.display_order = _order_number(display_value)
        unit.work_order = _order_number(work_value)

        candidate_value = (
            normalized.get("wilayah kandidat visual")
            or normalized.get("wilayah kandidat")
            or normalized.get("candidate ranges")
        )
        for candidate in extract_candidate_ranges(
            candidate_value,
            label="Wilayah kandidat visual",
        ):
            _append_range_unique(unit.candidate_ranges, candidate)

        location_pools = normalized.get("kolam visual per lokasi narasi")
        for candidate in extract_candidate_ranges(
            location_pools,
            label="Kolam visual per lokasi narasi",
        ):
            _append_range_unique(unit.candidate_ranges, candidate)

    ordered = sorted(
        (
            (unit.work_order, unit.id)
            for unit in plan.units.values()
            if unit.work_order is not None
        ),
        key=lambda item: (item[0], item[1]),
    )
    plan.work_queue = [unit_id for _, unit_id in ordered]
    return plan


def parse_1b2_text(text: str) -> V42OneB2Plan:
    plan = V42OneB2Plan(source_path="", source_sha256="")
    current_block: V42BlockSpec | None = None
    current_field: str | None = None
    current_unit: V42UnitSpec | None = None

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        work = NUMBERED_WORK_RE.match(line)
        if work:
            item = _normalize_work_item(work.group(1))
            _append_unique(plan.work_queue, item)
            unit_id = _first_unit_id(item)
            if unit_id:
                unit = _ensure_unit(
                    plan,
                    unit_id,
                    current_block.id if current_block else None,
                )
                unit.work_order = plan.work_queue.index(item) + 1
            continue

        heading = BLOCK_HEADING_RE.match(line.strip("*_ "))
        if heading:
            block_id = heading.group(1).upper()
            title = heading.group(2).strip(" -*_")
            current_block = _ensure_block(plan, block_id)
            if title:
                current_block.title = title
            current_field = None
            current_unit = None
            continue

        field_match = _field_line(line)
        if field_match:
            current_field, value = field_match
            if current_block is not None:
                current_block.fields[current_field] = value
                field_key = _key(current_field)

                if field_key == "urutan tayang":
                    current_block.display_order = _unit_ids(value)
                elif field_key == "urutan pengerjaan":
                    current_block.work_order = _work_items(value)
                    for item in current_block.work_order:
                        _append_unique(plan.work_queue, item)

                for unit_id in _unit_ids(value):
                    unit = _ensure_unit(plan, unit_id, current_block.id)
                    _append_unique(current_block.unit_ids, unit_id)

                ranges = extract_candidate_ranges(value, label=current_field)
                if ranges:
                    for candidate in ranges:
                        _append_range_unique(current_block.candidate_ranges, candidate)

            current_unit = _unit_context_from_line(plan, line, current_block)
            if current_unit and value:
                for candidate in extract_candidate_ranges(value, label=current_field or ""):
                    _append_range_unique(current_unit.candidate_ranges, candidate)
            continue

        unit_context = _unit_context_from_line(plan, line, current_block)
        if unit_context is not None:
            current_unit = unit_context

        if current_block is not None:
            for unit_id in _unit_ids(line):
                unit = _ensure_unit(plan, unit_id, current_block.id)
                _append_unique(current_block.unit_ids, unit_id)

        ranges = extract_candidate_ranges(line, label=current_field or "")
        if ranges:
            target_unit = current_unit
            if target_unit is not None:
                for candidate in ranges:
                    _append_range_unique(target_unit.candidate_ranges, candidate)
            elif current_block is not None:
                for candidate in ranges:
                    _append_range_unique(current_block.candidate_ranges, candidate)

    # If a per-block work order was found but no standalone work list exists.
    if not plan.work_queue:
        for block in plan.blocks.values():
            for item in block.work_order:
                _append_unique(plan.work_queue, item)

    return plan


def extract_candidate_ranges(
    value: Any,
    *,
    label: str = "",
    location: str | None = None,
) -> list[CandidateRange]:
    if value is None:
        return []

    if isinstance(value, dict):
        ranges: list[CandidateRange] = []
        for key, item in value.items():
            ranges.extend(
                extract_candidate_ranges(
                    item,
                    label=label or str(key),
                    location=str(key),
                )
            )
        return ranges

    if isinstance(value, list):
        ranges: list[CandidateRange] = []
        for item in value:
            ranges.extend(
                extract_candidate_ranges(item, label=label, location=location)
            )
        return ranges

    text = str(value)
    ranges = []
    for match in RANGE_RE.finditer(text):
        start = parse_timestamp(match.group("start"))
        end = parse_timestamp(match.group("end"))
        if end <= start:
            continue
        ranges.append(
            CandidateRange(
                start_ms=start,
                end_ms=end,
                source_text=match.group(0),
                label=label,
                location=location,
            )
        )
    return ranges


def parse_timestamp(value: str) -> int:
    token = str(value).strip().replace(",", ".")
    parts = token.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError(f"Timestamp tidak valid: {value}")

    try:
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        else:
            hours = 0
            minutes = int(parts[0])
            seconds = float(parts[1])
    except ValueError as exc:
        raise ValueError(f"Timestamp tidak valid: {value}") from exc

    if hours < 0 or minutes < 0 or seconds < 0 or seconds >= 60:
        raise ValueError(f"Timestamp tidak valid: {value}")
    if len(parts) == 3 and minutes >= 60:
        raise ValueError(f"Timestamp tidak valid: {value}")

    return int(round(((hours * 60 + minutes) * 60 + seconds) * 1000))


def _registration_records(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        raise ValueError("Registrasi Pusat harus berupa object atau array.")

    normalized = {_key(k): v for k, v in raw.items()}
    for key in (
        "registrasi pusat",
        "registrasi",
        "records",
        "units",
        "data",
    ):
        value = normalized.get(key)
        if isinstance(value, list):
            return value

    # Accept a single registration record.
    if _first_unit_id(normalized.get("unit") or normalized.get("id")):
        return [raw]

    raise ValueError("Array registrasi unit tidak ditemukan.")


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("DOCX 1B2 tidak valid atau document.xml tidak ditemukan.") from exc

    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        chunks = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        text = "".join(chunks).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _field_line(line: str) -> tuple[str, str] | None:
    clean = line.strip().strip("*")
    if ":" not in clean:
        return None
    key, value = clean.split(":", 1)
    key = key.strip().strip("*")
    if not key or len(key) > 100:
        return None
    return key, value.strip().strip("*")


def _unit_context_from_line(
    plan: V42OneB2Plan,
    line: str,
    block: V42BlockSpec | None,
) -> V42UnitSpec | None:
    match = re.match(r"^\s*[-*]?\s*([NJD]-\d{3,})\s*:", line, re.IGNORECASE)
    if not match:
        return None
    unit = _ensure_unit(plan, match.group(1), block.id if block else None)
    if block is not None:
        _append_unique(block.unit_ids, unit.id)
    return unit


def _ensure_block(plan: V42OneB2Plan, block_id: str) -> V42BlockSpec:
    block_id = block_id.upper()
    if block_id not in plan.blocks:
        plan.blocks[block_id] = V42BlockSpec(id=block_id)
    return plan.blocks[block_id]


def _ensure_unit(
    plan: V42OneB2Plan,
    unit_id: str,
    block_id: str | None = None,
) -> V42UnitSpec:
    unit_id = unit_id.upper()
    unit = plan.units.get(unit_id)
    if unit is None:
        unit = V42UnitSpec(
            id=unit_id,
            kind=_unit_kind(unit_id),
            block_id=block_id,
        )
        plan.units[unit_id] = unit
    elif block_id and not unit.block_id:
        unit.block_id = block_id
    return unit


def _unit_kind(unit_id: str) -> str:
    prefix = unit_id[:1].upper()
    return {
        "N": "narration",
        "J": "anchor",
        "D": "dialog",
    }.get(prefix, "unknown")


def _unit_ids(value: Any) -> list[str]:
    return [match.upper() for match in UNIT_RE.findall(str(value or ""))]


def _work_items(value: Any) -> list[str]:
    text = str(value or "")
    tokens: list[tuple[int, str]] = []
    for match in UNIT_RE.finditer(text):
        tokens.append((match.start(), match.group(1).upper()))
    for match in AUDIT_RE.finditer(text):
        tokens.append((match.start(), f"Audit {match.group(1).upper()}"))
    tokens.sort(key=lambda item: item[0])
    return [token for _, token in tokens]


def _first_unit_id(value: Any) -> str | None:
    ids = _unit_ids(value)
    return ids[0] if ids else None


def _first_block_id(value: Any) -> str | None:
    match = BLOCK_RE.search(str(value or ""))
    return match.group(1).upper() if match else None


def _normalize_work_item(value: str) -> str:
    audit = AUDIT_RE.search(value)
    if audit:
        return f"Audit {audit.group(1).upper()}"
    unit = _first_unit_id(value)
    return unit or value.strip()


def _order_number(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _key(value: Any) -> str:
    text = str(value).strip().lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :")


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _append_range_unique(items: list[CandidateRange], value: CandidateRange) -> None:
    key = (value.start_ms, value.end_ms, value.location)
    if all((item.start_ms, item.end_ms, item.location) != key for item in items):
        items.append(value)


def _finalize_plan(plan: V42OneB2Plan) -> None:
    for block in plan.blocks.values():
        for unit_id in block.display_order:
            unit = _ensure_unit(plan, unit_id, block.id)
            _append_unique(block.unit_ids, unit_id)
            if unit.display_order is None:
                unit.display_order = block.display_order.index(unit_id) + 1

        for item in block.work_order:
            unit_id = _first_unit_id(item)
            if not unit_id:
                continue
            unit = _ensure_unit(plan, unit_id, block.id)
            _append_unique(block.unit_ids, unit_id)
            if unit.work_order is None:
                unit.work_order = plan.work_queue.index(item) + 1 if item in plan.work_queue else None

    # Synthesize per-block orders when the registration JSON supplied numeric
    # order fields rather than arrow-separated block fields.
    for block in plan.blocks.values():
        if not block.display_order:
            ordered_display = sorted(
                (
                    (unit.display_order, unit.id)
                    for unit in plan.units.values()
                    if unit.block_id == block.id and unit.display_order is not None
                ),
                key=lambda item: (item[0], item[1]),
            )
            block.display_order = [unit_id for _, unit_id in ordered_display]
        if not block.work_order:
            ordered_work = sorted(
                (
                    (unit.work_order, unit.id)
                    for unit in plan.units.values()
                    if unit.block_id == block.id and unit.work_order is not None
                ),
                key=lambda item: (item[0], item[1]),
            )
            block.work_order = [unit_id for _, unit_id in ordered_work]

    # Add block membership for units mentioned only in the global work queue when
    # there is exactly one plausible block.
    if len(plan.blocks) == 1:
        only_block = next(iter(plan.blocks.values()))
        for item in plan.work_queue:
            unit_id = _first_unit_id(item)
            if not unit_id:
                continue
            unit = _ensure_unit(plan, unit_id, only_block.id)
            _append_unique(only_block.unit_ids, unit_id)

    if not plan.blocks:
        plan.warnings.append("Tidak ada blok B-xxx yang terdeteksi.")
    if not plan.units:
        plan.warnings.append("Tidak ada unit N/J/D yang terdeteksi.")
    if not plan.work_queue:
        plan.warnings.append("Daftar kerja eksplisit belum terdeteksi.")
