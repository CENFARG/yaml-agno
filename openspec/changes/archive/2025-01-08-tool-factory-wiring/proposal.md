---
change: tool-factory-wiring
spec: SPEC_11
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/tools-slice-a-schema-resolver
  - openspec/specs/mcp-integration
  - openspec/specs/agent-config-schema
---

# Proposal: ToolFactory Wiring (SPEC_11 Slice C)

## Intent

Resolver el gap funcional de slices A+B: `AgentConfig.tools` ya se valida como
unión `ToolEntry`, y los resolvers individuales (BUILTIN_REGISTRY,
CustomToolLoader, MCPResolver) ya existen y devuelven objetos Agno — pero
`AgentFactory.build()` ignora `cfg.tools` por completo (`result.tools == []`
incluso con YAML poblado, `test_agent_factory.py:145`). Sin un orquestador que
dispatche cada `ToolEntry` al resolver correcto y aplique los flags `@tool`, un
YAML con `kind: function` + `requires_confirmation: true` se carga pero NUNCA
se aplica el HITL, y un YAML con tools nunca llega al `agno.Agent`. Slice C
cierra el loop: YAML `tools:` → lista mixta resuelta → `Agent(tools=[...])`.

## Why Now

- Es el siguiente slice en la cadena SPEC_11 (A=shipped, B=shipped, C=this).
- Las slices A+B son código muerto sin wiring: validan schema y exponen
  resolvers que nada invoca.
- `tool_call_limit`, hooks, caching y concurrencia se DEFERREN a slice D, pero
  requieren que este wiring exista primero.

## Scope

### In Scope

- **NEW** `src/yaml_agno/tools/toolFactory.py`: `ToolFactory(resolver).build(tool_entries) -> list[Any]`.
  Dispatcha cada `ToolEntry` por `kind` a BUILTIN_REGISTRY / CustomToolLoader /
  MCPResolver, recolecta lista mixta (Toolkit | Function | MCPTools).
- **NEW** `ToolFactory._wrap_tool(raw_callable, config)`: aplica `@tool(**flags)`
  desde `CustomToolConfig` al callable crudo retornado por `CustomToolLoader`
  (que por diseño de slice A NO wrapea).
- **MODIFY** `src/yaml_agno/tools/schema.py`: ampliar `CustomToolConfig` con
  flags `@tool` (`name`, `description`, `strict`, `requires_confirmation`,
  `requires_user_input`, `user_input_fields`, `external_execution`,
  `show_result`, `stop_after_tool_call`, `cache_results`, `cache_dir`,
  `cache_ttl`) + `model_validator` de exclusividad-mutua HITL (a lo sumo uno de
  `requires_confirmation`/`requires_user_input`/`external_execution` en `True`,
  SPEC_11 §3.1).
- **MODIFY** `src/yaml_agno/factories/agent_factory.py`: `build(cfg, resolver=None)`
  con parámetro opcional `resolver`; cuando `resolver` es provisto +
  `cfg.tools` no vacío, construye `ToolFactory(resolver)`, llama `build()`, y
  pasa el resultado a `Agent(tools=...)`. Cuando `resolver is None`, comportamiento
  actual (tools=`[]`) — cero tests rotos.
- **MODIFY** `src/yaml_agno/tools/__init__.py`: re-exportar `ToolFactory`.
- **Tests**: NEW `tests/unit/tools/test_tool_factory.py` (dispatch por kind,
  wrapping `@tool`, HITL validator); UPDATE `tests/unit/tools/test_schema.py`
  (flags ampliados + validator); UPDATE `tests/unit/factories/test_agent_factory.py`
  (escenario tools-forwarding; tests existentes sin cambio — `resolver` default `None`).

### Out of Scope (DEFER a slice D)

- **Hooks** (`tool_hooks`, `pre_hook`/`post_hook` resolution — TASK_005).
- **Caching** (`cache_callables`, `callable_tools_cache_key` — TASK_013).
- **Concurrencia** (`asyncio.TaskGroup` parallel tool calls — TASK_012).
- **Registry expansion** a 120+ toolkits (TASK_003 — se mantiene en 5).
- **`tool_call_limit` forwarding** (TASK_011) — `AgentConfig` no tiene campo
  `tool_call_limit` hoy; requiere decisión de schema SPEC_02. DEFER a slice D.
- **Integration test e2e** (TASK_014).
- Widening `AgentConfig.tools` a `list[ToolEntry]` tipado — se mantiene opaco
  (`list[dict[str, Any]]`); la validación `ToolEntry` ocurre dentro de
  `ToolFactory.build()` via `TypeAdapter`.

## Capabilities

### New Capabilities

- `tool-factory-wiring`: orquestador `ToolFactory` que dispatcha `ToolEntry` →
  objeto Agno, aplica `@tool(**flags)`, y el wiring `AgentFactory` →
  `Agent(tools=...)`.

### Modified Capabilities

- `tools-slice-a-schema-resolver`: `CustomToolConfig` gana flags `@tool` +
  validator HITL (cambio de schema-level, no sólo implementación).
- `agent-config-schema`: sin cambio de schema — `AgentConfig.tools` sigue
  opaco. Pero el *comportamiento* de `AgentFactory.build()` cambia (gana
  parámetro `resolver`), lo que se documenta como delta conductual.

## Approach

**Decisión: Option B — `AgentConfig.tools` opaco, resolver en factory time.**

`AgentConfig.tools` permanece `list[dict[str, Any]]` (9 slots opacos, PHIL002).
`ToolFactory.build()` acepta la lista cruda, valida cada dict contra la unión
`ToolEntry` via `TypeAdapter(ToolEntry)`, dispatcha por `kind`, y retorna la
lista mixta que `agno.Agent(tools=...)` acepta. `AgentFactory.build(cfg, resolver=None)`
es el punto natural de wiring: ya importa `agno.Agent`, ya es donde
`AgentConfig` conoce a Agno.

**ToolFactory (SYNC)**: viable porque `MCPResolver` (slice B) retorna instancias
`MCPTools`/`MultiMCPTools` UNCONNECTED, y `agno.Agent` auto-conecta durante
`aget_tools` (MRO name-check + `await tool.connect()`, verificado obs-2018).
No hay `await` en el path de construcción.

**`_wrap_tool(raw, config)`**: extrae los flags de `CustomToolConfig`, filtra
`None` (Agno usa sus defaults), y llama `tool(**flags)(raw)` produciendo un
`Function` object. El validator HITL a nivel schema garantiza fallo temprano
(antes del wrap), replicando la validación de Agno en el boundary (SPEC_11 §3.1).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/tools/tool_factory.py` | NEW | `ToolFactory` orchestrator + `_wrap_tool`. |
| `src/yaml_agno/tools/schema.py` | Modified | `CustomToolConfig` ampliada con ~12 flags `@tool` + `model_validator` HITL. |
| `src/yaml_agno/tools/__init__.py` | Modified | Re-export `ToolFactory`. |
| `src/yaml_agno/factories/agent_factory.py` | Modified | `build()` gana `resolver: AgnoResolver \| None = None`; wiring ToolFactory. |
| `tests/unit/tools/test_tool_factory.py` | NEW | Dispatch por kind, wrapping, HITL. |
| `tests/unit/tools/test_schema.py` | Modified | Flags ampliados + validator. |
| `tests/unit/factories/test_agent_factory.py` | Modified | +1 escenario tools-forwarding. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `CustomToolConfig` schema gap: shipped tiene solo `kind`+`path`; SPEC_11 §3.3 exige ~15 flags. Ampliar es breaking dentro del tools-layer (no toca AgentConfig). | High | Slice C lo resuelve directamente; `extra="forbid"` fuerza error explícito en YAMLs que usen flags no declarados. |
| `tool_call_limit` ownership: SPEC_11 §1.2 lo pone en `ToolSetConfig` (no existe shipped); `AgentConfig` no lo tiene. AgentFactory no puede forwardear lo que no existe. | Med | DEFER a slice D (decisión de SPEC_02). Slice C documenta el gap; no lo resuelve. |
| `AgentFactory.build()` signature change: agrega `resolver`. | Low | Default `None`; callers existentes (team_factory, workflow_factory, tests) siguen funcionando — tools se skipea. |
| `MultiMCPTools` DeprecationWarning en cada construcción (RISK004). | Med | Tests ya lo manejan (slice B). ToolFactory lo hereda sin acción extra. |
| HITL mutual-exclusivity: si el validator schema-level y el check de Agno divergen, doble fallo o silencio. | Low | Validator schema replica exactamente la constraint de Agno (a lo sumo uno True de los 3); fallo temprano en el boundary. |
| UNCONNECTED MCP instances acumuladas si el mismo AgentConfig se build-a múltiples veces. | Low | No es bug de slice C (caching es slice D). Documentado. |
| Discrepancia nomenclatura: shipped usa `path` (dotted-path); SPEC_11 §3.3 usa `module`. | Low | Mantener `path` (convención shipped, consistente con `CustomToolkitConfig`). Flags se añaden sobre `path`. |

## Rollback Plan

1. Revertir `agent_factory.py` al `build(cfg)` sin `resolver` (1 archivo, sin
   dependientes).
2. Eliminar `tool_factory.py` (NEW file, sin dependientes).
3. Revertir `CustomToolConfig` a `{kind, path}` en `schema.py`.
4. Los tests de slice A+B no dependen de slice C — el rollback no los rompe.
5. `openspec/specs/` no se modifica en slice C (sólo delta specs en el change
   folder) — rollback de archivos no toca specs publicados.

## Dependencies

- **Shipped**: `tools-slice-a-schema-resolver` (schema + CustomToolLoader +
  registry + security), `mcp-integration` (MCPResolver), `agent-config-schema`
  (AgentConfig.tools opaco).
- **Agno 2.6.22**: `@tool` decorator retorna `Function` (no callable); Agent
  acepta lista mixta `list[Toolkit | Callable | Function | MCPTools]`;
  auto-connect de MCPTools en `aget_tools`.

## Success Criteria

- [ ] `AgentFactory.build(cfg_with_tools, resolver)` produce un `Agent` cuyo
  `.tools` contiene los objetos Agno resueltos (no `[]`).
- [ ] `kind: function` con `requires_confirmation: true` produce un `Function`
  cuyo flag está aplicado (verificable via el objeto `Function`).
- [ ] `CustomToolConfig` con 2+ flags HITL en `True` levanta `ValidationError`
  a nivel schema (antes del wrap).
- [ ] `AgentFactory.build(cfg)` sin `resolver` sigue retornando `Agent` con
  `tools=[]` (cero tests existentes rotos).
- [ ] `ToolFactory.build([])` retorna `[]` (empty-state safe).
- [ ] Lista mixta (builtin + function + mcp) se construye sin `await` (sync path).

## Proposal Question Round

Las siguientes preguntas producto se dejan abiertas para revisión del usuario
 antes de pasar a `sdd-spec`. Si no se contestan, se asume el default anotado.

1. **`tool_call_limit`**: SPEC_11 §1.2 lo pone en un `ToolSetConfig` que no
   existe shipped. ¿Lo defer-realmos a slice D (default, recomendado para evitar
   scope creep en SPEC_02), o añadimos `tool_call_limit: int | None` a
   `AgentConfig` ahora? — **Default: DEFER a slice D.**
2. **`cache_results`/`cache_dir`/`cache_ttl` en `CustomToolConfig`**: estos flags
   se aplican via `@tool`, pero el caching *real* (LRU entre runs,
   `cache_callables`) es slice D. ¿Los declaramos en el schema de slice C
   (forwarded a `@tool`, Agno los respeta por-tool-call) o esperamos a slice D?
   — **Default: declarar en slice C; Agno los aplica por-call aunque la cache
   cross-run sea slice D.**
3. **`tool_hooks`/`ToolHookRef`**: el schema SPEC_11 §3.3 los incluye, pero la
   resolución de hooks es TASK_005 (slice D). ¿Los omitimos del schema de slice
   C (consistent con DEFER), o los incluimos como no-resueltos (parser los
   acepta pero ToolFactory los ignora con warning)? — **Default: OMITIR de slice
   C; `extra="forbid"` los rechaza hasta que slice D los añada explícitamente.**
4. **Naming del flag de path**: shipped usa `path` (dotted-path
   `my_pkg.tools.fetch`); SPEC_11 §3.3 usa `module` (`myapp.tools.fetch_order`,
   sin `.name` explícito — asume el último segmento). ¿Mantenemos `path`
   (default, consistencia con `CustomToolkitConfig` shipped) o alineamos a
   `module` + `name` opcional? — **Default: mantener `path`.**
5. **`AgentFactory.build()` signature**: ¿inyectamos `resolver: AgnoResolver`
   (default, ToolFactory se construye ad-hoc) o inyectamos `ToolFactory`
   directamente (más testeable, un paso más de construcción)? — **Default:
   inyectar `resolver` (ToolFactory es barata de construir, resolver es la
   dependencia compartida).**
