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


@chat.function(
    "list_conversations",
    action_type="read",
    data_model=ConversationRecord,
    description=(
        "List the user's past conversations with Webbee — every thread from every "
        "surface (panel, Telegram, terminal), pinned first then newest, marking "
        "which one is live right now. Use this FIRST whenever the user refers to "
        "something you talked about before, instead of answering from memory."),
)
async def fn_list_conversations(ctx, params: ListParams) -> ActionResult:
    """The inventory of the caller's own threads."""
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

    # Filtering is done here rather than asking the gateway for it: the API
    # has no search parameter, and inventing one there for a convenience the
    # caller can express locally would be a heavier change than it earns.
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
        "first, with which surface each was said on. Pass a thread id from "
        "list_conversations, or leave it empty to read the live conversation."),
)
async def fn_read_conversation(ctx, params: ReadParams) -> ActionResult:
    """One thread's messages."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    cid = params.conversation_id.strip()
    try:
        # No id given: resolve the live thread rather than refusing. "What were
        # we just saying" is the most natural way to ask, and it should work.
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
    msgs = [
        {
            "role": m.get("role", ""),
            "text": clip(m.get("content") or "", 400),
            "surface": m.get("surface") or "",
            "when": age(m.get("ts")),
        }
        for m in (data or {}).get("messages", [])
    ]

    title = meta.get("title") or "Untitled"
    if not msgs:
        return ActionResult.success(
            data=[], summary=f"“{title}” has no messages yet.")

    return ActionResult.success(
        data=msgs,
        summary=f"{len(msgs)} message(s) from “{title}”.",
    )
