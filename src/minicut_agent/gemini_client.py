from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
import socket
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .evidence_packets import ShotEvidence, UnitEvidencePacket
from .gemini_keys import (
    GeminiKeyPool,
    NoGeminiKeyAvailable,
    save_key_store,
)

DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_API_REVISION = "2026-05-20"
DEFAULT_MAX_IMAGES = 12
DEFAULT_MAX_INLINE_BYTES = 12 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 90.0

DECISIONS = {"keep", "reject", "trim"}


class GeminiRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GeminiResponseError(ValueError):
    pass


@dataclass(slots=True)
class EvidenceBatch:
    batch_index: int
    shot_indexes: list[int]
    image_count: int
    inline_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GeminiShotDecision:
    shot_index: int
    decision: str
    confidence: float
    reason: str
    trim_start_ms: int | None = None
    trim_end_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        shot: ShotEvidence,
        expected_index: int,
    ) -> "GeminiShotDecision":
        if not isinstance(data, Mapping):
            raise GeminiResponseError("Decision Gemini harus berupa object.")

        try:
            shot_index = int(data["shot_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GeminiResponseError("shot_index Gemini tidak valid.") from exc
        if shot_index != expected_index:
            raise GeminiResponseError(
                f"Gemini mengembalikan shot_index {shot_index}, "
                f"seharusnya {expected_index}."
            )

        decision = str(data.get("decision", "")).strip().lower()
        if decision not in DECISIONS:
            raise GeminiResponseError(
                f"Decision shot {shot_index} tidak valid: {decision!r}."
            )

        try:
            confidence = float(data.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise GeminiResponseError(
                f"Confidence shot {shot_index} tidak valid."
            ) from exc
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise GeminiResponseError(
                f"Confidence shot {shot_index} harus 0..1."
            )

        reason = str(data.get("reason", "")).strip()
        if not reason:
            raise GeminiResponseError(
                f"Reason shot {shot_index} tidak boleh kosong."
            )
        if len(reason) > 1200:
            reason = reason[:1200]

        trim_start = _optional_int(data.get("trim_start_ms"))
        trim_end = _optional_int(data.get("trim_end_ms"))

        if decision == "trim":
            if trim_start is None or trim_end is None:
                raise GeminiResponseError(
                    f"Trim shot {shot_index} harus memiliki start/end."
                )
            if not (
                shot.start_ms
                <= trim_start
                < trim_end
                <= shot.end_ms
            ):
                raise GeminiResponseError(
                    f"Trim shot {shot_index} keluar dari batas shot "
                    f"{shot.start_ms}..{shot.end_ms}."
                )
        else:
            trim_start = None
            trim_end = None

        return cls(
            shot_index=shot_index,
            decision=decision,
            confidence=confidence,
            reason=reason,
            trim_start_ms=trim_start,
            trim_end_ms=trim_end,
        )


@dataclass
class GeminiBatchResult:
    batch_index: int
    model: str
    key_id: str
    decisions: list[GeminiShotDecision]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_index": self.batch_index,
            "model": self.model,
            "key_id": self.key_id,
            "decisions": [item.to_dict() for item in self.decisions],
            "notes": self.notes,
        }


@dataclass
class GeminiUnitVerification:
    unit_id: str
    model: str
    batches: list[GeminiBatchResult] = field(default_factory=list)

    @property
    def decisions(self) -> list[GeminiShotDecision]:
        result: list[GeminiShotDecision] = []
        for batch in self.batches:
            result.extend(batch.decisions)
        return sorted(result, key=lambda item: item.shot_index)

    def summary(self) -> dict[str, Any]:
        counts = {name: 0 for name in sorted(DECISIONS)}
        for decision in self.decisions:
            counts[decision.decision] += 1
        return {
            "unit_id": self.unit_id,
            "model": self.model,
            "batches": len(self.batches),
            "decisions": len(self.decisions),
            **counts,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "unit_id": self.unit_id,
            "model": self.model,
            "batches": [item.to_dict() for item in self.batches],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GeminiUnitVerification":
        if int(data.get("schema_version", 1)) != 1:
            raise ValueError("Schema Gemini verification tidak didukung.")
        batches: list[GeminiBatchResult] = []
        for raw_batch in list(data.get("batches") or []):
            if not isinstance(raw_batch, Mapping):
                raise ValueError("Gemini batch checkpoint tidak valid.")
            decisions = [
                GeminiShotDecision(
                    shot_index=int(item["shot_index"]),
                    decision=str(item["decision"]),
                    confidence=float(item["confidence"]),
                    reason=str(item.get("reason", "")),
                    trim_start_ms=_optional_int(item.get("trim_start_ms")),
                    trim_end_ms=_optional_int(item.get("trim_end_ms")),
                )
                for item in list(raw_batch.get("decisions") or [])
            ]
            batches.append(
                GeminiBatchResult(
                    batch_index=int(raw_batch["batch_index"]),
                    model=str(raw_batch.get("model", "")),
                    key_id=str(raw_batch.get("key_id", "")),
                    decisions=decisions,
                    notes=str(raw_batch.get("notes", "")),
                )
            )
        return cls(
            unit_id=str(data["unit_id"]),
            model=str(data.get("model", "")),
            batches=batches,
        )


Transport = Callable[
    [str, Mapping[str, str], bytes, float],
    tuple[int, Mapping[str, str], bytes],
]
KeyStateSaver = Callable[[GeminiKeyPool], Any]


class GeminiEvidenceClient:
    """Bounded multimodal verification client using Gemini Interactions API."""

    def __init__(
        self,
        key_pool: GeminiKeyPool,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        api_revision: str = DEFAULT_API_REVISION,
        max_images_per_batch: int = DEFAULT_MAX_IMAGES,
        max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_key_attempts: int = 100,
        transport: Transport | None = None,
        key_state_saver: KeyStateSaver | None = save_key_store,
    ):
        self.key_pool = key_pool
        self.model = (
            model
            or os.environ.get("MINICUT_GEMINI_MODEL")
            or DEFAULT_GEMINI_MODEL
        ).strip()
        self.endpoint = (
            endpoint
            or os.environ.get("MINICUT_GEMINI_ENDPOINT")
            or DEFAULT_GEMINI_ENDPOINT
        ).strip()
        self.api_revision = str(api_revision).strip()
        self.max_images_per_batch = int(max_images_per_batch)
        self.max_inline_bytes = int(max_inline_bytes)
        self.timeout_seconds = float(timeout_seconds)
        self.max_key_attempts = max(1, int(max_key_attempts))
        self.transport = transport or _urllib_post
        self.key_state_saver = key_state_saver

        if not self.model:
            raise ValueError("Model Gemini tidak boleh kosong.")
        if not self.endpoint.startswith("https://"):
            raise ValueError("Endpoint Gemini harus HTTPS.")
        if self.max_images_per_batch < 1:
            raise ValueError("max_images_per_batch harus >= 1.")
        if self.max_inline_bytes < 64 * 1024:
            raise ValueError("max_inline_bytes terlalu kecil.")

    def verify_unit(
        self,
        packet: UnitEvidencePacket,
        *,
        unit_context: Mapping[str, Any] | None = None,
    ) -> GeminiUnitVerification:
        if not packet.shots:
            raise ValueError("Evidence packet tidak memiliki shot.")

        batches = build_evidence_batches(
            packet,
            max_images=self.max_images_per_batch,
            max_inline_bytes=self.max_inline_bytes,
        )
        result = GeminiUnitVerification(unit_id=packet.unit_id, model=self.model)

        for batch in batches:
            response, key_id = self._request_batch(
                packet,
                batch,
                unit_context=unit_context,
            )
            parsed = parse_batch_response(
                response,
                packet=packet,
                batch=batch,
                model=self.model,
                key_id=key_id,
            )
            result.batches.append(parsed)

        expected = list(range(1, len(packet.shots) + 1))
        actual = [item.shot_index for item in result.decisions]
        if actual != expected:
            raise GeminiResponseError(
                f"Gemini verification tidak lengkap. Expected {expected}, got {actual}."
            )
        return result

    def _request_batch(
        self,
        packet: UnitEvidencePacket,
        batch: EvidenceBatch,
        *,
        unit_context: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], str]:
        body = build_interaction_body(
            packet,
            batch,
            model=self.model,
            unit_context=unit_context,
        )
        payload = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        attempts = min(
            self.max_key_attempts,
            max(1, self.key_pool.summary()["total"]),
        )
        last_error: Exception | None = None

        for _ in range(attempts):
            try:
                record = self.key_pool.acquire()
            except NoGeminiKeyAvailable:
                if last_error is not None:
                    raise GeminiRequestError(str(last_error), retryable=True) from last_error
                raise

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": record.secret,
            }
            if self.api_revision:
                headers["Api-Revision"] = self.api_revision

            try:
                status, response_headers, raw = self.transport(
                    self.endpoint,
                    headers,
                    payload,
                    self.timeout_seconds,
                )
            except GeminiRequestError as exc:
                self.key_pool.report_failure(
                    record.key_id,
                    status_code=exc.status_code,
                    error=str(exc),
                )
                self._persist_pool()
                last_error = exc
                if exc.status_code is not None and 400 <= exc.status_code < 500:
                    if exc.status_code not in {401, 403, 429}:
                        raise
                continue
            except (OSError, TimeoutError, socket.timeout) as exc:
                self.key_pool.report_failure(
                    record.key_id,
                    error=str(exc),
                )
                self._persist_pool()
                last_error = exc
                continue

            if status < 200 or status >= 300:
                message = _provider_error_message(raw)
                retry_after = _retry_after_seconds(response_headers)
                self.key_pool.report_failure(
                    record.key_id,
                    status_code=status,
                    error=message,
                    retry_after_seconds=retry_after,
                )
                self._persist_pool()
                last_error = GeminiRequestError(
                    message or f"Gemini HTTP {status}",
                    status_code=status,
                    retryable=(status in {401, 403, 429} or status >= 500),
                )
                if 400 <= status < 500 and status not in {401, 403, 429}:
                    raise last_error
                continue

            try:
                decoded = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                # A malformed successful response is provider/protocol failure.
                self.key_pool.report_failure(
                    record.key_id,
                    error=f"Invalid Gemini JSON response: {exc}",
                )
                self._persist_pool()
                last_error = exc
                continue

            self.key_pool.report_success(record.key_id)
            self._persist_pool()
            return decoded, record.key_id

        message = (
            "Gemini gagal setelah mencoba key yang tersedia."
            if last_error is None
            else f"Gemini gagal setelah failover: {last_error}"
        )
        raise GeminiRequestError(message, retryable=True) from last_error

    def _persist_pool(self) -> None:
        if self.key_state_saver is None:
            return
        try:
            self.key_state_saver(self.key_pool)
        except OSError:
            # Provider result must not be discarded merely because health
            # metadata could not be flushed to disk.
            pass


def build_evidence_batches(
    packet: UnitEvidencePacket,
    *,
    max_images: int = DEFAULT_MAX_IMAGES,
    max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES,
) -> list[EvidenceBatch]:
    max_images = int(max_images)
    max_inline_bytes = int(max_inline_bytes)
    if max_images < 1 or max_inline_bytes < 1:
        raise ValueError("Batas batch Gemini tidak valid.")

    batches: list[EvidenceBatch] = []
    current: list[int] = []
    current_images = 0
    current_bytes = 0

    for shot_index, shot in enumerate(packet.shots, start=1):
        images = len(shot.frames)
        inline = sum(_base64_size(_frame_size(frame.path, frame.size_bytes)) for frame in shot.frames)

        if images > max_images or inline > max_inline_bytes:
            raise ValueError(
                f"Shot #{shot_index} sendiri melebihi batas evidence Gemini "
                f"({images} gambar, {inline} bytes inline)."
            )

        if current and (
            current_images + images > max_images
            or current_bytes + inline > max_inline_bytes
        ):
            batches.append(
                EvidenceBatch(
                    batch_index=len(batches) + 1,
                    shot_indexes=current,
                    image_count=current_images,
                    inline_bytes=current_bytes,
                )
            )
            current = []
            current_images = 0
            current_bytes = 0

        current.append(shot_index)
        current_images += images
        current_bytes += inline

    if current:
        batches.append(
            EvidenceBatch(
                batch_index=len(batches) + 1,
                shot_indexes=current,
                image_count=current_images,
                inline_bytes=current_bytes,
            )
        )

    if not batches:
        raise ValueError("Tidak ada evidence yang dapat dikirim ke Gemini.")
    return batches


def build_interaction_body(
    packet: UnitEvidencePacket,
    batch: EvidenceBatch,
    *,
    model: str,
    unit_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    schema = decision_schema(batch.shot_indexes)
    input_items: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _batch_prompt(
                packet,
                batch,
                unit_context=unit_context,
            ),
        }
    ]

    for shot_index in batch.shot_indexes:
        shot = packet.shots[shot_index - 1]
        for frame in shot.frames:
            path = Path(frame.path)
            raw = path.read_bytes()
            if not raw:
                raise ValueError(f"Frame evidence kosong: {path}")
            mime = _image_mime(path)
            input_items.extend(
                [
                    {
                        "type": "text",
                        "text": (
                            f"SHOT {shot_index} FRAME @ {frame.timestamp_ms} ms "
                            f"(shot {shot.start_ms}..{shot.end_ms} ms)"
                        ),
                    },
                    {
                        "type": "image",
                        "mime_type": mime,
                        "data": base64.b64encode(raw).decode("ascii"),
                    },
                ]
            )

    return {
        "model": model,
        "store": False,
        "system_instruction": (
            "You are the visual verification component of a local video editor. "
            "Evaluate only the supplied candidate shots. Never invent footage, "
            "shot indexes, timestamps, dialogue, or events outside the evidence. "
            "Return only the requested structured JSON."
        ),
        "input": input_items,
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
    }


def decision_schema(shot_indexes: Sequence[int]) -> dict[str, Any]:
    allowed = [int(item) for item in shot_indexes]
    return {
        "type": "object",
        "properties": {
            "unit_id": {"type": "string"},
            "batch_index": {"type": "integer"},
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "shot_index": {
                            "type": "integer",
                            "enum": allowed,
                        },
                        "decision": {
                            "type": "string",
                            "enum": ["keep", "reject", "trim"],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {"type": "string"},
                        "trim_start_ms": {"type": "integer"},
                        "trim_end_ms": {"type": "integer"},
                    },
                    "required": [
                        "shot_index",
                        "decision",
                        "confidence",
                        "reason",
                    ],
                },
            },
            "notes": {"type": "string"},
        },
        "required": [
            "unit_id",
            "batch_index",
            "decisions",
            "notes",
        ],
    }


def parse_batch_response(
    interaction: Mapping[str, Any],
    *,
    packet: UnitEvidencePacket,
    batch: EvidenceBatch,
    model: str,
    key_id: str,
) -> GeminiBatchResult:
    text = extract_output_text(interaction)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiResponseError(
            f"Gemini structured output bukan JSON valid: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise GeminiResponseError("Gemini structured output harus object.")

    if str(raw.get("unit_id", "")).strip() != packet.unit_id:
        raise GeminiResponseError("Gemini mengembalikan unit_id yang berbeda.")
    try:
        batch_index = int(raw.get("batch_index"))
    except (TypeError, ValueError) as exc:
        raise GeminiResponseError("Gemini batch_index tidak valid.") from exc
    if batch_index != batch.batch_index:
        raise GeminiResponseError("Gemini mengembalikan batch_index yang berbeda.")

    decision_items = raw.get("decisions")
    if not isinstance(decision_items, list):
        raise GeminiResponseError("Gemini decisions harus berupa array.")

    by_index: dict[int, Mapping[str, Any]] = {}
    for item in decision_items:
        if not isinstance(item, Mapping):
            raise GeminiResponseError("Item Gemini decision harus object.")
        try:
            index = int(item.get("shot_index"))
        except (TypeError, ValueError) as exc:
            raise GeminiResponseError("Gemini shot_index tidak valid.") from exc
        if index in by_index:
            raise GeminiResponseError(f"Gemini menduplikasi shot_index {index}.")
        by_index[index] = item

    if set(by_index) != set(batch.shot_indexes):
        raise GeminiResponseError(
            "Gemini harus mengembalikan tepat satu decision untuk setiap shot batch."
        )

    decisions = [
        GeminiShotDecision.from_dict(
            by_index[index],
            shot=packet.shots[index - 1],
            expected_index=index,
        )
        for index in batch.shot_indexes
    ]
    return GeminiBatchResult(
        batch_index=batch.batch_index,
        model=model,
        key_id=key_id,
        decisions=decisions,
        notes=str(raw.get("notes", "")).strip()[:2000],
    )


def extract_output_text(interaction: Mapping[str, Any]) -> str:
    steps = interaction.get("steps")
    if not isinstance(steps, list):
        raise GeminiResponseError("Response Gemini tidak memiliki steps.")

    texts: list[str] = []
    for step in steps:
        if not isinstance(step, Mapping) or step.get("type") != "model_output":
            continue
        content = step.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if (
                isinstance(item, Mapping)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            ):
                texts.append(str(item["text"]))
    output = "\n".join(texts).strip()
    if not output:
        raise GeminiResponseError("Response Gemini tidak memiliki model_output text.")
    return output


def _batch_prompt(
    packet: UnitEvidencePacket,
    batch: EvidenceBatch,
    *,
    unit_context: Mapping[str, Any] | None,
) -> str:
    shots = []
    for index in batch.shot_indexes:
        shot = packet.shots[index - 1]
        shots.append(
            {
                "shot_index": index,
                "start_ms": shot.start_ms,
                "end_ms": shot.end_ms,
                "location": shot.location,
                "label": shot.label,
                "subtitle": [
                    {
                        "start_ms": cue.start_ms,
                        "end_ms": cue.end_ms,
                        "text": cue.text,
                    }
                    for cue in shot.subtitles
                ],
                "frame_timestamps_ms": [
                    frame.timestamp_ms for frame in shot.frames
                ],
            }
        )

    context = _compact_context(unit_context or {})
    evidence = {
        "unit_id": packet.unit_id,
        "batch_index": batch.batch_index,
        "unit_context": context,
        "shots": shots,
    }
    prompt3_target = context.get("prompt3_target_duration_ms")
    prompt3_rules = ""
    if isinstance(prompt3_target, (int, float)) and int(prompt3_target) > 0:
        prompt3_rules = (
            " This is a Prompt 3 narration unit. The safe-padded narration audio "
            f"duration is {int(prompt3_target)} ms and is authoritative. Final "
            "visuals will be fitted locally at speed <=0.50x, with each final "
            "piece >=2000 ms, film audio muted, and source order strictly "
            "chronological. Prefer keep/trim/reject choices that can reasonably "
            "fit that duration; use trim when the useful continuous subrange is "
            "smaller than the full shot. Never request speed >0.50x and never "
            "reorder shots."
        )

    return (
        "Verify which supplied shots are useful candidates for the current V42 "
        "unit. Use only visible frame evidence, timestamps, labels/location, and "
        "overlapping film subtitles. Mark each shot exactly once as keep, reject, "
        "or trim. Use trim only when a smaller continuous portion is clearly "
        "better; trim timestamps must remain inside that shot. Confidence is "
        "0..1. Give a short factual reason. Do not create an edit or timeline "
        "action yet."
        + prompt3_rules
        + " Evidence JSON follows:\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )


def _compact_context(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, raw in list(value.items())[:40]:
        name = str(key)[:120]
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            text: Any = raw
            if isinstance(raw, str) and len(raw) > 3000:
                text = raw[:3000]
            result[name] = text
        elif isinstance(raw, list):
            result[name] = [
                _compact_scalar(item) for item in raw[:30]
            ]
        elif isinstance(raw, Mapping):
            nested: dict[str, Any] = {}
            for sub_key, sub_value in list(raw.items())[:20]:
                nested[str(sub_key)[:100]] = _compact_scalar(sub_value)
            result[name] = nested
        else:
            result[name] = str(raw)[:1000]
    return result


def _compact_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value[:1500]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1500]


def _frame_size(path: str, recorded_size: int) -> int:
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(f"Frame evidence tidak ditemukan: {file}")
    actual = file.stat().st_size
    if actual <= 0:
        raise ValueError(f"Frame evidence kosong: {file}")
    return actual


def _base64_size(raw_bytes: int) -> int:
    return 4 * math.ceil(max(0, int(raw_bytes)) / 3)


def _image_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime in {"image/jpeg", "image/png", "image/webp"}:
        return mime
    return "image/jpeg"


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise GeminiResponseError("Nilai timestamp boolean tidak valid.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GeminiResponseError("Nilai timestamp Gemini tidak valid.") from exc


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if str(key).lower() != "retry-after":
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, parsed)
    return None


def _provider_error_message(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, Mapping):
            error = payload.get("error")
            if isinstance(error, Mapping):
                message = str(error.get("message", "")).strip()
                if message:
                    return message[:1000]
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return raw.decode("utf-8", errors="replace").strip()[:1000]


def _urllib_post(
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout: float,
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(
        url,
        data=body,
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                int(response.status),
                dict(response.headers.items()),
                response.read(),
            )
    except urllib.error.HTTPError as exc:
        return (
            int(exc.code),
            dict(exc.headers.items()) if exc.headers else {},
            exc.read(),
        )
    except urllib.error.URLError as exc:
        raise OSError(str(exc.reason)) from exc
