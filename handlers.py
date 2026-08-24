"""Thoughts · Handler aggregator — one import that pulls in every tool.

The tools are split across three modules by blast radius (reads, writes,
delete). ``main.py`` imports THIS module alone, and every name is re-exported
here, so tests can `import handlers` and reach any tool without knowing which
file it happens to live in. Adding a fourth module later changes this file
and nothing else.
"""
from __future__ import annotations

from handlers_delete import fn_delete_conversation
from handlers_reads import fn_list_conversations, fn_read_conversation
from handlers_writes import (
    fn_continue_conversation,
    fn_new_conversation,
    fn_rename_conversation,
)

__all__ = [
    "fn_list_conversations",
    "fn_read_conversation",
    "fn_continue_conversation",
    "fn_new_conversation",
    "fn_rename_conversation",
    "fn_delete_conversation",
]
