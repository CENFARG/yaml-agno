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
    7. Real team.yaml → AgentFactory + TeamFactory + AgnoResolver + ProviderFactory
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
from yaml_agno.factories.team_factory import TeamFactory
from yaml_agno.models.config.agent_config import AgentConfig
from yaml_agno.models.config.agentos_config import AgentOSConfig
from yaml_agno.models.config.team_config import TeamConfig, TeamMemberConfig
from yaml_agno.di import AgnoResolver, build_agno_resolver, ProviderFactory
from yaml_agno.di.secret_resolver import ConfigSecretResolver

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


# ═══════════════════════════════════════════════════════════════════════════
# 7. Real strategic-gestion-team/team.yaml → full yaml-agno pipeline
# ═══════════════════════════════════════════════════════════════════════════

TEAM_YAML = """\
# Strategic Gestion Team — yaml-agno configuration
# Proof-of-concept: CENF strategic evaluation team as Agno coordinate-mode team.
# Run via: python run_team.py "Evaluar proyecto X"
#
# PROVIDER: OpenRouter (set OPENROUTER_API_KEY env var)
# Model IDs use OpenRouter format: "provider/model-name"

agents:
  - name: strategic-pm
    model: openrouter:deepseek/deepseek-v4-flash
    tool_call_limit: 20
    tools:
      - kind: builtin
        name: duckduckgo
      - kind: custom
        name: read_project_file
      - kind: custom
        name: list_project_files
    description: "Strategic Project Manager — team leader and final decision maker."

  - name: cost-analyst
    model: openrouter:deepseek/deepseek-v4-flash
    tool_call_limit: 10
    tools:
      - kind: builtin
        name: duckduckgo
      - kind: custom
        name: read_project_file
      - kind: custom
        name: list_project_files
    description: "Cost Governance Analyst — token economics and rate limit management."

  - name: fractal-validator
    model: openrouter:deepseek/deepseek-v4-flash
    tool_call_limit: 10
    tools:
      - kind: builtin
        name: duckduckgo
      - kind: custom
        name: read_project_file
      - kind: custom
        name: list_project_files
    description: "Fractal Validator — recursive depth analysis and hidden complexity detection."

  - name: gtm-strategist
    model: openrouter:deepseek/deepseek-v4-flash
    tool_call_limit: 10
    tools:
      - kind: builtin
        name: duckduckgo
      - kind: custom
        name: read_project_file
      - kind: custom
        name: list_project_files
    description: "Go-to-Market Strategist — distribution, growth, and channel strategy."

  - name: risk-officer
    model: openrouter:deepseek/deepseek-v4-flash
    tool_call_limit: 10
    tools:
      - kind: builtin
        name: duckduckgo
      - kind: custom
        name: read_project_file
      - kind: custom
        name: list_project_files
    description: "Risk & Compliance Officer — risk identification, classification, mitigation."

  - name: pmf-analyst
    model: openrouter:deepseek/deepseek-v4-flash
    tool_call_limit: 10
    tools:
      - kind: builtin
        name: duckduckgo
      - kind: custom
        name: read_project_file
      - kind: custom
        name: list_project_files
    description: "Product-Market Fit Analyst — market validation, competitive analysis, pricing."

team:
  name: strategic-gestion-team
  mode: coordinate
  max_iterations: 5
  instructions: |
    Strategic Gestion Team — evaluates project viability, risks, costs, and
    market for CENF projects. Produces actionable strategic decisions.

    The team leader (strategic-pm) coordinates the evaluation by consulting
    each specialist. All members provide their analysis; the leader consolidates
    into a final GO/NO-GO/PENDING decision.
  members:
    - member: leader
      agent: strategic-pm
      role: "Team leader — consolidates and decides"
    - member: cost
      agent: cost-analyst
      role: "Cost analysis and projections"
    - member: validator
      agent: fractal-validator
      role: "Depth validation and complexity assessment"
    - member: gtm
      agent: gtm-strategist
      role: "Go-to-market strategy"
    - member: risk
      agent: risk-officer
      role: "Risk assessment and compliance"
    - member: pmf
      agent: pmf-analyst
      role: "Product-market fit validation"
"""  # noqa: E501


_AGENT_NAMES = [
    "strategic-pm",
    "cost-analyst",
    "fractal-validator",
    "gtm-strategist",
    "risk-officer",
    "pmf-analyst",
]


def _extract_agent_entries(yaml_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract agent entries from the YAML dict, filtering to builtin tools only
    and injecting inline test instructions."""
    entries: list[dict[str, Any]] = []
    for agent in yaml_data["agents"]:
        builtin_tools = [t for t in agent.get("tools", []) if t.get("kind") == "builtin"]
        entries.append({
            "name": agent["name"],
            "model": agent["model"],
            "tool_call_limit": agent.get("tool_call_limit"),
            "description": agent.get("description"),
            "tools": builtin_tools,
            # instructions_file references external files — inline test instructions
            "instructions": f"Test instructions for {agent['name']}.",
        })
    return entries


class TestStrategicGestionTeamE2E:
    """7. Real strategic-gestion-team/team.yaml → full yaml-agno pipeline.

    Validates that the real 6-agent coordinate-mode team can be built
    end-to-end using yaml-agno's AgentFactory, TeamFactory, AgnoResolver,
    and ProviderFactory.
    """

    @pytest.fixture
    def team_data(self) -> dict[str, Any]:
        """Parse the real team.yaml into a dict."""
        return yaml.safe_load(TEAM_YAML)

    @staticmethod
    def _build_agents(
        entries: list[dict[str, Any]],
        resolver: Any | None = None,
        provider_factory: Any | None = None,
    ) -> dict[str, Agent]:
        """Build agents from extracted entries via AgentFactory."""
        agents: dict[str, Agent] = {}
        for entry in entries:
            ac = AgentConfig(
                name=entry["name"],
                model=entry["model"],
                instructions=entry["instructions"],
                description=entry.get("description"),
                tools=entry.get("tools", []),
                tool_call_limit=entry.get("tool_call_limit"),
            )
            agents[entry["name"]] = AgentFactory.build(
                ac,
                resolver=resolver,
                provider_factory=provider_factory,
            )
        return agents

    # ── 7.1 Parse team YAML structure ────────────────────────────────────

    def test_parse_team_yaml_has_six_agents(self, team_data: dict[str, Any]) -> None:
        """The real team.yaml must define exactly 6 agents."""
        assert "agents" in team_data
        assert len(team_data["agents"]) == 6
        parsed_names = {a["name"] for a in team_data["agents"]}
        assert parsed_names == set(_AGENT_NAMES)

    def test_parse_team_yaml_has_coordinate_team(self, team_data: dict[str, Any]) -> None:
        """The real team.yaml must define one team in coordinate mode."""
        assert "team" in team_data
        assert team_data["team"]["name"] == "strategic-gestion-team"
        assert team_data["team"]["mode"] == "coordinate"
        assert len(team_data["team"]["members"]) == 6

    # ── 7.2 Build all 6 agents (model string passthrough) ────────────────

    def test_build_all_six_agents(self, team_data: dict[str, Any]) -> None:
        """Every agent in the team config builds successfully via AgentFactory."""
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        assert len(agents) == 6
        for name in _AGENT_NAMES:
            assert name in agents
            assert isinstance(agents[name], Agent)
            assert agents[name].name == name

    # ── 7.3 Agent model validation ───────────────────────────────────────

    def test_agents_have_openrouter_deepseek_model(
        self, team_data: dict[str, Any]
    ) -> None:
        """Every agent's model is openrouter:deepseek/deepseek-v4-flash.

        Agno resolves the string to a Model instance; we validate the id.
        """
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        for name, agent in agents.items():
            assert isinstance(agent.model, object), f"{name} model is not set"
            model_id = getattr(agent.model, "id", None)
            assert model_id == "deepseek/deepseek-v4-flash", (
                f"{name}: expected deepseek/deepseek-v4-flash, got {model_id}"
            )

    # ── 7.4 Agent tool_call_limit validation ─────────────────────────────

    def test_strategic_pm_has_tool_call_limit_20(
        self, team_data: dict[str, Any]
    ) -> None:
        """The team leader (strategic-pm) must have tool_call_limit=20."""
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        assert agents["strategic-pm"].tool_call_limit == 20

    def test_other_agents_have_tool_call_limit_10(
        self, team_data: dict[str, Any]
    ) -> None:
        """All non-leader agents must have tool_call_limit=10."""
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        for name in _AGENT_NAMES:
            if name == "strategic-pm":
                continue
            assert agents[name].tool_call_limit == 10, (
                f"{name}: expected 10, got {agents[name].tool_call_limit}"
            )

    # ── 7.5 Builtin tools (duckduckgo) via resolver ──────────────────────

    def test_agents_have_duckduckgo_tool_when_resolver_provided(
        self, team_data: dict[str, Any]
    ) -> None:
        """Each agent gets duckduckgo builtin tool when resolver is wired."""
        from yaml_agno.di.agno_resolver import build_agno_resolver

        resolver = build_agno_resolver()
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries, resolver=resolver)

        from agno.tools.duckduckgo import DuckDuckGoTools

        for name, agent in agents.items():
            assert len(agent.tools) >= 1, f"{name}: expected >=1 tool, got {len(agent.tools)}"
            # At least one tool must be DuckDuckGoTools
            duck_tools = [t for t in agent.tools if isinstance(t, DuckDuckGoTools)]
            assert len(duck_tools) >= 1, f"{name}: no DuckDuckGoTools found"

    # ── 7.6 Build team via TeamFactory ───────────────────────────────────

    def test_build_team_with_six_members(
        self, team_data: dict[str, Any]
    ) -> None:
        """TeamFactory.build produces a Team with all 6 members in YAML order."""
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        team_cfg_data = team_data["team"]
        members = [
            TeamMemberConfig(member=m["member"], agent=m["agent"], role=m.get("role"))
            for m in team_cfg_data["members"]
        ]
        tc = TeamConfig(
            name=team_cfg_data["name"],
            mode=team_cfg_data["mode"],
            instructions=team_cfg_data.get("instructions"),
            members=members,
        )

        team = TeamFactory.build(tc, agents)

        assert team.name == "strategic-gestion-team"
        assert len(team.members) == 6
        # Member order matches YAML declaration order
        member_names = [m.name for m in team.members]
        assert member_names == _AGENT_NAMES

    # ── 7.7 Team mode and leader ─────────────────────────────────────────

    def test_team_mode_is_coordinate(
        self, team_data: dict[str, Any]
    ) -> None:
        """The team must operate in coordinate mode."""
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        team_cfg_data = team_data["team"]
        members = [
            TeamMemberConfig(member=m["member"], agent=m["agent"], role=m.get("role"))
            for m in team_cfg_data["members"]
        ]
        tc = TeamConfig(
            name=team_cfg_data["name"],
            mode=team_cfg_data["mode"],
            instructions=team_cfg_data.get("instructions"),
            members=members,
        )

        team = TeamFactory.build(tc, agents)

        from agno.team.mode import TeamMode

        assert team.mode is TeamMode.coordinate

    def test_team_leader_is_strategic_pm(
        self, team_data: dict[str, Any]
    ) -> None:
        """The team leader (first member) must be strategic-pm."""
        entries = _extract_agent_entries(team_data)
        agents = self._build_agents(entries)

        team_cfg_data = team_data["team"]
        members = [
            TeamMemberConfig(member=m["member"], agent=m["agent"], role=m.get("role"))
            for m in team_cfg_data["members"]
        ]
        tc = TeamConfig(
            name=team_cfg_data["name"],
            mode=team_cfg_data["mode"],
            instructions=team_cfg_data.get("instructions"),
            members=members,
        )

        team = TeamFactory.build(tc, agents)

        assert team.members[0].name == "strategic-pm"

    # ── 7.8 Full pipeline with ProviderFactory + AgnoResolver ────────────

    def test_agent_factory_build_with_provider_factory(
        self, team_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AgentFactory.build with resolver + ProviderFactory produces a real
        Agno Model instance with api_key injected for openrouter provider."""
        from core_infrastructure.config.adapters.in_memory_config_adapter import (
            InMemoryConfigAdapter,
        )
        from core_infrastructure.dependency import ImportlibDependencyAdapter
        from core_infrastructure.logger.adapters import InMemoryLoggerAdapter
        from core_infrastructure.observability.adapters import NoopObservabilityAdapter

        from yaml_agno.di.agno_resolver import build_agno_resolver
        from yaml_agno.di.provider_factory import ProviderFactory
        from yaml_agno.di.registries import AGNO_ALLOWLIST_PREFIXES
        from yaml_agno.di.secret_resolver import ConfigSecretResolver
        from yaml_agno.models.model_spec import parse_model_spec, ModelExpandedSpec

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-openrouter")

        cfg = InMemoryConfigAdapter()
        cfg.set_value("dependency.allowlist_paths", list(AGNO_ALLOWLIST_PREFIXES))
        logger = InMemoryLoggerAdapter()
        obs = NoopObservabilityAdapter()
        adapter = ImportlibDependencyAdapter(cfg, logger, obs)
        resolver = build_agno_resolver(adapter=adapter)
        secret_resolver = ConfigSecretResolver(cfg)
        pf = ProviderFactory(resolver, secret_resolver)

        # Build strategic-pm with the full provider_factory pipeline
        entries = _extract_agent_entries(team_data)
        pm_entry = next(e for e in entries if e["name"] == "strategic-pm")

        ac = AgentConfig(
            name=pm_entry["name"],
            model=pm_entry["model"],
            instructions=pm_entry["instructions"],
            description=pm_entry.get("description"),
            tools=pm_entry.get("tools", []),
            tool_call_limit=pm_entry.get("tool_call_limit"),
        )

        agent = AgentFactory.build(ac, resolver=resolver, provider_factory=pf)

        assert isinstance(agent, Agent)
        assert agent.name == "strategic-pm"
        # Model was built by ProviderFactory (real Agno Model instance)
        assert isinstance(agent.model, object)
        assert agent.model.id == "deepseek/deepseek-v4-flash"
        # api_key was injected via SecretResolver → env var
        assert getattr(agent.model, "api_key", None) == "sk-test-openrouter"

        # Verify ProviderFactory resolves the parsed model spec
        parsed = parse_model_spec("openrouter:deepseek/deepseek-v4-flash")
        if not isinstance(parsed, ModelExpandedSpec):
            spec = ModelExpandedSpec.model_validate(parsed.model_dump())
        else:
            spec = parsed
        built_model = pf.build(spec)
        assert built_model.id == "deepseek/deepseek-v4-flash"
        assert built_model.api_key == "sk-test-openrouter"


# ═══════════════════════════════════════════════════════════════════════════
# Helper Registries for AgentOSFactory DI
# ═══════════════════════════════════════════════════════════════════════════


class _DictRegistry:
    """Simple dict-based registry matching AgentRegistry Protocol."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data if data is not None else {}

    def get(self, ref: str) -> Any:
        if ref not in self._data:
            raise KeyError(ref)
        return self._data[ref]


class _DictDBManager:
    """Simple dict-based DB manager matching DatabaseManager Protocol."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data if data is not None else {}

    def get_db(self, ref: str) -> Any:
        if ref not in self._data:
            raise KeyError(ref)
        return self._data[ref]


# ═══════════════════════════════════════════════════════════════════════════
# SPEC_12 Full Pipeline (AgentOSFactory → AgentOS → get_app)
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentOSFullPipeline:
    """AgentOSFactory.build() end-to-end: Config → Factory → AgentOS → FastAPI."""

    def test_full_agentos_pipeline_config_to_app(self) -> None:
        """Build AgentOSConfig, AgentOSFactory, call build(), get AgentOS,
        call get_app(), verify routes."""
        from yaml_agno.factories.agentos_factory import AgentOSFactory

        agent = _build_test_agent("researcher")
        agent_registry = _DictRegistry({"researcher": agent})

        config = AgentOSConfig(
            name="e2e-agentos",
            agents=["researcher"],
        )

        factory = AgentOSFactory(
            agent_registry=agent_registry,
            team_registry=_DictRegistry(),
            workflow_registry=_DictRegistry(),
            knowledge_registry=_DictRegistry(),
            db_manager=_DictDBManager(),
        )

        agentos = factory.build(config)
        app = agentos.get_app()

        assert isinstance(app, FastAPI)

        pairs = _route_paths_and_methods(app)
        assert ("/health", "GET") in pairs
        assert ("/agents", "GET") in pairs

    def test_agentos_config_validators(self) -> None:
        """AgentOSConfig validators: at-least-one-target + CORS wildcard under RBAC."""

        with pytest.raises(
            ValueError,
            match="at least one of agents, teams, or workflows",
        ):
            AgentOSConfig(name="empty-targets")

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

    def test_agentos_with_a2a_interface_in_registry(self) -> None:
        """InterfaceRegistry resolves A2A in its builder dispatch map."""
        from yaml_agno.agentos.interfaces import InterfaceType

        registry = InterfaceRegistry()
        assert InterfaceType.A2A in registry._builders


# ═══════════════════════════════════════════════════════════════════════════
# 8. Production bootstrap pipeline — mirrors agno-teams/strategic-gestion-team
# ═══════════════════════════════════════════════════════════════════════════


class TestProductionBootstrapPipeline:
    """Replicates the EXACT bootstrap pipeline from production.

    References:
        - agno-teams/strategic-gestion-team/bootstrap.py
        - agno-teams/strategic-gestion-team/team_builder.py
    """

    @pytest.fixture
    def team_data(self) -> dict[str, Any]:
        return yaml.safe_load(TEAM_YAML)

    @pytest.fixture
    def resolver(self) -> AgnoResolver:
        """Step 1: build_agno_resolver() — same as bootstrap.py line 81."""
        return build_agno_resolver()

    @pytest.fixture
    def provider_factory(self, resolver: AgnoResolver) -> ProviderFactory:
        """Step 2: ProviderFactory(resolver, ConfigSecretResolver()) — same as
        bootstrap.py lines 82-83."""
        return ProviderFactory(resolver, ConfigSecretResolver())

    @staticmethod
    def _build_agents_with_di(
        team_data: dict[str, Any],
        resolver: AgnoResolver,
        provider_factory: ProviderFactory,
    ) -> dict[str, Agent]:
        """Build all agents from TEAM_YAML with full DI wiring.

        Mirrors TeamBuilder.build_agents() from team_builder.py (lines 54-93),
        minus SQLite DB and custom tools (not available in test context).
        """
        agents: dict[str, Agent] = {}
        for raw_entry in team_data["agents"]:
            builtin_tools = [
                t for t in raw_entry.get("tools", []) if t.get("kind") == "builtin"
            ]
            ac = AgentConfig(
                name=raw_entry["name"],
                model=raw_entry["model"],
                instructions=f"Test instructions for {raw_entry['name']}.",
                description=raw_entry.get("description"),
                tools=builtin_tools,
                tool_call_limit=raw_entry.get("tool_call_limit"),
            )
            agents[raw_entry["name"]] = AgentFactory.build(
                ac, resolver=resolver, provider_factory=provider_factory,
            )
        return agents

    @staticmethod
    def _build_team_from_data(
        team_data: dict[str, Any],
        agents: dict[str, Agent],
    ):
        """Build team from TEAM_YAML with TeamConfig + TeamMemberConfig.

        Mirrors TeamBuilder.build_team() from team_builder.py (lines 96-124),
        minus max_iterations and leader model propagation.
        """
        team_cfg_data = team_data["team"]
        members = [
            TeamMemberConfig(
                member=m["member"], agent=m["agent"], role=m.get("role"),
            )
            for m in team_cfg_data["members"]
        ]
        tc = TeamConfig(
            name=team_cfg_data["name"],
            mode=team_cfg_data["mode"],
            instructions=team_cfg_data.get("instructions"),
            members=members,
        )
        return TeamFactory.build(tc, agents)

    # ── 8.1 DI chain ──────────────────────────────────────────────────────

    def test_production_bootstrap_pipeline_builds_resolver_and_factory(
        self, resolver: AgnoResolver, provider_factory: ProviderFactory,
    ) -> None:
        """build_agno_resolver() returns AgnoResolver; ProviderFactory instantiates."""
        assert isinstance(resolver, AgnoResolver)
        assert isinstance(provider_factory, ProviderFactory)

    # ── 8.2 Build all 6 agents with full DI ───────────────────────────────

    def test_production_bootstrap_builds_all_six_agents(
        self,
        team_data: dict[str, Any],
        resolver: AgnoResolver,
        provider_factory: ProviderFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every agent in the real team config builds via AgentFactory with
        resolver + provider_factory, matching the production pipeline."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-openrouter")

        agents = self._build_agents_with_di(team_data, resolver, provider_factory)

        assert len(agents) == 6
        for name in _AGENT_NAMES:
            assert name in agents
            assert isinstance(agents[name], Agent)
            assert agents[name].name == name
            model_id = getattr(agents[name].model, "id", None)
            assert model_id == "deepseek/deepseek-v4-flash", (
                f"{name}: expected deepseek/deepseek-v4-flash, got {model_id}"
            )

    # ── 8.3 Build coordinate team ─────────────────────────────────────────

    def test_production_bootstrap_builds_coordinate_team(
        self,
        team_data: dict[str, Any],
        resolver: AgnoResolver,
        provider_factory: ProviderFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TeamFactory.build produces a coordinate-mode team with 6 members
        matching the production pipeline."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-openrouter")

        agents = self._build_agents_with_di(team_data, resolver, provider_factory)
        team = self._build_team_from_data(team_data, agents)

        assert team.name == "strategic-gestion-team"

        from agno.team.mode import TeamMode

        assert team.mode is TeamMode.coordinate
        assert len(team.members) == 6

    # ── 8.4 Team is runnable ──────────────────────────────────────────────

    def test_production_pipeline_team_is_runnable(
        self,
        team_data: dict[str, Any],
        resolver: AgnoResolver,
        provider_factory: ProviderFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The full pipeline yields a Team with arun method — structural
        validation that the production team is executable."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-openrouter")

        agents = self._build_agents_with_di(team_data, resolver, provider_factory)
        team = self._build_team_from_data(team_data, agents)

        assert hasattr(team, "arun")
        assert callable(team.arun)
        assert hasattr(team, "name")
        assert team.name == "strategic-gestion-team"
