"""Read a caller-owned error classification without invoking attribute hooks."""

import inspect


def tagged_failure_class(error: object) -> str | None:
    tagged = inspect.getattr_static(error, "failure_class", None)
    return tagged if isinstance(tagged, str) and tagged else None
