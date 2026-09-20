from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

MAX_GEMINI_KEYS = 100
SCHEMA_VERSION = 1


class NoGeminiKeyAvailable(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass
class GeminiKeyRecord:
    key_id: str
    secret: str
    failure_count: int = 0
    cooldown_until: float = 0.0
    disabled: bool = False
    last_error: str = ""

    def masked(self) -> str:
        tail = self.secret[-4:] if len(self.secret) >= 4 else self.secret
        return f"••••{tail}"

    def public_state(self, now: float) -> dict[str, Any]:
        remaining = max(0.0, self.cooldown_until - now)
        if self.disabled:
            status = "disabled"
        elif remaining > 0:
            status = "cooldown"
        else:
            status = "ready"
        return {
            "key_id": self.key_id,
            "masked": self.masked(),
            "status": status,
            "failure_count": self.failure_count,
            "cooldown_seconds": round(remaining, 1),
            "last_error": self.last_error,
        }


class GeminiKeyPool:
    """Local-only Gemini API-key pool with round-robin failover and cooldown."""

    def __init__(
        self,
        keys: Iterable[str] = (),
        *,
        now: Callable[[], float] = time.time,
        max_keys: int = MAX_GEMINI_KEYS,
    ):
        self._now = now
        self.max_keys = int(max_keys)
        if self.max_keys < 1 or self.max_keys > MAX_GEMINI_KEYS:
            raise ValueError(f"max_keys harus 1..{MAX_GEMINI_KEYS}.")
        self._records: list[GeminiKeyRecord] = []
        self._cursor = 0
        self.replace_keys(keys)

    @property
    def records(self) -> tuple[GeminiKeyRecord, ...]:
        return tuple(self._records)

    def replace_keys(self, keys: Iterable[str]) -> None:
        cleaned = normalize_api_keys(keys)
        if len(cleaned) > self.max_keys:
            raise ValueError(
                f"Maksimal {self.max_keys} Gemini API key; ditemukan {len(cleaned)}."
            )

        previous = {record.key_id: record for record in self._records}
        records: list[GeminiKeyRecord] = []
        for secret in cleaned:
            key_id = key_fingerprint(secret)
            old = previous.get(key_id)
            if old is not None:
                old.secret = secret
                records.append(old)
            else:
                records.append(GeminiKeyRecord(key_id=key_id, secret=secret))
        self._records = records
        self._cursor = 0 if not records else min(self._cursor, len(records) - 1)

    def add_keys(self, keys: Iterable[str]) -> int:
        current = [record.secret for record in self._records]
        merged = normalize_api_keys([*current, *list(keys)])
        before = len(current)
        self.replace_keys(merged)
        return len(self._records) - before

    def acquire(self) -> GeminiKeyRecord:
        if not self._records:
            raise NoGeminiKeyAvailable("Belum ada Gemini API key.")

        now = self._now()
        count = len(self._records)
        earliest: float | None = None

        for offset in range(count):
            index = (self._cursor + offset) % count
            record = self._records[index]
            if record.disabled:
                continue
            if record.cooldown_until > now:
                earliest = (
                    record.cooldown_until
                    if earliest is None
                    else min(earliest, record.cooldown_until)
                )
                continue

            self._cursor = (index + 1) % count
            return record

        retry = None if earliest is None else max(0.0, earliest - now)
        if retry is None:
            raise NoGeminiKeyAvailable(
                "Semua Gemini API key dinonaktifkan. Import key yang valid."
            )
        raise NoGeminiKeyAvailable(
            "Semua Gemini API key sedang cooldown.",
            retry_after_seconds=retry,
        )

    def report_success(self, key_id: str) -> None:
        record = self._record(key_id)
        record.failure_count = 0
        record.cooldown_until = 0.0
        record.last_error = ""

    def report_failure(
        self,
        key_id: str,
        *,
        status_code: int | None = None,
        error: str = "",
        retry_after_seconds: float | None = None,
    ) -> None:
        record = self._record(key_id)
        now = self._now()
        record.failure_count += 1
        record.last_error = _safe_error(error, status_code)

        if status_code in {401, 403}:
            record.disabled = True
            record.cooldown_until = 0.0
            return

        if status_code == 400:
            # A malformed request is normally not a key-health problem.
            # Keep the key available so provider/schema bugs do not burn the pool.
            record.cooldown_until = 0.0
            return

        if retry_after_seconds is not None:
            cooldown = max(1.0, float(retry_after_seconds))
        elif status_code == 429:
            cooldown = min(900.0, 20.0 * (2 ** min(record.failure_count - 1, 5)))
        elif status_code is not None and 500 <= status_code <= 599:
            cooldown = min(300.0, 5.0 * (2 ** min(record.failure_count - 1, 5)))
        else:
            # Network/transient failures.
            cooldown = min(120.0, 3.0 * (2 ** min(record.failure_count - 1, 5)))

        record.cooldown_until = max(record.cooldown_until, now + cooldown)

    def reenable(self, key_id: str) -> None:
        record = self._record(key_id)
        record.disabled = False
        record.failure_count = 0
        record.cooldown_until = 0.0
        record.last_error = ""

    def summary(self) -> dict[str, Any]:
        now = self._now()
        states = [record.public_state(now) for record in self._records]
        counts = {"ready": 0, "cooldown": 0, "disabled": 0}
        for state in states:
            counts[state["status"]] += 1
        return {
            "total": len(states),
            **counts,
            "max_keys": self.max_keys,
            "keys": states,
        }

    def to_store_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "keys": [
                {
                    "secret": record.secret,
                    "failure_count": record.failure_count,
                    "cooldown_until": record.cooldown_until,
                    "disabled": record.disabled,
                    "last_error": record.last_error,
                }
                for record in self._records
            ],
        }

    @classmethod
    def from_store_dict(
        cls,
        data: dict[str, Any],
        *,
        now: Callable[[], float] = time.time,
        max_keys: int = MAX_GEMINI_KEYS,
    ) -> "GeminiKeyPool":
        if not isinstance(data, dict):
            raise ValueError("Gemini key store harus berupa object.")
        if int(data.get("schema_version", 1)) != SCHEMA_VERSION:
            raise ValueError("Schema Gemini key store tidak didukung.")

        raw_keys = data.get("keys", [])
        if not isinstance(raw_keys, list):
            raise ValueError("Gemini key store keys harus berupa array.")
        if len(raw_keys) > max_keys:
            raise ValueError(f"Gemini key store melebihi batas {max_keys} key.")

        pool = cls([], now=now, max_keys=max_keys)
        seen: set[str] = set()
        for item in raw_keys:
            if not isinstance(item, dict):
                continue
            secret = normalize_api_key(item.get("secret", ""))
            if not secret:
                continue
            key_id = key_fingerprint(secret)
            if key_id in seen:
                continue
            seen.add(key_id)
            pool._records.append(
                GeminiKeyRecord(
                    key_id=key_id,
                    secret=secret,
                    failure_count=max(0, int(item.get("failure_count", 0))),
                    cooldown_until=max(0.0, float(item.get("cooldown_until", 0.0))),
                    disabled=bool(item.get("disabled", False)),
                    last_error=str(item.get("last_error", ""))[:240],
                )
            )
        return pool

    def _record(self, key_id: str) -> GeminiKeyRecord:
        for record in self._records:
            if record.key_id == key_id:
                return record
        raise KeyError(f"Gemini key id tidak ditemukan: {key_id}")


def normalize_api_key(value: Any) -> str:
    key = str(value or "").strip().strip('"').strip("'")
    if not key:
        return ""
    if any(ch.isspace() for ch in key):
        return ""
    if len(key) < 16:
        return ""
    return key


def normalize_api_keys(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_api_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def parse_key_text(text: str) -> list[str]:
    values: list[str] = []
    for token in re.split(r"[\r\n,;]+", str(text)):
        token = token.strip()
        if not token or token.startswith("#"):
            continue
        values.append(token)
    return normalize_api_keys(values)


def key_fingerprint(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"gk-{digest[:12]}"


def default_key_store_path() -> Path:
    override = os.environ.get("MINICUT_GEMINI_KEY_STORE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return base / "MiniCutV42" / "gemini_keys.json"
    return Path.home() / ".minicut-v42" / "gemini_keys.json"


def load_key_store(
    path: str | Path | None = None,
    *,
    now: Callable[[], float] = time.time,
    max_keys: int = MAX_GEMINI_KEYS,
) -> GeminiKeyPool:
    env_keys = parse_key_text(os.environ.get("MINICUT_GEMINI_KEYS", ""))
    source = Path(path).expanduser() if path is not None else default_key_store_path()

    if source.is_file():
        raw = json.loads(source.read_text(encoding="utf-8"))
        pool = GeminiKeyPool.from_store_dict(raw, now=now, max_keys=max_keys)
    else:
        pool = GeminiKeyPool([], now=now, max_keys=max_keys)

    if env_keys:
        pool.add_keys(env_keys)
    return pool


def save_key_store(
    pool: GeminiKeyPool,
    path: str | Path | None = None,
) -> Path:
    target = Path(path).expanduser() if path is not None else default_key_store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(
        json.dumps(pool.to_store_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def import_key_file(
    path: str | Path,
    *,
    existing: GeminiKeyPool | None = None,
) -> GeminiKeyPool:
    source = Path(path).expanduser()
    text = source.read_text(encoding="utf-8-sig", errors="replace")
    keys = parse_key_text(text)
    pool = existing or GeminiKeyPool()
    pool.add_keys(keys)
    return pool


def _safe_error(error: str, status_code: int | None) -> str:
    prefix = "" if status_code is None else f"HTTP {status_code}: "
    text = re.sub(r"\s+", " ", str(error or "")).strip()
    # Never retain anything that resembles a Gemini key in error metadata.
    text = re.sub(r"AIza[A-Za-z0-9_-]{20,}", "[REDACTED]", text)
    return (prefix + text)[:240]
