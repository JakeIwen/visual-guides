#!/usr/bin/env python3
"""HTTP runtime for visual guides and the guarded A/C infrared API."""

from __future__ import annotations

import hmac
import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote, urlsplit

from ac_ir import Command, Transport


DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 8791
DEFAULT_TOKEN_FILE_ENV = "AC_IR_TOKEN_FILE"
MAX_BODY_BYTES = 256
MIN_TRANSMIT_INTERVAL_SECONDS = 1.0
SOCKET_TIMEOUT_SECONDS = 5.0
STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".gif": "image/gif",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".webp": "image/webp",
}


class Delivery(str, Enum):
    DRY_RUN = "dry_run"
    TRANSMITTED = "transmitted"


@dataclass(frozen=True)
class AppConfig:
    static_root: Path
    commands: Mapping[str, Command]
    hardware_enabled: bool = False
    token: str | None = None
    transport: Transport | None = None
    min_transmit_interval: float = MIN_TRANSMIT_INTERVAL_SECONDS
    log_requests: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "static_root", self.static_root.resolve())
        if self.hardware_enabled and (not self.token or self.transport is None):
            raise ValueError("hardware mode requires a token and transport")
        if self.min_transmit_interval < 0:
            raise ValueError("minimum transmit interval cannot be negative")


class AcIrServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: AppConfig,
                 handler_class: type[AcIrHandler] | None = None):
        self.config = config
        self.transmit_lock = threading.Lock()
        self.last_transmit_at = float("-inf")
        super().__init__(address, handler_class or AcIrHandler)


class AcIrHandler(BaseHTTPRequestHandler):
    server: AcIrServer
    protocol_version = "HTTP/1.1"
    server_version = "VisualGuides/1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(SOCKET_TIMEOUT_SECONDS)

    @property
    def app(self) -> AcIrServer:
        return self.server

    def log_message(self, format_string: str, *args: object) -> None:
        if self.app.config.log_requests:
            super().log_message(format_string, *args)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "visual-guides"})
        elif path == "/api/ac/status":
            self._json(
                HTTPStatus.OK,
                {
                    "hardware_enabled": self.app.config.hardware_enabled,
                    "ac_state": "unknown",
                    "state_note": "Infrared sends are unconfirmed; no A/C state is inferred.",
                },
            )
        elif path == "/api/ac/commands":
            self._json(
                HTTPStatus.OK,
                {"commands": [command.preview() for command in self.app.config.commands.values()]},
            )
        elif path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "API endpoint not found")
        else:
            self._serve_static(path, send_body=True)

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "HEAD is not supported for API endpoints")
            return
        self._serve_static(path, send_body=False)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        prefix = "/api/ac/commands/"
        if not path.startswith(prefix) or "/" in path[len(prefix) :]:
            self._error(HTTPStatus.NOT_FOUND, "API endpoint not found")
            return
        command = self.app.config.commands.get(unquote(path[len(prefix) :]))
        if command is None:
            self._error(HTTPStatus.NOT_FOUND, "unknown A/C command")
            return
        body = self._read_json_body()
        if body is None:
            return
        if set(body) != {"preview"} or not isinstance(body["preview"], bool):
            self._error(HTTPStatus.BAD_REQUEST, "body must be exactly {\"preview\": boolean}")
            return
        if not self._origin_allowed():
            self._error(HTTPStatus.FORBIDDEN, "cross-origin writes are not allowed")
            return
        if body["preview"]:
            self._json(HTTPStatus.OK, delivery_response(command, Delivery.DRY_RUN))
            return
        self._transmit(command)

    def do_OPTIONS(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "cross-origin requests are not allowed")

    def _transmit(self, command: Command) -> None:
        config = self.app.config
        if not config.hardware_enabled:
            self._error(HTTPStatus.CONFLICT, "hardware transmission is disabled")
            return
        supplied = self.headers.get("Authorization", "")
        supplied_bytes = supplied.encode("latin-1")
        expected_bytes = f"Bearer {config.token}".encode("ascii")
        if not hmac.compare_digest(supplied_bytes, expected_bytes):
            self._error(HTTPStatus.UNAUTHORIZED, "valid bearer token required")
            return
        with self.app.transmit_lock:
            now = time.monotonic()
            if now - self.app.last_transmit_at < config.min_transmit_interval:
                self._error(HTTPStatus.TOO_MANY_REQUESTS, "transmit rate limit exceeded")
                return
            # A timeout or ir-ctl error is ambiguous: transmission may already
            # have begun. Start the cooldown before invoking the transport so
            # a retry cannot immediately duplicate a toggle command.
            self.app.last_transmit_at = now
            try:
                assert config.transport is not None
                config.transport.send(command)
            except Exception:
                self.app.last_transmit_at = time.monotonic()
                self._error(HTTPStatus.BAD_GATEWAY, "IR transmission failed")
                return
            self.app.last_transmit_at = time.monotonic()
        self._json(
            HTTPStatus.ACCEPTED,
            delivery_response(command, Delivery.TRANSMITTED),
        )

    def _read_json_body(self) -> dict[str, object] | None:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "invalid request body length")
            return None
        if self.headers.get_content_type() != "application/json":
            self._discard_body(length)
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")
            return None
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "request body must be valid JSON")
            return None
        if not isinstance(value, dict):
            self._error(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
            return None
        return value

    def _discard_body(self, length: int) -> None:
        if 0 <= length <= MAX_BODY_BYTES:
            self.rfile.read(length)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        parsed = urlsplit(origin)
        host = self.headers.get("Host", "")
        return parsed.scheme in {"http", "https"} and parsed.netloc == host and parsed.path == ""

    def _serve_static(self, requested_path: str, send_body: bool) -> None:
        aliases = {"/": "index.html", "/guides/air-conditioner.html": "guides/air-conditioner.html"}
        relative = aliases.get(requested_path)
        if relative is None:
            decoded = unquote(requested_path).lstrip("/")
            relative = decoded
        candidate = (self.app.config.static_root / relative).resolve()
        try:
            candidate.relative_to(self.app.config.static_root)
        except ValueError:
            self._error(HTTPStatus.NOT_FOUND, "file not found")
            return
        if not candidate.is_file():
            self._error(HTTPStatus.NOT_FOUND, "file not found")
            return
        data = candidate.read_bytes()
        content_type = STATIC_CONTENT_TYPES.get(
            candidate.suffix.lower(), "application/octet-stream"
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self.close_connection = True
        self._json(status, {"ok": False, "error": message})


def delivery_response(command: Command, delivery: Delivery) -> dict[str, object]:
    return {
        "ok": True,
        "command": command.name,
        "delivery": delivery,
        "confirmed": False,
        "waveform": command.preview(),
    }


