"""Thoughts · Turning stored values into things a person reads.

Timestamps come back from the archive as epoch seconds. Nobody scanning a
list of conversations wants 1787250954 — they want "2h ago". And the ISO
string is no better on a phone.

Deliberately coarse: below a minute everything is "just now", above a week
it is a date. Precision that nobody acts on is noise.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone


def age(ts: float | int | str | None) -> str:
    """Human-scale age of an epoch timestamp: 'just now', '4m', '2h', '3d'."""
    if not ts:
        return ""
    try:
        t = float(ts)
    except (TypeError, ValueError):
        return str(ts)[:19]

    delta = time.time() - t
    if delta < 0:
        return "just now"          # clock skew, not a reason to print nonsense
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 7 * 86400:
        return f"{int(delta // 86400)}d ago"
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%d %b")


def clip(text: str, n: int = 90) -> str:
    """One-line preview: collapse whitespace, then cut on a word boundary."""
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return f"{cut or s[:n]}…"
