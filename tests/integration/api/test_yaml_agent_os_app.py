"""Integration tests for ``YamlAgentOS.get_app()`` (SPEC_06 slice A).

Contract tests that the overridden ``get_app()`` returns a FastAPI app exposing
the native Agno router surface AND the slice-A health extensions. The native
routes are INHERITED via ``super().get_app()``; yaml-agno MUST NOT shadow or
duplicate any of them.
"""

from __future__ import annotations

from typing import Any

import pytest
from agno.agent import Agent
from fastapi import FastAPI

from yaml_agno.api.app import YamlAgentOS

pytestmark = [pytest.mark.integration]


def _route_paths_and_methods(app: FastAPI) -> set[tuple[str, str]]:
    """Collect (path, method) tuples for every mounted route."""
    pairs: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None:
            continue
        for method in methods:
            pairs.add((path, method))
    return pairs


def _build_test_agent(name: str = "integration-agent") -> Agent:
    return Agent(name=name, model="openai:gpt-4o")


class TestYamlAgentOSGetApp:
    """RED→GREEN contract tests for ``get_app()`` route surface."""

    def test_get_app_returns_fastapi_instance(self) -> None:
        """Scenario 4: ``get_app()`` returns a fastapi.FastAPI instance."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(agents=[agent])

        app = os_app.get_app()

        assert isinstance(app, FastAPI)

    def test_get_app_exposes_native_run_route(self) -> None:
        """Scenario 4: native POST /agents/{agent_id}/runs is inherited."""
        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent]).get_app()

        pairs = _route_paths_and_methods(app)

        assert ("/agents/{agent_id}/runs", "POST") in pairs

    def test_get_app_exposes_native_health_route(self) -> None:
        """Scenario 4: native GET /health is inherited."""
        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent]).get_app()

        pairs = _route_paths_and_methods(app)

        assert ("/health", "GET") in pairs

    def test_get_app_exposes_native_agents_list_route(self) -> None:
        """Scenario 4: native GET /agents is inherited."""
        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent]).get_app()

        pairs = _route_paths_and_methods(app)

        assert ("/agents", "GET") in pairs

    def test_get_app_mounts_health_extensions_by_default(self) -> None:
        """Scenario 5: ``mount_health=True`` (default) adds liveness + readiness."""
        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent]).get_app()

        pairs = _route_paths_and_methods(app)

        assert ("/health/liveness", "GET") in pairs
        assert ("/health/readiness", "GET") in pairs

    def test_get_app_skips_health_when_mount_health_false(self) -> None:
        """Scenario 5: ``mount_health=False`` skips both extension routes."""
        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent], mount_health=False).get_app()

        pairs = _route_paths_and_methods(app)

        assert ("/health/liveness", "GET") not in pairs
        assert ("/health/readiness", "GET") not in pairs

    def test_get_app_does_not_duplicate_native_run_route(self) -> None:
        """Scenario: exactly one POST /agents/{agent_id}/runs route (no yaml-agno duplicate)."""
        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent]).get_app()

        pairs = _route_paths_and_methods(app)

        run_routes = [p for p in pairs if p == ("/agents/{agent_id}/runs", "POST")]
        assert len(run_routes) == 1

    def test_get_app_end_to_end_liveness_request(self) -> None:
        """Scenario 6 (end-to-end): GET /health/liveness via TestClient returns alive."""
        from fastapi.testclient import TestClient

        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent], mount_tenant_context=False).get_app()
        client = TestClient(app)

        response = client.get("/health/liveness")

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_get_app_end_to_end_readiness_request(self) -> None:
        """Scenario 7 (end-to-end): GET /health/readiness returns ready with empty checks."""
        from fastapi.testclient import TestClient

        agent = _build_test_agent()
        app = YamlAgentOS(agents=[agent], mount_tenant_context=False).get_app()
        client: Any = TestClient(app)

        response = client.get("/health/readiness")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"] == {}
