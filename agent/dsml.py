"""Recognize unexecuted DSML, never parse it into executable tool calls.

Only Markdown code is a protocol example. Outside code, even an inline or cut-off
opener (or an orphan closer with unknown preceding arguments) makes the response
unsafe to deliver/replay. Drop that whole response, not just the protocol tags.
Callers remove private reasoning *before* classification, without stripping DSML.
"""
from __future__ import annotations

from functools import lru_cache
import re

_PIPE = r"[|\uFF5C]{1,2}[ \t]*"
_TOKEN = re.compile(
    rf"</?{_PIPE}DSML{_PIPE}(?:calls|tool_calls|function_calls|invoke|parameter)(?=[\s>]|\Z)",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _markdown_parser():
    # Already shipped by Rich. Use its block/container and backtick rules rather
    # than pairing ticks across unrelated paragraphs or guessing list indentation.
    from markdown_it import MarkdownIt

    parser = MarkdownIt('commonmark').disable('reference')
    # All non-code bytes must remain searchable, including link destinations,
    # raw HTML and escaped punctuation. Only actual backticks exempt inline text.
    parser.inline.ruler.enableOnly(['text', 'newline', 'backticks', 'escape'])
    return parser


def has_unexecuted_dsml(text: str) -> bool:
    """Whether visible text contains protocol outside actual Markdown code."""
    if not text or not _TOKEN.search(text):
        return False
    seen = 0
    for block in _markdown_parser().parse(text):
        seen += len(_TOKEN.findall(block.content))
        if block.type in ('fence', 'code_block'):
            # Fence info is not code content (and a backtick in backtick-fence
            # info invalidates the opener, which the parser already handles).
            if _TOKEN.search(block.info):
                return True
        elif block.type == 'inline':
            if any(_TOKEN.search(child.content) for child in block.children or ()
                   if child.type != 'code_inline'):
                return True
        elif _TOKEN.search(block.content):
            return True
    # markdown-it intentionally drops blocks past maxNesting. Unseen protocol
    # must fail closed, not inherit a code exemption the parser never proved.
    return seen != len(_TOKEN.findall(text))


def sanitize_dsml(text: str, *, context: str | None = None) -> str:
    """Never salvage narration or unknown argument tails from an unexecuted attempt."""
    if context is None:
        return "" if has_unexecuted_dsml(text) else text
    from agent.agent_runtime_helpers import strip_private_reasoning

    # Classify a continuation in context, but return only its scrubbed fragment.
    return "" if has_unexecuted_dsml(strip_private_reasoning(context)) else text


def filter_final_sources(agent, message, promoted, parts):
    """Filter only eligible sources; preserve precedence and joined code context."""
    from agent.agent_runtime_helpers import strip_private_reasoning
    from agent.conversation_loop import _join_truncated_parts

    def joined(candidate):
        return strip_private_reasoning(_join_truncated_parts([*parts, (candidate, False)]))

    candidate = strip_private_reasoning(promoted or message.content or "")
    content = joined(candidate) if candidate.strip() else ""
    leaked = has_unexecuted_dsml(content)
    if leaked:
        # Never salvage arguments or stale caches from a real current attempt.
        message.content = ""
        promoted, content = None, ""
        agent._current_streamed_assistant_text = ""
        agent._last_content_with_tools = None
        agent._last_content_tools_all_housekeeping = False
    elif not parts and not agent._has_content_after_think_block(candidate):
        stream = getattr(agent, "_current_streamed_assistant_text", "") or ""
        if has_unexecuted_dsml(joined(stream)):
            agent._current_streamed_assistant_text = ""
            stream = ""
        if (not agent._has_content_after_think_block(stream)
                and getattr(agent, "_last_content_tools_all_housekeeping", False)
                and has_unexecuted_dsml(joined(getattr(agent, "_last_content_with_tools", "") or ""))):
            agent._last_content_with_tools = None
            agent._last_content_tools_all_housekeeping = False
    return promoted, content, leaked
