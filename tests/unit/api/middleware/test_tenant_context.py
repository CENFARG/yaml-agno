"""RED tests for TenantContextMiddleware (SPEC_06 slice B).

Covers the composite user_id resolution contract defined in SPEC_06 §3.2:
  1. TenantContextMiddleware delegates to resolve_user_id() (SPEC_04).
  2. request.state.user_id is set before downstream handlers run.
  3. The composite format lives ONLY in resolve_user_id.
  4. Missing tenant_id causes UserIdentityResolutionError.
  5. user_id is never None when tenant_id + memory_cfg are valid.

These tests reference ``yaml_agno.api.middleware.tenant_context`` which does NOT
exist yet (RED phase). They MUST fail on ImportError until the GREEN phase.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

# --- Target import ---
from yaml_agno.api.middleware.tenant_context import TenantContextMiddleware
from yaml_agno.memory.user_identity import UserIdentityResolutionError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _memory_cfg(system_user_id: str | None = "agent:fallback") -> SimpleNamespace:
    """Minimal memory_cfg stub carrying ``system_user_id``.

    Mirrors the pattern from tests/yaml_agno/memory/test_user_identity.py.
    """
    return SimpleNamespace(system_user_id=system_user_id)


def _register_tenant_error_handler(app: FastAPI) -> None:
    """Register the 401 handler for ``UserIdentityResolutionError``.

    Mirrors what ``YamlAgentOS.get_app()`` registers in production so the
    test app reflects real behaviour: a missing tenant returns 401 with a
    structured JSON body, not a raw 500.
    """

    @app.exception_handler(UserIdentityResolutionError)
    async def _handler(
        request: Request, exc: UserIdentityResolutionError
    ) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})


def _build_test_app(
    memory_cfg: SimpleNamespace | None = None,
    *,
    raise_server_exceptions: bool = False,
) -> FastAPI:
    """Build a minimal FastAPI app with TenantContextMiddleware + a spy endpoint.

    The spy endpoint echoes back ``request.state.user_id`` so tests can assert
    the middleware resolution behaviour.

    Args:
        memory_cfg: Optional memory config for the middleware.
        raise_server_exceptions: Forwarded to ``TestClient``. Defaults to
            ``False`` so that unhandled middleware exceptions produce real HTTP
            500 responses instead of re-raising through the test client.
    """
    app = FastAPI()
    # Store this on the app instance so test helpers can pick it up.
    app.state._raise_server_exceptions = raise_server_exceptions

    if memory_cfg is None:
        memory_cfg = _memory_cfg()

    app.add_middleware(TenantContextMiddleware, memory_cfg=memory_cfg)
    _register_tenant_error_handler(app)

    @app.get("/spy")
    async def spy_endpoint(request: Request) -> dict[str, str | None]:
        return {"user_id": getattr(request.state, "user_id", None)}

    return app


def _client(app: FastAPI) -> TestClient:
    """Create a TestClient that respects the app's raise_server_exceptions flag."""
    flag: bool = getattr(app.state, "_raise_server_exceptions", False)
    return TestClient(app, raise_server_exceptions=flag)


# ---------------------------------------------------------------------------
# JWT-stamping helpers (JD-01: cover the previously-untested JWT path)
# ---------------------------------------------------------------------------


def _stamp_jwt_claims_middleware(
    *,
    tenant_claim: str | None = None,
    user_sub: str | None = None,
) -> type[BaseHTTPMiddleware]:
    """Build a middleware that stamps JWT-derived claims on ``request.state``.

    Mirrors what the AgentOS JWT middleware (``authorization=True``) does in
    production: after validating the JWT it stamps ``tenant_claim`` (from the
    ``tnt`` claim) and ``user_sub`` (from the ``sub`` claim) on
    ``request.state``. Only non-None values are stamped so a JWT that
    authenticates a user but carries no ``tnt`` claim can be modelled.

    Must be added AFTER ``TenantContextMiddleware`` so it is the OUTERMOST
    layer and runs first (Starlette wraps the last-added middleware outermost).
    """

    class _StampJwtClaimsMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self,
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            if tenant_claim is not None:
                request.state.tenant_claim = tenant_claim
            if user_sub is not None:
                request.state.user_sub = user_sub
            return await call_next(request)

    return _StampJwtClaimsMiddleware


def _build_jwt_test_app(
    *,
    tenant_claim: str | None = None,
    user_sub: str | None = None,
    memory_cfg: SimpleNamespace | None = None,
) -> FastAPI:
    """Build a FastAPI app whose request carries JWT-derived claims.

    Adds ``TenantContextMiddleware`` first (inner) then a stamping middleware
    (outer, runs first) so the middleware under test sees JWT claims on
    ``request.state`` exactly as it would behind AgentOS JWT auth.
    """
    app = FastAPI()
    app.state._raise_server_exceptions = False

    if memory_cfg is None:
        memory_cfg = _memory_cfg()

    app.add_middleware(TenantContextMiddleware, memory_cfg=memory_cfg)
    _register_tenant_error_handler(app)
    app.add_middleware(
        _stamp_jwt_claims_middleware(tenant_claim=tenant_claim, user_sub=user_sub)
    )

    @app.get("/spy")
    async def spy_endpoint(request: Request) -> dict[str, str | None]:
        return {"user_id": getattr(request.state, "user_id", None)}

    return app


# ---------------------------------------------------------------------------
# Scenario B.1 — Golden path: composite user_id from X-Tenant-Id header
# ---------------------------------------------------------------------------


class TestTenantContextMiddlewareGoldenPath:
    """GREEN scenarios — the middleware sets request.state.user_id correctly."""

    def test_composite_user_id_from_header_with_system_fallback(self) -> None:
        """X-Tenant-Id header → middleware delegates to resolve_user_id.

        Without JWT auth, ``principal_id`` is None, so ``resolve_user_id``
        falls back to ``memory_cfg.system_user_id`` as the principal.
        """
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_42"})

        assert resp.status_code == 200
        assert resp.json()["user_id"] == "tenant_42:agent:fallback"

    def test_composite_user_id_with_custom_system_user_id(self) -> None:
        """Different system_user_id produces a different composite."""
        cfg = _memory_cfg("workflow:invoice-processor")
        app = _build_test_app(memory_cfg=cfg)
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "acme"})

        assert resp.status_code == 200
        assert resp.json()["user_id"] == "acme:workflow:invoice-processor"

    def test_user_id_is_never_none_for_valid_request(self) -> None:
        """A valid request MUST set user_id, never leave it as None.

        Guards the NULL-bucket footgun (SPEC_06 §3.1 FODA): a None user_id
        matches every tenant in Agno's upsert conflict clauses.
        """
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_42"})

        assert resp.status_code == 200
        assert resp.json()["user_id"] is not None

    def test_different_tenants_produce_different_composites(self) -> None:
        """Two different X-Tenant-Id headers → two distinct composites."""
        cfg = _memory_cfg("agent:shared-bot")
        app = _build_test_app(memory_cfg=cfg)
        client = _client(app)

        r1 = client.get("/spy", headers={"X-Tenant-Id": "tenant_1"})
        r2 = client.get("/spy", headers={"X-Tenant-Id": "tenant_2"})

        assert r1.json()["user_id"] == "tenant_1:agent:shared-bot"
        assert r2.json()["user_id"] == "tenant_2:agent:shared-bot"
        assert r1.json()["user_id"] != r2.json()["user_id"]


# ---------------------------------------------------------------------------
# Scenario B.2 — Missing tenant_id raises (fail-fast, no NULL bucket)
# ---------------------------------------------------------------------------


class TestTenantContextMiddlewareFailFast:
    """RED scenarios — the middleware refuses to build a tenant-less user_id."""

    def test_missing_tenant_id_returns_401(self) -> None:
        """No X-Tenant-Id and no JWT tnt claim → resolve_user_id raises.

        The middleware catches ``UserIdentityResolutionError`` and returns
        401 Unauthorized. This is the CORRECT fail-fast behaviour — it
        prevents a None user_id from ever reaching Agno handlers while
        signalling the client that authentication is required.
        """
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy")  # no headers at all

        assert resp.status_code == 401

    def test_empty_tenant_header_returns_401(self) -> None:
        """Empty X-Tenant-Id header → resolve_user_id raises (empty is falsy)."""
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": ""})

        assert resp.status_code == 401

    def test_missing_tenant_returns_401_with_json_body(self) -> None:
        """No tenant → 401 Unauthorized with structured JSON body (not 500).

        A missing tenant is an authentication/authorization failure: the
        middleware cannot build a composite user_id, so it refuses rather
        than risk a NULL bucket. The correct HTTP status is 401 and the
        body MUST be a JSON object with a non-empty ``detail`` key so
        clients can present a meaningful error.
        """
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy")  # no headers at all

        assert resp.status_code == 401
        assert resp.headers["content-type"] == "application/json"
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)
        assert body["detail"]  # non-empty message


# ---------------------------------------------------------------------------
# Scenario B.3 — Delegation contract: resolve_user_id is the single source
# ---------------------------------------------------------------------------


class TestTenantContextMiddlewareDelegationContract:
    """The middleware DELEGATES to resolve_user_id; it does NOT build inline."""

    @patch("yaml_agno.api.middleware.tenant_context.resolve_user_id")
    def test_calls_resolve_user_id_exactly_once(self, mock_resolve) -> None:
        """The middleware MUST call resolve_user_id exactly once per request.

        It MUST NOT construct f"{tenant_id}:{principal_id}" inline.
        """
        mock_resolve.return_value = "tenant_42:mock-result"

        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_42"})

        mock_resolve.assert_called_once()
        assert resp.json()["user_id"] == "tenant_42:mock-result"

    @patch("yaml_agno.api.middleware.tenant_context.resolve_user_id")
    def test_passes_correct_args_to_resolve_user_id(self, mock_resolve) -> None:
        """Verify the middleware forwards the right args to resolve_user_id.

        - tenant_id from X-Tenant-Id header.
        - principal_id is None (no JWT auth → no sub claim).
        - memory_cfg from the middleware init.
        - context is None.
        """
        mock_resolve.return_value = "acme:alice"

        cfg = _memory_cfg("system:bot")
        app = _build_test_app(memory_cfg=cfg)
        client = _client(app)

        client.get("/spy", headers={"X-Tenant-Id": "acme"})

        mock_resolve.assert_called_once_with(
            memory_cfg=cfg,
            principal_id=None,
            tenant_id="acme",
            context=None,
        )


# ---------------------------------------------------------------------------
# Scenario B.4 — Edge cases
# ---------------------------------------------------------------------------


class TestTenantContextMiddlewareEdgeCases:
    """Boundary behaviour for the middleware."""

    def test_request_without_user_id_attr_initially(self) -> None:
        """Before the middleware runs, request.state.user_id does NOT exist.

        The middleware SETS it; it should not assume it's already there.
        """
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_42"})

        assert resp.status_code == 200
        # The spy endpoint echoes the value the middleware set.
        assert resp.json()["user_id"] is not None

    def test_dispatch_calls_next_and_returns_response(self) -> None:
        """The middleware MUST call the next handler and return its response.

        Confirms the dispatch pattern is correct (returns await call_next).
        """
        app = _build_test_app()
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_42"})

        assert resp.status_code == 200
        assert "user_id" in resp.json()


# ---------------------------------------------------------------------------
# Scenario B.5 - JWT claim precedence + anti-spoofing (Judgment Day JD-01)
# ---------------------------------------------------------------------------


class TestTenantContextMiddlewareJwtPrecedence:
    """JWT claims are authoritative; the header is a fallback only without JWT.

    Covers the two Judgment-Day findings (JD-01):
      1. The JWT extraction path (``request.state.tenant_claim`` /
         ``request.state.user_sub``) was completely untested - every previous
         test exercised the ``X-Tenant-Id`` header fallback only.
      2. Anti-spoofing: when a JWT is active but carries no ``tnt`` claim, the
         client-controlled ``X-Tenant-Id`` header MUST NOT be trusted (a
         tenant_A JWT must not impersonate tenant_B via the header).
    """

    def test_jwt_claims_used_when_header_absent(self) -> None:
        """JWT tenant_claim + user_sub drive the composite when no header is set.

        This is the previously-untested primary production path under
        ``authorization=True``.
        """
        app = _build_jwt_test_app(tenant_claim="jwt_tenant", user_sub="jwt_user")
        client = _client(app)

        resp = client.get("/spy")  # no X-Tenant-Id header

        assert resp.status_code == 200
        # principal comes from user_sub, NOT memory_cfg.system_user_id
        assert resp.json()["user_id"] == "jwt_tenant:jwt_user"

    def test_jwt_tenant_wins_over_disagreeing_header(self) -> None:
        """A spoofing X-Tenant-Id header is ignored when a JWT tnt is present.

        tenant_A JWT + ``X-Tenant-Id: tenant_B`` -> the composite MUST use
        tenant_A (JWT is authoritative).
        """
        app = _build_jwt_test_app(tenant_claim="tenant_A", user_sub="alice")
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_B"})

        assert resp.status_code == 200
        body = resp.json()["user_id"]
        assert body == "tenant_A:alice"
        assert not body.startswith("tenant_B:")

    def test_jwt_principal_used_over_system_fallback(self) -> None:
        """user_sub (JWT sub claim) is the principal, not system_user_id."""
        cfg = _memory_cfg("agent:fallback")
        app = _build_jwt_test_app(
            tenant_claim="jwt_tenant", user_sub="real_human", memory_cfg=cfg
        )
        client = _client(app)

        resp = client.get("/spy")

        assert resp.status_code == 200
        assert resp.json()["user_id"] == "jwt_tenant:real_human"

    def test_jwt_active_without_tnt_rejects_spoofing_header(self) -> None:
        """Anti-spoofing: authenticated JWT without a tnt claim must not trust the header.

        A valid JWT authenticates the user (``user_sub`` set) but carries no
        tenant (``tenant_claim`` absent). A client-supplied
        ``X-Tenant-Id: tenant_B`` must NOT be honoured - otherwise a tenant_A
        user impersonates tenant_B. The middleware fails fast (401) rather than
        trusting the client-controlled header.
        """
        # user_sub set => JWT is active; tenant_claim intentionally absent.
        app = _build_jwt_test_app(user_sub="alice")
        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_B"})

        assert resp.status_code == 401

    def test_no_jwt_falls_back_to_header(self) -> None:
        """Without any JWT (no user_sub), the header is the legitimate source.

        Regression guard: the anti-spoofing logic must not break the local-dev
        / non-JWT path that relies on ``X-Tenant-Id``.
        """
        app = _build_jwt_test_app()  # no claims stamped at all

        client = _client(app)

        resp = client.get("/spy", headers={"X-Tenant-Id": "tenant_42"})

        assert resp.status_code == 200
        assert resp.json()["user_id"] == "tenant_42:agent:fallback"

    @patch("yaml_agno.api.middleware.tenant_context.resolve_user_id")
    def test_jwt_values_forwarded_to_resolve_user_id(self, mock_resolve) -> None:
        """resolve_user_id receives the JWT tenant + JWT principal, not the header."""
        mock_resolve.return_value = "tenant_A:alice"

        cfg = _memory_cfg("agent:fallback")
        app = _build_jwt_test_app(
            tenant_claim="tenant_A", user_sub="alice", memory_cfg=cfg
        )
        client = _client(app)

        client.get("/spy", headers={"X-Tenant-Id": "tenant_B"})  # spoof attempt

        mock_resolve.assert_called_once_with(
            memory_cfg=cfg,
            principal_id="alice",
            tenant_id="tenant_A",
            context=None,
        )
