#!/usr/bin/env python3
"""Stable service and CLI entry point for Visual Guides."""

from visual_guides_cli import main, read_token, send_via_server
from visual_guides_server import AcIrHandler, AcIrServer, AppConfig, Delivery, delivery_response

__all__ = [
    "AcIrHandler", "AcIrServer", "AppConfig", "Delivery", "delivery_response",
    "main", "read_token", "send_via_server",
]


if __name__ == "__main__":
    raise SystemExit(main())
