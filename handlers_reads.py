"""Thoughts · Read tools — what threads exist, and what is inside one.

Split from the write tools on purpose: these two never change anything, and
keeping them apart means the destructive side of this app is a short file a
reviewer can read in one sitting.
"""
from __future__ import annotations

from app import ActionResult, chat, failed, _user_id
from fmt import age, clip
from models import ConversationRecord, MessageRecord
from params import ListParams, ReadParams
import hashlib
import re



def _clean_message_text(text: str) -> str:
    """Strip internal kernel markers like [Actions: ...] and clean whitespace."""
    if not isinstance(text, str) or not text:
        return ""
    s = text.strip()
    if s.startswith("[Actions:"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:].strip()
    return s


def _row(c: dict, active_id: str) -> dict:
    """One archive record, shaped for a human reading a list."""
    return {
        "id": c.get("id", ""),
        "title": c.get("title") or "",
        "message_count": int(c.get("message_count") or 0),
        # The archive calls it `last_message_preview`; older/other shapes may
        # say `preview`. Accept both rather than silently rendering a blank
        # subtitle — an empty preview also half-kills the search filter below,
        # which matches on title OR preview.
        "preview": clip(c.get("last_message_preview") or c.get("preview") or "", 80),
        "updated": age(c.get("updated_at")),
        "live": c.get("id") == active_id,
        "pinned": bool(c.get("pinned")),
        "archived": bool(c.get("archived")),
    }




_STEP_SUFFIX = re.compile(r"-s[a-f0-9]+$")


def _terminal_conversation_id(run_id: str) -> str:
    """The Thoughts Room id of a terminal run (``marathon-…``).

    The gateway mirrors every terminal run into the room as ``conv_term_<h>``,
    where ``h`` is the first 16 hex of sha256 over the run id without its step
    suffix (gateway ``terminal_mirror``). A caller that still holds the raw run
    id reaches the same thread through ``ctx.conversations`` -- never by reading
    the vault directly: only the gateway knows whose thread it is.
    """
    norm = _STEP_SUFFIX.sub("", run_id.strip())
    return "conv_term_" + hashlib.sha256(norm.encode()).hexdigest()[:16]


@chat.function(
    "list_conversations",
    action_type="read",
    data_model=ConversationRecord,
    description=(
        "List the user's past conversations with Webbee across all surfaces "
        "(web panel, terminal, and connectors) — pinned first then newest, "
        "marking which one is live right now. Use this FIRST whenever the user refers "
        "to something you talked about before, instead of answering from memory."),
)
async def fn_list_conversations(ctx, params: ListParams) -> ActionResult:
    """The inventory of the caller's own threads (terminal runs included, as the gateway mirrors them)."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    try:
        data = await ctx.conversations.list(
            limit=params.limit, include_archived=params.include_archived)
    except Exception as e:
        return failed("list conversations", e)

    active_id = (data or {}).get("active_id") or ""
    rows = [_row(c, active_id) for c in (data or {}).get("conversations", [])]

    # Filtering is done here
    q = params.query.strip().lower()
    if q:
        rows = [r for r in rows
                if q in r["title"].lower() or q in r["preview"].lower()]

    if not rows:
        if q:
            return ActionResult.success(
                data=[], summary=f"No conversation matches “{params.query}”.")
        return ActionResult.success(
            data=[],
            summary="No conversations kept yet — this one becomes the first.")

    live = next((r for r in rows if r["live"]), None)
    tail = f" The live one is “{live['title'] or 'Untitled'}”." if live else ""
    match = f" matching “{params.query}”" if q else ""
    return ActionResult.success(
        data=rows,
        summary=f"{len(rows)} conversation(s){match}.{tail}",
    )


@chat.function(
    "read_conversation",
    action_type="read",
    data_model=MessageRecord,
    description=(
        "Read what was actually said in one conversation — its messages, oldest "
        "first, with who said what and when. Pass a thread id from "
        "list_conversations, or leave it empty to read the live conversation."),
)
async def fn_read_conversation(ctx, params: ReadParams) -> ActionResult:
    """One thread's messages, terminal runs included -- always through the gateway."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    cid = params.conversation_id.strip()

    if cid.startswith("marathon-"):
        cid = _terminal_conversation_id(cid)

    try:
        if not cid:
            listing = await ctx.conversations.list(limit=1)
            cid = (listing or {}).get("active_id") or ""
            if not cid:
                return ActionResult.success(
                    data=[], summary="There is no live conversation yet.")

        data = await ctx.conversations.messages(cid, limit=params.limit)
    except Exception as e:
        return failed("read the conversation", e)

    meta = (data or {}).get("conversation") or {}
    msgs = []
    _last_t, _last_r = None, None
    for m in (data or {}).get("messages", []):
        t = _clean_message_text(m.get("content") or "")
        r = m.get("role", "")
        if not t:
            continue
        if t == _last_t and r == _last_r:
            continue
        _last_t, _last_r = t, r
        msgs.append({
            "role": r,
            "text": clip(t, 400),
            "surface": m.get("surface") or "",
            "when": age(m.get("ts")),
        })

    title = meta.get("title") or "Untitled"
    if not msgs:
        return ActionResult.success(
            data=[], summary=f"“{title}” has no messages yet.")

    return ActionResult.success(
        data=msgs,
        summary=f"{len(msgs)} message(s) from “{title}”.",
    )
