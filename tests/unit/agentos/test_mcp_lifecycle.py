"""Unit tests for MCPServerLifecycle — SPEC_12 Slice 2, TASK_004.

Covers the mcp-lifecycle delta spec (5 requirements, 2 MCP scenarios)
with 6 TDD test cases:

    1.  MCPServerLifecycle — disabled settings → no config built
    2.  MCPServerLifecycle — enabled settings → config built with include_tags
    3.  MCPServerLifecycle — tools_to_expose maps to include_tags
    4.  MCPServerLifecycle — register stores AgentOS reference
    5.  MCPServerLifecycle — start enables MCP server on AgentOS
    6.  MCPServerLifecycle — stop is a clean no-op

Strict TDD: RED → GREEN → REFACTOR. Tests written BEFORE implementation.
"""

from __future__ import annotations

import pytest

from yaml_agno.models.config.agentos_config import MCPServerSettings

pytestmark = pytest.mark.unit

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def disabled_settings() -> MCPServerSettings:
    """MCP settings with everything disabled."""
    return MCPServerSettings(enabled=False)


@pytest.fixture
def enabled_settings() -> MCPServerSettings:
    """MCP settings with core tools enabled."""
    return MCPServerSettings(
        enabled=True,
        name="test-mcp-server",
        instructions="Use these tools for agent operations.",
        tools_to_expose=["core"],
        port=8765,
    )


@pytest.fixture
def mock_agentos(mocker):
    """A mock AgentOS instance that records mcp_server assignments."""
    os = mocker.MagicMock()
    os.name = "test-os"
    # Initialize internal state explicitly so Mock auto-creation doesn't
    # turn _mcp_enabled into a MagicMock (which is truthy).
    os._mcp_enabled = False
    os.mcp_config = None

    # Simulate the mcp_server property setter behavior:
    # AgentOS.mcp_server setter stores MCPServerConfig into mcp_config.
    def _mcp_server_setter(self, value):
        from agno.os.config import MCPServerConfig

        if isinstance(value, MCPServerConfig):
            self._mcp_enabled = True
            self.mcp_config = value
        else:
            self._mcp_enabled = bool(value)

    def _mcp_server_getter(self):
        return self._mcp_enabled

    type(os).mcp_server = property(
        fget=_mcp_server_getter,
        fset=_mcp_server_setter,
    )
    return os


# ═══════════════════════════════════════════════════════════════════════════
# Test cases
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPServerLifecycleDisabled:
    async def test_disabled_settings_no_config_built(
        self, disabled_settings, mock_agentos
    ):
        """When MCPServerSettings.enabled=False, start() does not build a config."""
        from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

        lifecycle = MCPServerLifecycle(disabled_settings)
        lifecycle.register(mock_agentos)

        await lifecycle.start()

        # AgentOS mcp_server property should NOT have been set
        assert mock_agentos.mcp_server is False
        assert getattr(mock_agentos, "mcp_config", None) is None


class TestMCPServerLifecycleEnabled:
    async def test_enabled_settings_builds_config(self, enabled_settings, mock_agentos):
        """When MCPServerSettings.enabled=True, start() builds an MCPServerConfig."""
        from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

        lifecycle = MCPServerLifecycle(enabled_settings)
        lifecycle.register(mock_agentos)

        await lifecycle.start()

        assert mock_agentos.mcp_server is True
        assert mock_agentos.mcp_config is not None

    async def test_tools_to_expose_maps_include_tags(
        self, enabled_settings, mock_agentos
    ):
        """tools_to_expose is mapped to MCPServerConfig.include_tags."""
        from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

        lifecycle = MCPServerLifecycle(enabled_settings)
        lifecycle.register(mock_agentos)

        await lifecycle.start()

        config = mock_agentos.mcp_config
        assert config.include_tags is not None
        assert "core" in config.include_tags

    async def test_register_stores_agentos_reference(
        self, enabled_settings, mock_agentos
    ):
        """register() stores the AgentOS reference for later start()."""
        from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

        lifecycle = MCPServerLifecycle(enabled_settings)
        lifecycle.register(mock_agentos)

        assert lifecycle._agentos is mock_agentos

    async def test_start_only_called_after_register(
        self, enabled_settings, mock_agentos
    ):
        """start() called without register() first is harmless (early-guard)."""
        from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

        lifecycle = MCPServerLifecycle(enabled_settings)
        # Deliberately do NOT call register()

        await lifecycle.start()

        # Should not crash; mcp_server stays unchanged
        assert not hasattr(mock_agentos, "mcp_config") or mock_agentos.mcp_config is None


class TestMCPServerLifecycleStop:
    async def test_stop_is_noop(self, enabled_settings, mock_agentos):
        """stop() is a clean no-op — AgentOS manages its own MCP lifecycle."""
        from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

        lifecycle = MCPServerLifecycle(enabled_settings)
        lifecycle.register(mock_agentos)
        await lifecycle.start()

        await lifecycle.stop()

        # After stop, mcp_server is still True — lifetime is AgentOS's responsibility
        assert mock_agentos.mcp_server is True
