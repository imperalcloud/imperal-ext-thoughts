# imperal-ext-thoughts

Imperal-owned system extension for the **Thoughts Room** — the place where
every conversation with Webbee is kept, from every surface.

The room already had a web page at `/workspace/thoughts`. This extension gives
it the other half: Webbee herself can reach the room from **any** surface, so
"what were we talking about on Tuesday?" works in Telegram and in the terminal,
not only in a browser tab.

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `list_conversations` | read | Every thread — pinned first, then newest — with message counts, previews and which one is **live** right now. Supports a text filter for when the user describes a conversation instead of naming it. |
| `read_conversation` | read | The messages inside one thread, oldest-first, each tagged with the surface it was said on. Empty id = the live conversation. |
| `continue_conversation` | write | Walk back into an earlier thread and make it live, so the next thing said continues *that* conversation everywhere. The current one is archived, never lost. |
| `new_conversation` | write | Start a clean thread. The previous one is archived and stays readable. |
| `rename_conversation` | write | Name a thread by hand. A hand-picked title is never overwritten by the automatic namer. |
| `delete_conversation` | destructive | Erase one thread for good. If it was live, the running chat record is cleared too and a fresh thread opens in its place. |

## Why it calls the gateway instead of reading storage

A conversation lives in two places that must stay in step: the **live chat
record** in kernel Redis — what every surface is reading at this moment — and
the **archived thread** on disk.

Keeping them in step is real logic: mirror before listing, archive before
switching, clear-and-reopen on delete. That logic already exists once, in the
gateway's conversations service. Reaching into Redis from here would be a
second copy of it, guaranteed to drift the first time either side changed.

So this app owns no rules of its own. It is a thin client of `/v1/conversations`
that shapes the answers for a human reader.

## Isolation

Every call carries the acting user's `imperal_id` in the `X-Acting-User`
header, and the gateway's routes accept **no** `user_id` parameter at all.
There is no shape of request that could ask for someone else's history — the
isolation is not a check that could be forgotten, it is the absence of a way
to express the question.

A service token with no acting user is refused rather than defaulted to
"some user": that fallback is how cross-tenant leaks are born.

## Layout

```
app.py               extension + gateway client (headers, timeouts, error scrubbing)
main.py              entry point; drops cached modules so a hot reimport serves THIS release
handlers.py          aggregator — re-exports every tool
handlers_reads.py    list_conversations, read_conversation
handlers_writes.py   continue_conversation, new_conversation, rename_conversation
handlers_delete.py   delete_conversation — alone, by blast radius
models.py            response shapes the kernel renders into tables
params.py            tool parameters; their descriptions are what the model reads
fmt.py               epoch → "2h ago", previews clipped on word boundaries
```
