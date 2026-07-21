---
change: mcp-integration
spec: SPEC_11
artifact: tasks
status: applied
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/mcp-integration/proposal.md (engram obs-2021)
  - spec: openspec/changes/mcp-integration/specs/mcp-integration/spec.md (engram obs-2022)
  - design: openspec/changes/mcp-integration/design.md (917 lines, complete — written by design agent before crash)
  - exploration: engram sdd/mcp-integration/explore (obs-2018 — verified Agno 2.6.22 signatures)
  - shipped_slice_a_schema: src/yaml_agno/tools/schema.py (McpToolConfig/McpMultiToolConfig placeholders, lines 76-93)
  - shipped_slice_a_loader: src/yaml_agno/tools/custom_loader.py (load_mcp/load_mcp_multi NotImplementedError, lines 73-90)
  - shipped_slice_a_security: src/yaml_agno/tools/security.py (is_module_allowed, _resolve_dotted pattern)
  - shipped_slice_a_tests_schema: tests/unit/tools/test_schema.py (4 placeholder tests MUST be updated — see Breaking Changes)
  - shipped_slice_a_tests_loader: tests/unit/tools/test_custom_loader.py (2 NotImplementedError tests MUST be updated)
  - normative_ssot: specs/SPEC_11_TOOLS_AND_MCP.md (§6.5, §6.9, §6.10, §9.6; decisions 10.2/10.5/10.7)
  - gate: .chats/decisions.yaml (VQ execution — SSOT for verification)
strict_tdd: true
test_command: python -m pytest -m unit
---

# Tasks: mcp-integration (SPEC_11 slice B — MCP server resolution)

> SPEC_11 **slice B**. Reemplaza los placeholders `McpToolConfig` /
> `McpMultiToolConfig` (slice A) por schemas reales con unión discriminada por
> `transport` (`StdioMcpConfig | HttpMcpConfig`) e introduce `MCPResolver`
> (SYNC, instancias **NO conectadas**). Elimina los `NotImplementedError` de
> `load_mcp` / `load_mcp_multi`. TDD estricto: RED → GREEN por componente.
>
> **DEFER**: `ToolFactory` + wiring (slice C), hooks/caching/`TaskGroup`
> (slice D), `connect()` / `close()` (Agent runtime).

## CRITICAL DECISIONS (bake in)

1. **SYNC resolver returns UNCONNECTED instances** — NO `connect()` in the
   resolver. Agent owns connect/close via `aget_tools` → `connect_mcp_tools`
   (diverges from SPEC_11 §9.6; the delta spec amends it).
2. **Dual discriminator**: `kind=mcp` (outer ToolEntry) → `transport=stdio|sse|streamable-http` (inner McpToolConfig). Both `StdioMcpConfig` and
   `HttpMcpConfig` MUST carry `kind: Literal["mcp"] = "mcp"` for the outer
   union to route correctly.
3. **timeout type branching**: SSE → `float`, StreamableHTTP → `timedelta`
   (resolver wraps). YAML carries `float | None` for both.
4. **`header_provider` str → Callable** via the SAME slice-A allowlist
   (`security.is_module_allowed` + `_resolve_dotted` pattern).
5. **`McpMultiToolConfig`**: `servers` + `allow_partial_failure` +
   `refresh_connection`. NO `cache_results` (deferred to slice D).
6. **`AgentConfig.tools` stays opaque** — NOT touched (wiring is slice C).

## Breaking Changes (slice-A test updates — MANDATORY)

The following slice-A tests assert placeholder behavior and WILL BREAK when
the placeholders are replaced. They MUST be updated in Phase 2 (RED) before
new tests are added:

| File | Test | Current assertion | New behavior |
|------|------|-------------------|--------------|
| `test_schema.py:52` | `test_tool_entry_mcp_placeholder_parses` | `McpToolConfig` is a BaseModel, `{"kind":"mcp","command":"echo"}` parses | `McpToolConfig` is now an Annotated union; must add `transport: stdio`; `isinstance` check changes |
| `test_schema.py:59` | `test_tool_entry_mcp_multi_placeholder_parses` | `{"kind":"mcp_multi"}` parses (no servers) | `servers` is now required (`min_length=1`); must add servers |
| `test_custom_loader.py:76` | `test_load_mcp_raises_not_implemented` | `McpToolConfig()` raises NotImplementedError | `McpToolConfig()` no longer constructs (union); NotImplementedError removed |
| `test_custom_loader.py:86` | `test_load_mcp_multi_raises_not_implemented` | `McpMultiToolConfig()` raises NotImplementedError | `McpMultiToolConfig()` requires servers; NotImplementedError removed |

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~520-600 (src ~280: schema modify ~110, mcp_resolver new ~180, custom_loader modify ~50, __init__ modify ~30; tests ~280: 3 new test files ~220 + 4 existing tests updated ~60) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | single PR with `size:exception` (slice is a coherent atomic unit — schema + resolver + delegation are interdependent; splitting creates broken intermediate states) |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Schema (StdioMcpConfig + HttpMcpConfig + McpMultiToolConfig real) + update 2 placeholder tests | single PR | base = feature/tracker branch; standalone-testable |
| 2 | MCPResolver (resolve_single + resolve_multi + timeout branching + header_provider) | single PR | depends on Unit 1 schemas |
| 3 | CustomToolLoader delegation + __init__ re-export + update 2 loader tests | single PR | depends on Unit 2; closes the slice |

> All three units ship in ONE PR (`size:exception`) because they are tightly
> coupled: the resolver imports the schemas, the loader imports the resolver.
> Splitting into separate PRs would create broken intermediate states where
> the loader delegates to a non-existent resolver or the resolver imports
> non-existent schemas. The estimate exceeds 400 lines primarily due to TDD
> test coverage (3 new test files); the src changes are ~280 lines.

## Phase 1: Baseline (pre-RED verification)

- [x] 1.1 Confirmar `git status` limpio y HEAD en la rama tracker del slice. **Req: Rollback Plan (baseline obligatorio).**
- [x] 1.2 Confirmar `src/yaml_agno/tools/schema.py` existe con placeholders `McpToolConfig` (line 76) / `McpMultiToolConfig` (line 88) y `extra="allow"`. **Req: MODIFIED placeholders.**
- [x] 1.3 Confirmar `src/yaml_agno/tools/custom_loader.py` existe con `load_mcp` (line 73) / `load_mcp_multi` (line 85) lanzando `NotImplementedError`. **Req: load_mcp/load_mcp_multi delegan.**
- [x] 1.4 Confirmar `src/yaml_agno/tools/security.py` expone `is_module_allowed` + `SecurityError` (shipped slice A). **Req: header_provider vía allowlist.**
- [x] 1.5 Confirmar Agno imports (runtime-verified by orchestrator): `python -c "from agno.tools.mcp import MCPTools, MultiMCPTools; from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams; print('OK')"`. **Req: MCPResolver.resolve_single/resolve_multi.**
- [x] 1.6 Confirmar `SSEClientParams.timeout` es `Optional[float]` y `StreamableHTTPClientParams.timeout` es `Optional[timedelta]` (divergence confirmed). **Req: Tipo de timeout difiere por transport.**

## Phase 2: RED — tests unitarios (cubren los 21 escenarios)

> Todos bajo `tests/unit/tools/` con `@pytest.mark.unit`. Un archivo test por
> componente, en orden de dependencia. Primero actualizar los 4 tests de
> slice A que rompen, luego escribir los nuevos.

- [x] 2.1 **Actualizar** `tests/unit/tools/test_schema.py`: reescribir `test_tool_entry_mcp_placeholder_parses` → `test_tool_entry_mcp_stdio_from_dict` (dict con `kind:mcp, transport:stdio, command:"..."` parsea como `StdioMcpConfig`); reescribir `test_tool_entry_mcp_multi_placeholder_parses` → `test_tool_entry_mcp_multi_with_servers` (dict con `kind:mcp_multi, servers:[...]` parsea como `McpMultiToolConfig`). **Req: MODIFIED placeholders.**
- [x] 2.2 **Actualizar** `tests/unit/tools/test_custom_loader.py`: reescribir `test_load_mcp_raises_not_implemented` → `test_load_mcp_delegates_to_resolver` (stub MCPResolver, asser delegación, NO NotImplementedError); reescribir `test_load_mcp_multi_raises_not_implemented` → `test_load_mcp_multi_delegates_to_resolver`. **Req: load_mcp/load_mcp_multi delegan.**
- [x] 2.3 Crear `tests/unit/tools/test_mcp_schema.py`: dual-discriminator routing (`kind:mcp + transport:stdio` → `StdioMcpConfig`; `kind:mcp + transport:sse` → `HttpMcpConfig`; `kind:mcp + transport:streamable-http` → `HttpMcpConfig`); stdio rejects `headers` (ValidationError, extra=forbid); stdio rejects `header_provider`; stdio rejects `url`/`timeout`; http golden path streamable-http con headers + refresh_connection; http golden path SSE con timeout + sse_read_timeout; http rejects extra fields; `McpMultiToolConfig` servers min_length=1 (empty → ValidationError); `McpMultiToolConfig` golden path con 2 servers + allow_partial_failure; transport ausente → ValidationError; transport inválido → ValidationError. **Scenarios: Golden stdio; RED stdio headers; RED stdio header_provider; Golden streamable-http; Golden SSE timeout; Discriminación por transport; McpMulti con servers; RED servers vacío.**
- [x] 2.4 Crear `tests/unit/tools/test_mcp_resolver.py`: `resolve_single` stdio retorna `MCPTools(command=, env=)` UNCONNECTED (monkeypatch `MCPTools.__init__` captura kwargs, asser NO connect llamado, asser función síncrona); `resolve_single` http streamable-http construye `StreamableHTTPClientParams` (asser url + headers pasados, `MCPTools` recibe `server_params` + `transport`); `resolve_single` http SSE construye `SSEClientParams` con `timeout=float`; timeout streamable-http envuelto en `timedelta` (asser `isinstance(params.timeout, timedelta)` y equivale `timedelta(seconds=30)`); timeout SSE permanece float (asser `params.timeout == 5.0`); header_provider resuelto vía allowlist (callable real bajo `agno.tools.` prefix, asser pasado al constructor); header_provider None → no SecurityError (path corto); header_provider no allowlisted → `SecurityError` (sin importar módulo); header_provider sin punto → `ValueError`; `resolve_multi` con 2 servers stdio construye `MultiMCPTools(commands=[...], allow_partial_failure=)` (monkeypatch `MultiMCPTools.__init__`); `resolve_multi` con servidores mixtos (1 stdio + 1 http) popula `commands` + `server_params_list`; `resolve_multi` emite `DeprecationWarning` (`pytest.warns(DeprecationWarning)`); `resolve_multi` NO llama connect. **Scenarios: resolve_single retorna UNCONNECTED; resolve_single http construye ClientParams; resolve_multi con servidores stdio; timeout streamable timedelta; timeout SSE float; header_provider allowlist; RED header_provider no allowlisted; DeprecationWarning al construir multi.**
- [x] 2.5 Crear `tests/unit/tools/test_custom_loader_mcp.py`: `load_mcp` delega a `MCPResolver.resolve_single` (stub resolver, asser delegación); `load_mcp_multi` delega a `MCPResolver.resolve_multi`; `load_mcp` NO levanta `NotImplementedError`; lazy construction del `_mcp_resolver` (asser se construye una sola vez). Usa `InMemoryDependencyAdapter` + AgnoResolver real o stub. **Scenarios: load_mcp delega al resolver; load_mcp/load_mcp_multi ya no NotImplementedError.**
- [x] 2.6 Correr `python -m pytest tests/unit/tools/ -m unit` → **RED confirmado** (tests nuevos fallan por `ImportError` de `StdioMcpConfig`/`HttpMcpConfig`/`MCPResolver`; tests actualizados fallan porque el schema actual aún tiene placeholders). **Gate TDD: no pasar a Phase 3 sin RED visible.**

## Phase 3: GREEN — implementación (literal del design §1-4)

> Código fiel al design (documentación viva). NO modificar `agent_config.py`.
> Orden: `schema` (sin deps internos) → `mcp_resolver` (dep schema TYPE_CHECKING
> + security) → `custom_loader` (dep mcp_resolver) → `__init__` re-export.

- [x] 3.1 Modificar `src/yaml_agno/tools/schema.py` literal del design §1: reemplazar `McpToolConfig` placeholder (lines 76-86) con `StdioMcpConfig` (`extra="forbid"`, `transport: Literal["stdio"]="stdio"`, `command` obligatorio max 500, `env` opcional, `kind: Literal["mcp"]="mcp"`) + `HttpMcpConfig` (`extra="forbid"`, `transport: Literal["streamable-http","sse"]`, `url` obligatorio, `headers`/`timeout`/`sse_read_timeout`/`header_provider`/`refresh_connection` opcionales, `kind: Literal["mcp"]="mcp"`); `McpToolConfig = Annotated[StdioMcpConfig | HttpMcpConfig, Field(discriminator="transport")]`; reemplazar `McpMultiToolConfig` placeholder (lines 88-93) con modelo real (`extra="forbid"`, `servers: list[McpToolConfig]` min_length=1, `allow_partial_failure` bool=False, `refresh_connection` bool=False); actualizar `__all__` (añadir `StdioMcpConfig`, `HttpMcpConfig`); actualizar docstring módulo. **Reqs: StdioMcpConfig; HttpMcpConfig; McpToolConfig unión discriminada; McpMultiToolConfig; MODIFIED placeholders.**
- [x] 3.2 Crear `src/yaml_agno/tools/mcp_resolver.py` literal del design §2: `MCPResolver(resolver: AgnoResolver)`, `resolve_single(config: McpToolConfig) -> MCPTools` SYNC (分支 stdio → `_build_stdio` retorna `MCPTools(command=, env=)`; http → `_build_http`); `_build_http_params(config) -> tuple[ClientParams, url, transport]` (SSE → `SSEClientParams(url, headers, timeout=float, sse_read_timeout=float)`; streamable-http → `StreamableHTTPClientParams(url, headers, timeout=timedelta(seconds=N), sse_read_timeout=timedelta(...)`); `_resolve_header_provider(config)` vía `_resolve_dotted` (rpartition + `is_module_allowed` + `resolver.resolve_class`); `resolve_multi(config: McpMultiToolConfig) -> MultiMCPTools` SYNC (fan-out servers → `commands[]` + `server_params_list[]` + `urls[]` + `urls_transports[]`, forward `allow_partial_failure` + `refresh_connection`). NO `connect()` en ningún método. Imports: `from agno.tools.mcp import MCPTools, MultiMCPTools` + `from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams`. **Reqs: MCPResolver.resolve_single; MCPResolver.resolve_multi; timeout difiere por transport; header_provider vía allowlist.**
- [x] 3.3 Modificar `src/yaml_agno/tools/custom_loader.py` literal del design §3: añadir `self._mcp_resolver: MCPResolver | None = None` en `__init__`; añadir `_get_mcp_resolver()` lazy construction; reemplazar `load_mcp` (lines 73-83) → delega a `self._get_mcp_resolver().resolve_single(config)` (remover NotImplementedError); reemplazar `load_mcp_multi` (lines 85-90) → delega a `self._get_mcp_resolver().resolve_multi(config)`. Añadir import `from yaml_agno.tools.mcp_resolver import MCPResolver`. **Req: load_mcp/load_mcp_multi delegan.**
- [x] 3.4 Modificar `src/yaml_agno/tools/__init__.py` literal del design §4: añadir `from yaml_agno.tools.mcp_resolver import MCPResolver`; añadir `StdioMcpConfig`, `HttpMcpConfig` al import de schema; actualizar `__all__` (añadir `MCPResolver`, `StdioMcpConfig`, `HttpMcpConfig`). Actualizar docstring. **Req: Re-export API pública.**
- [x] 3.5 Correr `python -m pytest tests/unit/tools/ -m unit` → **GREEN** (21 escenarios cubiertos + 4 tests actualizados pasan). **Gate TDD: cero FAIL antes de Phase 4.**

## Phase 4: Verificación (calidad + invariantes)

- [x] 4.1 `python -m pytest -m unit` verde global (sin regresiones en suite existente — especialmente `test_schema.py` y `test_custom_loader.py` actualizados). **Scenario: Suite unit verde.**
- [x] 4.2 `ruff check .` sin findings. **Scenario: Ruff limpio.**
- [x] 4.3 `mypy src/yaml_agno` sin errores (incl. TYPE_CHECKING imports del resolver + mcp_resolver). **Scenario: Mypy limpio.**
- [x] 4.4 Smoke MCPTools construction (no-network): `python -c "from agno.tools.mcp import MCPTools; t = MCPTools(command='echo hi'); assert not t.initialized; print('UNCONNECTED OK')"` (confirma construcción SIN connect). **Scenario: resolve_single retorna UNCONNECTED.**
- [x] 4.5 Cold imports no circulares: `python -c "from yaml_agno.tools import *"` Y `python -c "from yaml_agno.models import AgentConfig"` ambos limpios (lección slice #4 / TECH010). **Scenario: Sin import circular.**
- [x] 4.6 Smoke API pública: `python -c "from yaml_agno.tools import MCPResolver, StdioMcpConfig, HttpMcpConfig, McpToolConfig, McpMultiToolConfig; print('OK')"` imprime OK. **Scenario: Import API pública.**
- [x] 4.7 Agno import sanity: `python -c "from agno.tools.mcp import MCPTools, MultiMCPTools; from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams; print('OK')"` (si FALLA, el path del resolver import es incorrecto). **Req: MCPResolver imports correctos.**
- [x] 4.8 Dual discriminator sanity: `python -c "from pydantic import TypeAdapter; from yaml_agno.tools import McpToolConfig; ta=TypeAdapter(McpToolConfig); print(ta.validate_python({'kind':'mcp','transport':'stdio','command':'echo hi'})); print(ta.validate_python({'kind':'mcp','transport':'sse','url':'http://x'}))"` (routes stdio → StdioMcpConfig, sse → HttpMcpConfig). **Scenario: Discriminación por transport.**
- [x] 4.9 `git diff --name-only src/yaml_agno/models/config/agent_config.py` → **vacío** (AgentConfig.tools queda opaco, wiring es slice C). **Req: Invariantes DEFERRED (AgentConfig NO modificado).**
- [x] 4.10 `git diff --name-only specs/` → **vacío** (SSOT read-only). **Req: specs intocadas.**
- [x] 4.11 Aserción negativa DEFER: `python -c "import yaml_agno.tools as t; assert not hasattr(t, 'ToolFactory'); print('DEFER OK')"` (slice B no implementa ToolFactory — eso es slice C). **Req: DEFER ToolFactory.**
- [x] 4.12 **GATE decisions.yaml VQ execution**: ejecutar las VQ relevantes de `.chats/decisions.yaml` contra el código entregado y confirmar que passan:
  - VQ001 (PHIL004 Anti-Frankenstein): el resolver NO reimplementa `connect()`/importlib — delega al Agno constructor + slice-A allowlist.
  - VQ003 (TECH010 Cold imports): `from yaml_agno.tools import MCPResolver` + `from yaml_agno.models import AgentConfig` ambos limpios.
  - VQ008 (STRAT003 TaskGroup): `grep -rn 'gather' src/yaml_agno/tools/mcp_resolver.py` → ZERO (no asyncio.gather; resolver es sync).
  - TECH011 (Agno API verifications): `mcp_tools` finding confirma NO headers/timeout top-level (viven en ClientParams); `multi_mcp_tools` DeprecationWarning documentada. **Req: GATE decisions.yaml coherencia código-vs-decisiones.**

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 Commits atómicos en orden: `test: update slice-A placeholder tests for MCP schema replacement` (2.1+2.2) → `test: add MCP schema + resolver + loader delegation RED tests` (2.3+2.4+2.5) → `feat: replace MCP placeholders with StdioMcpConfig/HttpMcpConfig discriminated union` (3.1) → `feat: add MCPResolver returning UNCONNECTED MCPTools/MultiMCPTools` (3.2) → `feat: delegate load_mcp/load_mcp_multi to MCPResolver` (3.3) → `feat: re-export MCPResolver and MCP config schemas` (3.4). **No commitear specs/ ni agent_config.py.**

## TDD Compliance Matrix (11 reqs → RED → GREEN → escenario)

| Req | RED task | GREEN task | Escenarios cubiertos |
|-----|----------|------------|----------------------|
| `StdioMcpConfig` (transport stdio, rechaza headers) | 2.3 | 3.1 | Golden stdio con command; RED stdio con headers; RED stdio con header_provider |
| `HttpMcpConfig` (transport streamable-http \| sse) | 2.3 | 3.1 | Golden streamable-http con headers; Golden SSE con timeout |
| `McpToolConfig` unión discriminada por transport | 2.3 | 3.1 | Discriminación por transport (stdio → StdioMcpConfig, sse/http → HttpMcpConfig) |
| `McpMultiToolConfig` (lista de servidores) | 2.3 | 3.1 | McpMulti con servers list; RED servers vacío rechazado |
| `MCPResolver.resolve_single` retorna UNCONNECTED | 2.4 | 3.2 | resolve_single retorna UNCONNECTED (sin connect); resolve_single http construye ClientParams |
| `MCPResolver.resolve_multi` retorna MultiMCPTools UNCONNECTED | 2.4 | 3.2 | resolve_multi con servidores stdio; NO se llama connect |
| Tipo timeout difiere por transport (SSE=float, HTTP=timedelta) | 2.4 | 3.2 | timeout streamable se envuelve timedelta; timeout SSE permanece float |
| `header_provider` str → Callable vía allowlist | 2.4 | 3.2 | header_provider se resuelve vía allowlist; RED header_provider no allowlisted |
| `DeprecationWarning` de MultiMCPTools documentada | 2.4 | 3.2 | DeprecationWarning al construir multi (no suprimida) |
| `load_mcp`/`load_mcp_multi` delegan a MCPResolver | 2.5 | 3.3 | load_mcp delega al resolver; no NotImplementedError |
| MODIFIED placeholders reemplazados | 2.1, 2.2 | 3.1, 3.3 | Placeholders → schemas con campos; load_mcp/load_mcp_multi ya no NotImplementedError |
| REMOVED connect() en resolver | 2.4 | 3.2 | resolve_single retorna UNCONNECTED (sin connect) — implícito en todos los resolver tests |
| DEFERRED (AgentConfig NO modificado, ToolFactory NO implementado) | — | 4.9, 4.11 | AgentConfig.tools queda opaco (slice C); ToolFactory ausente (slice C) |

## Implementation Order (dependencias)

```
Phase 1 baseline (verify placeholders + Agno imports + timeout divergence)
   ↓
Phase 2 RED (5 pasos, orden por dependencia):
   2.1 actualizar test_schema.py (2 tests)  ┐
   2.2 actualizar test_custom_loader.py (2 tests) ┤
   2.3 test_mcp_schema.py (nuevo)  ├─ paralelizables tras 2.1+2.2
   2.4 test_mcp_resolver.py (nuevo) ┤
   2.5 test_custom_loader_mcp.py (nuevo) ┘
   2.6 gate RED (todos fallan)
   ↓
Phase 3 GREEN (orden por deps internos):
   3.1 schema.py modify (sin deps internos — sólo Pydantic)
   3.2 mcp_resolver.py new (dep schema TYPE_CHECKING + security + Agno)
   3.3 custom_loader.py modify (dep mcp_resolver)
   3.4 __init__.py modify (dep los 3 anteriores)
   3.5 gate GREEN (21 escenarios + 4 actualizados)
   ↓
Phase 4 verificación (gate: GREEN + ruff + mypy + cold imports + VQ)
   ↓
Phase 5 commits granular
```
