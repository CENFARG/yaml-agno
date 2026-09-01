"""Unit tests for VQ010 refuse-to-start contract in run_server (SPEC_06, S5a.1 WU3).

Verifies that ``run_server`` (the production entry point) strictly enforces VQ010:
- Refuses to start (raises ``RuntimeError``) when ``authorization=True`` is not passed.
- Refuses before building the app or attempting to resolve agent sources.
- Refuses (raises ``RuntimeError``) BEFORE ``create_app`` when ``authorization=True``
  is not paired with an ``authorization_config`` whose ``user_isolation`` is
  strictly ``True`` (auth-vq010-isolation-guard, WU3 defense-in-depth).
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


def _assert_vq010_runtime_error(
    exc_info: pytest.ExceptionInfo[RuntimeError],
) -> None:
    """Shared assertion: a RuntimeError refusal names VQ010 + user_isolation."""
    message = str(exc_info.value)
    assert "VQ010" in message
    assert "user_isolation" in message


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


# ═══════════════════════════════════════════════════════════════════════════
# VQ010 — isolation refusal (auth-vq010-isolation-guard, WU3)
# ═══════════════════════════════════════════════════════════════════════════


class TestRunServerIsolationGuard:
    """VQ010: run_server refuses authenticated-but-unisolated startup.

    Defense-in-depth: the isolation predicate runs in ``run_server`` BEFORE
    ``create_app`` (a ``RuntimeError`` naming VQ010 proves the refusal
    happened pre-build; a ``ValueError`` from ``YamlAgentOS`` would prove it
    happened too late, and ``FileNotFoundError`` would prove it never ran).
    """

    def test_run_server_refuses_missing_config(self) -> None:
        """(True, authorization_config=None) → RuntimeError VQ010, never FileNotFoundError."""
        with pytest.raises(RuntimeError, match="VQ010") as exc_info:
            run_server(
                config_path="/nonexistent/path/that/does/not/exist.yaml",
                authorization=True,
                authorization_config=None,
                server_factory=FakeServer,
            )

        assert not isinstance(exc_info.value, FileNotFoundError)
        _assert_vq010_runtime_error(exc_info)

    @pytest.mark.parametrize(
        "user_isolation",
        [False, None],
        ids=["explicit-false", "implicit-default"],
    )
    def test_run_server_refuses_non_isolated_config(
        self, user_isolation: bool | None
    ) -> None:
        """(True, user_isolation=False/unset) → RuntimeError VQ010 pre-create_app."""
        agent = _build_test_agent()
        authorization_config = (
            AuthorizationConfig(user_isolation=user_isolation)
            if user_isolation is not None
            else AuthorizationConfig()
        )

        assert authorization_config.user_isolation is not True

        with pytest.raises(RuntimeError, match="VQ010") as exc_info:
            run_server(
                agents=[agent],
                authorization=True,
                authorization_config=authorization_config,
                mount_tenant_context=False,
                server_factory=FakeServer,
            )

        _assert_vq010_runtime_error(exc_info)

    def test_run_server_rejects_truthy_authorization(self) -> None:
        """authorization='true' → RuntimeError VQ010 (only ``is True`` passes)."""
        agent = _build_test_agent()

        with pytest.raises(RuntimeError, match="VQ010") as exc_info:
            run_server(
                agents=[agent],
                authorization="true",  # type: ignore[arg-type]
                authorization_config=AuthorizationConfig(user_isolation=True),
                server_factory=FakeServer,
            )

        _assert_vq010_runtime_error(exc_info)

    def test_run_server_boots_valid_isolated_config(
        self, authorization_config: AuthorizationConfig
    ) -> None:
        """(True, user_isolation=True) → constructs, FakeServer.run() exactly once."""
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
        assert server.run_count == 1
