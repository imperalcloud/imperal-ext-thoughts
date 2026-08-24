"""Thoughts · Shared state — the user's own conversations, from any surface.

WHAT THIS IS. The Thoughts Room is where every conversation the user has
with Webbee is kept: panel, Telegram, terminal, all of it. The room has a
web page, and until now that page was the ONLY way to reach it. This
extension gives the room the other half — so Webbee herself can answer
"what were we talking about last Tuesday", walk back into an older thread,
or start a clean one, from whichever surface the user happens to be on.

WHY IT CALLS THE GATEWAY INSTEAD OF READING STORAGE.
The conversations live in two places that must stay in step: the LIVE chat
record in kernel Redis (what every surface is reading right now) and the
per-thread archive on disk. Keeping them in step — mirror before read,
archive before switch, clear-and-reopen on delete — is real logic, and it
already exists once, in the gateway's conversations service. Reaching into
Redis from here would be a second copy of that logic, guaranteed to drift
the first time either side changes. So this app is a thin, honest client of
/v1/conversations and owns no rules of its own.

OWN DATA ONLY. Every call is made with the acting user's imperal_id in the
X-Acting-User header, and the gateway's routes take no user_id parameter at
all: there is no shape of request that could ask for somebody else's
history. The isolation is not a check that could be forgotten here — it is
the absence of a way to express the question.
"""
from __future__ import annotations

import logging
import os

from imperal_sdk import Extension
from imperal_sdk._shared_http import shared_http
from imperal_sdk.chat import ActionResult, ChatExtension  # noqa: F401 (re-exported)

log = logging.getLogger("thoughts")

AUTH_GW = os.getenv("IMPERAL_GATEWAY_URL", "http://104.224.88.155:8085")
AUTH_SERVICE_TOKEN = os.getenv("AUTH_SERVICE_TOKEN", "")

# The gateway caps a listing at 200 and a message page at 500; mirror those
# here so a caller gets a clear refusal from us instead of a 422 from there.
MAX_LIST = 200
MAX_MESSAGES = 500

ext = Extension(
    "thoughts", version="1.0.0",
    # Declare exactly what this touches: the caller's own conversations,
    # read and written. Never a wildcard, even for a system app.
    capabilities=["conversations:read", "conversations:write"],
    display_name="Thoughts",
    description=(
        "Every conversation with Webbee, on every surface, kept and reachable — "
        "search back through past threads, continue an older one, rename or pin "
        "what matters, and start fresh without losing what came before."
    ),
    icon="icon.svg",
    actions_explicit=True,
    system=True,  # Imperal-owned platform app — always available, no install step.
)

chat = ChatExtension(
    ext,
    "tool_thoughts_chat",
    description=(
        "The user's own conversation history with Webbee across panel, Telegram "
        "and terminal: list threads, read one, continue it, rename/pin/archive, "
        "start a new one, delete one."
    ),
    system_prompt=(
        "Thoughts Room module — the user's conversation history, shared by every "
        "surface.\n\n"
        "ONE LIVE THREAD AT A TIME. Whatever is active is the conversation every "
        "surface is reading: activating an older thread in Telegram means the "
        "panel and the terminal are in that thread too. Say so when it matters, "
        "because it surprises people.\n\n"
        "list_conversations is the inventory (pinned first, then newest) and "
        "marks which one is live. read_conversation opens one and returns its "
        "messages oldest-first. continue_conversation makes an older thread the "
        "live one. start_new_conversation archives the current talk and opens a "
        "clean one — nothing is lost. update_conversation renames, pins or "
        "archives. delete_conversation destroys one for good.\n\n"
        "Titles are generated in the background from the first exchange, so a "
        "young thread may still read 'Untitled' — that is normal, not a bug, and "
        "a user-chosen name is never overwritten.\n\n"
        "When the user asks what you talked about before, LOOK — list, then read "
        "the thread that matches — rather than answering from what you happen to "
        "remember in this turn."
    ),
)


def _user_id(ctx) -> str:
    """ALWAYS the acting user. These tools never accept a foreign user_id."""
    return ctx.user.imperal_id


def _headers(uid: str) -> dict:
    # X-Acting-User is what turns a service token into "this user's call".
    # Without it the gateway refuses rather than defaulting to somebody —
    # which is exactly the behaviour we want to inherit, not work around.
    return {"X-Service-Token": AUTH_SERVICE_TOKEN, "X-Acting-User": uid}


def _err(status: int, body: str) -> str:
    """A gateway failure in words the caller can act on."""
    if status == 404:
        return "That conversation does not exist (it may already be deleted)."
    if status == 403:
        return "That conversation belongs to someone else."
    return f"HTTP {status}: {body[:200]}"


async def gw(method: str, path: str, uid: str,
             *, params: dict | None = None,
             body: dict | None = None) -> tuple[dict | None, str | None]:
    """Call the conversations API as `uid`. Returns (json, None) or (None, error)."""
    async with shared_http(timeout=10.0) as c:
        r = await c.request(
            method, f"{AUTH_GW}{path}",
            headers=_headers(uid), params=params, json=body,
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail") or r.text[:300]
            except Exception:
                detail = r.text[:300] or "(empty body)"
            return None, _err(r.status_code, str(detail))
        return r.json(), None


@ext.health_check
async def health(ctx) -> dict:
    return {"status": "ok", "version": ext.version}


def safe_err(e: Exception) -> str:
    """Never let an internal gateway URL/IP leak into a chat-facing error."""
    s = str(e)
    return "internal error" if "http" in s.lower() and "://" in s else s
