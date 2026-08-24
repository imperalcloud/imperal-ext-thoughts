"""Thoughts · Response models — the shapes the caller actually reads.

These exist so an answer about conversations is a TABLE of real threads, not
a wall of JSON: the kernel renders a data_model into something a person can
scan on any surface, and picks sensible columns from the field descriptions.

Only fields worth showing are declared. The archive stores more per thread
(sequence numbers, storage paths, mirror bookkeeping) and none of it helps
anybody decide which conversation to open.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationRecord(BaseModel):
    """One thread in the room."""

    id: str = Field(description="Thread id — pass this to read/continue/rename/delete")
    title: str = Field(default="", description="Its name; empty until it has earned one")
    message_count: int = Field(default=0, description="How many messages it holds")
    preview: str = Field(default="", description="Opening of the last message")
    updated: str = Field(default="", description="How long ago it was last touched")
    live: bool = Field(default=False, description="True for the one every surface is reading now")
    pinned: bool = Field(default=False, description="Kept at the top of the list")
    archived: bool = Field(default=False, description="Hidden from the default listing")


class MessageRecord(BaseModel):
    """One message inside a thread, oldest-first."""

    role: str = Field(description="who said it — user or assistant")
    text: str = Field(description="What was said")
    surface: str = Field(default="", description="Where it was said — panel, telegram, terminal")
    when: str = Field(default="", description="How long ago")


class DeletedRecord(BaseModel):
    """What a delete actually did — stated, not assumed."""

    deleted: str = Field(description="The thread id that is now gone")
    was_live: bool = Field(default=False, description="Whether it was the live conversation")
    replacement_id: str = Field(default="", description="The fresh thread opened in its place, if any")
    note: str = Field(default="", description="Plain-language account of what happened")


class SwitchedRecord(BaseModel):
    """The thread that is live after a switch, a start, or a rename."""

    conversation_id: str = Field(description="The thread this call acted on")
    title: str = Field(default="", description="Its name right now")
    message_count: int = Field(default=0, description="How many messages it holds")
    note: str = Field(default="", description="What happened to the previous thread")
