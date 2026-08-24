"""Tests for the Thoughts write tools — continue, start, rename.

These three are the ones that were shipping a call to a factory method the
SDK does not have (``ActionResult.ok``). Nothing in the read tests could have
caught it: it only fires when a write actually succeeds. Hence a test per
tool that drives the SUCCESS path all the way to the returned object.
"""
import httpx
import pytest

import handlers as h
from params import ContinueParams, NewParams, RenameParams

LIST_PATH = "/v1/conversations"


# ── continue_conversation ──────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_continue_makes_the_thread_live(make_ctx, gw_mock):
    gw_mock.post(
        "/v1/conversations/c_old/activate",
        json={"conversation": {"id": "c_old", "title": "Billing", "message_count": 12}},
    )

    res = await h.fn_continue_conversation(
        make_ctx(), ContinueParams(conversation_id="c_old"))

    assert res.status == "success"
    assert res.data["conversation_id"] == "c_old"
    assert res.data["title"] == "Billing"
    assert "Billing" in res.summary


@pytest.mark.asyncio
async def test_continue_refuses_an_empty_id_without_calling_the_gateway(make_ctx, gw_mock):
    """Guessing which conversation to resurrect is worse than asking."""
    res = await h.fn_continue_conversation(
        make_ctx(), ContinueParams(conversation_id="   "))

    assert res.status == "error"
    assert "list_conversations" in res.error
    assert gw_mock.calls == []


@pytest.mark.asyncio
async def test_continue_reports_a_missing_thread_plainly(make_ctx, gw_mock):
    gw_mock.post("/v1/conversations/c_gone/activate",
                 json={"detail": "not found"}, status=404)

    res = await h.fn_continue_conversation(
        make_ctx(), ContinueParams(conversation_id="c_gone"))

    assert res.status == "error"
    assert "does not exist" in res.error.lower()


# ── new_conversation ───────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_new_starts_a_thread_and_says_the_old_one_survived(make_ctx, gw_mock):
    gw_mock.post(LIST_PATH, json={"conversation": {"id": "c_new", "title": ""}})

    res = await h.fn_new_conversation(make_ctx(), NewParams())

    assert res.status == "success"
    assert res.data["conversation_id"] == "c_new"
    assert res.data["message_count"] == 0
    assert "archived" in res.data["note"].lower()


@pytest.mark.asyncio
async def test_new_passes_a_chosen_title_through(make_ctx, gw_mock):
    gw_mock.post(LIST_PATH, json={"conversation": {"id": "c_new", "title": "Infra audit"}})

    res = await h.fn_new_conversation(make_ctx(), NewParams(title="Infra audit"))

    body = gw_mock.last("POST", LIST_PATH).read().decode()
    assert "Infra audit" in body
    assert res.data["title"] == "Infra audit"


# ── rename_conversation ────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_rename_sets_the_title_and_stops_auto_naming(make_ctx, gw_mock):
    gw_mock.patch(
        "/v1/conversations/c1",
        json={"conversation": {"id": "c1", "title": "Ceph migration", "message_count": 7}},
    )

    res = await h.fn_rename_conversation(
        make_ctx(), RenameParams(conversation_id="c1", title="Ceph migration"))

    assert res.status == "success"
    assert res.data["title"] == "Ceph migration"
    # The gateway is told this is a human title, so the namer leaves it alone.
    body = gw_mock.last("PATCH", "/v1/conversations/c1").read().decode()
    assert "title_generated" in body


@pytest.mark.asyncio
async def test_rename_refuses_a_blank_title(make_ctx, gw_mock):
    res = await h.fn_rename_conversation(
        make_ctx(), RenameParams(conversation_id="c1", title="   "))

    assert res.status == "error"
    assert gw_mock.calls == []


@pytest.mark.asyncio
async def test_a_gateway_outage_never_leaks_the_internal_url(make_ctx, gw_mock):
    gw_mock.error("POST", "/v1/conversations/c1/activate",
                  httpx.ConnectError("failed to connect to http://10.0.0.5:8085"))

    res = await h.fn_continue_conversation(
        make_ctx(), ContinueParams(conversation_id="c1"))

    assert res.status == "error"
    assert "8085" not in res.error and "://" not in res.error
