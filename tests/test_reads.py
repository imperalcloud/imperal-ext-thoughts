"""Tests for the Thoughts read tools — listing and reading a thread.

The gateway is mocked (see tests/conftest.py); no network. Every test drives
the real handler functions against the real ``app.gw``.
"""
import httpx
import pytest

import handlers as h
from params import ListParams, ReadParams

UID = "imp_u_TEST"
LIST_PATH = "/v1/conversations"


def _conv(cid, title="", n=3, preview="hello", updated=None, **kw):
    return {
        "id": cid, "title": title, "message_count": n,
        "preview": preview, "updated_at": updated or 1787250000,
        **kw,
    }


TWO_THREADS = {
    "conversations": [
        _conv("c_billing", "Billing questions", 12, "so the invoice is wrong"),
        _conv("c_deploy", "Deploy runbook", 4, "shipped it"),
    ],
    "active_id": "c_deploy",
}


# ── list_conversations ─────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_list_returns_threads_and_marks_the_live_one(make_ctx, gw_mock):
    gw_mock.get(LIST_PATH, json=TWO_THREADS)

    res = await h.fn_list_conversations(make_ctx(), ListParams())

    assert res.status == "success"
    assert [c["id"] for c in res.data] == ["c_billing", "c_deploy"]
    live = [c for c in res.data if c["live"]]
    assert len(live) == 1 and live[0]["id"] == "c_deploy"


@pytest.mark.asyncio
async def test_list_sends_the_acting_user_header(make_ctx, gw_mock):
    """The entire per-user isolation rests on this header being present."""
    gw_mock.get(LIST_PATH, json=TWO_THREADS)

    await h.fn_list_conversations(make_ctx("imp_u_SOMEONE"), ListParams())

    req = gw_mock.last("GET", LIST_PATH)
    assert req.headers.get("X-Acting-User") == "imp_u_SOMEONE"


@pytest.mark.asyncio
async def test_list_filters_by_query_over_title_and_preview(make_ctx, gw_mock):
    gw_mock.get(LIST_PATH, json=TWO_THREADS)

    res = await h.fn_list_conversations(
        make_ctx(), ListParams(query="INVOICE"))          # case-insensitive

    assert [c["id"] for c in res.data] == ["c_billing"]


@pytest.mark.asyncio
async def test_list_says_so_when_the_room_is_empty(make_ctx, gw_mock):
    gw_mock.get(LIST_PATH, json={"conversations": [], "active_id": ""})

    res = await h.fn_list_conversations(make_ctx(), ListParams())

    assert res.status == "success"
    assert res.data == []
    assert "no conversation" in (res.summary or res.error or "").lower()


@pytest.mark.asyncio
async def test_list_reports_a_gateway_failure_instead_of_pretending(make_ctx, gw_mock):
    gw_mock.error("GET", LIST_PATH, httpx.ConnectError("boom"))

    res = await h.fn_list_conversations(make_ctx(), ListParams())

    assert res.status == "error"


@pytest.mark.asyncio
async def test_list_never_leaks_the_internal_gateway_url(make_ctx, gw_mock):
    gw_mock.error("GET", LIST_PATH, httpx.ConnectError("http://10.0.0.5:8085 refused"))

    res = await h.fn_list_conversations(make_ctx(), ListParams())

    assert res.status == "error"
    assert "10.0.0.5" not in str(res.error)
    assert "://" not in str(res.error)


# ── read_conversation ──────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_read_returns_messages_oldest_first(make_ctx, gw_mock):
    gw_mock.get("/v1/conversations/c_billing/messages", json={
        "conversation": {"title": "Billing questions"},
        "messages": [
            {"role": "user", "content": "why is it wrong", "surface": "telegram", "ts": 1787250000},
            {"role": "assistant", "content": "checking now", "surface": "telegram", "ts": 1787250060},
        ],
    })

    res = await h.fn_read_conversation(
        make_ctx(), ReadParams(conversation_id="c_billing"))

    assert res.status == "success"
    assert [m["role"] for m in res.data] == ["user", "assistant"]
    assert res.data[0]["surface"] == "telegram"


@pytest.mark.asyncio
async def test_read_without_an_id_reads_the_live_thread(make_ctx, gw_mock):
    """Empty id must resolve to the live thread, not 404 on an empty path."""
    gw_mock.get(LIST_PATH, json=TWO_THREADS)
    gw_mock.get("/v1/conversations/c_deploy/messages", json={
        "conversation": {"title": "Deploy runbook"},
        "messages": [{"role": "user", "content": "ship it", "ts": 1787250000}],
    })

    res = await h.fn_read_conversation(make_ctx(), ReadParams())

    assert res.status == "success"
    assert gw_mock.was_called("GET", "/v1/conversations/c_deploy/messages")


@pytest.mark.asyncio
async def test_read_explains_a_missing_thread_in_plain_words(make_ctx, gw_mock):
    gw_mock.get("/v1/conversations/c_gone/messages", json={"detail": "not found"}, status=404)

    res = await h.fn_read_conversation(
        make_ctx(), ReadParams(conversation_id="c_gone"))

    assert res.status == "error"
    assert "does not exist" in str(res.error).lower()
