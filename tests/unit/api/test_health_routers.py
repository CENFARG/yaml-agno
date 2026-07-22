"""Unit tests for the liveness and readiness factory routers.

Slice A of SPEC_06. The factory routers mirror
``agno/os/routers/health.py:get_health_router`` in shape and return an
``APIRouter`` whose handlers expose the liveness and readiness probes.

Slice A readiness is intentionally a no-op gate: it returns ``ready`` with an
empty ``checks`` map. The real Postgres ping lands with SPEC_03 B-E; until then
the route MUST NOT fabricate a fake ``{"postgres": ...}`` entry.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from yaml_agno.api.health import (
    LivenessResponse,
    ReadinessResponse,
    get_liveness_router,
    get_readiness_router,
)

pytestmark = pytest.mark.unit


class TestLivenessRouter:
    """RED→GREEN tests for ``get_liveness_router()``."""

    def test_factory_returns_api_router(self) -> None:
        """Scenario: factory returns a FastAPI APIRouter."""
        router = get_liveness_router()
        assert isinstance(router, APIRouter)

    def test_liveness_endpoint_returns_alive_response(self) -> None:
        """Scenario 6: GET /health/liveness returns 200 and {"status": "alive"}."""
        app = FastAPI()
        app.include_router(get_liveness_router())
        client = TestClient(app)

        response = client.get("/health/liveness")

        assert response.status_code == 200
        body = response.json()
        assert body == {"status": "alive"}

    def test_liveness_response_model_shape(self) -> None:
        """Scenario: LivenessResponse Pydantic model has a ``status`` field."""
        model = LivenessResponse(status="alive")
        assert model.status == "alive"


class TestReadinessRouter:
    """RED→GREEN tests for ``get_readiness_router()``."""

    def test_factory_returns_api_router(self) -> None:
        """Scenario: factory returns a FastAPI APIRouter."""
        router = get_readiness_router()
        assert isinstance(router, APIRouter)

    def test_readiness_endpoint_returns_ready_with_empty_checks(self) -> None:
        """Scenario 7: GET /health/readiness returns 200, status "ready", empty checks.

        Slice A gate is intentionally a no-op: the real Postgres ping arrives
        with SPEC_03. The route MUST NOT fake a ``postgres`` check.
        """
        app = FastAPI()
        app.include_router(get_readiness_router())
        client = TestClient(app)

        response = client.get("/health/readiness")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"] == {}

    def test_readiness_response_model_shape(self) -> None:
        """Scenario: ReadinessResponse Pydantic model has status + checks fields."""
        model = ReadinessResponse(status="ready", checks={})
        assert model.status == "ready"
        assert model.checks == {}
