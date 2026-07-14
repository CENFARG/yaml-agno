---
change: mcp-integration
spec: SPEC_11
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/tools-slice-a-schema-resolver
slice: B_mcp_integration
---

# Proposal: Integración MCP (SPEC_11 slice B)

## Intent

SPEC_11 slice A entregó `McpToolConfig`/`McpMultiToolConfig` como placeholders
vacíos (`schema.py:76-93`) y `CustomToolLoader.load_mcp`/`load_mcp_multi` que
lanzan `NotImplementedError` (`custom_loader.py:73-90`). Slice B los reemplaza
por schemas reales (unión discriminada por `transport`) y un `MCPResolver`
SYNC que construye instancias `MCPTools`/`MultiMCPTools` **no conectadas** — el
`Agent` de Agno ejecuta `connect()`/`close()` en su lifecycle async
(`agent/_tools.py: aget_tools` → `connect_mcp_tools`).

**Éxito**: un YAML con `kind: mcp` (stdio o http) o `kind: mcp_multi` valida,
resuelve a una instancia Agno sin conexión, y `Agent` la conecta al primer run.
No hay `async` en el resolver.

## Scope

### In Scope

- Reemplazar placeholder `McpToolConfig` por unión discriminada:
  `StdioMcpConfig` (`transport: Literal["stdio"]`, `command`, `env`,
  `extra="forbid"`, rechaza `headers`) | `HttpMcpConfig`
  (`transport: Literal["streamable-http","sse"]`, `url`, `headers`, `timeout`,
  `sse_read_timeout`, `header_provider`, `refresh_connection`,
  `extra="forbid"`).
- Reemplazar placeholder `McpMultiToolConfig`: `servers: list[McpToolConfig]`
  (`min_length=1`), `allow_partial_failure: bool=False`,
  `refresh_connection: bool=False`, `extra="forbid"`. Emite `DeprecationWarning`
  documentada.
- NUEVO `src/yaml_agno/tools/mcp_resolver.py`: `MCPResolver` SYNC con
  `resolve_single(config) -> MCPTools` y `resolve_multi(config) ->
  MultiMCPTools` devolviendo instancias **no conectadas**. Construye
  `SSEClientParams` (timeout=float) / `StreamableHTTPClientParams`
  (timeout=timedelta) según `transport`. Resuelve `header_provider` (str
  dotted-path → `Callable[..., dict]`) reutilizando
  `security.is_module_allowed` + el mecanismo de
  `CustomToolLoader._resolve_dotted`.
- `CustomToolLoader.load_mcp`/`load_mcp_multi` delegan al `MCPResolver`
  (elimina `NotImplementedError`).
- Tests: discriminación por `transport`, stdio rechaza headers, construcción
  de params stdio/http, timeout SSE=float vs StreamableHTTP=timedelta,
  resolución de `header_provider`, `allow_partial_failure`, manejo de
  `DeprecationWarning`.
- Reconciliar SPEC_11 §9.6 (eliminar `await tools.connect()` del resolver;
  ampliar `resolve_multi` a `commands`/`urls`/`urls_transports`/
  `server_params_list`/`allow_partial_failure`).

### Out of Scope (DEFER explícito)

- **Slice C**: `ToolFactory.build(tool_set)` y wiring en `AgentFactory`
  (`Agent.tools`).
- **Slice D**: hooks (`ToolHookRef`), `cache_callables`, concurrencia
  (`TaskGroup`), expansión de `BUILTIN_REGISTRY` a 120+.
- `close()` lifecycle: responsabilidad del `Agent` (registra en
  `_mcp_tools_initialized_on_run`, desconecta post-run).
- `refresh_connection` runtime: el resolver sólo forwardea el flag; Agno lo
  maneja.
- `header_provider` por-servidor en `MultiMCPTools`: Agno no lo soporta (se
  aplica uniforme a todos los servers). Documentado — los usuarios usan
  múltiples `kind: mcp` para per-server.

## Capabilities

### New Capabilities

- `mcp-integration`: schema MCP (stdio/http/multi) + `MCPResolver` SYNC que
  devuelve instancias Agno no conectadas.

### Modified Capabilities

- `tools-slice-a-schema-resolver`: los placeholders `McpToolConfig`/
  `McpMultiToolConfig` se reemplazan por schemas reales;
  `load_mcp`/`load_mcp_multi` dejan de lanzar `NotImplementedError`.

## Approach

**Decisión clave — SYNC resolver**: `MCPResolver.resolve_single`/
`resolve_multi` son síncronos y devuelven instancias construidas pero **no
conectadas**. El `Agent` de Agno detecta `MCPTools`/`MultiMCPTools` por MRO en
`aget_tools` y ejecuta `await tool.connect()` si `not tool.initialized`. Esto
mantiene el resolver alineado con el patrón SYNC de slice A
(`CustomToolLoader`) y con TECH004 (async boundary en bootstrap, no en
resolución). Diverge de SPEC_11 §9.6 (líneas 832, 840) que muestra
`await tools.connect()` en el resolver — el spec se reconcilia en este slice.

**División del schema por transport**: `McpToolConfig = Annotated[
StdioMcpConfig | HttpMcpConfig, Field(discriminator="transport")]`. stdio
rechaza `headers` por `extra="forbid"` (Agno levanta `ValueError` si se
inyecta `header_provider` en stdio — reforzado a nivel schema).
`HttpMcpConfig` discrimina entre `sse` y `streamable-http` para construir el
`ClientParams` correcto.

**timeout type divergence**: YAML porta `float` (segundos) para ambos
transports. El resolver ramifica: SSE → pasa el float directo;
StreamableHTTP → `timedelta(seconds=...)`.

**`header_provider`**: YAML porta `str` (dotted-path). El resolver lo resuelve
a `Callable[..., dict]` reutilizando `security.is_module_allowed` + el mismo
mecanismo de `CustomToolLoader._resolve_dotted` (NO es un import path nuevo).
Agno inspecciona la signature del callable y pasa run_context/agent/team sólo
si la función los declara.

**`resolve_multi` completo**: soporta `commands`/`urls`/`urls_transports`/
`server_params_list`/`allow_partial_failure` (SPEC_11 §9.6 era incompleto —
sólo `commands`). `MultiMCPTools` emite `DeprecationWarning` incondicional;
tests filtran o usan `pytest.warns`, y se documenta migración a múltiples
`kind: mcp`.

## Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `src/yaml_agno/tools/schema.py` | Modified | Placeholders → `StdioMcpConfig`/`HttpMcpConfig`/`McpMultiToolConfig` reales (líneas 76-93). |
| `src/yaml_agno/tools/mcp_resolver.py` | New | `MCPResolver` SYNC: `resolve_single`/`resolve_multi`, construcción de params, resolución de `header_provider`. |
| `src/yaml_agno/tools/custom_loader.py` | Modified | `load_mcp`/`load_mcp_multi` delegan al resolver (líneas 73-90). |
| `src/yaml_agno/tools/security.py` | Reused | `is_module_allowed` reutilizado para `header_provider` (sin cambios). |
| `specs/SPEC_11_TOOLS_AND_MCP.md` | Modified | §9.6: eliminar `connect()` del resolver, ampliar `resolve_multi`. |
| `tests/tools/` | New | Schema, resolver, DeprecationWarning, header_provider, timeout-type. |

## Risks

| Riesgo | Likelihood | Mitigación |
|--------|------------|------------|
| **R-MCP-1**: SPEC_11 §9.6 muestra `await connect()` en el resolver (líneas 832, 840) — diverge de SYNC. | High | Reconciliar §9.6 en este slice; decisions TECH004 ubica async en bootstrap. |
| **R-MCP-2**: `StreamableHTTPClientParams.timeout` es `timedelta`; `SSEClientParams.timeout` es `float`. | Medium | Resolver ramifica por transport; YAML porta float, se envuelve a `timedelta(seconds=...)` para streamable-http. |
| **R-MCP-3**: `MultiMCPTools` emite `DeprecationWarning` en toda construcción. | High | Tests filtran con `filterwarnings`; documentar migración (RISK004). |
| **R-MCP-4**: `header_provider` en `MultiMCPTools` aplica a todos los servers; per-server no soportado. | Medium | Documentar; usuarios con headers por-servidor usan múltiples `kind: mcp`. |
| **R-MCP-5**: `Agent` log_warning (no raise) si `connect()` falla — tool MCP puede no estar disponible silenciosamente. | Medium | Documentar en verification; considerar surfacing futuro. |
| **R-MCP-6**: `header_provider` en stdio hace que Agno levante `ValueError`. | Low | Schema rechaza `headers` en stdio vía `extra="forbid"` antes de runtime. |

## Rollback Plan

Slice B toca 3 archivos (`schema.py`, `custom_loader.py`, nuevo
`mcp_resolver.py`) + spec + tests. Rollback: revertir el commit del slice y
restaurar los placeholders de slice A (`git revert`). Los placeholders vuelven
a `NotImplementedError` — `AgentConfig.tools` con `kind: mcp` sigue parseando
(pero no resuelve), consistente con el estado pre-B. No hay migración de datos
ni cambios en `AgentConfig.tools` (sigue `list[ToolEntry]`; slice A ya
incluía `McpToolConfig`/`McpMultiToolConfig` en la unión).

## Dependencies

- Slice A entregado (PR #17, archivado `2025-01-08-tools-slice-a-schema-resolver`):
  `schema.py` placeholders, `custom_loader.py` `NotImplementedError`,
  `security.is_module_allowed`.
- Agno v2.6.22: `agno.tools.mcp.MCPTools`, `agno.tools.mcp.MultiMCPTools`,
  `SSEClientParams`, `StreamableHTTPClientParams`, `StdioServerParameters`.
- `agno/tools/mcp/mcp.py`: `MCPTools.__init__` (sin headers/timeout top-level).
- `agent/_tools.py`: `connect_mcp_tools`/`disconnect_mcp_tools` (async
  lifecycle del Agent).

## Success Criteria

- [ ] `kind: mcp` con `transport: stdio` valida y resuelve a `MCPTools` no
  conectada.
- [ ] `kind: mcp` con `transport: streamable-http` y `transport: sse` validan
  y resuelven a `MCPTools` no conectada con `ClientParams` correctos
  (timeout tipo correcto por transport).
- [ ] `kind: mcp_multi` valida, resuelve a `MultiMCPTools` no conectada,
  emite `DeprecationWarning` (filtrada/assertada en tests).
- [ ] stdio + `headers` rechazado a nivel schema (`ValidationError`).
- [ ] `header_provider` (str dotted-path) resuelve a `Callable` vía allowlist;
  módulo no-allowlisted → `SecurityError`.
- [ ] `MCPResolver` no llama `connect()`/`close()` — el `Agent` lo hace.
- [ ] `resolve_multi` soporta `commands`/`urls`/`urls_transports`/
  `server_params_list`/`allow_partial_failure`.
- [ ] SPEC_11 §9.6 reconciliado (sin `connect()` en resolver; `resolve_multi`
  ampliado).
- [ ] 100% coverage en módulos nuevos/modificados; `pytest -m unit` verde.
