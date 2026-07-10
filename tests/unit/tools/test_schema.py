"""Unit tests for ``yaml_agno.tools.schema`` — SPEC_11 slice A.

Covers the ToolEntry discriminated union: kind discrimination (5 kinds),
field validation (extra=allow on builtin/mcp, extra=forbid on function/
toolkit_class), and the MCP placeholders.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolConfig,
    CustomToolkitConfig,
    McpMultiToolConfig,
    McpToolConfig,
    ToolEntry,
)


@pytest.mark.unit
def test_tool_entry_builtin_from_dict() -> None:
    """Golden: dict with kind=builtin -> BuiltinToolConfig."""
    entry = TypeAdapter(ToolEntry).validate_python({"kind": "builtin", "name": "calculator"})
    assert isinstance(entry, BuiltinToolConfig)
    assert entry.name == "calculator"


@pytest.mark.unit
def test_tool_entry_function_from_dict() -> None:
    """Golden: dict with kind=function -> CustomToolConfig."""
    entry = TypeAdapter(ToolEntry).validate_python(
        {"kind": "function", "path": "my_pkg.tools.fetch"}
    )
    assert isinstance(entry, CustomToolConfig)
    assert entry.path == "my_pkg.tools.fetch"


@pytest.mark.unit
def test_tool_entry_toolkit_class_from_dict() -> None:
    """Golden: dict with kind=toolkit_class -> CustomToolkitConfig."""
    entry = TypeAdapter(ToolEntry).validate_python(
        {"kind": "toolkit_class", "path": "my_pkg.MyToolkit", "init_args": {"x": 1}}
    )
    assert isinstance(entry, CustomToolkitConfig)
    assert entry.init_args == {"x": 1}


@pytest.mark.unit
def test_tool_entry_mcp_placeholder_parses() -> None:
    """MCP kind parses (placeholder); the LOADER raises, not the schema."""
    entry = TypeAdapter(ToolEntry).validate_python({"kind": "mcp", "command": "echo"})
    assert isinstance(entry, McpToolConfig)


@pytest.mark.unit
def test_tool_entry_mcp_multi_placeholder_parses() -> None:
    """mcp_multi kind parses (placeholder)."""
    entry = TypeAdapter(ToolEntry).validate_python({"kind": "mcp_multi"})
    assert isinstance(entry, McpMultiToolConfig)


@pytest.mark.unit
def test_tool_entry_rejects_unknown_kind() -> None:
    """RED: an unknown kind value fails validation."""
    with pytest.raises(ValidationError):
        TypeAdapter(ToolEntry).validate_python({"kind": "banana", "name": "x"})


@pytest.mark.unit
def test_builtin_extra_allow() -> None:
    """BuiltinToolConfig allows extra fields (toolkit-specific flags)."""
    entry = BuiltinToolConfig(name="calculator", some_flag=True)  # type: ignore[call-arg]
    assert entry.name == "calculator"


@pytest.mark.unit
def test_function_extra_forbid() -> None:
    """CustomToolConfig forbids extra fields."""
    with pytest.raises(ValidationError):
        CustomToolConfig(path="x.y", bogus=True)  # type: ignore[call-arg]


@pytest.mark.unit
def test_function_requires_path() -> None:
    """RED: function without path fails."""
    with pytest.raises(ValidationError):
        CustomToolConfig()  # type: ignore[call-arg]
