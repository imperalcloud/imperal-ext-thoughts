"""Test harness for imperal-ext-thoughts.

The tools reach the gateway through exactly one function — ``app.gw`` — which
opens its client via ``shared_http`` (the SDK's per-process keepalive pool).

WHY THIS PATCHES ``app.shared_http`` AND NOT ``httpx.AsyncClient``.
The SDK's own module says so: "monkeypatch the importing module's
``shared_http`` symbol with any async-context-manager factory". Patching
``httpx.AsyncClient`` — the pattern the older sibling extensions use — would
NOT intercept these calls, because the pool is built once per process and
handed out again on later calls. A test written that way would pass while
touching nothing, which is worse than no test at all.

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

import app as app_mod  # noqa: E402 (import after the sys.path fix-up above)


@pytest.fixture
def make_ctx():
    """Minimal ctx stand-in — only ``ctx.user.imperal_id`` is ever read."""
    def _make(imperal_id: str = "imp_u_TEST"):
        return SimpleNamespace(user=SimpleNamespace(imperal_id=imperal_id))
    return _make


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
        async def fake_shared_http(*_a, **_kw):
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as c:
                yield c

        monkeypatch.setattr(app_mod, "shared_http", fake_shared_http)

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
