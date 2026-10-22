"""Minimal client User-Agent and local connector outcome diagnostics.

No consent setting enables conversation, turn or tool correlation headers in this fork.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "CallRef",
    "connector_headers",
    "log_connector_outcome",
    "response_request_id",
    "user_agent",
]

REQUEST_ID_HEADER = "x-request-id"

# Host OS family used only in the standard client User-Agent.
_OS_FAMILY = {"darwin": "macos", "linux": "linux", "win32": "windows"}

# The account route answers 404 with this code until the vendor has created the account.
_EXPECTED_MISSES = frozenset({"connection_not_found"})


@dataclass(frozen=True)
class CallRef:
    """Local log correlation only; these ids are never sent in request headers."""

    turn_id: Optional[str] = None
    tool_call_id: Optional[str] = None


def user_agent() -> str:
    from hermes_cli.version_info import get_version_info
    from hermes_platform.host.facts import os_family

    os_name = _OS_FAMILY.get(os_family(), "unknown")
    return f"hermes-agent/{get_version_info().base_version} ({os_name})"


def connector_headers(call: Optional[CallRef] = None) -> dict[str, str]:
    """Standard client User-Agent only; ignore call ids for outbound requests."""
    return {"User-Agent": user_agent()}


def response_request_id(response: object) -> Optional[str]:
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return None
    value = headers.get(REQUEST_ID_HEADER) or headers.get("X-Request-Id")
    return str(value) if value else None


def log_connector_outcome(
    route: str, status: Optional[int], *, code: Optional[str] = None, request_id: Optional[str] = None,
    call: Optional[CallRef] = None,
) -> None:
    """One line per connector HTTP outcome: failures at WARNING, success and expected misses at DEBUG.

    The ``code`` makes a line a failure, not the status: a 200 whose body failed carries one, and a
    304 that refreshed a cached list does not."""
    level = logging.WARNING if code is not None and code not in _EXPECTED_MISSES else logging.DEBUG
    logger.log(
        level, "connector %s %s %s request_id=%s dispatch=%s",
        route, status if status is not None else "transport", code or "-", request_id or "-",
        (call.tool_call_id if call else None) or "-",
    )
