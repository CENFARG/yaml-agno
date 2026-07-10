---
change: tools-slice-a-schema-resolver
spec: SPEC_11
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/dependency-facade
  - openspec/specs/agent-config-schema
---

# Proposal: Tools Slice A — Tool Schema + Resolver Foundation

## Intent

`AgentConfig.tools` es hoy un slot opaco (`list[ToolConfig]` con `ToolConfig = dict[str, Any]`,
`agent_config.py:14,52`): no hay validación de forma ni resolución a objetos Agno.
SPEC_11 necesita transformar ese slot en una unión discriminada validada y resolver 3 de
los 5 `kind` (`builtin`, `function`, `toolkit_class`) en objetos Agno nativos. MCP, orquestación
y hooks vienen después — este slice pone los cimientos de-serializables y reutiliza
`AgnoResolver.resolve_class` (`di/agno_resolver.py:184`) que ya está shipped.

## Why Now

- `AgnoResolver.resolve_class` (public, `agno_resolver.py:184-199`) + `ImportlibDependencyAdapter`
  ya están shipped por SPEC_01 — slice A no agrega dependencias.
- El slot `AgentConfig.tools` ya existe (`agent_config.py:52`); sólo necesita type-narrowing.
- No hay async ni red: Pydantic + importlib + `inspect.signature`. TDD puro (patrón ProviderFactory).

## Scope

### In Scope

- `src/yaml_agno/tools/schema.py` — `ToolEntry` (unión discriminada por `kind`:
  `builtin` | `function` | `toolkit_class`; las variantes `mcp`/`mcp_multi` se declaran
  pero quedan sin resolver en este slice), `BuiltinToolConfig` (`extra=allow`),
  `CustomToolConfig`, `CustomToolkitConfig`.
- `src/yaml_agno/tools/custom_loader.py` — `CustomToolLoader.load(config) -> Callable`
  (callable CRUDO vía `AgnoResolver.resolve_class` + allowlist; SIN `@tool` wrapping).
- `src/yaml_agno/tools/registry.py` — `BUILTIN_REGISTRY` con 5 adapters
  (`calculator`, `yfinance`, `hackernews`, `duckduckgo`, `shell`); cada adapter filtra
  kwargs vía `inspect.signature(cls.__init__)` (NO `dataclasses.fields` — los Toolkits
  NO son dataclasses) y normaliza alias (`stock_price` → `enable_stock_price`).
- `src/yaml_agno/tools/security.py` — `is_module_allowed` + `SecurityError` (allowlist guard).
- Update `agent_config.py` — `tools` se type-narrowa a `list[ToolEntry]`; `ToolConfig`
  se conserva como alias deprecado para no romper referencias existentes.
- Tests: schema (unión discriminada), `custom_loader` (allowlist + import), `registry`
  (5 adapters + normalización de alias).

### Out of Scope (DEFER explícito)

- **Slice B** — MCP (single + multi): `MCPResolverImpl`, `header_provider` Callable resolution,
  lifecycle connect/close. `kind: mcp`/`mcp_multi` se declaran en el schema pero NO se resuelven.
- **Slice C** — `ToolFactory` orchestrator + wiring `AgentFactory`: `@tool(**flags)` wrapping del
  callable crudo, `tool_call_limit` forwarding, integración con SPEC_01.
- **Slice D** — Hooks (`ToolHookRef`), caching de callables, concurrencia `TaskGroup`,
  expansión del `BUILTIN_REGISTRY` a 120+ toolkits.
- Renombre/borrado de `ToolConfig` (se conserva como alias deprecado).

## Capabilities

### New Capabilities

- `tool-schema`: unión discriminada `ToolEntry` + sub-configs (`BuiltinToolConfig`,
  `CustomToolConfig`, `CustomToolkitConfig`) — la forma validada del slot `tools`.
- `tool-custom-loader`: resolución de dotted-path callables vía `AgnoResolver` + allowlist.
- `tool-builtin-registry`: 5 adapters con filtrado por `inspect.signature` + alias normalization.
- `tool-import-whitelist`: `is_module_allowed` + `SecurityError` (backend sanitization owner SPEC_11).

### Modified Capabilities

- `agent-config-schema`: el campo `tools` se type-narrowa de `list[dict]` opaco a
  `list[ToolEntry]` (back-compat preservada vía alias `ToolConfig` deprecado).

## Approach

1. **Schema** (`tools/schema.py`): unión PEP 695 `Annotated[..., Field(discriminator="kind")]`.
   Las variantes `mcp`/`mcp_multi` se incluyen como placeholders forward-compat pero
   levantan `NotImplementedError` si alguien intenta instanciarlas fuera del slice B.
2. **Resolver del conflicto de nombre**: introducir `ToolEntry` como nombre canónico de la
   unión. `ToolConfig = dict[str, Any]` (`agent_config.py:14`) se mantiene como alias
   **deprecado** (warning + re-export). `AgentConfig.tools` pasa a `list[ToolEntry]` pero
   acepta dicts crudos por compatibilidad (Pydantic los coerce vía la unión discriminada).
3. **CustomToolLoader** reusa `AgnoResolver.resolve_class(module_path, class_name)`
   (`agno_resolver.py:184`) — NO reimplementa importlib. `is_module_allowed` filtra antes.
   Devuelve el callable **crudo**; el wrapping `@tool` es slice C.
4. **Adapters del BUILTIN_REGISTRY**: `inspect.signature(cls.__init__)` filtra kwargs
   (los Toolkits son clases regulares, NO dataclasses — `dataclasses.fields()` fallaría).
   Alias normalization por adapter (ej. YFinance `_ALIASES`).
5. **TDD estricto**: RED-GREEN-REFACTOR. Tests con `@dataclass` stubs + `InMemoryDependencyAdapter`
   siguiendo `tests/unit/di/test_provider_factory.py`. Sin red, sin async.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/schema.py` | New | Unión discriminada `ToolEntry` + sub-configs |
| `src/yaml_agno/tools/custom_loader.py` | New | `CustomToolLoader` vía `AgnoResolver` |
| `src/yaml_agno/tools/registry.py` | New | `BUILTIN_REGISTRY` 5 adapters |
| `src/yaml_agno/tools/security.py` | New | `is_module_allowed` + `SecurityError` |
| `src/yaml_agno/models/config/agent_config.py` | Modified | `tools: list[ToolEntry]`; `ToolConfig` alias deprecado |
| `tests/unit/tools/` | New | schema, custom_loader, registry |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `ToolConfig` name clash rompe referencias existentes | Low | Alias deprecado + re-export; `AgentConfig.tools` acepta dicts crudos vía coerce |
| Toolkits NO son dataclasses → `dataclasses.fields` falla | Verified | Usar `inspect.signature(cls.__init__)` (confirmado en exploración) |
| Registry futuro (120+) cambia forma de adapters | Low | Protocol `ToolkitRegistry` (SPEC_11 §9.2) mantiene extensibilidad |
| Pydantic coerce de dict → ToolEntry rechaza configs válidas | Medium | Tests de round-trip YAML→ToolEntry en TDD |
| `MCPTools`/`MCPResolver` referenciados desde schema pero no resueltos | Low | Placeholders `NotImplementedError` explícitos; slice B los implementa |

## Rollback Plan

Slice A es aditivo (4 archivos nuevos + type-narrow de 1 campo). Rollback:

1. Revertir `agent_config.py` a `tools: list[ToolConfig]` (alias vuelve a ser canónico).
2. Eliminar `src/yaml_agno/tools/` (los 4 módulos nuevos).
3. `git revert` del commit del slice — sin migración de datos (slots opacos preservados).

No hay cambios en `AgentFactory` ni en runtime de Agno — el slice no toca el camino de build.

## Dependencies

- `AgnoResolver.resolve_class` (shipped, `di/agno_resolver.py:184`) — reusado, no modificado.
- `openspec/specs/dependency-facade` (SPEC_01) — `AgnoResolver` + `ImportlibDependencyAdapter`.
- `openspec/specs/agent-config-schema` (SPEC_02) — `AgentConfig.tools` slot a type-narrowa.
- SPEC_11 §1.2 (ToolEntry union, `SPEC_11_TOOLS_AND_MCP.md:47`) + §9.2-9.5 (resolvers, lineas 666-810).

## Success Criteria

- [ ] `AgentConfig(tools=[{"kind": "builtin", "name": "calculator"}])` valida sin error.
- [ ] `CustomToolLoader.load` devuelve callable crudo; allowlist bloquea módulos no listados.
- [ ] 5 adapters del `BUILTIN_REGISTRY` construyen Toolkit/Callable con kwargs filtrados.
- [ ] Alias normalization: `stock_price: true` → `enable_stock_price=True` (YFinance).
- [ ] `ToolConfig = dict[str, Any]` sigue importable (deprecado) — cero referencias rotas.
- [ ] Cobertura 100% en los 4 módulos nuevos (Strict TDD, `coverage_threshold: 100`).
