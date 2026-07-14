# Delta Specification — tool-factory-wiring

> **SPEC_11 slice C**: introduce el `ToolFactory` orchestrator (SYNC), ensancha
> `CustomToolConfig` con los flags de `@tool` + validador HITL, aplica el wrapping
> con `@tool(**flags)`, y cablea `AgentFactory.build` para resolver `AgentConfig.tools`
> (opaco) en una lista mixta de objetos Agno al momento de construir el Agent.
>
> **Decisión clave (bake-in)**: **Option B** — `AgentConfig.tools` permanece opaco
> (`list[dict[str, Any]]`). La validación a la unión `ToolEntry` ocurre dentro de
> `ToolFactory.build`, NO en `AgentConfig` (preserva la simetría de los 9 slots
> opacos; cero tests rotos). El `ToolFactory` es **SYNC** porque el `MCPResolver`
> retorna instancias **DESCONECTADAS**; el Agent de Agno auto-conecta en runtime.
>
> **DEFERRED (slice D, fuera de alcance)**: hooks (`tool_hooks`, `pre_hook`/
> `post_hook`), caching (`cache_callables`, `callable_tools_cache_key`),
> concurrencia (`asyncio.TaskGroup`), `tool_call_limit` forwarding (requiere
> campo en `AgentConfig` — evolución SPEC_02), registry expansión a 120+.

## ADDED Requirements

### Requirement: `ToolFactory.build` — orquestador SYNC que retorna lista mixta

El sistema DEBE proveer una clase `ToolFactory` en
`src/yaml_agno/tools/tool_factory.py` con un método SYNC `build(raw_tools:
list[dict[str, Any]]) -> list[Any]`. El método DEBE aceptar la lista opaca
de `AgentConfig.tools` (dicts crudos), validar cada dict contra la unión
`ToolEntry` (vía `TypeAdapter(ToolEntry)`), y dispatchar por `kind` al
resolver apropiado. El resultado DEBE ser una lista mixta de objetos Agno
(`Toolkit` instances, `Function` objects, `MCPTools`/`MultiMCPTools`
instancias UNCONNECTED). El método DEBE NO ser asíncrono. Un `kind`
desconocido o ausente DEBE producir `ValidationError`.

#### Scenario: Golden path — ToolFactory con tools mixtas (builtin + function + mcp)

- GIVEN un `ToolFactory` con un `AgnoResolver` y una lista opaca:
  `[{kind: builtin, name: calculator}, {kind: function, path: mypkg.fn},
  {kind: mcp, transport: stdio, command: "uvx mcp-server-git"}]`
- WHEN `ToolFactory.build(raw_tools)` se ejecuta
- THEN retorna una lista de 3 elementos
- AND el primero es una instancia de `CalculatorTools` (Toolkit)
- AND el segundo es un `Function` object (envuelto por `@tool`)
- AND el tercero es una instancia `MCPTools` NO conectada
- AND el método es síncrono (no coroutine)

#### Scenario: Lista vacía retorna lista vacía

- GIVEN un `ToolFactory` y `raw_tools: []`
- WHEN `ToolFactory.build([])` se ejecuta
- THEN retorna `[]` (sin llamar al resolver)

#### Scenario: RED — kind desconocido produce ValidationError

- GIVEN un `ToolFactory` y `raw_tools: [{kind: bogus}]`
- WHEN `ToolFactory.build(raw_tools)` se ejecuta
- THEN se levanta `ValidationError` (la unión `ToolEntry` rechaza el `kind`)

### Requirement: Dispatch por `kind` a resolvers existentes

`ToolFactory.build` DEBE dispatchar cada `ToolEntry` por su `kind`:

| `kind` | Resolver | Resultado |
|--------|----------|-----------|
| `builtin` | `BUILTIN_REGISTRY[name]` + `adapter.build()` | `Toolkit` instance |
| `function` | `CustomToolLoader.load_callable` + `@tool(**flags)` wrap | `Function` object |
| `toolkit_class` | `CustomToolLoader.load_toolkit_class` + instantiate | `Toolkit` instance |
| `mcp` / `mcp_multi` | `CustomToolLoader.load_mcp` / `load_mcp_multi` | `MCPTools` / `MultiMCPTools` UNCONNECTED |

Un `builtin` con `name` ausente en `BUILTIN_REGISTRY` DEBE levantar
`UnknownBuiltinError`. El dispatch DEBE usar `isinstance` sobre los
subtipos concretos de `ToolEntry` (no string matching).

#### Scenario: Dispatch builtin → BUILTIN_REGISTRY

- GIVEN un `ToolFactory` y `raw_tools: [{kind: builtin, name: calculator}]`
- WHEN `build(raw_tools)` se ejecuta
- THEN el resultado es la instancia producida por
  `BUILTIN_REGISTRY["calculator"].build(resolver, init_args)`

#### Scenario: Dispatch mcp → MCPResolver (UNCONNECTED)

- GIVEN un `ToolFactory` y `raw_tools: [{kind: mcp, transport: stdio,
  command: "uvx x"}]`
- WHEN `build(raw_tools)` se ejecuta
- THEN delega a `CustomToolLoader.load_mcp` → `MCPResolver.resolve_single`
- AND retorna una instancia `MCPTools` con `initialized == False` (NO conectada)

#### Scenario: Dispatch function → CustomToolLoader + @tool wrap

- GIVEN un `ToolFactory` y `raw_tools: [{kind: function, path: mypkg.fn}]`
- WHEN `build(raw_tools)` se ejecuta
- THEN delega a `CustomToolLoader.load_callable` (retorna callable crudo)
- AND aplica `@tool(**flags)` sobre el callable crudo
- AND retorna un `Function` object (no el callable crudo)

### Requirement: `@tool` wrapping — function kind recibe `@tool(**flags)`

Para el `kind: function`, el `ToolFactory` DEBE tomar el callable crudo
retornado por `CustomToolLoader.load_callable` y envolverlo con el
decorador `@tool` de `agno.tools` aplicando los flags declarados en el
`CustomToolConfig` ensanchado. El decorator `@tool(**flags)` DEBE importarse
de `agno.tools`. El resultado del wrapping DEBE ser un `Function` object de
Agno (NO un callable plan). Los flags con valor `None` o default DEBE NO
pasarse al decorator (sólo flags explícitamente setados).

#### Scenario: @tool wrapping aplica flags del config

- GIVEN un `CustomToolConfig` con `path: mypkg.fn`,
  `requires_confirmation: True`, `cache_results: True`, `cache_ttl: 3600`
- WHEN el `ToolFactory` procesa esta entrada
- THEN llama `tool(requires_confirmation=True, cache_results=True,
  cache_ttl=3600)(raw_callable)`
- AND el resultado es un `Function` object
- AND `Function.requires_confirmation` es `True`

#### Scenario: @tool sin flags explícitos — wrapper mínimo

- GIVEN un `CustomToolConfig` con sólo `path: mypkg.fn` (todos los flags
  en default)
- WHEN el `ToolFactory` procesa esta entrada
- THEN llama `tool()(raw_callable)` (sin kwargs de flags)
- AND retorna un `Function` object

### Requirement: `CustomToolConfig` ensanchado con flags de `@tool`

`CustomToolConfig` DEBE ensancharse desde su forma mínima (`kind` + `path`)
para incluir los flags de `@tool` de SPEC_11 §3.1. Los siguientes campos
DEBEN añadirse (todos opcionales con defaults seguros): `name: str | None`,
`description: str | None`, `strict: bool | None`, `requires_confirmation:
bool = False`, `requires_user_input: bool = False`, `user_input_fields:
list[str] = []`, `external_execution: bool = False`,
`show_result: bool | None = None`, `stop_after_tool_call: bool = False`,
`cache_results: bool = False`, `cache_dir: str | None = None`,
`cache_ttl: int | None = Field(default=None, ge=1)`. `model_config` DEBE
permanecer `extra="forbid"`. Los flags `tool_hooks`, `pre_hook`, `post_hook`
NO DEBEN incluirse (deferred a slice D).

#### Scenario: CustomToolConfig ensanchado acepta flags

- GIVEN un YAML con `kind: function, path: mypkg.fn,
  requires_confirmation: true, cache_results: true, cache_ttl: 3600,
  show_result: null, stop_after_tool_call: false`
- WHEN se valida como `CustomToolConfig`
- THEN `requires_confirmation` es `True`, `cache_results` es `True`,
  `cache_ttl` es `3600`, `show_result` es `None`
- AND `path` se conserva

#### Scenario: CustomToolConfig minimal sigue válido

- GIVEN un YAML con `kind: function, path: mypkg.fn`
- WHEN se valida como `CustomToolConfig`
- THEN `requires_confirmation` default `False`, `cache_results` default
  `False`, `cache_ttl` default `None`
- AND todos los demás flags en sus defaults

#### Scenario: RED — campo ajeno rechazado por extra="forbid"

- GIVEN un YAML con `kind: function, path: mypkg.fn, rogue_field: 1`
- WHEN se valida como `CustomToolConfig`
- THEN se levanta `ValidationError` por `extra="forbid"`

### Requirement: Validador HITL de exclusividad mutua

`CustomToolConfig` DEBE incluir un `model_validator(mode="after")` que
rechace combinaciones donde más de uno de `requires_confirmation`,
`requires_user_input`, `external_execution` sea `True`. A lo sumo UNO de
los tres DEBE poder ser `True` simultáneamente. La violación DEBE producir
`ValidationError` en el boundary (no delegar a Agno). Esto replica la
restricción del decorator `@tool` (SPEC_11 §3.1 constraint) a nivel schema.

#### Scenario: RED — HITL mutual-exclusivity con 2 flags True

- GIVEN un YAML con `kind: function, path: mypkg.fn,
  requires_confirmation: true, requires_user_input: true`
- WHEN se valida como `CustomToolConfig`
- THEN se levanta `ValidationError` con mensaje de exclusividad HITL

#### Scenario: RED — HITL con los 3 flags True

- GIVEN un YAML con los 3 flags HITL en `True`
- WHEN se valida como `CustomToolConfig`
- THEN se levanta `ValidationError`

#### Scenario: Un solo flag HITL True es válido

- GIVEN un YAML con `kind: function, path: mypkg.fn,
  external_execution: true`
- WHEN se valida como `CustomToolConfig`
- THEN la validación pasa (un solo flag True)

### Requirement: `AgentConfig.tools` permanece opaco (invariante Option B)

`AgentConfig.tools` DEBE permanecer tipado como `list[ToolConfig]` donde
`ToolConfig = dict[str, Any]` (opaco). El sistema DEBE NO ensanchar
`AgentConfig.tools` a `list[ToolEntry]` en este slice. La validación a la
unión `ToolEntry` DEBE ocurrir dentro de `ToolFactory.build`, NO en
`AgentConfig`. Los tests existentes que usan dicts kindless (e.g.
`tools=[{"name": "t"}]`) DEBEN seguir pasando sin modificación.

#### Scenario: AgentConfig.tools sigue aceptando dicts opacos

- GIVEN un `AgentConfig` con `tools: [{"name": "t"}]` (dict kindless)
- WHEN se valida el `AgentConfig`
- THEN la validación pasa (sin validar el contenido del dict)
- AND `cfg.tools` es `list[dict[str, Any]]`

### Requirement: `AgentFactory.build` gana parámetro opcional `resolver`

`AgentFactory.build` DEBE ganar un parámetro opcional
`resolver: AgnoResolver | None = None`. Cuando `resolver` es provisto Y
`cfg.tools` es no-vacío, el factory DEBE construir un `ToolFactory(resolver)`,
llamar `build(cfg.tools)`, y pasar el resultado a `Agent(tools=resolved)`.
Cuando `resolver` es `None` O `cfg.tools` está vacío, el factory DEBE pasar
`tools=[]` (o `None`) al `Agent` — sin llamar al `ToolFactory`. La firma
DEBE ser `build(cfg: AgentConfig, resolver: AgnoResolver | None = None)`.

#### Scenario: AgentFactory wiring — resolver + tools → Agent(tools=[...])

- GIVEN un `AgentConfig` con `tools: [{kind: builtin, name: calculator}]`
  y un `AgnoResolver`
- WHEN `AgentFactory.build(cfg, resolver=resolver)` se ejecuta
- THEN se construye un `ToolFactory(resolver)`
- AND se llama `ToolFactory.build(cfg.tools)` retornando una lista no-vacía
- AND el `Agent` resultante tiene `agent.tools` con la instancia resuelta

#### Scenario: AgentFactory sin resolver — tools=[] (backward compat)

- GIVEN un `AgentConfig` con `tools: [{kind: builtin, name: calculator}]`
  y `resolver=None`
- WHEN `AgentFactory.build(cfg)` se ejecuta (sin resolver)
- THEN el `Agent` resultante tiene `agent.tools == []` (vacío)
- AND NO se construye ningún `ToolFactory`
- AND los tests existentes de `test_agent_factory` pasan sin modificación

#### Scenario: AgentFactory con resolver pero cfg.tools vacío

- GIVEN un `AgentConfig` con `tools: []` y un `AgnoResolver` provisto
- WHEN `AgentFactory.build(cfg, resolver=resolver)` se ejecuta
- THEN `agent.tools == []` (no se llama `ToolFactory.build`)

### Requirement: SYNC `ToolFactory` — MCP retorna UNCONNECTED, Agent conecta

El `ToolFactory` DEBE ser enteramente síncrono. Para entradas `mcp` /
`mcp_multi`, DEBE delegar a `CustomToolLoader.load_mcp` / `load_mcp_multi`
(que retornan instancias NO conectadas). El `ToolFactory` DEBE NO llamar
`connect()` sobre las instancias MCP. El ciclo connect/close es propiedad
del `Agent` de Agno (`aget_tools` → `connect_mcp_tools`).

#### Scenario: ToolFactory SYNC no llama connect en MCP

- GIVEN un `ToolFactory` y `raw_tools: [{kind: mcp, transport: stdio,
  command: "uvx x"}]`
- WHEN `ToolFactory.build(raw_tools)` se ejecuta
- THEN el `MCPTools` retornado tiene `initialized == False`
- AND el método `build` es síncrono (no usa `await`)

## MODIFIED Requirements

### Requirement: `CustomToolConfig` (schema minimal → ensanchado con flags)

`CustomToolConfig` DEBE pasar de su forma minimal (`kind: Literal["function"]`
+ `path: str` con `extra="forbid"`) a incluir los flags de `@tool` de
SPEC_11 §3.1 (`name`, `description`, `strict`, `requires_confirmation`,
`requires_user_input`, `user_input_fields`, `external_execution`,
`show_result`, `stop_after_tool_call`, `cache_results`, `cache_dir`,
`cache_ttl`) más el validador HITL de exclusividad mutua. `extra="forbid"`
DEBE conservarse. Los flags de hooks (`tool_hooks`, `pre_hook`, `post_hook`)
NO se incluyen (slice D).

(Previously: `CustomToolConfig` tenía sólo `kind` + `path`, sin flags de
`@tool`; el wrapping con `@tool` no era posible porque el config no portaba
los flags.)

#### Scenario: CustomToolConfig previo (minimal) ya no es la forma final

- GIVEN el código entregado por este slice
- WHEN se inspecciona `yaml_agno.tools.schema.CustomToolConfig`
- THEN el modelo tiene los campos `requires_confirmation`, `cache_results`,
  `cache_ttl`, `show_result`, `stop_after_tool_call`, etc.
- AND tiene un `model_validator` HITL
- AND `extra="forbid"` se conserva

### Requirement: `AgentFactory.build` (identity-only → identity + tools)

`AgentFactory.build` DEBE pasar de mapear sólo 4 campos de identidad
(name/instructions/description/model) a además resolver `cfg.tools` cuando
se provee un `resolver`. La firma DEBE cambiar de `build(cfg: AgentConfig)
-> Agent` a `build(cfg: AgentConfig, resolver: AgnoResolver | None = None)
-> Agent`. Los callers existentes que pasan sólo `cfg` DEBEN seguir
funcionando (resolver default `None` → tools `[]`).

(Previously: `AgentFactory.build` mapeaba sólo name/instructions/description/
model; `cfg.tools` era silenciosamente ignorado; `result.tools == []`
siempre, incluso con `cfg.tools` poblado.)

#### Scenario: El signature gana resolver opcional

- GIVEN el código entregado por este slice
- WHEN se inspecciona `AgentFactory.build`
- THEN la firma es `build(cfg: AgentConfig, resolver: AgnoResolver | None =
  None) -> Agent`
- AND llamar `AgentFactory.build(cfg)` sin resolver sigue siendo válido
