"""Unit tests for ``yaml_agno.tools.tool_factory`` — SPEC_11 slice C.

ToolFactory orchestrates ``ToolEntry`` dispatch to native Agno objects.
Covers: empty list, unknown kind (ValidationError), builtin dispatch,
function wrapping with @tool flags, MCP UNCONNECTED return.

Uses a stub resolver that resolves real Agno toolkit classes (CalculatorTools)
and returns sentinels for custom paths, so dispatch behavior is verified
without coupling to the full DependencyManager wiring.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import ValidationError

from yaml_agno.tools.tool_factory import ToolFactory


class _RealResolver:
    """Stub resolver that actually imports Agno toolkit classes.

    For builtin dispatch, the ToolkitAdapter calls
    ``resolver.resolve_class(module_path, class_name)`` — so we delegate to
    real ``importlib`` to get a genuine ``CalculatorTools`` instance. For
    custom dotted-paths we return a sentinel callable/class (the factory's
    behavior under test is dispatch + wrapping, not the loader's import
    semantics, which are covered by ``test_custom_loader.py``).
    """

    def resolve_class(self, module_path: str, class_name: str) -> type:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)


class _CallableResolver:
    """Resolver that returns a raw stub callable for any dotted-path.

    Used for the ``function`` wrapping test — the factory wraps whatever the
    loader returns with ``@tool(**flags)``. The path MUST be under an
    allowlisted prefix (``agno.tools.``) so the loader's security guard passes.
    """

    def __init__(self) -> None:
        self.last_callable: Any = None

    def resolve_class(self, module_path: str, class_name: str) -> type:
        def _stub_tool(x: int = 0) -> int:  # pragma: no cover - never called
            """A stub tool function."""
            return x + 1

        _stub_tool.__module__ = module_path
        _stub_tool.__name__ = class_name
        self.last_callable = _stub_tool
        return _stub_tool  # type: ignore[return-value]


@pytest.mark.unit
def test_build_empty_list_returns_empty() -> None:
    """Slice C: ToolFactory.build([]) returns [] without calling resolver.

    Req: Lista vacía retorna lista vacía.
    """
    factory = ToolFactory(_RealResolver())  # type: ignore[arg-type]
    assert factory.build([]) == []


@pytest.mark.unit
def test_build_unknown_kind_raises_validation_error() -> None:
    """Slice C: build with an unknown kind raises ValidationError.

    Req: RED — kind desconocido produce ValidationError.
    """
    factory = ToolFactory(_RealResolver())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        factory.build([{"kind": "bogus"}])


@pytest.mark.unit
def test_build_dispatches_builtin() -> None:
    """Slice C: kind=builtin dispatches to BUILTIN_REGISTRY -> Toolkit instance.

    Req: Dispatch builtin.
    """
    factory = ToolFactory(_RealResolver())  # type: ignore[arg-type]
    result = factory.build([{"kind": "builtin", "name": "calculator"}])
    assert len(result) == 1
    from agno.tools.calculator import CalculatorTools

    assert isinstance(result[0], CalculatorTools)


@pytest.mark.unit
def test_build_wraps_function_with_tool_flags() -> None:
    """Slice C: kind=function wraps raw callable with @tool(**flags).

    Req: @tool wrapping aplica flags del config.
    """
    resolver = _CallableResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    result = factory.build(
        [{"kind": "function", "path": "agno.tools.stub.add", "requires_confirmation": True}]
    )
    assert len(result) == 1
    from agno.tools.function import Function

    wrapped = result[0]
    assert isinstance(wrapped, Function)
    assert wrapped.requires_confirmation is True


@pytest.mark.unit
def test_build_mcp_returns_unconnected() -> None:
    """Slice C: kind=mcp returns an UNCONNECTED MCPTools (initialized == False).

    Req: SYNC ToolFactory — MCP retorna UNCONNECTED.
    """
    factory = ToolFactory(_RealResolver())  # type: ignore[arg-type]
    result = factory.build([{"kind": "mcp", "transport": "stdio", "command": "uvx x"}])
    assert len(result) == 1
    from agno.tools.mcp import MCPTools

    mcp = result[0]
    assert isinstance(mcp, MCPTools)
    assert mcp.initialized is False
