"""TenantContextMiddleware: dev-only composite user_id resolver (SPEC_06 §3.2, S5a.1).

In dev mode (``authorization=False`` and ``mount_tenant_context=True``), this
middleware extracts ``tenant_id`` from the ``X-Tenant-Id`` header and DELEGATES
composite construction to the shared ``resolve_user_id()`` (SPEC_04 §1.4) so that
the composite format lives in ONE place.

In production JWT mode (``authorization=True``), this middleware is NOT mounted
(JD-01 structural mutual exclusion). Agno 2.8.7's native ``AuthMiddleware`` validates
the JWT and stamps ``request.state.user_id`` directly from the composite ``sub``
claim, and ``user_isolation=True`` scopes native operations.

@ai-directive: this middleware is for dev/non-JWT paths only. It extracts
``tenant_id`` from the ``X-Tenant-Id`` header, then DELEGATES to the shared
``resolve_user_id()`` (SPEC_04) to build the composite. It does NOT construct
``f"{tenant_id}:{raw_user_id}"`` inline — ``resolve_user_id`` is the single source
of truth for the composite format. It does NOT add a ``tenant_id`` column to
``agno_*`` tables (Agno does not support one), does NOT apply Postgres RLS, and
does NOT open a DB session. Per SPEC_03 §5 and SPEC_04 §3.3: tenant isolation of
yaml-agno's OWN config rows is explicit WHERE filters on ``yamlagno_*`` tables;
``tenant_id`` on ``agno_*`` tables is the composite ``user_id`` only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from yaml_agno.memory.user_identity import (  # SPEC_04 §1.4
    UserIdentityResolutionError,
    resolve_user_id,
)

__all__ = ["TenantContextMiddleware"]


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Set ``request.state.user_id`` to the composite ``"{tenant_id}:{principal_id}"``.

    This middleware extracts ``tenant_id`` from the ``X-Tenant-Id`` header, then
    DELEGATES to the shared ``resolve_user_id()`` (SPEC_04) to build the
    composite. The composite format lives ONLY in ``resolve_user_id``; this
    middleware never builds ``f"{tenant_id}:{raw_user_id}"`` inline.

    Used ONLY in dev/non-JWT mode. Mutually exclusive with JWT authorization
    (JD-01).

    Attributes:
        memory_cfg: YAML ``memory:`` block (SPEC_02 *Config). Carries
            ``system_user_id`` used by ``resolve_user_id`` as the principal.
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

        A missing/empty tenant_id is an authentication failure: the
        composite user_id cannot be built and a NULL bucket must never
        reach Agno. ``resolve_user_id`` raises
        ``UserIdentityResolutionError`` in that case. Because this
        middleware inherits ``BaseHTTPMiddleware``, the exception would
        surface as a raw 500 — it never reaches FastAPI's
        ``ExceptionMiddleware`` where ``@app.exception_handler`` lives.
        We catch it HERE and return 401 with a structured JSON body.
        ``get_app()`` also registers a handler as defense-in-depth.

        Args:
            request: Incoming request carrying ``X-Tenant-Id`` header.
            call_next: Next ASGI handler.

        Returns:
            The downstream response, or a 401 ``JSONResponse`` when the
            tenant cannot be resolved.
        """
        tenant_id = self._extract_tenant_id(request)

        # Single source of truth: resolve_user_id (SPEC_04) builds the
        # composite and fails fast if tenant_id is missing. Never None.
        try:
            request.state.user_id = resolve_user_id(
                memory_cfg=self.memory_cfg,
                principal_id=None,
                tenant_id=tenant_id,
                context=None,
            )
        except UserIdentityResolutionError as exc:
            return JSONResponse(
                status_code=401,
                content={"detail": str(exc)},
            )
        return await call_next(request)

    # ------------------------------------------------------------------
    # Extraction helpers (SPOT: one place to change extraction logic)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tenant_id(request: Request) -> str | None:
        """Extract ``tenant_id`` from ``X-Tenant-Id`` header.

        In dev mode (``authorization=False``), the ``X-Tenant-Id`` header is
        the legitimate tenant source for local development and test setups.

        Args:
            request: Incoming request.

        Returns:
            The tenant_id string from the header, or ``None`` if not present
            (``resolve_user_id`` then raises to avoid a NULL bucket).
        """
        return request.headers.get("X-Tenant-Id")
