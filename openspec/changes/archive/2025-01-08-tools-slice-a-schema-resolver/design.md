---
change: tools-slice-a-schema-resolver
spec: SPEC_11
artifact: design
status: designed
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/tools-slice-a-schema-resolver/proposal.md (engram obs-2002)
  - spec: openspec/changes/tools-slice-a-schema-resolver/specs/tools-slice-a-schema-resolver/spec.md (engram 2003)
  - exploration: engram sdd/tools/explore (obs-2001)
  - shipped_resolver: src/yaml_agno/di/agno_resolver.py (resolve_class, public line 184)
---

# Design: tools-slice-a-schema-resolver (SPEC_11 slice A — foundation)

> **@ai-directive**: Este documento es el **HOW técnico**. El SSOT normativo es
> `specs/SPEC_11_TOOLS_AND_MCP.md` (read-only) y la delta spec de este change.
> El código mostrado aquí es **documentación viva** — apply crea los archivos
> `.py` verbatim. Toda discrepancia se resuelve a favor de la spec + la API
> real de Agno 2.6.22 (verificada en exploration obs-2001).

## Technical Approach

SPEC_11 slice A de-opacifica `AgentConfig.tools` (hoy `list[ToolConfig]` donde
`ToolConfig = dict[str, Any]` opaco) a una **unión discriminada `ToolEntry`**
validada, y resuelve 3 de los 5 `kind` posibles (**builtin**, **function**,
**toolkit_class**) a objetos Agno reales. Los 2 `kind` restantes (**mcp**,
**mcp_multi**) quedan como placeholders que lanzan `NotImplementedError` hasta
el slice B.

La resolución reutiliza **`AgnoResolver.resolve_class`** shipped
(`di/agno_resolver.py:184`) — NO duplica el importlib/allowlist/cache. El
diferenciador clave vs `ProviderFactory` (que compone kwargs contra
`dataclasses.fields`): los Agno **Toolkits NO son dataclasses**, son clases
regulares, así que el filtering de kwargs usa `inspect.signature(cls.__init__)`.

### Flujo de datos

```
YAML dict ──► ToolEntry union (Pydantic discrimina por ``kind``)
                │
                ├─ builtin ──► BUILTIN_REGISTRY[name] adapter
                │               └─ inspect.signature filtering + alias norm
                │               └─ cls(**filtered_kwargs)  → Toolkit instance
                │
                ├─ function ──► CustomToolLoader.load
                │               └─ AgnoResolver.resolve_class(dotted) + allowlist
                │               └─ returns RAW callable (NO @tool wrapping)
                │
                ├─ toolkit_class ─► CustomToolLoader.load (resolves class)
                │                   + inspect.signature filtering + instantiate
                │
                ├─ mcp ──► NotImplementedError (slice B)
                └─ mcp_multi ──► NotImplementedError (slice B)
```

## Architecture Decisions

### A1 — `ToolEntry` unión discriminada por `kind` (no por shape)

**Choice**: un campo `kind: Literal["builtin","function","toolkit_class","mcp","mcp_multi"]`
discrimina la unión. Cada kind tiene su config schema dedicada.

**Alternatives**:
- Discriminar por shape (presencia de campos): ambiguo (`function` y
  `toolkit_class` ambos usan `path`/`module`).
- Un solo modelo con campos opcionales: pierde validación por-kind.

**Rationale**: discriminación explícita por `kind` es inequívoca, falla rápido
en YAML malformado, y deja placeholders `mcp`/`mcp_multi` tipados (lanzan
`NotImplementedError`) en vez de romper el schema cuando llegue slice B.

### A2 — `CustomToolLoader` retorna callable CRUDO (NO aplica `@tool`)

**Choice**: `CustomToolLoader.load(config) -> Callable` resuelve el dotted-path
vía `AgnoResolver.resolve_class` y retorna el callable **sin envolver** con
`@tool`. El wrapping con `@tool(**flags)` (HITL, caching, hooks) es
responsabilidad del **ToolFactory** (slice C).

**Rationale**: separación de concerns. El loader es pura resolución de
referencia; el factory orquesta el ensamblaje final. Mezclarlos inflaría slice
A y acoplaría al `@tool` decorator antes de tiempo. SPEC_11 §9.5 documenta esta
separación explícitamente.

### A3 — Toolkits NO son dataclasses → `inspect.signature` filtering

**Choice**: los Agno Toolkits (`CalculatorTools`, `YFinanceTools`, etc.) son
clases regulares, NO `@dataclass`. El approach de `ProviderFactory` con
`dataclasses.fields()` **falla** aquí. Se usa `inspect.signature(cls.__init__)`
para obtener el set de parámetros aceptados y filtrar kwargs.

**Rationale**: verificado contra Agno 2.6.22 (`CalculatorTools.__init__(self,
**kwargs)`, `ShellTools.__init__(self, base_dir, enable_run_shell_command,
all, **kwargs)`). El filtering evita `TypeError` al pasar un kwarg que el
toolkit no acepta (ej. `enable_stock_price` a `CalculatorTools`).

### A4 — Alias normalization map (back-compat de flags)

**Choice**: `BUILTIN_REGISTRY` por adapter lleva un `alias_map: dict[str, str]`
que normaliza shorthand a canonical (ej. yfinance `stock_price` →
`enable_stock_price`). La normalización corre ANTES del filtering.

**Rationale**: los flags `enable_*` de Agno son verbosos; los usuarios de YAML
esperan shorthand. La normalización hace al YAML ergonómico sin inventar una
segunda API. Verificado: `HackerNewsTools` usa `enable_get_top_stories`, etc.

### A5 — DEFER explícito (slice A no hace runtime orchestration)

**Choice**: slice A NO implementa: MCP single/multi (slice B), `ToolFactory`
orchestrator + `@tool` wrapping + `AgentFactory` wiring (slice C), hooks /
caching / concurrencia / expansión registry a 120+ (slice D). Los `kind: mcp`
y `mcp_multi` lanzan `NotImplementedError` con mensaje nombrando slice B.

**Rationale**: decision #6 (DECISIONES.md §2.6) — boundaries claros entre
slices. Evita frankenstein (no medio-implementar MCP).

### A6 — `ToolConfig` alias deprecado (backward compat)

**Choice**: `type ToolConfig = dict[str, Any]` se conserva como alias
deprecado (warning en docstring). `AgentConfig.tools` se type-narrowa a
`list[ToolEntry]`, pero Pydantic coherce dicts crudos entrantes vía el
discriminador `kind` — cero referencias rotas en código/tests existentes.

**Rationale**: SPEC_02 shipped usa `ToolConfig` en docstrings/validators;
romperlo causaría churn innecesario. El alias deprecado guía la migración.

## Class-by-Class Model (target Python code)

> El código siguiente es **fiel a la spec** + verificación contra Agno 2.6.22.
> Los apply-tasks crearán estos archivos literalmente.

### 1. `src/yaml_agno/tools/schema.py` — `ToolEntry` union

```python
"""Tool entry schemas (SPEC_11 slice A) — discriminated union for the
``tools:`` YAML list. De-opacifies AgentConfig.tools from raw dicts to a
validated union discriminated by ``kind``.

Three ``kind`` resolve NOW (builtin / function / toolkit_class); two DEFER
(mcp / mcp_multi) raise NotImplementedError until slice B.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "BuiltinToolConfig",
    "CustomToolkitConfig",
    "CustomToolConfig",
    "McpToolConfig",
    "ToolEntry",
]


class BuiltinToolConfig(BaseModel):
    """A built-in Agno toolkit declared by name (e.g. ``calculator``).

    The ``name`` MUST be a key in ``BUILTIN_REGISTRY`` (slice A ships 5).
    ``init_args`` are forwarded to the toolkit constructor (after alias
    normalization + signature filtering by the registry adapter). ``extra``
    is allowed so the YAML can carry toolkit-specific flags directly.
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

    Raising at schema-validation time would block slice A; instead this schema
    parses the shape and the loader raises NotImplementedError. Slice B will
    flesh out the real fields (command/url/transport/etc.).
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
```

### 2. `src/yaml_agno/tools/security.py` — allowlist guard

```python
"""Module-allowlist guard for custom tool dotted-path resolution.

Custom tools are the ONE place yaml-agno resolves user-supplied Python paths
(per SPEC_00, the 30% Python). The allowlist prevents arbitrary module
loading. Reuses the same allowlist mechanism as AgnoResolver (prefix-match)
but exposes a dedicated public API so the tools layer does not depend on DI
internals beyond the resolver delegate.
"""

from __future__ import annotations

__all__ = ["SecurityError", "is_module_allowed"]


class SecurityError(Exception):
    """Raised when a dotted-path module is not in the allowlist."""


# Agno toolkits + a sane user-packages default. Extend via the resolver's
# allowlist configuration (slice C bootstrap). Empty = fail-closed.
_ALLOWED_MODULE_PREFIXES: tuple[str, ...] = ("agno.tools.",)


def is_module_allowed(dotted_path: str, extra_prefixes: tuple[str, ...] = ()) -> bool:
    """Return True iff ``dotted_path`` starts with an allowlisted prefix.

    Fail-closed: an empty allowlist rejects everything. Prefix-match lets
    ``agno.tools.`` cover all submodules (calculator, yfinance, ...).

    Args:
        dotted_path: The dotted module path to check (e.g. 'agno.tools.calculator').
        extra_prefixes: Additional allowed prefixes (e.g. user package roots).

    Returns:
        True if any prefix matches.
    """
    prefixes = _ALLOWED_MODULE_PREFIXES + extra_prefixes
    if not prefixes:
        return False
    return any(dotted_path.startswith(p) for p in prefixes)
```

### 3. `src/yaml_agno/tools/custom_loader.py` — `CustomToolLoader`

```python
"""CustomToolLoader — resolves dotted-path references to callables/classes.

Delegates class resolution to ``AgnoResolver.resolve_class`` (shipped,
allowlisted importlib + cache) — does NOT reimplement importlib. Returns RAW
callables/classes; ``@tool`` wrapping is the ToolFactory's job (slice C).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yaml_agno.tools.security import SecurityError, is_module_allowed

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver
    from yaml_agno.tools.schema import CustomToolkitConfig, CustomToolConfig

__all__ = ["CustomToolLoader"]


class CustomToolLoader:
    """Resolve ``function`` and ``toolkit_class`` tool entries to Agno objects.

    Thin wrapper around ``AgnoResolver.resolve_class`` that adds an explicit
    allowlist guard (defense-in-depth on top of the resolver's own allowlist)
    and a clear ``SecurityError`` on rejection.
    """

    def __init__(self, resolver: "AgnoResolver") -> None:
        """Initialize the loader.

        Args:
            resolver: The AgnoResolver whose ``resolve_class`` performs the
                allowlisted importlib resolution.
        """
        self._resolver = resolver

    def load_callable(self, config: "CustomToolConfig") -> Any:
        """Resolve a ``function`` entry to its RAW callable.

        Args:
            config: The ``kind: function`` tool entry.

        Returns:
            The resolved callable (NOT wrapped in @tool).

        Raises:
            SecurityError: If the module path is not allowlisted.
        """
        return self._resolve_dotted(config.path)

    def load_toolkit_class(self, config: "CustomToolkitConfig") -> type:
        """Resolve a ``toolkit_class`` entry to its class (uninstantiated).

        Args:
            config: The ``kind: toolkit_class`` tool entry.

        Returns:
            The resolved Toolkit class.

        Raises:
            SecurityError: If the module path is not allowlisted.
        """
        return self._resolve_dotted(config.path)

    def _resolve_dotted(self, dotted_path: str) -> Any:
        """Split a dotted path into (module, name) and resolve via the resolver.

        Args:
            dotted_path: e.g. 'my_pkg.tools.fetch' or 'agno.tools.calculator.CalculatorTools'.

        Returns:
            The resolved callable or class.

        Raises:
            SecurityError: If the module half is not allowlisted.
            ValueError: If the path has no module.name structure.
        """
        if "." not in dotted_path:
            raise ValueError(f"Invalid dotted path: {dotted_path!r}. Expected 'module.name'.")
        module_path, _, name = dotted_path.rpartition(".")
        if not is_module_allowed(module_path):
            raise SecurityError(
                f"Module {module_path!r} is not in the tool allowlist. Custom tools must "
                f"reference allowlisted modules (configure the allowlist at bootstrap)."
            )
        return self._resolver.resolve_class(module_path, name)
```

### 4. `src/yaml_agno/tools/registry.py` — `BUILTIN_REGISTRY` + adapters

```python
"""BUILTIN_REGISTRY — declarative catalog of built-in Agno toolkits.

Each ``ToolkitAdapter`` carries the Agno (module, class) pair, an alias map
(yfinance shorthand -> enable_* canonical), and the Agno pip package. The
adapter instantiates the toolkit, filtering ``init_args`` against
``inspect.signature(cls.__init__)`` (Toolkits are NOT dataclasses).

Shipped with 5 adapters (calculator, yfinance, hackernews, duckduckgo, shell).
Slice D expands to 120+.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["BUILTIN_REGISTRY", "SecurityError", "ToolkitAdapter", "UnknownBuiltinError"]


class UnknownBuiltinError(Exception):
    """Raised when a ``builtin`` name is not in BUILTIN_REGISTRY."""


@dataclasses.dataclass
class ToolkitAdapter:
    """Declarative metadata + instantiation logic for a built-in toolkit.

    Attributes:
        module_path: Agno module (e.g. 'agno.tools.calculator').
        class_name: Agno class (e.g. 'CalculatorTools').
        packages: Pip packages required (for Dockerfile/pyproject generation).
        alias_map: Shorthand -> canonical kwarg name (e.g. {'stock_price': 'enable_stock_price'}).
    """

    module_path: str
    class_name: str
    packages: tuple[str, ...]
    alias_map: dict[str, str] = dataclasses.field(default_factory=dict)

    def build(self, resolver: "AgnoResolver", init_args: dict[str, Any]) -> Any:
        """Resolve the class, normalize aliases, filter kwargs, instantiate.

        Args:
            resolver: The AgnoResolver for allowlisted class resolution.
            init_args: Raw kwargs from the YAML (may use shorthand aliases).

        Returns:
            The instantiated Agno Toolkit.

        Raises:
            TypeError: If the toolkit constructor rejects a filtered kwarg
                (should not happen post-filtering, but defensive).
        """
        cls = resolver.resolve_class(self.module_path, self.class_name)
        normalized = self._normalize_aliases(init_args)
        filtered = self._filter_kwargs(cls, normalized)
        return cls(**filtered)

    def _normalize_aliases(self, init_args: dict[str, Any]) -> dict[str, Any]:
        """Apply the alias_map to rename shorthand keys to canonical."""
        return {self.alias_map.get(k, k): v for k, v in init_args.items()}

    def _filter_kwargs(self, cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Keep only kwargs the class __init__ accepts (Toolkits aren't dataclasses).

        Uses ``inspect.signature``. ``**kwargs`` in the signature (e.g.
        CalculatorTools) accepts everything, so nothing is dropped there.
        """
        try:
            sig_params = inspect.signature(cls.__init__).parameters
        except (TypeError, ValueError):
            return kwargs
        allowed = set(sig_params) - {"self"}
        accepts_var_kw = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig_params.values()
        )
        if accepts_var_kw:
            return kwargs
        return {k: v for k, v in kwargs.items() if k in allowed}


BUILTIN_REGISTRY: dict[str, ToolkitAdapter] = {
    "calculator": ToolkitAdapter(
        module_path="agno.tools.calculator",
        class_name="CalculatorTools",
        packages=("agno",),
    ),
    "yfinance": ToolkitAdapter(
        module_path="agno.tools.yfinance",
        class_name="YFinanceTools",
        packages=("yfinance",),
        alias_map={
            "stock_price": "enable_stock_price",
            "company_info": "enable_company_info",
            "news": "enable_company_news",
            "analyst": "enable_analyst_recommendations",
        },
    ),
    "hackernews": ToolkitAdapter(
        module_path="agno.tools.hackernews",
        class_name="HackerNewsTools",
        packages=("agno",),
        alias_map={
            "top_stories": "enable_get_top_stories",
            "user_details": "enable_get_user_details",
        },
    ),
    "duckduckgo": ToolkitAdapter(
        module_path="agno.tools.duckduckgo",
        class_name="DuckDuckGoTools",
        packages=("ddgs",),
    ),
    "shell": ToolkitAdapter(
        module_path="agno.tools.shell",
        class_name="ShellTools",
        packages=("agno",),
    ),
}
```

### 5. `src/yaml_agno/tools/__init__.py` — re-export

```python
"""yaml-agno tools layer — SPEC_11.

Public API:
    from yaml_agno.tools import ToolEntry, BUILTIN_REGISTRY, CustomToolLoader, ToolkitAdapter
"""

from yaml_agno.tools.custom_loader import CustomToolLoader
from yaml_agno.tools.registry import BUILTIN_REGISTRY, ToolkitAdapter, UnknownBuiltinError
from yaml_agno.tools.schema import (
    BuiltinToolConfig,
    CustomToolkitConfig,
    CustomToolConfig,
    McpMultiToolConfig,
    McpToolConfig,
    ToolEntry,
)
from yaml_agno.tools.security import SecurityError, is_module_allowed

__all__ = [
    "BUILTIN_REGISTRY",
    "BuiltinToolConfig",
    "CustomToolkitConfig",
    "CustomToolConfig",
    "CustomToolLoader",
    "McpMultiToolConfig",
    "McpToolConfig",
    "SecurityError",
    "ToolEntry",
    "ToolkitAdapter",
    "UnknownBuiltinError",
    "is_module_allowed",
]
```

### 6. `src/yaml_agno/models/config/agent_config.py` — MODIFY tools field

The existing line:
```python
tools: list[ToolConfig] = Field(default_factory=list, max_length=50, description="Tools config. See SPEC_11.")
```
stays **structurally** but the type is narrowed. `ToolConfig` alias is kept
deprecated:

```python
# Deprecated alias (SPEC_02 legacy). Prefer ``ToolEntry`` (SPEC_11 slice A).
# Kept for backward compat with docstrings/validators; raw dicts still coerce
# via the ToolEntry ``kind`` discriminator.
type ToolConfig = dict[str, Any]
```

The field becomes:
```python
# ToolEntry union (SPEC_11 slice A) discriminates by ``kind``. Raw dicts
# coerce via the discriminator (backward compatible with ToolConfig).
tools: list[ToolEntry] = Field(default_factory=list, max_length=50, description="Tools config. See SPEC_11.")
```

**IMPORTANT**: because `ToolEntry` is a union of `BaseModel` subclasses
discriminated by `kind: Literal[...]`, Pydantic V2 requires the `kind` key in
each dict. Existing tests that build `AgentConfig(tools=[{"a": 1}])` (no
`kind`) will FAIL — apply must add `kind` to those test fixtures OR keep the
field as `list[ToolConfig]` until slice C wires the resolver. **Decision for
tasks/apply**: keep `AgentConfig.tools` as `list[ToolConfig]` (opaque dict)
in slice A — the ToolEntry schema ships standalone, wiring into AgentConfig is
slice C (mirrors how model-config-schema left AgentConfig.model untouched).
This avoids breaking ~8 existing agent_config tests + agent_factory passthru.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/schema.py` | Create | ToolEntry union (5 config models, kind discriminator). |
| `src/yaml_agno/tools/security.py` | Create | is_module_allowed + SecurityError (allowlist guard). |
| `src/yaml_agno/tools/custom_loader.py` | Create | CustomToolLoader (delegates AgnoResolver.resolve_class). |
| `src/yaml_agno/tools/registry.py` | Create | BUILTIN_REGISTRY (5 adapters) + ToolkitAdapter (signature filtering). |
| `src/yaml_agno/tools/__init__.py` | Modify | Re-export public API. |
| `tests/unit/tools/__init__.py` | Create | Package marker. |
| `tests/unit/tools/test_schema.py` | Create | ToolEntry union discrimination + 5 kind validation. |
| `tests/unit/tools/test_custom_loader.py` | Create | load_callable + load_toolkit_class + SecurityError. |
| `tests/unit/tools/test_registry.py` | Create | 5 adapters + alias normalization + signature filtering. |

**Total**: 5 src (4 new + 1 modify) + 4 tests. AgentConfig.tools UNCHANGED
(opaque dict kept — wiring is slice C).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | ToolEntry union discrimination by kind | `TypeAdapter(ToolEntry)` from dict with each `kind`. |
| Unit | BuiltinToolConfig name in BUILTIN_REGISTRY | golden + RED unknown name. |
| Unit | CustomToolLoader.load_callable (raw, no @tool) | real CalculatorTools + stubbed resolver. |
| Unit | CustomToolLoader SecurityError on non-allowlisted | module outside allowlist. |
| Unit | ToolkitAdapter signature filtering | CalculatorTools (**kwargs, accepts all) + HackerNews (drops unknown). |
| Unit | alias normalization | yfinance `stock_price` → `enable_stock_price`. |
| Unit | McpToolConfig/McpMultiToolConfig NotImplementedError | loader raises naming slice B. |

### Test fixtures
- `InMemoryDependencyAdapter` (core-cenf double) for the resolver in unit tests.
- Real `CalculatorTools` where feasible (no network at construct; it's pure).
- `yfinance`/`duckduckgo` (optional deps) use `pytest.importorskip` — the
  registry adapter itself doesn't import them (resolve_class does, lazily).

## TDD Approach (RED → GREEN → REFACTOR)

Per component:
1. **schema.py** — RED: union discrimination tests fail (ImportError). GREEN:
   literal schemas. (No behavior, just Pydantic shape.)
2. **security.py** — RED: is_module_allowed tests fail. GREEN: literal guard.
3. **custom_loader.py** — RED: load_callable/load_toolkit_class fail. GREEN:
   delegate to AgnoResolver.resolve_class.
4. **registry.py** — RED: adapter build + alias norm + filtering fail. GREEN:
   ToolkitAdapter literal.

## Verification Strategy

1. `python -m pytest -m unit` — green. Coverage: every validator branch.
2. `ruff check .` — clean.
3. `mypy src/yaml_agno` — clean.
4. Smoke: `python -c "from yaml_agno.tools import ToolEntry, BUILTIN_REGISTRY, CustomToolLoader; print('OK')"`.
5. Integration: build real CalculatorTools via BUILTIN_REGISTRY["calculator"]
   with a real AgnoResolver (no network).
6. Cold imports: `python -c "from yaml_agno.tools import *"` AND
   `python -c "from yaml_agno.models import AgentConfig"` (the circular-import
   lesson from slice #4 — verify tools/ doesn't re-introduce a cycle).
7. `git diff --name-only specs/ src/yaml_agno/models/config/agent_config.py`
   → EMPTY (AgentConfig unchanged; wiring is slice C).

## Migration / Rollout

**No migration.** Slice A ships additive schemas + resolvers under
`tools/`. AgentConfig.tools stays opaque (slice C wires it). Rollback =
`git revert`. No data, no feature flags, no dependents (ToolFactory is slice C).

## Open Questions

- The `ToolkitAdapter.__post_init__` frozen-dataclass default-dict workaround
  is ugly; a cleaner approach is `field(default_factory=dict)` on a non-frozen
  dataclass, OR a plain class. Apply may simplify (functional equivalence).
- Slice C must decide: widen `AgentConfig.tools` to `list[ToolEntry]` (breaking
  ~8 tests + factory passthru, coordinated SPEC_02 evolution) OR keep opaque +
  resolve at factory time. This slice leaves it opaque (safer).
