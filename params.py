"""Thoughts · Chat parameter models.

Kept in their own module: the deploy validator warns on modules over 300
lines, and parameters are read far more often than the handlers that use
them — by the model deciding HOW to call a tool. The descriptions here are
that decision's only input, so they are written for a reader, not a schema.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ListParams(BaseModel):
    limit: int = Field(
        default=30, ge=1, le=200,
        description="How many threads to return (newest/pinned first).")
    include_archived: bool = Field(
        default=False,
        description="Also list threads the user archived out of the way.")
    query: str = Field(
        default="",
        description=(
            "Optional filter — matches the thread's title or the preview of its "
            "last message, case-insensitive. Use it when the user describes a "
            "conversation instead of naming it ('the one about billing')."),
    )


class ReadParams(BaseModel):
    conversation_id: str = Field(
        default="",
        description=(
            "Which thread — its id from list_conversations. Empty = the live "
            "conversation (the one every surface is reading right now)."),
    )
    limit: int = Field(
        default=40, ge=1, le=500,
        description="How many messages to return, oldest-first.")


class ContinueParams(BaseModel):
    conversation_id: str = Field(
        description=(
            "Which thread to make live — its id from list_conversations. "
            "Never guess this: list first if the user described it in words."),
    )


class NewParams(BaseModel):
    title: str = Field(
        default="", max_length=200,
        description=(
            "Optional name for the new thread. Leave empty and it names itself "
            "from the first thing said in it."),
    )


class RenameParams(BaseModel):
    conversation_id: str = Field(
        description="Which thread to rename — its id from list_conversations.")
    title: str = Field(
        max_length=200,
        description=(
            "The new name. A hand-written name is final: the automatic namer "
            "stops touching this thread once a person has named it."),
    )


class DeleteParams(BaseModel):
    conversation_id: str = Field(
        description=(
            "Which thread to delete for good — its id from list_conversations. "
            "This cannot be undone, so it must be an id the user actually chose, "
            "never one inferred from a description."),
    )
