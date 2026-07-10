---
change: tools-slice-a-schema-resolver
spec: SPEC_11
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/tools-slice-a-schema-resolver/proposal.md (engram obs-2002)
  - spec: openspec/changes/tools-slice-a-schema-resolver/specs/tools-slice-a-schema-resolver/spec.md (engram 2003)
  - design: openspec/changes/tools-slice-a-schema-resolver/design.md (written inline by orchestrator)
  - exploration: engram sdd/tools/explore (obs-2001)
  - shipped_resolver: src/yaml_agno/di/agno_resolver.py (resolve_class, public line 184)
strict_tdd: true
test_command: python -m pytest -m unit
---

# Tasks: tools-slice-a-schema-resolver

> SPEC_11 **slice A** (foundation). De-opacifica `AgentConfig.tools` a una unión
> discriminada `ToolEntry` y resuelve 3 de 5 `kind` (builtin / function /
> toolkit_class). MCP, `ToolFactory`, `@tool` wrapping y hooks son **DEFER** a
> slices B/C/D. TDD estricto: RED → GREEN por componente.

## CRITICAL DECISION (bake in)

**`AgentConfig.tools` queda OPACO (`list[ToolConfig]`, `dict[str, Any]`) en slice A.**
El schema `ToolEntry` shipea **STANDALONE**; el wiring a `AgentConfig` es slice C
(misma táctica que `model-config-schema` dejó `AgentConfig.model` intacto).
**NO modificar `agent_config.py`.** Esto evita romper ~8 tests existentes y el
passthru de `agent_factory`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450 (src ~300: schema ~95, security ~40, custom_loader ~85, registry ~120, __init__ ~35; tests ~150) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | single PR (slice coherente, ~450 está cerca del budget pero es TDD-additive) |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception (single PR dentro del budget aproximado) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | ToolEntry schema + security + custom_loader + registry + tests (slice A completo) | PR único | net-new bajo `src/yaml_agno/tools/`; AgentConfig NO tocado; base = tracker branch |

## Open Items (leer antes de apply)

- **`AgentConfig.tools` queda opaco**: el campo se tipo-narrowa en slice C, NO
  aquí. El design §6 documenta la decisión; `git diff` sobre `agent_config.py`
  debe quedar **vacío**.
- **Toolkits NO son dataclasses**: `ProviderFactory._compose_kwargs`
  (`dataclasses.fields()`) NO aplica — los adapters usan
  `inspect.signature(cls.__init__)`. Verificado: `CalculatorTools.__init__(self,
  **kwargs)` acepta todo; `ShellTools` y `HackerNewsTools` tienen params fijos.
- **`yfinance`/`duckduckgo` son deps opcionales**: los adapters del registry NO
  importan los toolkits directamente (`resolve_class` lo hace lazy). Los tests
  que construyen instancias reales usan `pytest.importorskip`.
- **El `_filter_kwargs` short-circuit**: si `__init__` tiene `**kwargs`
  (CalculatorTools), el adapter pasa todo sin filtrar — comportamiento
  verificado y esperado.
- **`ToolkitAdapter` NO frozen**: el design propone `dataclasses.field(
  default_factory=dict)` sobre dataclass no-frozen (el comentario sobre
  `__post_init__` workaround queda obsoleto — apply usa el literal del design).

## Phase 1: Baseline (verificación pre-RED)

- [x] 1.1 Confirmar `git status` limpio y HEAD en la rama tracker del slice. **Req: Rollback Plan.**
- [x] 1.2 Confirmar `src/yaml_agno/tools/__init__.py` existe vacío (0 bytes, creado en bootstrap #2). **Req: Namespaces canónicos.**
- [x] 1.3 Confirmar `AgnoResolver.resolve_class` público en `src/yaml_agno/di/agno_resolver.py:184` y que acepta `(module_path, class_name) -> type`. **Req: CustomToolLoader delega al resolver shipped (no reimplementa importlib).**
- [x] 1.4 Confirmar `core_infrastructure.dependency.InMemoryDependencyAdapter` importable (double para tests, ya usado en `tests/unit/di/test_provider_factory.py`). **Req: Testing Strategy.**

## Phase 2: RED — tests unitarios (cubren los 18 escenarios)

> Todos bajo `tests/unit/tools/` con `@pytest.mark.unit`. Importan
> `InMemoryDependencyAdapter` + stubs `@dataclass` para los Toolkits (no tocan
> `agent_config.py`). Un archivo test por componente, en orden de dependencia.

- [x] 2.1 Crear `tests/unit/tools/__init__.py` (vacío) — package marker. **Req implícito (pytest discovery).**
- [x] 2.2 `tests/unit/tools/test_schema.py`: `TypeAdapter(ToolEntry)` discrimina por `kind` a `BuiltinToolConfig`/`CustomToolConfig`/`CustomToolkitConfig`/`McpToolConfig`/`McpMultiToolConfig`; ausencia de `kind` → `ValidationError`; `kind` desconocido (ej. `mcp` parsea pero loader luego lanza `NotImplementedError`); golden path `builtin calculator` con `include_tools` conservado; `BuiltinToolConfig` con `extra="allow"` deja flujar kwargs (duckduckgo `fixed_max_results`); `CustomToolConfig` golden path con flags HITL; exclusividad mutua HITL (`requires_confirmation`+`external_execution` en `True`) → `ValidationError`; `CustomToolkitConfig` golden path con `init_args`+`exclude_tools` conservados. **Scenarios: Discriminación por kind; Entrada sin kind rechazada; kind desconocido; ToolConfig alias obsoleto; Golden Path builtin/function/toolkit_class; RED builtin desconocido; extra=allow; exclusividad HITL.**
- [x] 2.3 `tests/unit/tools/test_security.py`: `is_module_allowed("agno.tools.calculator")` True; `is_module_allowed("os.system")` False (fail-closed default); whitelist `["myapp.tools."]` habilita submódulos por prefijo; `extra_prefixes` extiende en runtime. **Scenarios: RED módulo no allowlisted; Whitelist vacía rechaza todo; Match por prefijo.**
- [x] 2.4 `tests/unit/tools/test_custom_loader.py`: `load_callable` devuelve callable CRUDO (no `agno.tools.Function`, flags NO aplicados) vía stub resolver; `load_toolkit_class` devuelve la clase sin instanciar; `SecurityError` cuando `module_path` no está allowlisted (sin llamar `resolve_class`); `ValueError` en dotted-path sin punto; delegación al resolver verificada con spy. Usa `InMemoryDependencyAdapter` + AgnoResolver real o stub. **Scenarios: CustomToolLoader devuelve callable sin envolver; RED módulo no allowlisted; Slice A no envuelve con @tool.**
- [x] 2.5 `tests/unit/tools/test_registry.py`: `BUILTIN_REGISTRY` tiene exactamente 5 claves (`calculator`,`yfinance`,`hackernews`,`duckduckgo`,`shell`); cada `ToolkitAdapter` expone `module_path`/`class_name`/`packages`/`alias_map`; `_normalize_aliases` yfinance `stock_price`→`enable_stock_price` (y `company_news`/`analyst`); `_filter_kwargs` pasa todo si `__init__` tiene `**kwargs` (stub CalculatorTools); `_filter_kwargs` descarta `parametro_inventado` y conserva `fixed_max_results` (stub DuckDuckGo con signature fija); `build()` integra resolve→normalize→filter→instantiate con stub resolver; `UnknownBuiltinError` ausente del catálogo. **Scenarios: Alias normalization yfinance; Kwargs filtering duckduckgo; BUILTIN_REGISTRY 5 adapters.**
- [x] 2.6 Correr `python -m pytest tests/unit/tools/` → **RED confirmado** (todos fallan por `ImportError` de los módulos `tools.schema`/`tools.security`/`tools.custom_loader`/`tools.registry`). **Gate TDD: no pasar a Phase 3 sin RED visible.**

## Phase 3: GREEN — implementación (literal del design §1-5)

> Código fiel al design (documentación viva). NO modificar `agent_config.py`.
> Orden: `security` (sin deps) → `schema` (sin deps internos) → `custom_loader`
> (dep `security` + resolver TYPE_CHECKING) → `registry` (dep resolver
> TYPE_CHECKING) → `__init__` re-export.

- [x] 3.1 Crear `src/yaml_agno/tools/security.py` literal del design §2: `SecurityError`, `_ALLOWED_MODULE_PREFIXES = ("agno.tools.",)`, `is_module_allowed(dotted_path, extra_prefixes=()) -> bool` con fail-closed. **Req: Guarda de seguridad con allowlist.**
- [x] 3.2 Crear `src/yaml_agno/tools/schema.py` literal del design §1: `BuiltinToolConfig` (`extra="allow"`, `name` obligatorio), `CustomToolConfig` (`extra="forbid"`, `path`), `CustomToolkitConfig` (`extra="forbid"` o `"allow"` según design, `path`+`init_args`), `McpToolConfig`/`McpMultiToolConfig` (placeholders `kind` Literal), unión `ToolEntry = BuiltinToolConfig | CustomToolConfig | CustomToolkitConfig | McpToolConfig | McpMultiToolConfig`. **Req: Discriminación ToolEntry; BuiltinToolConfig; CustomToolConfig; CustomToolkitConfig.**
- [x] 3.3 Crear `src/yaml_agno/tools/custom_loader.py` literal del design §3: `CustomToolLoader(resolver)`, `load_callable(config)->Any` y `load_toolkit_class(config)->type`, `_resolve_dotted` parte en `(module_path, name)` vía `rpartition`, aplica `is_module_allowed(module_path)` antes de `resolver.resolve_class`. **Req: CustomToolLoader devuelve callable CRUDO.**
- [x] 3.4 Crear `src/yaml_agno/tools/registry.py` literal del design §4: `UnknownBuiltinError`, `@dataclass ToolkitAdapter` (`module_path`,`class_name`,`packages`,`alias_map`), `build(resolver, init_args)` (resolve→`_normalize_aliases`→`_filter_kwargs`→instantiate), `_filter_kwargs` con short-circuit `**kwargs`, `BUILTIN_REGISTRY` con 5 adapters (yfinance/hackernews con `alias_map`). **Req: BUILTIN_REGISTRY 5 adapters + filtrado signature; Alias normalization.**
- [x] 3.5 Crear `src/yaml_agno/tools/__init__.py` con re-export del design §5 (`ToolEntry`, `BUILTIN_REGISTRY`, `CustomToolLoader`, `ToolkitAdapter`, `SecurityError`, `is_module_allowed`, los 5 configs, `UnknownBuiltinError`) + `__all__`. **Req: Re-export API pública tools.**
- [x] 3.6 Correr `python -m pytest tests/unit/tools/ -m unit` → **GREEN** (18 escenarios cubiertos). **Gate TDD: cero FAIL antes de Phase 4.**

## Phase 4: Verificación (calidad + invariantes)

- [x] 4.1 `python -m pytest -m unit` verde global (sin regresiones en suite existente). **Scenario: Suite unit verde.**
- [x] 4.2 `ruff check .` sin findings. **Scenario: Ruff limpio.**
- [x] 4.3 `mypy src/yaml_agno` sin errores (incl. TYPE_CHECKING imports del resolver). **Scenario: Mypy limpio.**
- [x] 4.4 Smoke: `python -c "from yaml_agno.tools import ToolEntry, BUILTIN_REGISTRY, CustomToolLoader, ToolkitAdapter, SecurityError, is_module_allowed; print('OK')"` imprime OK. **Scenario: Import API pública.**
- [x] 4.5 Cold imports no circulares: `python -c "from yaml_agno.tools import *"` Y `python -c "from yaml_agno.models import AgentConfig"` ambos limpios (lección slice #4). **Scenario: Sin import circular.**
- [x] 4.6 `git diff --name-only src/yaml_agno/models/config/agent_config.py` → **vacío** (AgentConfig.tools queda opaco, wiring es slice C). **Req: Invariantes DEFERRED (AgentConfig NO modificado).**
- [x] 4.7 `git diff --name-only specs/` → **vacío** (SSOT read-only). **Req: specs intocadas.**
- [x] 4.8 Aserción negativa: `python -c "import yaml_agno.tools as t; assert not hasattr(t, 'ToolFactory') and not hasattr(t, 'MCPResolver'); print('DEFER OK')"` (slice A no implementa ToolFactory ni MCP). **Scenarios: Slice A no implementa ToolFactory.build; no envuelve con @tool.**

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 Commits atómicos en orden: `test: add tool schema + security + loader + registry RED tests` (2.x) → `feat: add ToolEntry schema and security allowlist` (3.1+3.2) → `feat: add CustomToolLoader delegating to AgnoResolver` (3.3) → `feat: add BUILTIN_REGISTRY with 5 toolkit adapters` (3.4) → `feat: re-export tools public API` (3.5). **No commitear specs/ ni agent_config.py.**

## TDD Compliance Matrix (9 reqs → RED → GREEN → escenario)

| Req | RED task | GREEN task | Escenarios cubiertos |
|-----|----------|------------|----------------------|
| Discriminación `ToolEntry` por `kind` | 2.2 | 3.2 | Discriminación por kind; sin kind rechazada; kind desconocido; alias obsoleto |
| `BuiltinToolConfig` | 2.2 | 3.2 | Golden builtin calculator; RED desconocido; extra=allow |
| `CustomToolConfig` | 2.2 | 3.2 | Golden function dotted-path; exclusividad HITL |
| `CustomToolkitConfig` | 2.2 | 3.2 | Golden toolkit_class con init_args |
| `CustomToolLoader` callable CRUDO | 2.4 | 3.3 | Devuelve callable sin envolver; no @tool |
| `BUILTIN_REGISTRY` 5 adapters | 2.5 | 3.4 | Alias yfinance; filtering duckduckgo; 5 adapters |
| `is_module_allowed` allowlist | 2.3 | 3.1 | No allowlisted rechazado; whitelist vacía fail-closed; match por prefijo |
| Invariantes DEFERRED | 2.4, 2.6 | 3.3, 4.8 | No ToolFactory; no @tool wrapping; no MCP |
| `AgentConfig.tools` type-narrow (MODIFIED) | — (DEFER slice C) | — (DEFER slice C) | Wiring en slice C; AgentConfig intocado en slice A |

## Implementation Order (dependencias)

```
Phase 1 baseline (verify stub + resolve_class public)
   ↓
Phase 2 RED (4 test files, independientes entre sí salvo __init__.py)
   2.1 __init__  →  2.2/2.3/2.4/2.5 (paralelizables)  →  2.6 gate RED
   ↓
Phase 3 GREEN (orden por deps internos):
   3.1 security (sin deps)  ┐
   3.2 schema   (sin deps)  ├─ paralelizables
                            ┘
   3.3 custom_loader (dep security + resolver TYPE_CHECKING)
   3.4 registry     (dep resolver TYPE_CHECKING, no tools deps internos)
   3.5 __init__ re-export (dep los 4 anteriores)
   ↓
Phase 4 verificación (gate: GREEN + ruff + mypy + invariantes)
   ↓
Phase 5 commits granular
```
