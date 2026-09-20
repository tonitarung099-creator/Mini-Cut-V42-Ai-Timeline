"""MCP companion for MiniCut V42 AI Timeline.

The desktop app owns the timeline. This stdio process discovers the desktop's
localhost bridge and exposes only validated timeline operations.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from mcp.server import MCPServer

from minicut_agent.bridge_discovery import read_discovery

mcp = MCPServer("MiniCut V42 Timeline")


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 25.0,
) -> dict[str, Any]:
    config = read_discovery()
    url = str(config["url"]).rstrip("/") + path
    token = str(config["token"])
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-MiniCut-Token": token,
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _execute(
    tool: str,
    args: dict[str, Any] | None = None,
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    final_args = dict(args or {})
    if expected_revision is not None:
        final_args["expected_revision"] = expected_revision
    return _request("POST", "/execute", {"tool": tool, "args": final_args})


@mcp.tool()
def get_state() -> dict[str, Any]:
    """Read timeline tracks, clips, playhead, revision and available tools."""
    return _request("GET", "/state", timeout=5.0)


@mcp.tool()
def seek(time_ms: int) -> dict[str, Any]:
    """Move the visible MiniCut timeline playhead without changing revision."""
    return _execute("seek", {"time_ms": time_ms})


@mcp.tool()
def insert_clip(
    source: str,
    track_id: str,
    source_in_ms: int,
    source_out_ms: int,
    timeline_start_ms: int,
    speed: float = 1.0,
    muted: bool = False,
    group_id: str = "",
    label: str = "",
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Insert an already-imported media source onto a timeline track."""
    return _execute(
        "insert_clip",
        {
            "source": source,
            "track_id": track_id,
            "source_in_ms": source_in_ms,
            "source_out_ms": source_out_ms,
            "timeline_start_ms": timeline_start_ms,
            "speed": speed,
            "muted": muted,
            "group_id": group_id or None,
            "label": label,
        },
        expected_revision=expected_revision,
    )


@mcp.tool()
def move_clip(
    clip_id: str,
    timeline_start_ms: int,
    track_id: str = "",
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Move a clip (and its linked A/V partners) on the timeline."""
    args: dict[str, Any] = {
        "clip_id": clip_id,
        "timeline_start_ms": timeline_start_ms,
    }
    if track_id:
        args["track_id"] = track_id
    return _execute("move_clip", args, expected_revision=expected_revision)


@mcp.tool()
def trim_clip(
    clip_id: str,
    edge: str,
    timeline_ms: int,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Trim the left or right edge of a clip and linked partners."""
    return _execute(
        "trim_clip",
        {"clip_id": clip_id, "edge": edge, "timeline_ms": timeline_ms},
        expected_revision=expected_revision,
    )


@mcp.tool()
def split_clip(
    clip_id: str,
    timeline_ms: int,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Split a clip and linked partners at a timeline position."""
    return _execute(
        "split_clip",
        {"clip_id": clip_id, "timeline_ms": timeline_ms},
        expected_revision=expected_revision,
    )


@mcp.tool()
def delete_clip(
    clip_id: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Delete a clip and linked partners."""
    return _execute(
        "delete_clip",
        {"clip_id": clip_id},
        expected_revision=expected_revision,
    )


@mcp.tool()
def set_speed(
    clip_id: str,
    speed: float,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Set playback speed for a clip and linked partners."""
    return _execute(
        "set_speed",
        {"clip_id": clip_id, "speed": speed},
        expected_revision=expected_revision,
    )


@mcp.tool()
def set_clip_mute(
    clip_id: str,
    muted: bool,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Mute or unmute a timeline clip."""
    return _execute(
        "set_clip_mute",
        {"clip_id": clip_id, "muted": muted},
        expected_revision=expected_revision,
    )


@mcp.tool()
def set_clip_lock(
    clip_id: str,
    locked: bool,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Lock or unlock a timeline clip."""
    return _execute(
        "set_clip_lock",
        {"clip_id": clip_id, "locked": locked},
        expected_revision=expected_revision,
    )


@mcp.tool()
def set_track_lock(
    track_id: str,
    locked: bool,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Lock or unlock a timeline track."""
    return _execute(
        "set_track_lock",
        {"track_id": track_id, "locked": locked},
        expected_revision=expected_revision,
    )


@mcp.tool()
def set_track_visibility(
    track_id: str,
    visible: bool,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Show or hide a video/subtitle timeline track."""
    return _execute(
        "set_track_visibility",
        {"track_id": track_id, "visible": visible},
        expected_revision=expected_revision,
    )


@mcp.tool()
def set_track_mute(
    track_id: str,
    muted: bool,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Mute or unmute an audio timeline track."""
    return _execute(
        "set_track_mute",
        {"track_id": track_id, "muted": muted},
        expected_revision=expected_revision,
    )


@mcp.tool()
def apply_batch(
    actions: list[dict[str, Any]],
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Atomically apply multiple validated timeline mutations."""
    payload: dict[str, Any] = {"actions": actions}
    if expected_revision is not None:
        payload["expected_revision"] = expected_revision
    return _request("POST", "/batch", payload)


@mcp.tool()
def undo(expected_revision: int | None = None) -> dict[str, Any]:
    """Undo the latest timeline transaction."""
    return _execute("undo", expected_revision=expected_revision)


@mcp.tool()
def redo(expected_revision: int | None = None) -> dict[str, Any]:
    """Redo the latest timeline transaction."""
    return _execute("redo", expected_revision=expected_revision)


if __name__ == "__main__":
    mcp.run()
