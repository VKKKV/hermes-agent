"""``hermes monitoring`` subcommand parser (local gateway health diagnostics)."""

from __future__ import annotations

from typing import Callable


def build_monitoring_parser(subparsers, *, cmd_monitoring: Callable) -> None:
    """Attach the ``monitoring`` subcommand (with actions) to ``subparsers``."""
    p = subparsers.add_parser(
        "monitoring", help="Inspect local gateway health",
        description="Inspect local gateway health. This fork ships no remote metrics or OTLP exporter.")
    sub = p.add_subparsers(dest="monitoring_action")

    sub.add_parser("status", help="Show local gateway health; no remote export")

    p.set_defaults(func=cmd_monitoring)
