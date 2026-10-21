"""Serve visual guides and a guarded Frigidaire A/C infrared API."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import stat
import sys
from http import HTTPStatus
from pathlib import Path

from ac_ir import COMMANDS, DEFAULT_DEVICE, Command, IrCtlTransport
from visual_guides_server import (
    DEFAULT_BIND,
    DEFAULT_PORT,
    DEFAULT_TOKEN_FILE_ENV,
    AcIrServer,
    AppConfig,
    Delivery,
)


def read_token(path: Path) -> str:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("token path must be a regular file")
    if metadata.st_mode & 0o077:
        raise ValueError("token file must not be accessible by group or other users")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 24 or len(token) > 512 or any(character.isspace() for character in token):
        raise ValueError("token file must contain one 24-512 character token")
    try:
        token.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("token file must contain an ASCII token") from error
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default=DEFAULT_BIND)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--static-root", type=Path, default=Path(__file__).parent / "static")
    parser.add_argument("--enable-hardware", action="store_true")
    parser.add_argument("--device", type=Path, default=DEFAULT_DEVICE)
    parser.add_argument("--token-file", type=Path, help=f"private bearer-token file (or set {DEFAULT_TOKEN_FILE_ENV})")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--list-commands", action="store_true")
    actions.add_argument("--preview", metavar="COMMAND")
    actions.add_argument("--send", metavar="COMMAND")
    return parser


def command_or_error(name: str) -> Command:
    try:
        return COMMANDS[name]
    except KeyError as error:
        raise SystemExit(f"unknown command: {name}") from error


def send_via_server(command: Command, port: int, token: str) -> dict[str, object]:
    """Ask the one running service to transmit; never retry an ambiguous send."""
    if not 1 <= port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            "POST", f"/api/ac/commands/{command.name}", body=b'{"preview":false}',
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response_body = response.read()
    except (OSError, TimeoutError) as error:
        raise SystemExit(f"send failed: {error}") from error
    finally:
        connection.close()
    if response.status != HTTPStatus.ACCEPTED:
        try:
            detail = json.loads(response_body).get("error", "request rejected")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            detail = "request rejected"
        raise SystemExit(f"send failed: HTTP {response.status}: {detail}")
    try:
        payload = json.loads(response_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SystemExit("send failed: service returned invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("delivery") != Delivery.TRANSMITTED:
        raise SystemExit("send failed: service returned an invalid response")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_commands:
        for command in COMMANDS.values():
            print(f"{command.name}\t{command.label}")
        return 0
    if args.preview:
        print(json.dumps(command_or_error(args.preview).preview(), indent=2))
        return 0
    if args.send:
        command = command_or_error(args.send)
        if not args.enable_hardware:
            raise SystemExit("--send requires explicit --enable-hardware")
        token_path = args.token_file or os.environ.get(DEFAULT_TOKEN_FILE_ENV)
        if not token_path:
            raise SystemExit(f"--token-file or {DEFAULT_TOKEN_FILE_ENV} must name a private token file")
        print(json.dumps(send_via_server(command, args.port, read_token(Path(token_path)))))
        return 0

    token = None
    transport = None
    if args.enable_hardware:
        token_path = args.token_file or os.environ.get(DEFAULT_TOKEN_FILE_ENV)
        if not token_path:
            raise SystemExit(f"--token-file or {DEFAULT_TOKEN_FILE_ENV} must name a private token file")
        token = read_token(Path(token_path))
        transport = IrCtlTransport(device=args.device)
    server = AcIrServer((args.bind, args.port), AppConfig(
        static_root=args.static_root, commands=COMMANDS, hardware_enabled=args.enable_hardware,
        token=token, transport=transport,
    ))
    print(f"visual guides listening on http://{args.bind}:{server.server_port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
