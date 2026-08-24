"""Thoughts · Write tools — walk back into a thread, start one, name one.

None of these destroy anything: switching threads archives the current one
rather than dropping it, and renaming replaces a title the user can change
again. The one tool that really removes something lives in
``handlers_delete.py``, on its own, with its own action_type.
"""
from __future__ import annotations

from app import ActionResult, chat, gw, safe_err, _user_id
from fmt import clip
from models import SwitchedRecord
from params import ContinueParams, NewParams, RenameParams


@chat.function(
    "continue_conversation",
    action_type="write",
    data_model=SwitchedRecord,
    effects=["update:conversation"],
    event="conversation_switched",
    description=(
        "Walk back into an earlier conversation and make it the live one, so the "
        "next thing said continues THAT thread on every surface. The current "
        "conversation is archived first, never lost. Use when the user wants to "
        "pick up something from before — list_conversations first to get the id."),
)
async def fn_continue_conversation(ctx, params: ContinueParams) -> ActionResult:
    """Make an existing thread the live conversation."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    cid = (params.conversation_id or "").strip()
    if not cid:
        return ActionResult.error(
            "Which conversation? Run list_conversations and pass an id.")

    try:
        data, err = await gw("POST", f"/v1/conversations/{cid}/activate", uid)
    except Exception as e:
        return ActionResult.error(f"Could not switch conversation: {safe_err(e)}")
    if err:
        return ActionResult.error(err)

    conv = (data or {}).get("conversation") or {}
    title = conv.get("title") or "(untitled)"
    return ActionResult.success(
        data={
            "conversation_id": cid,
            "title": title,
            "message_count": int(conv.get("message_count") or 0),
            "note": "This is now the live thread on every surface.",
        },
        summary=f"Now continuing “{title}”.",
    )


@chat.function(
    "new_conversation",
    action_type="write",
    data_model=SwitchedRecord,
    effects=["create:conversation"],
    event="conversation_started",
    description=(
        "Start a fresh conversation thread. The current one is archived first and "
        "stays readable. Use when the user wants a clean slate or is clearly "
        "changing subject and asks to start over."),
)
async def fn_new_conversation(ctx, params: NewParams) -> ActionResult:
    """Open a brand-new thread and make it live."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    title = (params.title or "").strip()[:200]
    try:
        data, err = await gw("POST", "/v1/conversations", uid, body={"title": title})
    except Exception as e:
        return ActionResult.error(f"Could not start a conversation: {safe_err(e)}")
    if err:
        return ActionResult.error(err)

    conv = (data or {}).get("conversation") or {}
    shown = conv.get("title") or title or "(it will name itself)"
    return ActionResult.success(
        data={
            "conversation_id": conv.get("id", ""),
            "title": shown,
            "message_count": 0,
            "note": "The previous thread was archived, not lost.",
        },
        summary=f"Fresh thread started — {shown}.",
    )


@chat.function(
    "rename_conversation",
    action_type="write",
    data_model=SwitchedRecord,
    effects=["update:conversation"],
    event="conversation_renamed",
    description=(
        "Give a conversation a name of the user's choosing. A hand-picked title is "
        "kept as-is and never overwritten by the automatic namer afterwards."),
)
async def fn_rename_conversation(ctx, params: RenameParams) -> ActionResult:
    """Set a title the automatic namer will then leave alone."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    cid = (params.conversation_id or "").strip()
    title = (params.title or "").strip()[:200]
    if not cid:
        return ActionResult.error(
            "Which conversation? Run list_conversations and pass an id.")
    if not title:
        return ActionResult.error("A title cannot be empty.")

    # title_generated=False is the whole point: it tells the namer this one is
    # spoken for. Renaming without it would work, and then be silently undone.
    try:
        data, err = await gw(
            "PATCH", f"/v1/conversations/{cid}", uid,
            body={"title": title, "title_generated": False},
        )
    except Exception as e:
        return ActionResult.error(f"Could not rename: {safe_err(e)}")
    if err:
        return ActionResult.error(err)

    conv = (data or {}).get("conversation") or {}
    return ActionResult.success(
        data={
            "conversation_id": cid,
            "title": conv.get("title") or title,
            "message_count": int(conv.get("message_count") or 0),
            "note": "Named by hand — the automatic namer will not touch it.",
        },
        summary=f"Renamed to “{clip(title, 60)}”.",
    )
