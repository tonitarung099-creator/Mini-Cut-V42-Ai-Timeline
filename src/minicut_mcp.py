"""MCP stdio bridge for MiniCut Studio + AI Agent.

The desktop app must be running with its local bridge enabled. This process is
launched by an MCP host and proxies standardized MCP tools to 127.0.0.1:8765.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any
from mcp.server import MCPServer

BASE_URL = os.environ.get("MINICUT_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
mcp = MCPServer("MiniCut Studio")


def _execute(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        BASE_URL + "/execute",
        data=json.dumps({"tool": tool, "args": args or {}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


@mcp.tool()
def get_state() -> dict[str, Any]:
    """Read the current MiniCut project, playhead, cuts, duration, and readiness."""
    with urllib.request.urlopen(BASE_URL + "/state", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


@mcp.tool()
def seek(time_ms: str | int) -> dict[str, Any]:
    """Move the MiniCut playhead to a timecode or millisecond position."""
    return _execute("seek", {"time_ms": time_ms})


@mcp.tool()
def add_cut(time_ms: str | int) -> dict[str, Any]:
    """Add a cut at a requested time; MiniCut snaps it to the nearest safe keyframe."""
    return _execute("add_cut", {"time_ms": time_ms})


@mcp.tool()
def remove_cut(index: int) -> dict[str, Any]:
    """Remove one cut by its zero-based cut index."""
    return _execute("remove_cut", {"index": index})


@mcp.tool()
def clear_cuts() -> dict[str, Any]:
    """Remove every cut in the current MiniCut project."""
    return _execute("clear_cuts", {})


@mcp.tool()
def divide_equal(parts: int) -> dict[str, Any]:
    """Divide the whole movie into approximately equal parts using safe keyframes."""
    return _execute("divide_equal", {"parts": parts})


@mcp.tool()
def divide_interval(interval_ms: str | int) -> dict[str, Any]:
    """Create cuts at a repeated interval, e.g. 600000 or '00:10:00'."""
    return _execute("divide_interval", {"interval_ms": interval_ms})


@mcp.tool()
def undo() -> dict[str, Any]:
    """Undo the most recent MiniCut agent timeline change."""
    return _execute("undo", {})


@mcp.tool()
def save_project(path: str = "") -> dict[str, Any]:
    """Save the project JSON. If path is empty the app may show its normal save dialog."""
    return _execute("save_project", {"path": path} if path else {})


@mcp.tool()
def export_all(output_dir: str) -> dict[str, Any]:
    """Export all parts to an explicit output folder using FFmpeg stream copy."""
    return _execute("export_all", {"output_dir": output_dir})


if __name__ == "__main__":
    mcp.run()
