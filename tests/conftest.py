"""Test harness for imperal-ext-thoughts.

The tools reach the conversation store through exactly one thing —
``ctx.conversations``, the SDK namespace — so that is what the harness has
to stand up.

WHY IT INJECTS A **REAL** CLIENT AND NOT A FAKE NAMESPACE.
Handing the handlers a stub object with ``list``/``delete`` methods would be
easier and would test almost nothing: the interesting part of this app is
which route each tool ends up asking for, and a stub answers that question
by definition. So the fixture builds a genuine ``ConversationsClient`` and
takes the ground out from under it instead — the client constructs its own
paths, headers and error types exactly as it does in production, and the
mock only decides what comes back. Every route assertion in these tests is
therefore still a real assertion.

WHY IT PATCHES ``_gateway.shared_http``.
The SDK opens its connections through a per-process keepalive pool, built
once and handed out again on later calls. Patching ``httpx.AsyncClient`` —
the pattern the older sibling extensions use — would intercept nothing,
because by test time the pool already exists. The SDK's own suite patches
this same symbol, for this same reason.

No respx: the validation host's worker venv has httpx + pytest and nothing
else.
"""
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

# The ext modules use bare `import app` / `from app import ...`, so the package
# root must be importable BEFORE any test module imports them.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from imperal_sdk import _gateway  # noqa: E402
from imperal_sdk.conversations.client import ConversationsClient  # noqa: E402

GW = "http://gateway.test:8085"
TOKEN = "svc-token-test"


class GatewayMock:
    """Routes (method, path) -> canned response, exception, or callable.

    Every request is recorded, so a test can assert not just on the answer but
    on what was actually ASKED — including the X-Acting-User header, which is
    the whole basis of this app's per-user isolation.
    """

    def __init__(self, monkeypatch):
        self.routes: dict[tuple[str, str], object] = {}
        self.calls: list[httpx.Request] = []
        self._install(monkeypatch)

    def _install(self, monkeypatch) -> None:
        handler = self._handle

        @asynccontextmanager
        async def fake_pool(*_a, **_kw):
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as c:
                yield c

        monkeypatch.setattr(_gateway, "shared_http", fake_pool)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        spec = self.routes.get((request.method, request.url.path))
        if spec is None:
            raise AssertionError(
                f"gw_mock: no route registered for "
                f"{(request.method, request.url.path)}")
        if isinstance(spec, BaseException):
            raise spec
        if callable(spec):
            return spec(request)
        return spec

    # ── route registration ──────────────────────────────────────────── #
    def route(self, method: str, path: str, *, json=None, status: int = 200):
        self.routes[(method, path)] = httpx.Response(status, json=json)

    def get(self, path: str, *, json=None, status: int = 200):
        self.route("GET", path, json=json, status=status)

    def post(self, path: str, *, json=None, status: int = 200):
        self.route("POST", path, json=json, status=status)

    def patch(self, path: str, *, json=None, status: int = 200):
        self.route("PATCH", path, json=json, status=status)

    def delete(self, path: str, *, json=None, status: int = 200):
        self.route("DELETE", path, json=json, status=status)

    def error(self, method: str, path: str, exc: BaseException):
        self.routes[(method, path)] = exc

    # ── assertions ──────────────────────────────────────────────────── #
    def was_called(self, method: str, path: str) -> bool:
        return any(r.method == method and r.url.path == path for r in self.calls)

    def last(self, method: str, path: str) -> httpx.Request:
        for r in reversed(self.calls):
            if r.method == method and r.url.path == path:
                return r
        raise AssertionError(f"gw_mock: nothing recorded for {(method, path)}")


@pytest.fixture
def gw_mock(monkeypatch):
    return GatewayMock(monkeypatch)


@pytest.fixture
def make_ctx():
    """A ctx stand-in carrying the two things the handlers read.

    ``ctx.conversations`` is the real client (see the module docstring), so
    the route a tool asks for is genuinely the route the SDK builds.
    """
    def _make(imperal_id: str = "imp_u_TEST"):
        return SimpleNamespace(
            user=SimpleNamespace(imperal_id=imperal_id),
            conversations=ConversationsClient(
                gateway_url=GW, service_token=TOKEN, user_id=imperal_id,
                extension_id="thoughts", tenant_id="t1"),
        )
    return _make
