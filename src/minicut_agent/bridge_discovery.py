from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def discovery_path() -> Path:
    override = os.environ.get("MINICUT_BRIDGE_INFO_FILE")
    if override:
        return Path(override).expanduser()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MiniCutV42" / "bridge.json"
    return Path.home() / ".minicut_v42" / "bridge.json"


def write_discovery(*, url: str, token: str, pid: int) -> Path:
    path = discovery_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {
                "url": url.rstrip("/"),
                "token": token,
                "pid": int(pid),
                "protocol": 1,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)
    return path


def read_discovery() -> dict[str, Any]:
    url_override = os.environ.get("MINICUT_BRIDGE_URL")
    token_override = os.environ.get("MINICUT_BRIDGE_TOKEN")
    if url_override:
        return {
            "url": url_override.rstrip("/"),
            "token": token_override or "",
            "pid": None,
            "protocol": 1,
        }

    path = discovery_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Bridge discovery harus berupa object JSON.")
    url = str(data.get("url", "")).rstrip("/")
    token = str(data.get("token", ""))
    if not url or not token:
        raise ValueError("Bridge discovery tidak lengkap.")
    return data


def remove_discovery(*, token: str | None = None) -> None:
    path = discovery_path()
    if not path.exists():
        return
    if token is not None:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if current.get("token") != token:
                return
        except (OSError, ValueError, json.JSONDecodeError):
            return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
