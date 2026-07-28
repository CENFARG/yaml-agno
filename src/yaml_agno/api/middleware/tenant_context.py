"""TenantContextMiddleware: composite user_id for Agno native user_isolation.

Agno has no ``tenant_id`` concept; it scopes native runs on
``request.state.user_id`` (``agents/router.py:616``, ``teams/router.py:588``)
and ``AuthorizationConfig.user_isolation`` (``os/config.py:125``) threads that
value on every user-scoped DB read/write. This middleware extracts ``tenant_id``
+ principal from the request, then DELEGATES the composite construction to the
shared ``resolve_user_id()`` (SPEC_04 §1.4) so that the composite format lives
in ONE place (HTTP and autonomous runs alike).

@ai-directive: this middleware extracts ``tenant_id`` + principal from the
request, then DELEGATES to the shared ``resolve_user_id()`` (SPEC_04) to build
the composite. It does NOT construct ``f"{tenant_id}:{raw_user_id}"`` inline —
``resolve_user_id`` is the single source of truth for the composite format. It
does NOT add a ``tenant_id`` column to ``agno_*`` tables (Agno does not support
one), does NOT apply Postgres RLS, and does NOT open a DB session. Per SPEC_03
§5 and SPEC_04 §3.3: tenant isolation of yaml-agno's OWN config rows is
explicit WHERE filters on ``yamlagno_*`` tables; ``tenant_id`` on ``agno_*``
tables is the composite ``user_id`` only. A contextvar (``set_tenant_id``) is
telemetry-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from yaml_agno.memory.user_identity import resolve_user_id  # SPEC_04 §1.4

__all__ = ["TenantContextMiddleware"]


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Set ``request.state.user_id`` to the composite ``"{tenant_id}:{principal_id}"``.

    This middleware extracts ``tenant_id`` + principal from the request, then
    DELEGATES to the shared ``resolve_user_id()`` (SPEC_04) to build the
    composite. The composite format lives ONLY in ``resolve_user_id``; this
    middleware never builds ``f"{tenant_id}:{raw_user_id}"`` inline.

    Attributes:
        memory_cfg: YAML ``memory:`` block (SPEC_02 *Config). Carries
            ``system_user_id`` used by ``resolve_user_id`` when no human
            principal is present on the request.
    """

    def __init__(self, app: Any, memory_cfg: Any = None) -> None:
        """Initialize with the YAML memory block (for ``system_user_id`` fallback).

        Args:
            app: The ASGI app (passed by ``add_middleware``).
            memory_cfg: YAML ``memory:`` block (SPEC_02 *Config). Carries
                ``system_user_id`` used by ``resolve_user_id`` when no human
                principal is present on the request.
        """
        super().__init__(app)
        self.memory_cfg = memory_cfg

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Delegate to ``resolve_user_id`` and stamp ``request.state``.

        Args:
            request: Incoming request; may carry JWT claims or ``X-Tenant-Id``.
            call_next: Next ASGI handler.

        Returns:
            The downstream response. Native AgentOS handlers and
            ``get_scoped_user_id`` read ``request.state.user_id`` for scoping.
        """
        tenant_id = self._extract_tenant_id(request)
        principal_id = self._extract_raw_user_id(request)

        # Single source of truth: resolve_user_id (SPEC_04) builds the
        # composite and fails fast if tenant_id or principal is missing.
        # Never None.
        request.state.user_id = resolve_user_id(
            memory_cfg=self.memory_cfg,
            principal_id=principal_id,
            tenant_id=tenant_id,
            context=None,
        )
        return await call_next(request)

    # ------------------------------------------------------------------
    # Extraction helpers (SPOT: one place to change extraction logic)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tenant_id(request: Request) -> str | None:
        """Extract ``tenant_id`` from JWT ``tnt`` claim or ``X-Tenant-Id`` header.

        Precedence (anti-spoofing, JD-01):
          1. JWT ``tnt`` claim (``request.state.tenant_claim``) is AUTHORITATIVE
             when present. The client-controlled ``X-Tenant-Id`` header is
             ignored so a tenant_A JWT cannot impersonate tenant_B via the
             header.
          2. If a JWT authenticated the user (``request.state.user_sub`` is set)
             but carries no ``tnt`` claim, the header is STILL NOT trusted: the
             request is JWT-authenticated, so a client-supplied tenant would be a
             spoofing vector. Returns ``None`` so ``resolve_user_id`` fails fast
             (UserIdentityResolutionError -> 500) instead of trusting the header.
          3. Only when NO JWT is active (no ``user_sub``) is ``X-Tenant-Id`` the
             legitimate tenant source (local dev, integration tests, non-JWT
             setups).

        The middleware cannot read AgentOS' ``authorization`` flag, so JWT
        activity is inferred from ``user_sub`` (the validated ``sub`` claim),
        which the JWT middleware stamps on ``request.state``.

        Args:
            request: Incoming request.

        Returns:
            The tenant_id string, or ``None`` if no trustworthy source is
            present (``resolve_user_id`` then raises to avoid a NULL bucket).
        """
        jwt_tenant: str | None = getattr(request.state, "tenant_claim", None)
        if jwt_tenant:
            # JWT provided an authoritative tenant claim -> ignore the header.
            return jwt_tenant
        # No tenant in the JWT. If a JWT authenticated a user, the request is
        # JWT-authenticated and the client-controlled header MUST NOT be trusted
        # as a tenant source (would allow cross-tenant impersonation). Fail fast
        # rather than fall through to the header.
        if getattr(request.state, "user_sub", None):
            return None
        # No JWT active: X-Tenant-Id is the legitimate tenant source.
        return request.headers.get("X-Tenant-Id")

    @staticmethod
    def _extract_raw_user_id(request: Request) -> str | None:
        """Extract the principal (raw user id) from the JWT ``sub`` claim.

        When AgentOS JWT middleware is active, the validated ``sub`` claim is
        available on ``request.state``. Without JWT auth (local dev, integration
        tests), this returns ``None`` and ``resolve_user_id`` falls back to
        ``memory_cfg.system_user_id``.

        Args:
            request: Incoming request.

        Returns:
            The raw user id string, or ``None`` if no JWT ``sub`` claim.
        """
        return getattr(request.state, "user_sub", None)
