"""Tool entry schemas (SPEC_11 slice A) — discriminated union for the
``tools:`` YAML list.

De-opacifies ``AgentConfig.tools`` from raw dicts to a validated union
discriminated by ``kind``. Three ``kind`` resolve NOW (builtin / function /
toolkit_class); two DEFER (mcp / mcp_multi) raise NotImplementedError until
slice B.

NOTE: this schema ships standalone in slice A. ``AgentConfig.tools`` stays the
opaque ``list[dict]``; wiring is slice C (mirrors how model-config-schema left
``AgentConfig.model`` untouched).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BuiltinToolConfig",
    "CustomToolConfig",
    "CustomToolkitConfig",
    "McpMultiToolConfig",
    "McpToolConfig",
    "ToolEntry",
]


class BuiltinToolConfig(BaseModel):
    """A built-in Agno toolkit declared by name (e.g. ``calculator``).

    The ``name`` MUST be a key in ``BUILTIN_REGISTRY``. ``init_args`` are
    forwarded to the toolkit constructor (after alias normalization + signature
    filtering by the registry adapter). ``extra`` is allowed so the YAML can
    carry toolkit-specific flags directly.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["builtin"] = "builtin"
    name: str = Field(..., min_length=1, description="BUILTIN_REGISTRY key (e.g. 'calculator').")
    init_args: dict[str, Any] = Field(
        default_factory=dict, description="Toolkit constructor kwargs (alias-normalized + filtered)."
    )


class CustomToolConfig(BaseModel):
    """A single custom function declared as a dotted-path callable reference.

    ``path`` is resolved via ``AgnoResolver.resolve_class`` (allowlisted). The
    callable is returned RAW by ``CustomToolLoader`` — ``@tool`` wrapping is the
    ToolFactory's job (slice C), NOT this schema.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["function"] = "function"
    path: str = Field(..., min_length=1, description="Dotted-path callable (e.g. 'my_pkg.tools.fetch').")


class CustomToolkitConfig(BaseModel):
    """A custom toolkit class declared as a dotted-path reference.

    Like ``function`` but resolves a Toolkit CLASS (instantiated with
    ``init_args`` after signature filtering), not a bare callable.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["toolkit_class"] = "toolkit_class"
    path: str = Field(..., min_length=1, description="Dotted-path toolkit class (e.g. 'my_pkg.MyToolkit').")
    init_args: dict[str, Any] = Field(default_factory=dict, description="Toolkit constructor kwargs.")


class McpToolConfig(BaseModel):
    """Placeholder for MCP single-server config (DEFERRED to slice B).

    The loader raises NotImplementedError; slice B will flesh out the real
    fields (command/url/transport/etc.).
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["mcp"] = "mcp"


class McpMultiToolConfig(BaseModel):
    """Placeholder for MultiMCPTools config (DEFERRED to slice B)."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["mcp_multi"] = "mcp_multi"


# Discriminated union. Pydantic V2 routes by the ``kind`` Literal.
ToolEntry = (
    BuiltinToolConfig
    | CustomToolConfig
    | CustomToolkitConfig
    | McpToolConfig
    | McpMultiToolConfig
)
