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
import os
import json
import logging
import httpx

log = logging.getLogger("thoughts.reads")
VAULT_BASE_URL = os.getenv("IMPERAL_VAULT_URL", "http://10.199.6.160:8000")
VAULT_TIMEOUT = float(os.getenv("IMPERAL_VAULT_TIMEOUT", "2.0"))


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




def _human_terminal_title(session_id: str) -> str:
    """Derive a friendly title from marathon session id."""
    # marathon-imp_u_XWnehlFBls-r7bb586ff8d96-s15f1f9 -> Terminal (r7bb586)
    parts = session_id.split("-")
    repo_part = ""
    for p in parts:
        if p.startswith("r") and len(p) >= 7:
            repo_part = p[:7]
            break
    if repo_part:
        return f"Terminal Marathon ({repo_part})"
    return f"Terminal Session ({session_id[:16]})"


async def _fetch_vault_terminal_sessions(uid: str, active_id: str) -> list[dict]:
    """Fetch terminal sessions from Redis registry / Vault to make them visible in Thoughts Room."""
    rows = []
    try:
        # Check Redis coding_remote:sessions for this user
        import redis.asyncio as aioredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = aioredis.from_url(redis_url, decode_responses=True)
        try:
            sess_items = await r.zrevrange(f"imperal:coding_remote:sessions:{uid}", 0, 50, withscores=True)
        finally:
            await r.aclose()

        async with httpx.AsyncClient(timeout=VAULT_TIMEOUT) as client:
            for item in sess_items:
                sess_id = item[0] if isinstance(item, (list, tuple)) else str(item)
                score = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else 0
                
                # Fetch turn count & preview from Vault
                msg_count = 0
                preview = "Terminal marathon session"
                try:
                    resp = await client.get(
                        f"{VAULT_BASE_URL}/v1/session/history",
                        params={"user_id": uid, "session_id": sess_id, "limit": 1, "offset": 0}
                    )
                    if resp.status_code == 200:
                        vdata = resp.json()
                        msg_count = vdata.get("total", 0)
                        items = vdata.get("items", [])
                        if items:
                            first_text = items[0].get("text", "")
                            preview = clip(first_text, 80)
                except Exception as ve:
                    log.debug("Vault history peek failed for %s: %s", sess_id, ve)

                if msg_count > 0:
                    rows.append({
                        "id": sess_id,
                        "title": _human_terminal_title(sess_id),
                        "message_count": int(msg_count),
                        "preview": preview,
                        "updated": age(score) if score else "recently",
                        "live": sess_id == active_id,
                        "pinned": False,
                        "archived": False,
                        "_score": float(score or 0),
                    })
    except Exception as e:
        log.warning("Failed to load terminal sessions for %s: %s", uid, e)
    return rows

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
    """The inventory of the caller's own threads — including terminal marathons from Vault."""
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

    # Cross-surface Vault & Terminal threads integration (2026-09-17)
    try:
        vault_threads = await _fetch_vault_terminal_sessions(uid, active_id)
        existing_ids = {r["id"] for r in rows}
        for vt in vault_threads:
            if vt["id"] not in existing_ids:
                rows.append(vt)
    except Exception as e:
        log.debug("fetch vault terminal sessions failed (fail-soft): %s", e)

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
    """One thread's messages — supports standard gateway threads AND Vault terminal sessions."""
    uid = _user_id(ctx)
    if not uid:
        return ActionResult.error("Could not identify the calling user.")

    cid = params.conversation_id.strip()

    # Case 1: Terminal Marathon Session from Tenant Vault
    if cid.startswith("marathon-") or cid.startswith("sess-terminal-") or "terminal" in cid:
        try:
            async with httpx.AsyncClient(timeout=VAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{VAULT_BASE_URL}/v1/session/history",
                    params={"user_id": uid, "session_id": cid, "limit": params.limit, "offset": 0},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    msgs = [
                        {
                            "role": m.get("role", "user"),
                            "text": clip(m.get("text") or "", 600),
                            "surface": "terminal",
                            "when": age(m.get("ts")),
                        }
                        for m in items
                    ]
                    title = _human_terminal_title(cid)
                    if not msgs:
                        return ActionResult.success(
                            data=[], summary=f"“{title}” has no messages yet.")
                    return ActionResult.success(
                        data=msgs,
                        summary=f"{len(msgs)} message(s) from “{title}” (Terminal Vault).",
                    )
        except Exception as e:
            log.warning("read terminal session from vault failed: %s", e)

    # Case 2: Standard gateway conversations
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
