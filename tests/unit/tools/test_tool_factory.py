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


# --- SPEC_11 slice D: hook resolution + forwarding in _wrap_tool (R2+R3+R6) ---


class _HookStubResolver:
    """Resolver that returns distinct stub callables for each dotted-path.

    Each call to ``resolve_class`` returns a NEW sentinel callable and records
    the (module_path, class_name) pair so tests can assert call order. The
    path MUST be under an allowlisted prefix (``agno.tools.``) for the
    loader's security guard to pass.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.stubs: list[Any] = []

    def resolve_class(self, module_path: str, class_name: str) -> Any:
        self.calls.append((module_path, class_name))

        def _hook_stub(**kwargs: object) -> object:  # pragma: no cover - never called
            return None

        _hook_stub.__module__ = module_path
        _hook_stub.__name__ = class_name
        self.stubs.append(_hook_stub)
        return _hook_stub


@pytest.mark.unit
def test_wrap_tool_resolves_pre_hook() -> None:
    """Slice D R2: _wrap_tool resolves pre_hook dotted-path and forwards to @tool.

    Req: Reenvío dorado pre_hook a @tool.
    """
    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    result = factory.build(
        [{"kind": "function", "path": "agno.tools.stub.fn", "pre_hook": "agno.tools.hooks.audit"}]
    )
    assert len(result) == 1
    from agno.tools.function import Function

    wrapped = result[0]
    assert isinstance(wrapped, Function)
    # The pre_hook must be set to the resolved callable (the last stub created).
    assert wrapped.pre_hook is resolver.stubs[-1]


@pytest.mark.unit
def test_wrap_tool_resolves_tool_hooks_list() -> None:
    """Slice D R2: _wrap_tool resolves tool_hooks list and forwards in order.

    Req: Reenvío dorado tool_hooks como lista (orden preservado).
    """
    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    result = factory.build(
        [
            {
                "kind": "function",
                "path": "agno.tools.stub.fn",
                "tool_hooks": ["agno.tools.hooks.h1", "agno.tools.hooks.h2"],
            }
        ]
    )
    assert len(result) == 1
    from agno.tools.function import Function

    wrapped = result[0]
    assert isinstance(wrapped, Function)
    # tool_hooks must contain 2 resolved callables in the same order as the YAML.
    # stubs[0] is the path callable; stubs[1] and stubs[2] are the hooks.
    assert isinstance(wrapped.tool_hooks, list)
    assert len(wrapped.tool_hooks) == 2
    assert wrapped.tool_hooks[0] is resolver.stubs[1]
    assert wrapped.tool_hooks[1] is resolver.stubs[2]


@pytest.mark.unit
def test_wrap_tool_omits_hooks_when_absent() -> None:
    """Slice D R2: when no hooks are set, @tool is invoked without hook keys.

    Req: Hooks omitidos cuando están ausentes (sin regresión).
    """
    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    result = factory.build([{"kind": "function", "path": "agno.tools.stub.fn"}])
    assert len(result) == 1
    from agno.tools.function import Function

    wrapped = result[0]
    assert isinstance(wrapped, Function)
    # No hooks were resolved.
    assert wrapped.pre_hook is None
    assert wrapped.post_hook is None
    # tool_hooks should be Agno's default (None when not forwarded).
    assert wrapped.tool_hooks is None


@pytest.mark.unit
def test_wrap_tool_rejects_non_allowlisted_hook() -> None:
    """Slice D R3: a non-allowlisted hook module raises SecurityError.

    Req: Hook en módulo no allowlisted (RED de seguridad).
    """
    from yaml_agno.tools.security import SecurityError

    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    with pytest.raises(SecurityError):
        factory.build(
            [{"kind": "function", "path": "agno.tools.stub.fn", "pre_hook": "evil_pkg.spy"}]
        )


@pytest.mark.unit
def test_wrap_tool_partial_hooks_transaction() -> None:
    """Slice D R3: tool_hooks with one allowlisted + one non-allowlisted is all-or-nothing.

    Req: Transacción parcial — un hook ok y otro evil -> SecurityError (no Function built).
    """
    from yaml_agno.tools.security import SecurityError

    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    with pytest.raises(SecurityError):
        factory.build(
            [
                {
                    "kind": "function",
                    "path": "agno.tools.stub.fn",
                    "tool_hooks": ["agno.tools.hooks.ok", "evil_pkg.bad"],
                }
            ]
        )


@pytest.mark.unit
def test_caching_plus_hooks_coexist() -> None:
    """Slice D R6: cache_results + pre_hook both forwarded, no flag lost.

    Req: Caching+hooks coexisten (invariante slice C preservada).
    """
    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    result = factory.build(
        [
            {
                "kind": "function",
                "path": "agno.tools.stub.fn",
                "cache_results": True,
                "cache_ttl": 300,
                "pre_hook": "agno.tools.hooks.audit",
            }
        ]
    )
    assert len(result) == 1
    from agno.tools.function import Function

    wrapped = result[0]
    assert isinstance(wrapped, Function)
    # Both caching and hook are present.
    assert wrapped.cache_results is True
    assert wrapped.cache_ttl == 300
    assert wrapped.pre_hook is resolver.stubs[-1]


@pytest.mark.unit
def test_caching_without_hooks_no_regression() -> None:
    """Slice D R6: caching flags still forwarded when no hooks are set.

    Req: Caching sin hooks sin regresión (byte-idéntico a slice C).
    """
    resolver = _HookStubResolver()
    factory = ToolFactory(resolver)  # type: ignore[arg-type]
    result = factory.build(
        [
            {
                "kind": "function",
                "path": "agno.tools.stub.fn",
                "cache_results": True,
                "cache_dir": "/tmp/cache",
                "cache_ttl": 600,
            }
        ]
    )
    assert len(result) == 1
    from agno.tools.function import Function

    wrapped = result[0]
    assert isinstance(wrapped, Function)
    assert wrapped.cache_results is True
    assert wrapped.cache_dir == "/tmp/cache"
    assert wrapped.cache_ttl == 600
