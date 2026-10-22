"""Local gateway health and redacted in-process diagnostics.

The event bus is retained for local service state and explicit subscribers.
This fork ships no remote exporter and does not persist an upload queue.
"""

from __future__ import annotations

from . import emitter, events

emit = emitter.emit
get_emitter = emitter.get_emitter

__all__ = ["emit", "emitter", "events", "get_emitter"]
