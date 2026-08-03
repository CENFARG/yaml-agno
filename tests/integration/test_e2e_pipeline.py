"""E2E pipeline integration tests for yaml-agno.

Exercises the full YAML → Config → Factory → AgentOS → FastAPI → middleware
stack in a single file. Each test validates one vertical slice of the pipeline.

Covers:
    1. YAML → AgentConfig → AgentFactory.build() → agno.Agent
    2. YAML → YamlAgentOS(config_path=) → get_app() → FastAPI
    3. Health endpoints: /health, /health/liveness, /health/readiness
    4. TenantContextMiddleware: X-Tenant-Id header → composite user_id
    5. AgentOSConfig → to_agno_kwargs() → kwargs dict
    6. InterfaceSpec(A2A) → A2AInterfaceConfig → A2AInterfaceFactory
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from agno.agent import Agent
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yaml_agno.agentos.a2a_interface import (
    A2AInterfaceConfig,
    A2AInterfaceFactory,
    A2APrefix,
)
from yaml_agno.agentos.interfaces import InterfaceRegistry, InterfaceSpec
from yaml_agno.api.app import YamlAgentOS
from yaml_agno.factories.agent_factory import AgentFactory
from yaml_agno.models.config.agent_config import AgentConfig
from yaml_agno.models.config.agentos_config import AgentOSConfig

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


def _build_test_agent(name: str = "e2e-pipeline-agent") -> Agent:
    """Build a minimal agno.Agent for pipeline tests."""
    return Agent(name=name, model="openai:gpt-4o")


# ═══════════════════════════════════════════════════════════════════════════
# Test Classes
# ═══════════════════════════════════════════════════════════════════════════


class TestYamlToAgentPipeline:
    """1. YAML definition → AgentConfig → AgentFactory.build() → agno.Agent."""

    def test_full_yaml_to_agent(self, tmp_path: Path) -> None:
        """Parse a YAML agent definition through the full build pipeline."""
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(
            """
name: e2e-yaml-agent
model: openai:gpt-4o
instructions: You are a test agent.
description: E2E pipeline test agent
            """.strip(),
            encoding="utf-8",
        )

        # 1. Read YAML
        with yaml_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        # 2. Validate → AgentConfig (SPEC_02)
        cfg = AgentConfig.model_validate(data)
        assert cfg.name == "e2e-yaml-agent"
        assert cfg.model == "openai:gpt-4o"
        assert cfg.instructions == "You are a test agent."
        assert cfg.description == "E2E pipeline test agent"

        # 3. Build → agno.Agent (SPEC_01)
        agent = AgentFactory.build(cfg)
        assert isinstance(agent, Agent)
        assert agent.name == "e2e-yaml-agent"
        # Agno 2.8+ resolves model strings to Model instances; the id
        # field carries the model identifier from the provider:id string.
        assert agent.model.id == "gpt-4o"

    def test_yaml_validation_rejects_invalid(self, tmp_path: Path) -> None:
        """Invalid YAML raises pydantic.ValidationError at the boundary."""
        yaml_file = tmp_path / "bad_agent.yaml"
        yaml_file.write_text(
            """
name: invalid!name
model: broken-format
            """.strip(),
            encoding="utf-8",
        )

        with yaml_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        with pytest.raises(ValueError):  # pydantic.ValidationError extends ValueError
            AgentConfig.model_validate(data)


class TestYamlAgentOSFullApp:
    """2. YAML → YamlAgentOS(config_path=) → get_app() → FastAPI with routes."""

    def test_config_path_builds_full_app(self, tmp_path: Path) -> None:
        """A YAML file with two agents produces a FastAPI app with all routes."""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(
            """
- name: e2e-os-agent-1
  model: openai:gpt-4o
- name: e2e-os-agent-2
  model: openai:gpt-4o
            """.strip(),
            encoding="utf-8",
        )

        os_app = YamlAgentOS(config_path=str(yaml_file))
        app = os_app.get_app()

        assert isinstance(app, FastAPI)

        pairs = _route_paths_and_methods(app)

        # Native Agno routes (inherited from AgentOS)
        assert ("/health", "GET") in pairs
        assert ("/agents", "GET") in pairs
        assert ("/agents/{agent_id}/runs", "POST") in pairs

        # yaml-agno health extensions (SPEC_06 slice A)
        assert ("/health/liveness", "GET") in pairs
        assert ("/health/readiness", "GET") in pairs

    def test_agents_endpoint_lists_yaml_agents(self, tmp_path: Path) -> None:
        """GET /agents returns the agents declared in the YAML file."""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(
            """
- name: e2e-os-agent-1
  model: openai:gpt-4o
- name: e2e-os-agent-2
  model: openai:gpt-4o
            """.strip(),
            encoding="utf-8",
        )

        os_app = YamlAgentOS(
            config_path=str(yaml_file),
            mount_tenant_context=False,
        )
        app = os_app.get_app()
        client: Any = TestClient(app)

        response = client.get("/agents")
        assert response.status_code == 200

        agent_names = {entry["name"] for entry in response.json()}
        assert "e2e-os-agent-1" in agent_names
        assert "e2e-os-agent-2" in agent_names


class TestHealthEndpoints:
    """3. GET /health, /health/liveness, /health/readiness return 200.

    Tenant context middleware is disabled for these tests — they validate
    the health route surface, not the middleware stack.
    """

    def test_native_health_responds(self) -> None:
        """GET /health (native Agno) returns 200."""
        agent = _build_test_agent("health-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=False,
        ).get_app()
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200

    def test_liveness_responds_alive(self) -> None:
        """GET /health/liveness returns {"status": "alive"}."""
        agent = _build_test_agent("liveness-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=False,
        ).get_app()
        client = TestClient(app)

        response = client.get("/health/liveness")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_readiness_responds_ready_with_empty_checks(self) -> None:
        """GET /health/readiness returns ready with empty checks (slice A)."""
        agent = _build_test_agent("readiness-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=False,
        ).get_app()
        client = TestClient(app)

        response = client.get("/health/readiness")
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"] == {}


class TestTenantContextMiddleware:
    """4. TenantContextMiddleware: X-Tenant-Id → composite user_id."""

    def test_valid_tenant_header_passes_through(self) -> None:
        """X-Tenant-Id + memory_cfg.system_user_id → 200 (user_id resolved)."""
        memory_cfg = SimpleNamespace(system_user_id="system")
        agent = _build_test_agent("tenant-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=True,
            memory_cfg=memory_cfg,
        ).get_app()
        client = TestClient(app)

        response = client.get(
            "/health/liveness",
            headers={"X-Tenant-Id": "org-42"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_missing_tenant_header_returns_401(self) -> None:
        """No X-Tenant-Id and no memory_cfg → 401 Unauthorized."""
        agent = _build_test_agent("tenant-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=True,
            # No memory_cfg → resolve_user_id fails on missing tenant_id
        ).get_app()
        client = TestClient(app)

        response = client.get("/health/liveness")
        assert response.status_code == 401

        body = response.json()
        assert "detail" in body

    def test_tenant_header_without_system_user_id_returns_401(self) -> None:
        """X-Tenant-Id present but no memory_cfg.system_user_id → 401."""
        agent = _build_test_agent("tenant-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=True,
            # memory_cfg is None → resolve_user_id has no fallback principal
        ).get_app()
        client = TestClient(app)

        response = client.get(
            "/health/liveness",
            headers={"X-Tenant-Id": "org-42"},
        )
        # tenant_id resolves from header, but principal_id is None
        # and memory_cfg=None has no system_user_id → UserIdentityResolutionError
        assert response.status_code == 401

    def test_middleware_skipped_when_mount_tenant_context_false(self) -> None:
        """mount_tenant_context=False → requests pass without tenant header."""
        agent = _build_test_agent("no-tenant-agent")
        app = YamlAgentOS(
            agents=[agent],
            mount_tenant_context=False,
        ).get_app()
        client = TestClient(app)

        response = client.get("/health/liveness")
        # Middleware not mounted → no tenant requirement
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


class TestAgentOSConfigPipeline:
    """5. AgentOSConfig → to_agno_kwargs() → valid kwargs dict."""

    def test_minimal_config_produces_valid_kwargs(self) -> None:
        """A minimal AgentOSConfig with one agent produces correct kwargs."""
        cfg = AgentOSConfig(
            name="e2e-agentos",
            agents=["researcher"],
        )

        kwargs = cfg.to_agno_kwargs()

        # Identity carried through
        assert kwargs["name"] == "e2e-agentos"
        # Ref lists preserved as-is (resolution happens in AgentOSFactory)
        assert kwargs["agents"] == ["researcher"]
        assert kwargs["teams"] == []
        assert kwargs["workflows"] == []
        # Default feature flags
        assert kwargs["auto_provision_dbs"] is True
        assert kwargs["tracing"] is False
        assert kwargs["a2a_interface"] is False
        # Nested settings serialized
        assert isinstance(kwargs["authorization"], dict)
        assert kwargs["authorization"]["enabled"] is False
        assert isinstance(kwargs["mcp"], dict)
        assert kwargs["mcp"]["enabled"] is False
        assert isinstance(kwargs["scheduler"], dict)
        assert kwargs["scheduler"]["enabled"] is False
        assert isinstance(kwargs["resync"], dict)
        assert kwargs["resync"]["enabled"] is False

    def test_rejects_empty_targets(self) -> None:
        """AgentOSConfig with no agents, teams, or workflows fails validation."""
        with pytest.raises(
            ValueError,
            match="at least one of agents, teams, or workflows",
        ):
            AgentOSConfig(name="empty-targets")

    def test_rejects_cors_wildcard_with_rbac(self) -> None:
        """CORS wildcard '*' is forbidden when authorization is enabled."""
        with pytest.raises(
            ValueError,
            match="CORS wildcard",
        ):
            AgentOSConfig(
                name="rbac-agentos",
                agents=["researcher"],
                authorization={"enabled": True},
                cors_allowed_origins=["*"],
            )


class TestInterfaceRegistryA2APipeline:
    """6. InterfaceSpec(A2A) → A2AInterfaceConfig → A2AInterfaceFactory."""

    def test_spec_validation_a2a_no_target_required(self) -> None:
        """A2A InterfaceSpec does not require a target (set-based dispatch)."""
        spec = InterfaceSpec(type="a2a")
        assert spec.type == "a2a"
        assert spec.target is None

    def test_spec_rejects_non_a2a_without_target(self) -> None:
        """Non-A2A interface types require a target."""
        for iface_type in ("slack", "whatsapp", "telegram", "agui"):
            with pytest.raises(ValueError, match="target is required"):
                InterfaceSpec(type=iface_type)

    def test_a2a_config_requires_at_least_one_component(self) -> None:
        """A2AInterfaceConfig must have at least one agent, team, or workflow."""
        # Valid: at least one agent
        config = A2AInterfaceConfig(agents=["researcher"])
        assert config.agents == ["researcher"]
        assert config.prefix.value == "/a2a"

        # Invalid: empty
        with pytest.raises(ValueError, match="at least one agent"):
            A2AInterfaceConfig()

    def test_a2a_config_all_refs_groups_by_kind(self) -> None:
        """all_refs() returns declared refs grouped by component kind."""
        config = A2AInterfaceConfig(
            agents=["researcher", "writer"],
            teams=["review-team"],
            workflows=["pipeline-wf"],
        )

        refs = config.all_refs()
        assert refs["agents"] == ["researcher", "writer"]
        assert refs["teams"] == ["review-team"]
        assert refs["workflows"] == ["pipeline-wf"]

    def test_a2a_prefix_must_start_with_slash(self) -> None:
        """A2APrefix must start with '/'."""
        # Valid
        prefix = A2APrefix(value="/custom-a2a")
        assert prefix.value == "/custom-a2a"

        # Invalid: no leading slash
        with pytest.raises(ValueError):
            A2APrefix(value="a2a")

    def test_a2a_interface_factory_exists(self) -> None:
        """A2AInterfaceFactory is instantiable (no deps required)."""
        factory = A2AInterfaceFactory()
        assert factory is not None

    def test_interface_registry_has_a2a_builder(self) -> None:
        """InterfaceRegistry includes A2A in its builder dispatch map."""
        registry = InterfaceRegistry()
        # Public API: InterfaceType enum carries the dispatched types
        from yaml_agno.agentos.interfaces import InterfaceType

        assert InterfaceType.A2A in registry._builders
