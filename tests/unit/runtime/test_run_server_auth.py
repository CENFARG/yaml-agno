"""Unit tests for VQ010 refuse-to-start contract in run_server (SPEC_06, S5a.1 WU3).

Verifies that ``run_server`` (the production entry point) strictly enforces VQ010:
- Refuses to start (raises ``RuntimeError``) when ``authorization=True`` is not passed.
- Refuses before building the app or attempting to resolve agent sources.
- Passes the guard and invokes the injected ``server_factory`` when ``authorization=True``
  is provided with a valid ``authorization_config``.
"""

from __future__ import annotations

from typing import Any

import pytest
from agno.agent import Agent
from agno.os.config import AuthorizationConfig
from fastapi import FastAPI

from yaml_agno.runtime.server import run_server

pytest_plugins = ["tests.integration.helpers.conftest"]
pytestmark = pytest.mark.unit


def _build_test_agent(name: str = "runtime-auth-agent") -> Agent:
    """Build a minimal real agno.Agent for test fixtures."""
    return Agent(name=name, model="openai:gpt-4o")


class FakeServer:
    """Fake uvicorn.Server for capturing run_server invocations."""

    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        self.app = app
        self.host = host
        self.port = port
        self.run_count = 0

    def run(self) -> None:
        self.run_count += 1


class TestRunServerAuthGuard:
    """VQ010 refuse-to-start contract tests for ``run_server``."""

    def test_run_server_refuses_without_authorization_kwarg(self) -> None:
        """VQ010: run_server without authorization raises RuntimeError."""
        agent = _build_test_agent()
        with pytest.raises(
            RuntimeError,
            match=r"authorization.*True|refuses to start|VQ010",
        ):
            run_server(agents=[agent], server_factory=FakeServer)

    def test_run_server_refuses_with_authorization_false(self) -> None:
        """VQ010: run_server with authorization=False raises RuntimeError."""
        agent = _build_test_agent()
        with pytest.raises(
            RuntimeError,
            match=r"authorization.*True|refuses to start|VQ010",
        ):
            run_server(agents=[agent], authorization=False, server_factory=FakeServer)

    def test_run_server_refuses_before_building_or_reading_config(self) -> None:
        """Refusal guard executes as the FIRST statement before any building.

        Even with a non-existent config path, RuntimeError is raised first,
        never FileNotFoundError.
        """
        with pytest.raises(RuntimeError, match=r"authorization.*True|refuses to start|VQ010"):
            run_server(
                config_path="/nonexistent/path/that/does/not/exist.yaml",
                server_factory=FakeServer,
            )

    def test_run_server_refuses_with_truthy_non_boolean_authorization(self) -> None:
        """Refusal guard requires authorization to be strictly True (boolean)."""
        agent = _build_test_agent()
        with pytest.raises(RuntimeError, match=r"authorization.*True|refuses to start|VQ010"):
            run_server(
                agents=[agent],
                authorization="true",  # type: ignore[arg-type]
                server_factory=FakeServer,
            )

    def test_run_server_allows_authorization_true_and_reaches_factory(
        self, authorization_config: AuthorizationConfig
    ) -> None:
        """With authorization=True, run_server passes guard and calls server.run()."""
        captured: dict[str, Any] = {}

        def fake_factory(app: FastAPI, host: str, port: int) -> FakeServer:
            server = FakeServer(app=app, host=host, port=port)
            captured["server"] = server
            return server

        agent = _build_test_agent()

        run_server(
            agents=[agent],
            authorization=True,
            authorization_config=authorization_config,
            mount_tenant_context=False,
            host="127.0.0.1",
            port=8000,
            server_factory=fake_factory,
        )

        server: FakeServer = captured["server"]
        assert isinstance(server.app, FastAPI)
        assert server.host == "127.0.0.1"
        assert server.port == 8000
        assert server.run_count == 1
