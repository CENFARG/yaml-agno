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


# ---------------------------------------------------------------------------
# 8. InterfaceRegistry integration (Slice 2, PR 3 — TASK_009)
# ---------------------------------------------------------------------------


class TestInterfaceRegistryIntegration:
    """Scenario 8: InterfaceRegistry.build_all called when config has interfaces."""

    def test_interfaces_resolved_via_registry(
        self, mock_agent_registry, mock_team_registry, mock_workflow_registry,
        mock_knowledge_registry, mock_db_manager, mocker,
    ) -> None:
        """When config has interfaces, call interface_registry.build_all."""
        from yaml_agno.agentos.interfaces import InterfaceRegistry, InterfaceSpec, InterfaceType

        # Build a real InterfaceRegistry (not mocked — we verify call-through)
        mock_iface_registry = mocker.Mock(spec=InterfaceRegistry)
        fake_iface = mocker.Mock(name="interface:slack_main")
        mock_iface_registry.build_all.return_value = [fake_iface]

        # Need a stub MCPServerLifecycle too (new param in TASK_009)
        mock_mcp_lifecycle = mocker.Mock()
        mock_mcp_lifecycle._settings.enabled = True  # keep mcp register happy

        factory_with_iface = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_iface_registry,
            db_manager=mock_db_manager,
            mcp_lifecycle=mock_mcp_lifecycle,
        )

        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="iface-os",
            agents=["researcher"],
            interfaces=[
                {"type": "slack", "target": "researcher", "config": {"bot_token": "xoxb-test"}},
            ],
        )
        factory_with_iface.build(config)

        # build_all MUST have been called with a list of InterfaceSpec
        mock_iface_registry.build_all.assert_called_once()
        call_args = mock_iface_registry.build_all.call_args[0]
        assert len(call_args[0]) == 1
        assert isinstance(call_args[0][0], InterfaceSpec)
        assert call_args[0][0].type == InterfaceType.SLACK
        assert call_args[0][0].target == "researcher"

        # Resolved interfaces forwarded as kwarg
        assert captured.get("interfaces") == [fake_iface]

    def test_interfaces_not_called_when_empty(
        self, mock_agent_registry, mock_team_registry, mock_workflow_registry,
        mock_knowledge_registry, mock_db_manager, mocker,
    ) -> None:
        """When config has no interfaces, build_all is NOT called."""
        mock_iface_registry = mocker.Mock()
        mock_mcp_lifecycle = mocker.Mock()
        mock_mcp_lifecycle._settings.enabled = False

        factory_no_iface = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_iface_registry,
            db_manager=mock_db_manager,
            mcp_lifecycle=mock_mcp_lifecycle,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(name="no-iface-os", agents=["researcher"])
        factory_no_iface.build(config)

        # Interface registry was never called
        mock_iface_registry.build_all.assert_not_called()

    def test_interfaces_not_called_when_registry_none(
        self, mock_agent_registry, mock_team_registry, mock_workflow_registry,
        mock_knowledge_registry, mock_db_manager, mocker,
    ) -> None:
        """When interface_registry is None, build_all is NOT called (graceful)."""
        mock_mcp_lifecycle = mocker.Mock()
        mock_mcp_lifecycle._settings.enabled = False

        factory_no_registry = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=None,
            db_manager=mock_db_manager,
            mcp_lifecycle=mock_mcp_lifecycle,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="no-registry-os",
            agents=["researcher"],
            interfaces=[{"type": "agui", "target": "researcher"}],
        )
        # Should NOT raise — gracefully skips when registry is None
        factory_no_registry.build(config)

    def test_interfaces_logs_warning_when_registry_none(self, factory, mocker, caplog) -> None:
        """When interfaces exist but registry is None, log a warning."""
        mock_mcp_lifecycle = mocker.Mock()
        mock_mcp_lifecycle._settings.enabled = False

        factory_no_registry = AgentOSFactory(
            agent_registry=factory._agent_registry,
            team_registry=factory._team_registry,
            workflow_registry=factory._workflow_registry,
            knowledge_registry=factory._knowledge_registry,
            interface_registry=None,
            db_manager=factory._db_manager,
            mcp_lifecycle=mock_mcp_lifecycle,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="warn-os",
            agents=["researcher"],
            interfaces=[{"type": "agui", "target": "researcher"}],
        )

        import logging

        with caplog.at_level(logging.WARNING):
            factory_no_registry.build(config)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert any("interface" in r.message.lower() for r in warnings)


# ---------------------------------------------------------------------------
# 9. MCPServerLifecycle integration (Slice 2, PR 3 — TASK_009)
# ---------------------------------------------------------------------------


class TestMCPServerLifecycleIntegration:
    """Scenario 9: MCPServerLifecycle.register called when mcp.enabled."""

    def test_mcp_lifecycle_register_called(
        self, mock_agent_registry, mock_team_registry, mock_workflow_registry,
        mock_knowledge_registry, mock_interface_registry, mock_db_manager, mocker,
    ) -> None:
        """When mcp.enabled, call mcp_lifecycle.register(agentos) after build."""
        mock_mcp = mocker.Mock()
        # MCPServerLifecycle.register must exist and be callable
        mock_mcp.register = mocker.Mock()

        factory_with_mcp = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            mcp_lifecycle=mock_mcp,
        )

        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="mcp-os",
            agents=["researcher"],
            mcp=MCPServerSettings(enabled=True, name="mcp-srv", port=9090),
        )
        result = factory_with_mcp.build(config)

        # register() called with the AgentOS instance
        mock_mcp.register.assert_called_once()
        assert mock_mcp.register.call_args[0][0] is result

    def test_mcp_lifecycle_not_called_when_disabled(
        self, mock_agent_registry, mock_team_registry, mock_workflow_registry,
        mock_knowledge_registry, mock_interface_registry, mock_db_manager, mocker,
    ) -> None:
        """When mcp is disabled, register() is NOT called."""
        mock_mcp = mocker.Mock()
        mock_mcp.register = mocker.Mock()

        factory_with_mcp = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            mcp_lifecycle=mock_mcp,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="no-mcp-os",
            agents=["researcher"],
            mcp=MCPServerSettings(enabled=False),
        )
        factory_with_mcp.build(config)

        # register() never called
        mock_mcp.register.assert_not_called()

    def test_mcp_lifecycle_not_called_when_none(
        self, mock_agent_registry, mock_team_registry, mock_workflow_registry,
        mock_knowledge_registry, mock_interface_registry, mock_db_manager, mocker,
    ) -> None:
        """When mcp_lifecycle is None, no crash (graceful)."""
        factory_no_mcp = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            mcp_lifecycle=None,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="no-lifecycle-os",
            agents=["researcher"],
            mcp=MCPServerSettings(enabled=True),
        )
        # Should NOT raise
        factory_no_mcp.build(config)


# ---------------------------------------------------------------------------
# 10. AuthorizationAdapter integration (Slice 3 — INTG01)
# ---------------------------------------------------------------------------


class TestAuthorizationAdapterIntegration:
    """INTG01: AgentOSFactory wires AuthorizationAdapter for secret resolution."""

    def test_factory_uses_authorization_adapter_for_secret_resolution(
        self,
        mock_agent_registry,
        mock_team_registry,
        mock_workflow_registry,
        mock_knowledge_registry,
        mock_interface_registry,
        mock_db_manager,
        mocker,
    ) -> None:
        """AuthorizationAdapter.build() is called; its result forwarded to AgentOS."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=lambda key: {"JWT_SECRET": "resolved-secret"}[key])
        auth_adapter = AuthorizationAdapter(secret_manager=sm)

        factory = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            authorization_adapter=auth_adapter,
        )

        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="auth-os",
            agents=["researcher"],
            authorization=AuthorizationSettings(
                enabled=True,
                config={"jwt_secret_ref": "${SECRET:JWT_SECRET}"},
            ),
        )
        factory.build(config)

        assert captured["authorization"] is True
        assert captured["authorization_config"] is not None
        sm.assert_called_once_with("JWT_SECRET")

    def test_factory_without_auth_adapter_still_builds(
        self,
        mock_agent_registry,
        mock_team_registry,
        mock_workflow_registry,
        mock_knowledge_registry,
        mock_interface_registry,
        mock_db_manager,
        mocker,
    ) -> None:
        """Without AuthorizationAdapter, factory falls back to legacy build."""
        factory = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            # authorization_adapter=None (default)
        )

        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="no-adapter-os",
            agents=["researcher"],
            authorization=AuthorizationSettings(
                enabled=True,
                basic_auth={"username": "admin", "password": "plain"},
            ),
        )
        factory.build(config)

        assert captured["authorization"] is True
        assert captured["authorization_config"] is not None

    def test_auth_adapter_disabled_auth_skips(self, factory, mocker) -> None:
        """When authorization is disabled, neither adapter nor legacy builds."""
        captured: dict = {}

        def _fake_init(self, **kwargs):
            captured.update(kwargs)

        mocker.patch.object(AgentOS, "__init__", _fake_init)

        config = AgentOSConfig(
            name="no-auth-os",
            agents=["researcher"],
            authorization=AuthorizationSettings(enabled=False),
        )
        factory.build(config)

        # authorization field not forwarded (excluded by to_agno_kwargs None exclusion)
        assert "authorization" not in captured
        assert "authorization_config" not in captured


# ---------------------------------------------------------------------------
# 11. ResyncManager factory integration (Slice 3 — INTG02)
# ---------------------------------------------------------------------------


class TestResyncManagerFactoryIntegration:
    """INTG02: AgentOSFactory attaches ResyncManager after AgentOS construction."""

    def test_factory_attaches_resync_manager_after_build(
        self,
        mock_agent_registry,
        mock_team_registry,
        mock_workflow_registry,
        mock_knowledge_registry,
        mock_interface_registry,
        mock_db_manager,
        mocker,
    ) -> None:
        """ResyncManager.attach(agentos) called after AgentOS(**kwargs)."""
        from pathlib import Path

        from yaml_agno.agentos.resync_manager import ResyncManager
        from yaml_agno.models.config.agentos_config import ResyncSettings

        rm = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True, watch=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        factory = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            resync_manager=rm,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="resync-os",
            agents=["researcher"],
            resync=ResyncSettings(enabled=True),
        )
        factory.build(config)

        # ResyncManager should have been attached to the AgentOS instance
        assert rm._os is not None

    def test_resync_enabled_but_no_manager_logs_warning(
        self, factory, mocker, caplog,
    ) -> None:
        """When resync.enabled but no ResyncManager injected → WARNING."""
        import logging

        from yaml_agno.models.config.agentos_config import ResyncSettings

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="no-rm-os",
            agents=["researcher"],
            resync=ResyncSettings(enabled=True),
        )

        with caplog.at_level(logging.WARNING):
            factory.build(config)

        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ResyncManager" in str(w) for w in warnings)

    def test_resync_disabled_no_attach_even_with_manager(
        self,
        mock_agent_registry,
        mock_team_registry,
        mock_workflow_registry,
        mock_knowledge_registry,
        mock_interface_registry,
        mock_db_manager,
        mocker,
    ) -> None:
        """resync disabled → attach() NOT called even if manager injected."""
        from pathlib import Path

        from yaml_agno.agentos.resync_manager import ResyncManager
        from yaml_agno.models.config.agentos_config import ResyncSettings

        rm = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=False),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        factory = AgentOSFactory(
            agent_registry=mock_agent_registry,
            team_registry=mock_team_registry,
            workflow_registry=mock_workflow_registry,
            knowledge_registry=mock_knowledge_registry,
            interface_registry=mock_interface_registry,
            db_manager=mock_db_manager,
            resync_manager=rm,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="no-resync-os",
            agents=["researcher"],
            resync=ResyncSettings(enabled=False),
        )
        factory.build(config)

        # _os still None — attach was never called
        assert rm._os is None

    def test_deferred_slice3_log_removed(
        self, factory, mocker, caplog,
    ) -> None:
        """Old 'deferred to Slice 3' log must NOT appear when manager injected."""
        import logging
        from pathlib import Path

        from yaml_agno.agentos.resync_manager import ResyncManager
        from yaml_agno.models.config.agentos_config import ResyncSettings

        rm = ResyncManager(
            config_path=Path("agentos.yaml"),
            settings=ResyncSettings(enabled=True),
            obs=mocker.Mock(),
            config=mocker.Mock(),
        )

        factory_with_rm = AgentOSFactory(
            agent_registry=factory._agent_registry,
            team_registry=factory._team_registry,
            workflow_registry=factory._workflow_registry,
            knowledge_registry=factory._knowledge_registry,
            interface_registry=factory._interface_registry,
            db_manager=factory._db_manager,
            resync_manager=rm,
        )

        mocker.patch.object(AgentOS, "__init__", return_value=None)

        config = AgentOSConfig(
            name="clean-os",
            agents=["researcher"],
            resync=ResyncSettings(enabled=True),
        )

        with caplog.at_level(logging.WARNING):
            factory_with_rm.build(config)

        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("Slice 3" in str(w) for w in warnings)
