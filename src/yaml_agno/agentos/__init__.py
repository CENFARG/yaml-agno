"""agentos — AgentOS Control-Plane components (SPEC_12).

Slice 1 (shipped): AgentOSConfig, AgentOSFactory with registry injection.
Slice 2: InterfaceRegistry, MCPServerLifecycle, LifespanAdapter.
"""

from __future__ import annotations

from yaml_agno.agentos.interfaces import (
    InterfaceBuildError,
    InterfaceCredentialError,
    InterfaceRegistry,
    InterfaceSpec,
    InterfaceType,
)
from yaml_agno.agentos.lifespan import LifespanAdapter
from yaml_agno.agentos.mcp_lifecycle import MCPServerLifecycle

__all__ = [
    "InterfaceBuildError",
    "InterfaceCredentialError",
    "InterfaceRegistry",
    "InterfaceSpec",
    "InterfaceType",
    "LifespanAdapter",
    "MCPServerLifecycle",
]
