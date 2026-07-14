---
change: tools-hooks-caching
spec: SPEC_11
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/tool-factory-wiring
---

# Proposal: Tools Hooks, Caching y tool_call_limit (SPEC_11 Slice D — final)

## Intent

Cerrar SPEC_11 habilitando los hooks de tools (`pre_hook`/`post_hook`/`tool_hooks`)
y `tool_call_limit` como datos declarativos en YAML que se resuelven y forwardean
a Agno, sin reimplementar runtime. El caching por llamada (`cache_results`/`cache_dir`/
`cache_ttl`) ya se entregó en slice C; este slice lo documenta como DONE. Es el slice
final de SPEC_11: sin él, un usuario YAML no puede declarar observabilidad/confirmación
alrededor de la ejecución de tools ni acotar la cantidad de tool calls por run.

**Why now**: slices A+B+C entregaron schema, `ToolFactory`, `CustomToolLoader`,
registry, `MCPResolver` y los flags de `@tool` (incluido caching). Los hooks y
`tool_call_limit` son los últimos huecos de SPEC_11 antes de archivar la SPEC.

## Scope

### In Scope (NOW)

- **Hooks en `CustomToolConfig`** (`src/yaml_agno/tools/schema.py`): añadir
  `pre_hook: str | None`, `post_hook: str | None`, `tool_hooks: list[str] = []`
  como refs dotted-path (mismo patrón que `header_provider` en `HttpMcpConfig`).
  Conservar `extra="forbid"`.
- **Resolución + forwarding de hooks** (`src/yaml_agno/tools/tool_factory.py`):
  en `_wrap_tool`, resolver cada ref dotted-path → `Callable` vía
  `CustomToolLoader._resolve_dotted` (REUSAR infra existente — allowlist +
  `AgnoResolver.resolve_class`, NO crear `hooks.py`) y forwardear a
  `agno_tool(pre_hook=..., post_hook=..., tool_hooks=[...])`.
- **`tool_call_limit` en `AgentConfig`** (`src/yaml_agno/models/config/agent_config.py`):
  añadir `tool_call_limit: int | None = Field(default=None, ge=1)`.
- **Forwarding de `tool_call_limit`** (`src/yaml_agno/factories/agent_factory.py`):
  pasar `tool_call_limit` al `Agent(...)` cuando esté seteado.
- **Tests**: resolución de hooks (dotted-path → Callable), forwarding al
  decorator, `tool_call_limit` forwarding, integración `@tool(pre_hook=...)`.
- **Documentar caching como DONE**: `cache_results`/`cache_dir`/`cache_ttl` ya
  viven en `CustomToolConfig` y `_wrap_tool` ya los forwardea (slice C). Sin
  código nuevo — sólo constancia en este proposal.

### Out of Scope

- **Registry expansión a 120+** (`BuiltinToolConfig` → 139 módulos Agno):
  SEPARADO a su propio change `tools-registry-expansion`. Es DATA masiva, no
  lógica. Slice D retiene los 5 adapters actuales (calculator, yfinance,
  hackernews, duckduckgo, shell).
- **Concurrency executor** (`executor.py` / `run_tools_concurrently`,
  SPEC_11 TASK_012): **NEVER**. La ejecución de tools es interna al `Agent`
  de Agno (`Agent.run()`/`arun()`). yaml-agno sólo BUILD tools (SYNC), no los
  ejecuta. Reimplementar el loop de ejecución sería frankenstein.
- **Cross-run callable caching** (`cache_callables`/`callable_tools_cache_key`,
  SPEC_11 §8.3/§10.4): **DEFER** post-MVP. Es un LRU del objeto tool construido
  entre runs; las tools son baratas de construir excepto MCP (que auto-conecta).
  El caching por llamada (slice C) ya cubre el caso de uso principal.
- **Custom exceptions vía `module`** (SPEC_11 §8.2): **DEFER**. Usar
  `agno.exceptions` (`RetryAgentRun`, `StopAgentRun`) directamente.
- **Ensanchar `AgentConfig.tools` a `list[ToolEntry]`**: fuera (invariante Option B
  del slice C — `tools` permanece opaco `list[dict[str, Any]]`).

## Capabilities

### New Capabilities

None — no se introduce una nueva capability; se extiende la existente.

### Modified Capabilities

- `tool-factory-wiring`: añade campos de hooks a `CustomToolConfig` +
  resolución/forwarding en `_wrap_tool`, y añade `tool_call_limit` a
  `AgentConfig` con forwarding en `AgentFactory.build`. El caching (slice C)
  se documenta como entregado, sin cambios de spec.

## Approach

1. **Schema** (`schema.py`): los 3 campos de hooks son `str` (dotted-path) y
   `list[str]`, NO `Callable` — el callable se resuelve en runtime vía
   `_resolve_dotted` (idéntico a `header_provider`). Esto mantiene el YAML
   serializable y respeta la whitelist de imports (SPEC_11 §10.3).
2. **Resolución** (`tool_factory.py` `_wrap_tool`): por cada hook ref, llamar
   `CustomToolLoader._resolve_dotted(ref)` → `Callable`; inyectar en el dict
   `flags` bajo `pre_hook`/`post_hook`/`tool_hooks`. El filtro existente
   (`v is not None`) ya descarta los no-seteados. Verificado en runtime por el
   orchestrador: `@tool(pre_hook=callable)(func)` setea `Function.pre_hook`.
3. **`tool_call_limit`** (`agent_config.py`): un solo `Field(default=None, ge=1)`.
   `AgentFactory.build` lo forwardea a `Agent(tool_call_limit=...)` sólo si no es
   `None` (respeta el default de Agno).
4. **No `hooks.py`**: SPEC_11 TASK_005 propone un resolver `hooks.py` separado,
   pero reusa `CustomToolLoader._resolve_dotted` (allowlist + `resolve_class`).
   Un archivo extra es frankenstein.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/schema.py` | Modified | Añade `pre_hook`, `post_hook`, `tool_hooks` a `CustomToolConfig`; actualiza docstring (quita nota "INTENTIONALLY ABSENT"). |
| `src/yaml_agno/tools/tool_factory.py` | Modified | `_wrap_tool` resuelve refs dotted-path → Callable y las añade al dict `flags`. |
| `src/yaml_agno/models/config/agent_config.py` | Modified | Añade `tool_call_limit: int \| None = Field(default=None, ge=1)`. |
| `src/yaml_agno/factories/agent_factory.py` | Modified | Forwardea `tool_call_limit` al `Agent(...)`; quita el comment de DEFER. |
| `tests/` | New | Casos de hook resolution, forwarding, `tool_call_limit`, integración `@tool(pre_hook=...)`. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `@tool(pre_hook=...)` no acepta hooks por kwargs en alguna versión Agno | Low | Verificado por orchestrador en runtime (Agno 2.6.22): `Function.pre_hook` se setea. Apply debe re-verificar con un test de integración. |
| Hook ref apunta a módulo fuera de la allowlist → error opaco | Med | `_resolve_dotted` ya hace fail-closed (SPEC_11 §10.3). Mensaje de error debe nombrar el módulo rechazado. |
| `tool_call_limit` cruza SPEC_11/SPEC_02 (AgentConfig es SPEC_02) | Low | Slice D añade el campo; el wiring a `Agent` es SPEC_01 (AgentFactory). Coordinar que el campo no rompa los 9 slots opacos de SPEC_02. |
| Usuario espera concurrency custom (executor.py) | Low | Documentar en README/SPEC que la concurrencia es interna a Agno; `asyncio.TaskGroup` (STRAT003) aplica al bootstrap, no a tool execution. |

## Rollback Plan

Todos los cambios son aditivos (campos opcionales con default `None`/`[]`,
forwarding condicional). Revertir el commit / PR del slice restaura el estado
de slice C sin migración de datos ni breaking change en YAML existente (los
campos nuevos son opcionales). Los YAML que declaren hooks quedarían
rechazados por `extra="forbid"` tras el rollback — esperado y seguro.

## Dependencies

- `openspec/specs/tool-factory-wiring` (slice C — ya entregado: `ToolFactory`,
  `_wrap_tool`, flags de `@tool`, caching).
- `CustomToolLoader._resolve_dotted` (custom_loader.py) — infra de resolución
  dotted-path con allowlist (preexistente).

## Success Criteria

- [ ] `CustomToolConfig` acepta `pre_hook`/`post_hook`/`tool_hooks` y rechaza
      campos ajenos (`extra="forbid"` se conserva).
- [ ] `_wrap_tool` resuelve refs dotted-path → Callable y forwardea a
      `@tool(pre_hook=..., post_hook=..., tool_hooks=[...])`; el `Function`
      resultante tiene los hooks seteados.
- [ ] `AgentConfig` acepta `tool_call_limit: int >= 1` (default `None`);
      `AgentFactory.build` lo forwardea al `Agent`.
- [ ] Un YAML con `tool_hooks: ["myapp.hooks.logger_hook"]` produce un
      `Function` cuyo `tool_hooks` contiene el callable resuelto.
- [ ] Caching por llamada (slice C) sigue funcionando sin regresión.
- [ ] SPEC_11 queda archivable tras este slice.

## Proposal question round

Las decisiones técnicas (hooks NOW, caching DONE, concurrency NEVER, registry
SEPARATED, tool_call_limit NOW) fueron pre-resueltas por exploración +
verificación runtime del orchestrator. Quedan preguntas de
producto/PRD que conviene confirmar antes de spec:

1. **Negocio — hooks**: ¿cuál es el caso de uso prioritario (logging/observabilidad,
   confirmation/autorización, métricas, auditoría)? Define el ejemplo canónico
   del README y el test de integración.
2. **Reglas — allowlist de hooks**: ¿los módulos de hooks viven bajo un prefijo
   fijo (ej. `myapp.hooks.`) o cualquier módulo en la allowlist de custom tools
   puede proveer hooks? ¿Quién lo configura (bootstrap ConfigManager)?
3. **Reglas — `tool_call_limit` bound superior**: SPEC_11 no fija un máximo.
   ¿ dejamos `ge=1` sin tope, o imponemos un `le=100` razonable por seguridad
   de costos? Impacta el `Field`.
4. **Edge case — hook que falla**: si `_resolve_dotted` no encuentra el módulo,
   ¿fail-fast en `ToolFactory.build` (ValidationError) o skip con warning?
   Fail-fast es más seguro pero rompe el run entero.
5. **Outcome — archivado SPEC_11**: tras este slice, ¿se archiva SPEC_11
   completa, o queda abierta por el registry 120+ (`tools-registry-expansion`)
   como change dependiente?

**Assunciones default si no hay respuesta**: (1) logging como ejemplo canónico;
(2) misma allowlist que custom tools (§10.3); (3) `ge=1` sin tope superior
(seguir Agno); (4) fail-fast ValidationError; (5) SPEC_11 archivable; registry
es change separado independiente.
