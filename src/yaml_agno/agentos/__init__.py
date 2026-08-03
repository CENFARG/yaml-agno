"""agentos — AgentOS Control-Plane components (SPEC_12 + SPEC_26).

Slice 1 (shipped): AgentOSConfig, AgentOSFactory with registry injection.
Slice 2: InterfaceRegistry, MCPServerLifecycle, LifespanAdapter.
Slice 3: ResyncManager, AuthorizationAdapter, error types.
SPEC_26 (a2a-interface): A2AInterfaceConfig, A2AInterfaceFactory, A2APrefix,
    A2ADependencyError, A2AReferenceError.
"""

from __future__ import annotations

from yaml_agno.agentos.a2a_interface import (
    A2ADependencyError,
    A2AInterfaceConfig,
    A2AInterfaceFactory,
    A2APrefix,
    A2AReferenceError,
)
from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter
from yaml_agno.agentos.errors import AuthorizationBuildError, ResyncBlockedError
from yaml_agno.agentos.interfaces import (
    InterfaceBuildError,
    InterfaceCredentialError,
    InterfaceRegistry,
    InterfaceSpec,
    InterfaceType,
)
from yaml_agno.agentos.lifespan import LifespanAdapter
from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle
from yaml_agno.agentos.resync_manager import ResyncManager

__all__ = [
    "A2ADependencyError",
    "A2AInterfaceConfig",
    "A2AInterfaceFactory",
    "A2APrefix",
    "A2AReferenceError",
    "AuthorizationAdapter",
    "AuthorizationBuildError",
    "InterfaceBuildError",
    "InterfaceCredentialError",
    "InterfaceRegistry",
    "InterfaceSpec",
    "InterfaceType",
    "LifespanAdapter",
    "MCPServerLifecycle",
    "ResyncBlockedError",
    "ResyncManager",
]
