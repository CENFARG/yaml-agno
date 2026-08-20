"""Integration tests for the runtime server entry point (SPEC_06 slice A).

Covers Scenarios 10 and 11 of the slice-A spec: ``create_app`` returns a FastAPI
app with the native route surface, and ``run_server`` constructs a uvicorn server
via an injectable factory and invokes ``.run()`` exactly once.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agno.agent import Agent
from agno.os.config import AuthorizationConfig
from fastapi import FastAPI

from yaml_agno.runtime.server import create_app, run_server

pytestmark = [pytest.mark.integration]


def _build_test_agent(name: str = "runtime-agent") -> Agent:
    return Agent(name=name, model="openai:gpt-4o")


class TestCreateApp:
    """RED→GREEN tests for ``runtime.create_app``."""

    def test_create_app_returns_fastapi_app(self) -> None:
        """Scenario 10: ``create_app`` returns a fastapi.FastAPI instance."""
        agent = _build_test_agent()

        app = create_app(agents=[agent])

        assert isinstance(app, FastAPI)

    def test_create_app_exposes_native_run_route(self) -> None:
        """Scenario 10: the returned app exposes native POST /agents/{agent_id}/runs."""
        agent = _build_test_agent()
        app = create_app(agents=[agent])

        pairs: set[tuple[str, str]] = set()
        for route in app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path is None or methods is None:
                continue
            for method in methods:
                pairs.add((path, method))

        assert ("/agents/{agent_id}/runs", "POST") in pairs

    def test_create_app_with_config_path_builds_agents(self, tmp_path: Path) -> None:
        """Scenario 10: ``create_app(config_path=...)`` builds agents from YAML.

        Verified by hitting the inherited ``GET /agents`` endpoint, which Agno
        populates from the agents list forwarded to ``super().__init__``.
        In dev mode, requests pass an ``X-Tenant-Id`` header and the app is
        configured with a ``memory_cfg`` principal fallback.
        """
        from fastapi.testclient import TestClient

        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(
            """
- name: runtime-yaml-agent
  model: openai:gpt-4o
            """.strip(),
            encoding="utf-8",
        )

        app = create_app(
            config_path=str(yaml_file),
            memory_cfg=SimpleNamespace(system_user_id="dev-user"),
        )

        assert isinstance(app, FastAPI)
        client: Any = TestClient(app)
        response = client.get("/agents", headers={"X-Tenant-Id": "dev-tenant"})

        assert response.status_code == 200
        agent_names = {entry["name"] for entry in response.json()}
        assert "runtime-yaml-agent" in agent_names


class TestRunServer:
    """RED→GREEN tests for ``runtime.run_server`` with injectable factory."""

    def test_run_server_uses_injected_server_factory(
        self, authorization_config: AuthorizationConfig
    ) -> None:
        """Scenario 11: ``server_factory`` is invoked once with app + host + port."""
        captured: dict[str, Any] = {}

        class FakeServer:
            def __init__(self, app: FastAPI, host: str, port: int) -> None:
                captured["app"] = app
                captured["host"] = host
                captured["port"] = port
                self.run_count = 0

            def run(self) -> None:
                self.run_count += 1
                captured["run_count"] = self.run_count

        def fake_factory(app: FastAPI, host: str, port: int) -> FakeServer:
            return FakeServer(app=app, host=host, port=port)

        agent = _build_test_agent()

        run_server(
            agents=[agent],
            host="127.0.0.1",
            port=0,
            server_factory=fake_factory,
            authorization=True,
            authorization_config=authorization_config,
            mount_tenant_context=False,
        )

        assert isinstance(captured["app"], FastAPI)
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 0
        assert captured.get("run_count") == 1
