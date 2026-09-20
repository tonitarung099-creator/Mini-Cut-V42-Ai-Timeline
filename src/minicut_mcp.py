"""MCP companion for MiniCut V42 AI Timeline.

The desktop app owns the timeline. External AI is review-first: it may inspect
state, seek for inspection, and propose/cancel plans. Timeline mutation is
applied by the user from the desktop UI after review.
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


def _execute(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return _request("POST", "/execute", {"tool": tool, "args": dict(args or {})})


@mcp.tool()
def get_state() -> dict[str, Any]:
    """Read timeline, revision, playhead, workflow state and pending AI plan."""
    return _request("GET", "/state", timeout=5.0)


@mcp.tool()
def seek(time_ms: int) -> dict[str, Any]:
    """Move the visible playhead for inspection without editing the timeline."""
    return _execute("seek", {"time_ms": time_ms})


@mcp.tool()
def propose_plan(
    title: str,
    actions: list[dict[str, Any]],
    expected_revision: int,
    explanation: str = "",
    block_id: str = "",
    unit_id: str = "",
) -> dict[str, Any]:
    """Submit a review-only edit plan. This never mutates the timeline."""
    return _execute(
        "propose_plan",
        {
            "title": title,
            "actions": actions,
            "expected_revision": expected_revision,
            "explanation": explanation,
            "block_id": block_id or None,
            "unit_id": unit_id or None,
            "created_by": "mcp",
        },
    )


@mcp.tool()
def get_pending_plan() -> dict[str, Any]:
    """Read the AI plan currently waiting for user review."""
    return _execute("get_pending_plan", {})


@mcp.tool()
def cancel_plan() -> dict[str, Any]:
    """Cancel the pending AI plan without changing the timeline."""
    return _execute("cancel_plan", {})


if __name__ == "__main__":
    mcp.run()
