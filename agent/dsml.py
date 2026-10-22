"""Recognize unexecuted DSML, never parse it into executable tool calls.

Only Markdown code is a protocol example. Outside code, even an inline or cut-off
opener (or an orphan closer with unknown preceding arguments) makes the response
unsafe to deliver/replay. Drop that whole response, not just the protocol tags.
Callers remove private reasoning *before* classification, without stripping DSML.
"""
from __future__ import annotations

import re

_PIPE = r"[|\uFF5C]{1,2}[ \t]*"
_TOKEN = re.compile(
    rf"</?{_PIPE}DSML{_PIPE}(?:calls|tool_calls|function_calls|invoke|parameter)(?=[\s>]|\Z)",
    re.IGNORECASE,
)
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})([^\r\n]*)")
_TICKS = re.compile(r"`+")


def _inline_code_spans(text: str, start: int, end: int):
    """Pair equal-length backtick runs in linear time, including unmatched runs."""
    runs = list(_TICKS.finditer(text, start, end))
    next_run: dict[int, int] = {}
    partners: list[int | None] = [None] * len(runs)
    for index in range(len(runs) - 1, -1, -1):
        size = runs[index].end() - runs[index].start()
        partners[index] = next_run.get(size)
        next_run[size] = index
    index = 0
    while index < len(runs):
        partner = partners[index]
        if partner is None:
            index += 1
        else:
            yield runs[index].start(), runs[partner].end()
            index = partner + 1


def _code_spans(text: str):
    """Ordered Markdown code spans; unclosed fences remain literal code examples."""
    fence_start = None
    fence_char = ""
    fence_size = 0
    prose_start = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line)
        if match and fence_start is None:
            marker, info = match.groups()
            if marker[0] == "`" and "`" in info:
                offset += len(line)
                continue
            yield from _inline_code_spans(text, prose_start, offset)
            fence_start, fence_char, fence_size = offset, marker[0], len(marker)
        elif match and fence_start is not None:
            marker, info = match.groups()
            if marker[0] == fence_char and len(marker) >= fence_size and not info.strip():
                yield fence_start, offset + len(line)
                fence_start = None
                prose_start = offset + len(line)
        offset += len(line)
    if fence_start is not None:
        yield fence_start, len(text)
    else:
        yield from _inline_code_spans(text, prose_start, len(text))


def has_unexecuted_dsml(text: str) -> bool:
    """Whether visible text contains protocol outside Markdown code (O(n))."""
    if not text or not _TOKEN.search(text):
        return False
    spans = iter(_code_spans(text))
    code_start, code_end = next(spans, (len(text), len(text)))
    for token in _TOKEN.finditer(text):
        while code_end <= token.start():
            code_start, code_end = next(spans, (len(text), len(text)))
        if not code_start <= token.start() < code_end:
            return True
    return False


def sanitize_dsml(text: str) -> str:
    """Never salvage narration or unknown argument tails from an unexecuted attempt."""
    return "" if has_unexecuted_dsml(text) else text
