"""Unit tests for ``yaml_agno.tools.schema`` — SPEC_11 slices A + B.

Covers the ToolEntry discriminated union: kind discrimination (5 kinds),
field validation (extra=allow on builtin, extra=forbid on function/
toolkit_class/mcp), and the MCP transport-discriminated union (slice B).
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolConfig,
    CustomToolkitConfig,
    McpMultiToolConfig,
    StdioMcpConfig,
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
def test_tool_entry_mcp_stdio_from_dict() -> None:
    """Slice B: kind=mcp + transport=stdo -> StdioMcpConfig."""
    entry = TypeAdapter(ToolEntry).validate_python(
        {"kind": "mcp", "transport": "stdio", "command": "uvx mcp-server-git"}
    )
    assert isinstance(entry, StdioMcpConfig)
    assert entry.command == "uvx mcp-server-git"
    assert entry.transport == "stdio"


@pytest.mark.unit
def test_tool_entry_mcp_multi_with_servers() -> None:
    """Slice B: kind=mcp_multi with servers list -> McpMultiToolConfig."""
    entry = TypeAdapter(ToolEntry).validate_python(
        {
            "kind": "mcp_multi",
            "servers": [{"transport": "stdio", "command": "echo hi"}],
        }
    )
    assert isinstance(entry, McpMultiToolConfig)
    assert len(entry.servers) == 1
    assert isinstance(entry.servers[0], StdioMcpConfig)


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


# --- SPEC_11 slice C: CustomToolConfig widened with @tool flags + HITL validator ---


@pytest.mark.unit
def test_custom_tool_config_accepts_tool_flags() -> None:
    """Slice C: CustomToolConfig accepts the widened @tool flags.

    Req: CustomToolConfig ensanchado acepta flags.
    """
    config = CustomToolConfig(
        path="x.y",
        requires_confirmation=True,
        cache_results=True,
        cache_ttl=3600,
    )
    assert config.path == "x.y"
    assert config.requires_confirmation is True
    assert config.cache_results is True
    assert config.cache_ttl == 3600


@pytest.mark.unit
def test_custom_tool_config_minimal_still_valid() -> None:
    """Slice C: minimal CustomToolConfig (path only) stays valid with defaults.

    Req: CustomToolConfig minimal sigue válido.
    """
    config = CustomToolConfig(path="x.y")
    assert config.path == "x.y"
    assert config.requires_confirmation is False
    assert config.requires_user_input is False
    assert config.external_execution is False
    assert config.cache_results is False
    assert config.cache_ttl is None
    assert config.name is None
    assert config.description is None


@pytest.mark.unit
def test_hitl_validator_rejects_two_flags_true() -> None:
    """Slice C: HITL validator rejects 2 of 3 HITL flags True.

    Req: Validador HITL — RED con 2 flags True.
    """
    with pytest.raises(ValidationError):
        CustomToolConfig(
            path="x.y",
            requires_confirmation=True,
            requires_user_input=True,
        )


@pytest.mark.unit
def test_hitl_validator_rejects_three_flags_true() -> None:
    """Slice C: HITL validator rejects all 3 HITL flags True.

    Req: RED — HITL con los 3 flags True.
    """
    with pytest.raises(ValidationError):
        CustomToolConfig(
            path="x.y",
            requires_confirmation=True,
            requires_user_input=True,
            external_execution=True,
        )


@pytest.mark.unit
def test_hitl_single_flag_true_is_valid() -> None:
    """Slice C: a single HITL flag True is valid (no raise).

    Req: Un solo flag HITL True es válido.
    """
    config = CustomToolConfig(path="x.y", external_execution=True)
    assert config.external_execution is True


# --- SPEC_11 slice D: CustomToolConfig hook fields (pre_hook/post_hook/tool_hooks) ---


@pytest.mark.unit
def test_custom_tool_config_accepts_hook_fields() -> None:
    """Slice D: CustomToolConfig accepts pre_hook, post_hook, tool_hooks.

    Req R1: Configuración válida con hook fields.
    """
    config = CustomToolConfig(
        path="x.y",
        pre_hook="myapp.hooks.audit_pre",
        post_hook="myapp.hooks.audit_post",
        tool_hooks=["myapp.hooks.a", "myapp.hooks.b"],
    )
    assert config.pre_hook == "myapp.hooks.audit_pre"
    assert config.post_hook == "myapp.hooks.audit_post"
    assert config.tool_hooks == ["myapp.hooks.a", "myapp.hooks.b"]


@pytest.mark.unit
def test_tool_hooks_defaults_empty() -> None:
    """Slice D: tool_hooks defaults to [] when omitted; pre_hook/post_hook default None.

    Req R1: tool_hooks como lista vacía por defecto.
    """
    config = CustomToolConfig(path="x.y")
    assert config.tool_hooks == []
    assert config.pre_hook is None
    assert config.post_hook is None


@pytest.mark.unit
def test_pre_hook_invalid_no_dot() -> None:
    """Slice D: pre_hook without a dot (no module.name structure) is rejected.

    Req R1: Referencia dotted-path inválida (sin punto).

    The schema-level validation requires a dotted-path; a bare name has no
    module separator. ``min_length=1`` is satisfied, but the model_validator
    or field constraint must reject a structurally invalid dotted-path. Since
    the design says the schema validates SYNTAX (must contain at least one '.'),
    we add a field_validator for this.
    """
    with pytest.raises(ValidationError):
        CustomToolConfig(path="x.y", pre_hook="hooks_audit")  # no dot
