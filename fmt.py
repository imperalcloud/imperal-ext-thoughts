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


def _epoch(ts: float | int | str) -> float | None:
    """Epoch seconds from either a number or an ISO-8601 string.

    The archive stores ISO-8601 with a trailing ``Z`` (see fs_backend._now),
    while other callers pass epoch seconds. Accepting only one of those meant
    every archive timestamp fell through to a raw ``2026-08-24T13:16:49`` in
    the UI — the exact string this module exists to avoid.
    """
    try:
        return float(ts)
    except (TypeError, ValueError):
        pass
    text = str(ts).strip()
    if not text:
        return None
    try:
        # fromisoformat handles "+00:00" but not the "Z" spelling before 3.11.
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # The archive is UTC throughout. A bare timestamp read as LOCAL time
        # is wrong by the machine's offset — three hours here, which turned
        # "26m ago" into "3h ago". Absent an offset, assume the zone the
        # storage actually uses.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def age(ts: float | int | str | None) -> str:
    """Human-scale age of a timestamp: 'just now', '4m', '2h', '3d'.

    Accepts epoch seconds or an ISO-8601 string.
    """
    if not ts:
        return ""
    t = _epoch(ts)
    if t is None:
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
