"""agentos — AgentOS Control-Plane components (SPEC_12).

Slice 1 (shipped): AgentOSConfig, AgentOSFactory with registry injection.
Slice 2: InterfaceRegistry, MCPServerLifecycle, LifespanAdapter.
Slice 3: ResyncManager, AuthorizationAdapter, error types.
"""

from __future__ import annotations

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
