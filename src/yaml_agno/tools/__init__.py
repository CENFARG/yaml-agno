"""yaml-agno tools layer — SPEC_11 (slices A + B).

Public API:
    from yaml_agno.tools import (
        ToolEntry, BUILTIN_REGISTRY, CustomToolLoader, ToolkitAdapter,
        MCPResolver, StdioMcpConfig, HttpMcpConfig,
    )
"""

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.mcp_resolver import MCPResolver
from yaml_agno.tools.registry import BUILTIN_REGISTRY, ToolkitAdapter, UnknownBuiltinError
from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolConfig,
    CustomToolkitConfig,
    HttpMcpConfig,
    McpMultiToolConfig,
    McpToolConfig,
    StdioMcpConfig,
    ToolEntry,
)
from yaml_agno.tools.security import SecurityError, is_module_allowed

__all__ = [
    "BUILTIN_REGISTRY",
    "BuiltinToolConfig",
    "CustomToolConfig",
    "CustomToolLoader",
    "CustomToolkitConfig",
    "HttpMcpConfig",
    "MCPResolver",
    "McpMultiToolConfig",
    "McpToolConfig",
    "SecurityError",
    "StdioMcpConfig",
    "ToolEntry",
    "ToolkitAdapter",
    "UnknownBuiltinError",
    "is_module_allowed",
]
