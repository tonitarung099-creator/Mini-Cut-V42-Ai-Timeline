from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .ai_plan import TimelinePlanManager
from .bridge_discovery import remove_discovery, write_discovery
from .timeline_tools import TimelineToolRegistry

MAX_BODY_BYTES = 1024 * 1024


class BridgeRouter:
    """Pure request router. Call it only from the Qt/UI thread in production."""

    def __init__(
        self,
        registry: TimelineToolRegistry,
        *,
        state_provider: Callable[[], dict[str, Any]] | None = None,
        seek_handler: Callable[[int], dict[str, Any]] | None = None,
        allowed_sources_provider: Callable[[], set[str]] | None = None,
        mutation_callback: Callable[[], None] | None = None,
        plan_manager: TimelinePlanManager | None = None,
        plan_callback: Callable[[], None] | None = None,
    ):
        self.registry = registry
        self.state_provider = state_provider or (lambda: {})
        self.seek_handler = seek_handler
        self.allowed_sources_provider = allowed_sources_provider or (lambda: set())
        self.mutation_callback = mutation_callback
        self.plan_manager = plan_manager
        self.plan_callback = plan_callback

    def state(self) -> dict[str, Any]:
        state = self.registry.state()
        extra = dict(self.state_provider() or {})
        state.update(extra)
        state["bridge_tools"] = [
            *self.registry.tool_names,
            "batch",
            "seek",
        ]
        if self.plan_manager is not None:
            state["bridge_tools"].extend(
                ["propose_plan", "get_pending_plan", "cancel_plan"]
            )
            state["pending_plan"] = (
                None
                if self.plan_manager.pending is None
                else self.plan_manager.pending.to_dict()
            )
        return state

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        tool = str(payload.get("tool", ""))
        args = dict(payload.get("args") or {})

        if tool == "seek":
            if self.seek_handler is None:
                return self._error("seek", "unsupported", "Seek belum tersedia.")
            try:
                milliseconds = int(args["time_ms"])
                if milliseconds < 0:
                    raise ValueError("time_ms tidak boleh negatif.")
                result = self.seek_handler(milliseconds)
            except (KeyError, TypeError, ValueError) as exc:
                return self._error("seek", "validation_error", str(exc))
            return {
                "ok": True,
                "tool": "seek",
                "revision": self.registry.revision,
                "result": result,
            }

        if tool == "get_state":
            return {
                "ok": True,
                "tool": "get_state",
                "revision": self.registry.revision,
                "result": self.state(),
            }

        if tool in {"propose_plan", "get_pending_plan", "cancel_plan"}:
            if self.plan_manager is None:
                return self._error(tool, "unsupported", "AI plan manager belum tersedia.")

            if tool == "get_pending_plan":
                return self.plan_manager.get_pending()

            if tool == "cancel_plan":
                result = self.plan_manager.cancel()
                if result.get("ok"):
                    self._notify_plan()
                return result

            actions = args.get("actions", [])
            if not isinstance(actions, list):
                return self._error(
                    tool, "validation_error", "actions plan harus berupa array."
                )
            for action in actions:
                if not isinstance(action, dict):
                    return self._error(
                        tool, "validation_error", "Setiap action plan harus berupa object."
                    )
                action_tool = str(action.get("tool", ""))
                action_args = dict(action.get("args") or {})
                source_error = self._validate_insert_source(action_tool, action_args)
                if source_error is not None:
                    source_error["tool"] = tool
                    return source_error

            result = self.plan_manager.propose(args)
            if result.get("ok"):
                self._notify_plan()
            return result

        source_error = self._validate_insert_source(tool, args)
        if source_error is not None:
            return source_error

        result = self.registry.execute(tool, args)
        if result.get("ok") and tool not in {"get_state"}:
            self._notify_mutation()
        return result

    def batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        actions = payload.get("actions")
        if not isinstance(actions, list):
            return self._error("batch", "validation_error", "actions harus berupa array.")

        for action in actions:
            if not isinstance(action, dict):
                return self._error("batch", "validation_error", "Setiap action harus berupa object.")
            tool = str(action.get("tool", ""))
            args = dict(action.get("args") or {})
            source_error = self._validate_insert_source(tool, args)
            if source_error is not None:
                source_error["tool"] = "batch"
                return source_error

        expected = payload.get("expected_revision")
        result = self.registry.execute_batch(actions, expected_revision=expected)
        if result.get("ok"):
            self._notify_mutation()
        return result

    def _validate_insert_source(
        self, tool: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        if tool != "insert_clip":
            return None
        source = str(args.get("source", ""))
        allowed = {str(item) for item in self.allowed_sources_provider()}
        if not source or source not in allowed:
            return self._error(
                tool,
                "source_not_allowed",
                "AI hanya boleh memasukkan media yang sudah di-import ke proyek.",
            )
        return None

    def _notify_mutation(self) -> None:
        if self.mutation_callback is not None:
            self.mutation_callback()

    def _notify_plan(self) -> None:
        if self.plan_callback is not None:
            self.plan_callback()

    def _error(self, tool: str, code: str, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "tool": tool,
            "revision": self.registry.revision,
            "error": {"code": code, "message": message},
        }


@dataclass
class _PendingRequest:
    method: str
    path: str
    payload: dict[str, Any]
    event: threading.Event = field(default_factory=threading.Event)
    status: int = 500
    response: dict[str, Any] = field(
        default_factory=lambda: {
            "ok": False,
            "error": {"code": "not_processed", "message": "Request belum diproses."},
        }
    )


class QtBridgeDispatcher(QObject):
    """Moves HTTP-thread work onto the QObject's owning Qt thread."""

    requestReceived = Signal(object)

    def __init__(self, router: BridgeRouter, parent: QObject | None = None):
        super().__init__(parent)
        self.router = router
        self.requestReceived.connect(
            self._handle_request,
            Qt.ConnectionType.QueuedConnection,
        )

    def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, Any]]:
        pending = _PendingRequest(method, path, dict(payload or {}))
        self.requestReceived.emit(pending)
        if not pending.event.wait(timeout):
            return 504, {
                "ok": False,
                "error": {
                    "code": "ui_timeout",
                    "message": "Qt UI tidak merespons bridge tepat waktu.",
                },
            }
        return pending.status, pending.response

    @Slot(object)
    def _handle_request(self, pending: _PendingRequest) -> None:
        try:
            if pending.method == "GET" and pending.path == "/state":
                pending.status = 200
                pending.response = {
                    "ok": True,
                    "result": self.router.state(),
                }
            elif pending.method == "POST" and pending.path == "/execute":
                pending.status = 200
                pending.response = self.router.execute(pending.payload)
            elif pending.method == "POST" and pending.path == "/batch":
                pending.status = 200
                pending.response = self.router.batch(pending.payload)
            else:
                pending.status = 404
                pending.response = {
                    "ok": False,
                    "error": {"code": "not_found", "message": "Endpoint tidak ditemukan."},
                }
        except Exception as exc:  # defensive boundary: never kill bridge thread
            pending.status = 500
            pending.response = {
                "ok": False,
                "error": {"code": "internal_error", "message": str(exc)},
            }
        finally:
            pending.event.set()


class LocalTimelineBridge:
    """Token-authenticated localhost HTTP bridge for MCP/AI clients."""

    def __init__(
        self,
        dispatcher: QtBridgeDispatcher,
        *,
        host: str = "127.0.0.1",
        preferred_port: int = 8765,
    ):
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Bridge hanya boleh bind ke localhost.")
        self.dispatcher = dispatcher
        self.host = "127.0.0.1"
        self.preferred_port = int(preferred_port)
        self.token = secrets.token_urlsafe(32)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.url = ""

    @property
    def running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def start(self) -> str:
        if self.running:
            return self.url

        dispatcher = self.dispatcher
        token = self.token

        class Handler(BaseHTTPRequestHandler):
            server_version = "MiniCutBridge/1"

            def log_message(self, format: str, *args) -> None:
                return

            def _authorized(self) -> bool:
                supplied = self.headers.get("X-MiniCut-Token", "")
                if not supplied:
                    auth = self.headers.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        supplied = auth[7:]
                return secrets.compare_digest(supplied, token)

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _reject_auth(self) -> None:
                self._send(
                    401,
                    {
                        "ok": False,
                        "error": {
                            "code": "unauthorized",
                            "message": "Bridge token tidak valid.",
                        },
                    },
                )

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_BODY_BYTES:
                    raise ValueError("Body request terlalu besar.")
                raw = self.rfile.read(length)
                if not raw:
                    return {}
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Body JSON harus berupa object.")
                return payload

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send(200, {"ok": True, "service": "MiniCut Timeline Bridge"})
                    return
                if not self._authorized():
                    self._reject_auth()
                    return
                status, response = dispatcher.call("GET", self.path)
                self._send(status, response)

            def do_POST(self) -> None:
                if not self._authorized():
                    self._reject_auth()
                    return
                try:
                    payload = self._read_json()
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send(
                        400,
                        {
                            "ok": False,
                            "error": {"code": "invalid_json", "message": str(exc)},
                        },
                    )
                    return
                status, response = dispatcher.call("POST", self.path, payload)
                self._send(status, response)

        try:
            server = ThreadingHTTPServer((self.host, self.preferred_port), Handler)
        except OSError:
            server = ThreadingHTTPServer((self.host, 0), Handler)

        server.daemon_threads = True
        self.server = server
        port = int(server.server_address[1])
        self.url = f"http://127.0.0.1:{port}"
        write_discovery(url=self.url, token=self.token, pid=os.getpid())

        self.thread = threading.Thread(
            target=server.serve_forever,
            name="MiniCutTimelineBridge",
            daemon=True,
        )
        self.thread.start()
        return self.url

    def stop(self) -> None:
        server, thread = self.server, self.thread
        self.server = None
        self.thread = None

        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        remove_discovery(token=self.token)
