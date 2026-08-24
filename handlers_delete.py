"""Thoughts · Erase one conversation — the only tool here that destroys.

Its own module, deliberately. Everything in ``handlers_writes.py`` is
recoverable: switching archives, renaming can be renamed back. This cannot
be undone, so it gets `action_type="destructive"` (the kernel raises a
confirmation before it runs, on every surface) and a reviewer can read the
entire blast radius in one short file.

WHY IT DOES NOT DELETE ANYTHING ITSELF. A conversation exists in two places
— the archived thread on disk and, if it happens to be the live one, the
running chat record in kernel Redis that every surface is reading. Deleting
only the first would leave the user still talking INTO the thread they just
erased, and it would reappear on the next mirror. The gateway's delete
already handles both halves (drop the archive, and if it was live, clear the
record and open a fresh thread). Re-implementing that here would be a second
copy of the rule, certain to drift. So this asks the gateway and reports
exactly what came back — including which case it was.
"""
from __future__ import annotations

from app import ActionResult, chat, failed, _user_id
from models import DeletedRecord
from params import DeleteParams


@chat.function(
    "delete_conversation",
    action_type="destructive",
    data_model=DeletedRecord,
    effects=["delete:conversation"],
    event="conversation_deleted",
    description=(
        "Permanently erase ONE conversation and everything said in it. This cannot "
        "be undone. If it is the live thread, the chat record is cleared too and a "
        "fresh thread opens in its place, so nothing keeps writing into a deleted "
        "conversation. Always confirm which thread with the user first."),
)
async def fn_delete_conversation(ctx, params: DeleteParams) -> ActionResult:
    """Erase one thread; say plainly what happened to the live record."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    cid = (params.conversation_id or "").strip()
    if not cid:
        return ActionResult.error(
            "Which conversation? Run list_conversations and pass an id — "
            "this is not a call to make on a guess.")

    try:
        data = await ctx.conversations.delete(cid)
    except Exception as e:
        return failed("delete the conversation", e)

    payload = data or {}
    was_live = bool(payload.get("was_active"))
    replacement = str(payload.get("new_active_id") or "")

    if was_live:
        note = (
            "It was the live thread, so the running chat record was cleared and a "
            "fresh conversation opened in its place."
        )
    else:
        note = "It was not the live thread — the current conversation is untouched."

    return ActionResult.success(
        data={
            "deleted": cid,
            "was_live": was_live,
            "replacement_id": replacement,
            "note": note,
        },
        summary=f"Conversation erased. {note}",
    )
