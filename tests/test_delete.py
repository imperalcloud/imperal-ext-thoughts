"""Tests for delete_conversation — the one tool here that destroys.

Covered with more care than the rest on purpose: a mistake in a read shows a
stale list, a mistake here loses a conversation for good. What matters is not
only that it deletes, but that it tells the truth about WHAT happened —
especially the live-thread case, where the running chat record is cleared and
a fresh thread takes its place.
"""
import httpx
import pytest

import handlers as h
from params import DeleteParams


@pytest.mark.asyncio
async def test_delete_removes_an_ordinary_thread(make_ctx, gw_mock):
    gw_mock.delete("/v1/conversations/c_old", json={"deleted": "c_old", "was_active": False})

    res = await h.fn_delete_conversation(
        make_ctx(), DeleteParams(conversation_id="c_old"))

    assert res.status == "success"
    assert res.data["deleted"] == "c_old"
    assert res.data["was_live"] is False
    assert res.data["replacement_id"] == ""


@pytest.mark.asyncio
async def test_delete_of_the_live_thread_reports_the_replacement(make_ctx, gw_mock):
    """The user must learn that the thread they were IN is gone and what replaced it."""
    gw_mock.delete(
        "/v1/conversations/c_live",
        json={"deleted": "c_live", "was_active": True, "new_active_id": "c_fresh"},
    )

    res = await h.fn_delete_conversation(
        make_ctx(), DeleteParams(conversation_id="c_live"))

    assert res.status == "success"
    assert res.data["was_live"] is True
    assert res.data["replacement_id"] == "c_fresh"
    note = res.data["note"].lower()
    assert "live" in note or "fresh" in note


@pytest.mark.asyncio
async def test_delete_refuses_an_empty_id_without_touching_the_gateway(make_ctx, gw_mock):
    """An unqualified delete is the one call that must never be guessed."""
    res = await h.fn_delete_conversation(
        make_ctx(), DeleteParams(conversation_id="  "))

    assert res.status == "error"
    assert gw_mock.calls == []


@pytest.mark.asyncio
async def test_delete_of_a_missing_thread_says_so_plainly(make_ctx, gw_mock):
    gw_mock.delete("/v1/conversations/c_gone", json={"detail": "not found"}, status=404)

    res = await h.fn_delete_conversation(
        make_ctx(), DeleteParams(conversation_id="c_gone"))

    assert res.status == "error"
    assert "does not exist" in res.error.lower()


@pytest.mark.asyncio
async def test_delete_of_someone_elses_thread_is_refused(make_ctx, gw_mock):
    """The gateway owns this rule; the tool must relay it, not soften it."""
    gw_mock.delete("/v1/conversations/c_theirs", json={"detail": "forbidden"}, status=403)

    res = await h.fn_delete_conversation(
        make_ctx(), DeleteParams(conversation_id="c_theirs"))

    assert res.status == "error"
    assert "someone else" in res.error.lower()


@pytest.mark.asyncio
async def test_delete_sends_the_acting_user_header(make_ctx, gw_mock):
    gw_mock.delete("/v1/conversations/c1", json={"deleted": "c1"})

    await h.fn_delete_conversation(
        make_ctx("imp_u_OWNER"), DeleteParams(conversation_id="c1"))

    req = gw_mock.last("DELETE", "/v1/conversations/c1")
    assert req.headers.get("X-Acting-User") == "imp_u_OWNER"


@pytest.mark.asyncio
async def test_delete_never_claims_success_on_an_outage(make_ctx, gw_mock):
    """Reporting a delete that did not happen is the worst possible lie here."""
    gw_mock.error("DELETE", "/v1/conversations/c1",
                  httpx.ConnectError("connect failed to http://10.0.0.5:8085"))

    res = await h.fn_delete_conversation(
        make_ctx(), DeleteParams(conversation_id="c1"))

    assert res.status == "error"
    assert "8085" not in res.error and "://" not in res.error
