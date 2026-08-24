"""Thoughts · Shared state — the user's own conversations, from any surface.

WHAT THIS IS. The Thoughts Room is where every conversation the user has
with Webbee is kept: panel, Telegram, terminal, all of it. The room has a
web page, and until now that page was the ONLY way to reach it. This
extension gives the room the other half — so Webbee herself can answer
"what were we talking about last Tuesday", walk back into an older thread,
or start a clean one, from whichever surface the user happens to be on.

WHY IT OWNS NO STORAGE LOGIC. The conversations live in two places that
must stay in step: the LIVE chat record in kernel Redis (what every surface
is reading right now) and the per-thread archive on disk. Keeping them in
step — mirror before read, archive before switch, clear-and-reopen on
delete — is real logic, and it already exists once, in the platform's
conversations service. Reaching into Redis from here would be a second copy
of that logic, guaranteed to drift the first time either side changes. So
this app decides nothing about storage and owns no rules of its own.

HOW IT REACHES THEM: `ctx.conversations`, the SDK namespace. This file
holds no URL, no service token and no header assembly, because none of that
is an app's business — it is the platform's, and the SDK is where the
platform states it once. Version 1.0.0 shipped with a hand-rolled HTTP
client here purely because the worker was still on an SDK that predated the
namespace; that reason expired the moment the worker moved to 5.12.1, and
with it the code.

OWN DATA ONLY. The namespace binds every call to the acting user and the
routes behind it accept no user_id at all: there is no shape of request
that could ask for somebody else's history. The isolation is not a check
that could be forgotten here — it is the absence of a way to express the
question.
"""
from __future__ import annotations

import logging

from imperal_sdk import Extension
from imperal_sdk.chat import ActionResult, ChatExtension  # noqa: F401 (re-exported)
from imperal_sdk.errors import APIError, AuthError, NotFoundError

log = logging.getLogger("thoughts")

ext = Extension(
    "thoughts", version="1.1.0",
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


def failed(action: str, e: Exception) -> ActionResult:
    """Turn an SDK error into something the caller can act on.

    WHY THIS EXISTS ONCE. `ctx.conversations` raises a typed error rather
    than returning a status code, and every handler wants the same three
    sentences for the same three cases. Written per-handler, the wordings
    drift until "gone" and "not yours" read identically — which is the one
    distinction a user actually needs.

    A raw error never reaches chat: an APIError's text can carry the
    gateway's internal URL, and that is nobody's business but ours.
    """
    if isinstance(e, NotFoundError):
        return ActionResult.error(
            "That conversation does not exist (it may already be deleted).")
    if isinstance(e, AuthError):
        return ActionResult.error("That conversation belongs to someone else.")
    if isinstance(e, ValueError):
        # Guard rejections (blank id, empty update) — already human-readable
        # and carry no internals.
        return ActionResult.error(str(e))
    if isinstance(e, APIError):
        log.warning("thoughts: %s failed: %s", action, e)
        return ActionResult.error(f"Could not {action} — the conversation store is unavailable.")
    log.exception("thoughts: %s failed unexpectedly", action)
    return ActionResult.error(f"Could not {action}.")


@ext.health_check
async def health(ctx) -> dict:
    return {"status": "ok", "version": ext.version}
