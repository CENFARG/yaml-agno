"""Unit tests for ``AgentOSFactory.build`` — SPEC_12 Slice 1, PR 2.

Covers the 7 scenarios from ``sdd/control-plane/design`` §5.2:

    1. Happy path — resolves refs and builds AgentOS
    2. Missing agent ref raises ValueError (fail-fast)
    3. Duplicate agent ref raises ValueError
    4. DB ref resolved via DatabaseManager
    5. Primitives pass through unchanged
    6. None db not forwarded to AgentOS kwargs
    7. Empty target config raises ValueError (validated pre-build)

Strict TDD: RED → GREEN → REFACTOR. Tests written BEFORE implementation.
"""

from __future__ import annotations

import pytest
from agno.os import AgentOS

from yaml_agno.factories.agentos_factory import AgentOSFactory
from yaml_agno.models.config.agentos_config import (
    AgentOSConfig,
    AuthorizationSettings,
    MCPServerSettings,
    SchedulerSettings,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_config() -> AgentOSConfig:
    """Minimal valid config: name + one agent."""
    return AgentOSConfig(name="test-os", agents=["researcher"])


@pytest.fixture
def full_config() -> AgentOSConfig:
    """Config exercising all Slice-1 reachable fields."""
    return AgentOSConfig(
        name="full-os",
        agents=["researcher", "summarizer"],
        teams=["research_team"],
        workflows=["qa_pipeline"],
        db="sqlite_db",
        knowledge=["kb_main"],
        authorization=AuthorizationSettings(enabled=True),
        mcp=MCPServerSettings(enabled=True, name="mcp-srv", port=9090),
        scheduler=SchedulerSettings(enabled=True, poll_interval=30),
        a2a_interface=True,
        cors_allowed_origins=["http://localhost:3000"],
        auto_provision_dbs=False,
        run_hooks_in_background=True,
        tracing=True,
    )


@pytest.fixture
def mock_agent_registry(mocker):
    """Registry that returns a fresh dummy Agent per ref."""
    registry = mocker.Mock()
    registry.get.side_effect = lambda ref: mocker.Mock(name=f"agent:{ref}")
    return registry


@pytest.fixture
def mock_team_registry(mocker):
    """Registry that returns a fresh dummy Team per ref."""
    registry = mocker.Mock()
    registry.get.side_effect = lambda ref: mocker.Mock(name=f"team:{ref}")
    return registry


@pytest.fixture
def mock_workflow_registry(mocker):
    """Registry that returns a fresh dummy Workflow per ref."""
    registry = mocker.Mock()
    registry.get.side_effect = lambda ref: mocker.Mock(name=f"wf:{ref}")
    return registry


@pytest.fixture
def mock_knowledge_registry(mocker):
    """Registry that returns a fresh dummy Knowledge per ref."""
    registry = mocker.Mock()
    registry.get.side_effect = lambda ref: mocker.Mock(name=f"kb:{ref}")
    return registry


@pytest.fixture
def mock_interface_registry(mocker):
    """Registry placeholder — Slice 1 deferred."""
    return mocker.Mock()


@pytest.fixture
def mock_db_manager(mocker):
    """Database manager that returns a dummy db per ref."""
    manager = mocker.Mock()
    manager.get_db.side_effect = lambda ref: mocker.Mock(name=f"db:{ref}")
    return manager


@pytest.fixture
def factory(
    mock_agent_registry,
    mock_team_registry,
    mock_workflow_registry,
    mock_knowledge_registry,
    mock_interface_registry,
    mock_db_manager,
) -> AgentOSFactory:
    """Fully-wired factory with all mocked registries."""
    return AgentOSFactory(
        agent_registry=mock_agent_registry,
        team_registry=mock_team_registry,
        workflow_registry=mock_workflow_registry,
        knowledge_registry=mock_knowledge_registry,
        interface_registry=mock_interface_registry,
        db_manager=mock_db_manager,
    )


# ---------------------------------------------------------------------------
# 1. Happy path — resolves refs and builds AgentOS
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Scenario 1: factory resolves all refs and constructs AgentOS."""

    def test_factory_resolves_refs_and_builds_agentos(self, factory, full_config, mocker) -> None:
        """All string refs resolved; primitives passthrough; AgentOS constructed.

        Patches ``AgentOS.__init__`` to capture kwargs and verify the factory
        forwarded the correct resolved objects and primitive values.
        """
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        result = factory.build(full_config)

        # Result is the AgentOS instance (mock-constructed)
        assert isinstance(result, AgentOS)

        # Agents: 2 refs → 2 resolved dummies
        assert len(captured["agents"]) == 2

        # Teams: 1 ref → 1 resolved dummy
        assert len(captured["teams"]) == 1

        # Workflows: 1 ref → 1 resolved dummy
        assert len(captured["workflows"]) == 1

        # Knowledge: 1 ref → 1 resolved dummy
        assert len(captured["knowledge"]) == 1

        # DB: sqlite_db resolved
        assert captured["db"] is not None

        # Scheduler: mapped from SchedulerSettings
        assert captured["scheduler"] is True
        assert captured["scheduler_poll_interval"] == 30

        # Authorization: enabled → authorization=True + authorization_config
        assert captured["authorization"] is True
        assert captured["authorization_config"] is not None

        # MCP server: enabled → mcp_server built (MCPServerConfig)
        mcp_srv = captured["mcp_server"]
        assert mcp_srv is not None
        # No custom tools in config → tools stays None (AgentOS default)

        # Primitives passthrough
        assert captured["name"] == "full-os"
        assert captured["a2a_interface"] is True
        assert captured["cors_allowed_origins"] == ["http://localhost:3000"]
        assert captured["auto_provision_dbs"] is False
        assert captured["run_hooks_in_background"] is True
        assert captured["tracing"] is True

    def test_minimal_config_builds(self, factory, basic_config, mocker) -> None:
        """Minimal config (name + one agent) produces a valid AgentOS."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        result = factory.build(basic_config)

        assert isinstance(result, AgentOS)
        assert len(captured["agents"]) == 1
        assert captured["name"] == "test-os"
        # DB not forwarded when None
        assert "db" not in captured


# ---------------------------------------------------------------------------
# 2. Missing agent ref raises ValueError (fail-fast)
# ---------------------------------------------------------------------------


class TestMissingRef:
    """Scenario 2: unresolved ref raises ValueError with diagnostic info."""

    def test_missing_agent_ref_raises_valueerror(self, factory, mock_agent_registry, mocker) -> None:
        """When a registry raises KeyError, factory wraps as ValueError."""
        mock_agent_registry.get.side_effect = KeyError("ghost")

        config = AgentOSConfig(name="broken-os", agents=["ghost"])

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match="ghost"):
            factory.build(config)

    def test_missing_team_ref_raises_valueerror(self, factory, mock_team_registry, mocker) -> None:
        """Team ref resolution failure also wraps as ValueError."""
        mock_team_registry.get.side_effect = KeyError("missing_team")

        config = AgentOSConfig(name="broken-os", teams=["missing_team"])

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match="missing_team"):
            factory.build(config)

    def test_missing_workflow_ref_raises_valueerror(self, factory, mock_workflow_registry, mocker) -> None:
        """Workflow ref resolution failure wraps as ValueError."""
        mock_workflow_registry.get.side_effect = KeyError("bad_wf")

        config = AgentOSConfig(name="broken-os", workflows=["bad_wf"])

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match="bad_wf"):
            factory.build(config)

    def test_missing_db_ref_raises_valueerror(self, factory, mock_db_manager, mocker) -> None:
        """DB ref resolution failure wraps as ValueError."""
        mock_db_manager.get_db.side_effect = KeyError("bad_db")

        config = AgentOSConfig(name="broken-os", agents=["researcher"], db="bad_db")

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match="bad_db"):
            factory.build(config)


# ---------------------------------------------------------------------------
# 3. Duplicate ref raises ValueError
# ---------------------------------------------------------------------------


class TestDuplicateRef:
    """Scenario 3: duplicate ref names in target lists are rejected."""

    def test_duplicate_agent_ref_raises_valueerror(self, factory, mocker) -> None:
        """Duplicate agent ref rejected before resolution."""
        config = AgentOSConfig(name="dup-os", agents=["researcher", "researcher"])

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match=r"(?i)duplicate"):
            factory.build(config)

    def test_duplicate_team_ref_raises_valueerror(self, factory, mocker) -> None:
        """Duplicate team ref rejected."""
        config = AgentOSConfig(name="dup-os", teams=["t1", "t1"])

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match=r"(?i)duplicate"):
            factory.build(config)

    def test_no_duplicate_with_unique_refs(self, factory, mocker) -> None:
        """Unique refs across target lists do not trigger duplicate error."""
        config = AgentOSConfig(
            name="ok-os",
            agents=["a1", "a2"],
            teams=["t1"],
            workflows=["w1", "w2"],
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        # Should not raise
        factory.build(config)


# ---------------------------------------------------------------------------
# 4. DB ref resolved via DatabaseManager
# ---------------------------------------------------------------------------


class TestDBRefResolution:
    """Scenario 4: db ref resolved through DatabaseManager.get_db()."""

    def test_db_ref_resolved(self, factory, mock_db_manager, mocker) -> None:
        """db="sqlite_db" → DatabaseManager.get_db("sqlite_db") → AgentOS(db=...)."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(name="db-os", agents=["researcher"], db="sqlite_db")
        factory.build(config)

        # DB manager was called with the ref
        mock_db_manager.get_db.assert_called_once_with("sqlite_db")

        # Resolved db forwarded to AgentOS
        assert "db" in captured
        assert captured["db"] is not None

    def test_db_ref_resolved_for_different_engine(self, factory, mock_db_manager, mocker) -> None:
        """db="postgres_prod" → DatabaseManager.get_db("postgres_prod")."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(name="pg-os", agents=["researcher"], db="postgres_prod")
        factory.build(config)

        mock_db_manager.get_db.assert_called_once_with("postgres_prod")
        assert "db" in captured


# ---------------------------------------------------------------------------
# 5. Primitives pass through unchanged
# ---------------------------------------------------------------------------


class TestPrimitivesPassthrough:
    """Scenario 5: non-ref primitive fields forwarded unchanged to AgentOS."""

    def test_primitives_passthrough_unchanged(self, factory, mocker) -> None:
        """name, tracing, auto_provision_dbs, run_hooks_in_background passthrough."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="primitive-os",
            agents=["researcher"],
            tracing=True,
            auto_provision_dbs=False,
            run_hooks_in_background=True,
            a2a_interface=False,
            cors_allowed_origins=["https://example.com"],
        )
        factory.build(config)

        assert captured["name"] == "primitive-os"
        assert captured["tracing"] is True
        assert captured["auto_provision_dbs"] is False
        assert captured["run_hooks_in_background"] is True
        assert captured["a2a_interface"] is False
        assert captured["cors_allowed_origins"] == ["https://example.com"]

    def test_lifespan_passthrough(self, factory, mocker) -> None:
        """lifespan import path string forwarded as-is."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="lifespan-os",
            agents=["researcher"],
            lifespan="my_package.lifespan:app_lifespan",
        )
        factory.build(config)

        assert captured["lifespan"] == "my_package.lifespan:app_lifespan"

    def test_base_app_passthrough(self, factory, mocker) -> None:
        """base_app import path string forwarded as-is."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="base-app-os",
            agents=["researcher"],
            base_app="my_package.app:create_app",
        )
        factory.build(config)

        assert captured["base_app"] == "my_package.app:create_app"


# ---------------------------------------------------------------------------
# 6. None db not forwarded
# ---------------------------------------------------------------------------


class TestNoneDBNotForwarded:
    """Scenario 6: when db is None, it is NOT passed to AgentOS kwargs."""

    def test_none_db_not_forwarded(self, factory, mocker) -> None:
        """db=None → AgentOS receives no 'db' key (relies on Agno default)."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(name="no-db-os", agents=["researcher"], db=None)
        factory.build(config)

        assert "db" not in captured

    def test_omitted_db_not_forwarded(self, factory, mocker) -> None:
        """Config created without db → not forwarded."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        # db omitted entirely (picks up None default)
        config = AgentOSConfig(name="no-db-os", agents=["researcher"])
        factory.build(config)

        assert "db" not in captured


# ---------------------------------------------------------------------------
# 7. Empty target config raises ValueError
# ---------------------------------------------------------------------------


class TestEmptyConfig:
    """Scenario 7: config with zero targets after resolution raises."""

    def test_empty_agentos_config_raises(self, factory, mocker) -> None:
        """No agents, teams, or workflows → ValueError.

        Note: AgentOSConfig itself rejects this at model_validate time
        (the _validate_at_least_one_target validator). This test verifies
        that the factory surfaces this cleanly rather than passing an
        invalid config through to AgentOS.
        """
        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match="must have at least one"):
            AgentOSConfig(name="empty-os")

    def test_all_targets_empty_lists_raises(self, factory, mocker) -> None:
        """Explicit empty lists for all target types also rejected."""
        mocker.patch.object(AgentOS, "__init__", return_value=None)

        with pytest.raises(ValueError, match="must have at least one"):
            AgentOSConfig(
                name="empty-os",
                agents=[],
                teams=[],
                workflows=[],
            )

    def test_config_with_only_teams_does_not_raise(self, factory, mocker) -> None:
        """Teams-only config is valid (no agents, no workflows)."""
        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(name="teams-only-os", teams=["t1"])
        # Should not raise
        factory.build(config)

    def test_config_with_only_workflows_does_not_raise(self, factory, mocker) -> None:
        """Workflows-only config is valid."""
        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(name="wf-only-os", workflows=["w1"])
        # Should not raise
        factory.build(config)
