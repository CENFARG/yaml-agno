"""Liveness and readiness factory routers (SPEC_06 slice A).

Mirrors ``agno/os/routers/health.py:get_health_router`` in shape: each factory
returns an ``APIRouter`` whose handler exposes a Kubernetes-friendly probe.

Slice A scope:

- **Liveness** — process-alive probe. Returns ``{"status": "alive"}``
  unconditionally; Kubernetes restarts the pod on failure.
- **Readiness** — gate probe. Slice A returns ``{"status": "ready", "checks": {}}``
  unconditionally. The real Postgres ping arrives with SPEC_03 B-E; until then
  the route is HONEST about what it can check (nothing) and MUST NOT fabricate
  a fake ``postgres`` entry.

@ai-directive: the readiness route MUST NOT include optional external adapters
in its check set (SPEC_06 §4.1). Slice A's empty ``checks`` map is the correct
placeholder; SPEC_03 will populate the mandatory Postgres check.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

__all__ = [
    "LivenessResponse",
    "ReadinessResponse",
    "get_liveness_router",
    "get_readiness_router",
]


class LivenessResponse(BaseModel):
    """Liveness probe response (process alive?)."""

    status: str = Field(..., description="alive | dead")


class ReadinessResponse(BaseModel):
    """Readiness probe response (ready to receive traffic?).

    Slice A returns ``ready`` unconditionally with an empty ``checks`` map.
    SPEC_03 B-E will populate the mandatory Postgres ping.
    """

    status: str = Field(..., description="ready | not_ready")
    checks: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Per-dependency readiness. Only MANDATORY deps gate status. "
            "Slice A: empty (no deps implemented yet)."
        ),
    )


def get_liveness_router(liveness_endpoint: str = "/health/liveness") -> APIRouter:
    """Build the liveness router (factory, mirrors ``get_health_router``).

    Args:
        liveness_endpoint: Path for the liveness probe.

    Returns:
        An ``APIRouter`` exposing the liveness probe.
    """
    router = APIRouter(tags=["Health"])

    @router.get(
        liveness_endpoint,
        operation_id="liveness_check",
        summary="Liveness Check",
        response_model=LivenessResponse,
    )
    async def liveness_check() -> LivenessResponse:
        """Return liveness; Kubernetes restarts the pod on failure."""
        return LivenessResponse(status="alive")

    return router


def get_readiness_router(
    readiness_endpoint: str = "/health/readiness",
) -> APIRouter:
    """Build the readiness router (factory, mirrors ``get_health_router``).

    Args:
        readiness_endpoint: Path for the readiness probe.

    Returns:
        An ``APIRouter`` exposing the readiness probe.

    @ai-directive: Slice A returns ``ready`` with an empty ``checks`` map. The
    real Postgres ping arrives with SPEC_03 B-E; until then the route MUST NOT
    fabricate a fake ``postgres`` entry. Optional adapters are NEVER part of the
    check set (SPEC_06 §4.1).
    """
    router = APIRouter(tags=["Health"])

    @router.get(
        readiness_endpoint,
        operation_id="readiness_check",
        summary="Readiness Check",
        response_model=ReadinessResponse,
        responses={503: {"description": "Not ready"}},
    )
    async def readiness_check() -> ReadinessResponse:
        """Return readiness; Kubernetes removes the pod from rotation when not ready.

        Slice A: always ready (no mandatory deps implemented yet).
        """
        return ReadinessResponse(status="ready", checks={})

    return router
