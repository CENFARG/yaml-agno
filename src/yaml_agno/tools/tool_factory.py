"""ToolFactory — orchestrates ``ToolEntry`` dispatch to Agno objects (SPEC_11 C).

The factory is the SINGLE wiring point between the validated ``ToolEntry``
union (slices A+B) and ``agno.Agent(tools=...)``. It accepts either raw dicts
(opaque ``AgentConfig.tools`` per Option B) or pre-parsed ``ToolEntry``
instances, validates raw dicts via ``TypeAdapter(ToolEntry)``, dispatches each
entry by ``kind`` to the correct resolver (BUILTIN_REGISTRY /
CustomToolLoader / MCPResolver), applies ``@tool(**flags)`` for ``function``
entries, and returns the mixed list ``agno.Agent`` accepts.

Synchronous by design: ``MCPResolver`` returns UNCONNECTED ``MCPTools`` /
``MultiMCPTools`` instances, and ``agno.Agent`` auto-connects them during
``aget_tools`` (verified obs-2018). No ``await`` is needed on the construction
path.

@ai-directive: SSOT is specs/SPEC_11_TOOLS_AND_MCP.md §3 (custom @tool),
§9.5 (CustomToolLoader raw return contract). Slice D adds hook resolution
(pre_hook / post_hook / tool_hooks dotted-path strings resolved to Callables
and forwarded to @tool). Cross-run caching (cache_callables) is DEFERRED
post-MVP; concurrency executor is NEVER (Agno owns tool execution); registry
expansion is SEPARATED to its own change.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from agno.tools.decorator import tool as agno_tool
from pydantic import TypeAdapter

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.registry import BUILTIN_REGISTRY
from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolConfig,
    CustomToolkitConfig,
    HttpMcpConfig,
    McpMultiToolConfig,
    StdioMcpConfig,
    ToolEntry,
)

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["ToolFactory"]


# Reusable validator: raw dict -> ToolEntry instance. Built ONCE at import
# (TypeAdapter is the documented Pydantic V2 pattern for validating unions
# outside a model field). Option B: validation boundary lives here, NOT in
# AgentConfig.
_ENTRY_ADAPTER: TypeAdapter[ToolEntry] = TypeAdapter(ToolEntry)


class ToolFactory:
    """Orchestrate ``ToolEntry`` dispatch into the mixed list Agent accepts.

    Construction is cheap (one ``CustomToolLoader``); ``resolver`` is the
    shared dependency. The factory holds no tool-level state — each
    ``build()`` call is independent.

    Scope: dispatch + ``@tool`` wrapping (slice C) + hook resolution (slice D).
    Cross-run caching (``cache_callables``) is DEFERRED post-MVP; concurrency
    executor is NEVER (Agno owns tool execution); registry expansion is
    SEPARATED to its own change.

    Attributes:
        _loader: The ``CustomToolLoader`` for ``function`` / ``toolkit_class``
            / ``mcp`` / ``mcp_multi`` resolution. Wraps the injected resolver.
    """

    def __init__(self, resolver: AgnoResolver) -> None:
        """Initialize the factory with the shared resolver.

        Args:
            resolver: The ``AgnoResolver`` whose ``resolve_class`` performs
                allowlisted importlib resolution for custom tools, toolkit
                classes, and MCP ``header_provider`` dotted-paths.
        """
        self._loader = CustomToolLoader(resolver)

    def build(self, tool_entries: Sequence[dict[str, Any] | ToolEntry]) -> list[Any]:
        """Dispatch each tool entry to its resolver, collect into Agent's mixed list.

        Accepts EITHER raw dicts (opaque ``AgentConfig.tools``, Option B) or
        pre-parsed ``ToolEntry`` instances. Raw dicts are validated against
        the ``ToolEntry`` union via ``TypeAdapter`` (the validation boundary
        moves from config-parse to factory-build; it does NOT disappear).

        Args:
            tool_entries: The raw ``AgentConfig.tools`` list (dicts) or a list
                of already-parsed ``ToolEntry`` instances. Empty list is safe
                and returns ``[]``.

        Returns:
            The mixed list ``agno.Agent(tools=...)`` accepts. Item types by
            ``kind``:

            - ``builtin``       -> Toolkit instance (e.g. ``CalculatorTools``)
            - ``function``      -> ``agno.tools.function.Function`` (wrapped)
            - ``toolkit_class`` -> Toolkit instance (custom subclass)
            - ``mcp``           -> UNCONNECTED ``MCPTools``
            - ``mcp_multi``     -> UNCONNECTED ``MultiMCPTools``

        Raises:
            UnknownBuiltinError: If a ``builtin`` entry's ``name`` is not in
                ``BUILTIN_REGISTRY``.
            SecurityError: If a custom tool / ``header_provider`` dotted-path
                references a non-allowlisted module.
            ValidationError: If a raw dict does not match any ``ToolEntry``
                branch (re-raised from ``TypeAdapter.validate_python``).
        """
        result: list[Any] = []
        for raw in tool_entries:
            entry = _ENTRY_ADAPTER.validate_python(raw) if isinstance(raw, dict) else raw
            if isinstance(entry, BuiltinToolConfig):
                # BUILTIN_REGISTRY[name] raises UnknownBuiltinError if absent.
                adapter = BUILTIN_REGISTRY[entry.name]
                result.append(adapter.build(self._loader._resolver, entry.init_args))
            elif isinstance(entry, CustomToolConfig):
                raw_callable = self._loader.load_callable(entry)
                result.append(self._wrap_tool(raw_callable, entry))
            elif isinstance(entry, CustomToolkitConfig):
                cls = self._loader.load_toolkit_class(entry)
                # CustomToolkitConfig already carries init_args; the registry's
                # signature-filtering lives on ToolkitAdapter (builtins). Custom
                # toolkit classes are user-owned; init_args are forwarded as-is.
                result.append(cls(**entry.init_args))
            elif isinstance(entry, StdioMcpConfig | HttpMcpConfig):
                # UNCONNECTED — Agent auto-connects during aget_tools (A2).
                result.append(self._loader.load_mcp(entry))
            elif isinstance(entry, McpMultiToolConfig):
                # UNCONNECTED — emits DeprecationWarning (RISK004, slice B).
                result.append(self._loader.load_mcp_multi(entry))
            else:  # pragma: no cover - exhaustive union, unreachable
                raise TypeError(f"Unsupported ToolEntry kind: {type(entry).__name__}")
        return result

    def _wrap_tool(self, raw_callable: Any, config: CustomToolConfig) -> Any:
        """Apply ``@tool(**flags)`` from ``CustomToolConfig`` to a raw callable.

        The ``CustomToolLoader`` returns the RAW callable by design (A4,
        SPEC_11 §9.5); this method is the single place where the ``@tool``
        decorator is applied. Flags set to ``None`` are DROPPED so Agno uses
        its own defaults (matches SPEC_11 §3.1: ``show_result`` default
        ``None``, ``name``/``description`` default to function name/docstring).

        Hook fields (``pre_hook`` / ``post_hook`` / ``tool_hooks``, slice D)
        are dotted-path strings RESOLVED HERE via
        ``self._loader._resolve_dotted`` — the same allowlisted path used for
        ``config.path`` itself and MCP ``header_provider`` (SPEC_11 §10.3).
        The resolved ``Callable`` objects are forwarded to ``@tool``, which
        sets them on the returned ``Function`` (verified Agno 2.6.22).

        Args:
            raw_callable: The bare callable resolved by
                ``CustomToolLoader.load_callable``.
            config: The validated ``CustomToolConfig`` carrying the ``@tool``
                flags. The HITL mutual-exclusivity was already enforced at
                schema-validation time (``model_validator``), so no runtime
                re-check is needed here.

        Returns:
            An ``agno.tools.function.Function`` object (the type
            ``@tool`` returns per TECH011).

        Raises:
            SecurityError: If a hook dotted-path references a non-allowlisted
                module (propagated from ``_resolve_dotted``).
            ValueError: If a hook dotted-path has no ``module.name`` structure
                (propagated from ``_resolve_dotted``).
        """
        # --- Slice D: resolve hook dotted-paths to Callables (A1, A2) ---
        # Reuses CustomToolLoader._resolve_dotted (the SAME allowlisted path
        # as `config.path` and MCP `header_provider`). No separate hooks.py.
        pre_hook_callable = (
            self._loader._resolve_dotted(config.pre_hook) if config.pre_hook is not None else None
        )
        post_hook_callable = (
            self._loader._resolve_dotted(config.post_hook) if config.post_hook is not None else None
        )
        tool_hooks_callables = [
            self._loader._resolve_dotted(hook_ref) for hook_ref in config.tool_hooks
        ]

        flags = {
            "name": config.name,
            "description": config.description,
            "requires_confirmation": config.requires_confirmation,
            "requires_user_input": config.requires_user_input,
            "user_input_fields": config.user_input_fields or None,
            "external_execution": config.external_execution,
            "external_execution_silent": config.external_execution_silent,
            "strict": config.strict,
            "show_result": config.show_result,
            "stop_after_tool_call": config.stop_after_tool_call,
            "cache_results": config.cache_results,
            "cache_dir": config.cache_dir,
            "cache_ttl": config.cache_ttl,
            "pre_hook": pre_hook_callable,
            "post_hook": post_hook_callable,
            "tool_hooks": tool_hooks_callables or None,
        }
        # Drop None-valued flags so Agno applies its own defaults. Boolean
        # False is KEPT (it is a meaningful explicit value, not "unset"). An
        # empty tool_hooks list is normalized to None above so it is dropped
        # here (Agno default is []).
        flags = {k: v for k, v in flags.items() if v is not None}
        return agno_tool(**flags)(raw_callable)
