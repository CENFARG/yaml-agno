# Delta Specification — mcp-integration

> **SPEC_11 slice B**: reemplaza los placeholders `McpToolConfig` / `McpMultiToolConfig`
> (shipped en slice A, `schema.py:76-93`) por schemas reales con unión discriminada por
> `transport`, e introduce `MCPResolver` (SYNC, instancias NO conectadas). Elimina los
> `NotImplementedError` de `CustomToolLoader.load_mcp` / `load_mcp_multi`.
>
> **Decisión clave (bake-in)**: `MCPResolver` es SYNC y retorna instancias
> **DESCONECTADAS** — NO llama `connect()`. El ciclo connect/close lo maneja el Agent
> de Agno en su lifecycle asíncrono (`aget_tools` → `connect_mcp_tools`). Esto
> **diverge** de SPEC_11 §9.6 (que muestra `await tools.connect()` en el resolver);
> dicha línea DEBE eliminarse.
>
> **DEFERRED (fuera de alcance)**: `ToolFactory` orchestrator + wiring (slice C),
> hooks / `cache_callables` / concurrencia `TaskGroup` (slice D), connect/close (Agent).

## ADDED Requirements

### Requirement: `StdioMcpConfig` (transport stdio, rechaza headers a nivel schema)

El sistema DEBE modelar la variante stdio de un servidor MCP con `StdioMcpConfig`.
`model_config` DEBE tener `extra="forbid"`. El campo `transport` DEBE ser
`Literal["stdio"]` (default `"stdio"`). El campo `command` DEBE ser obligatorio
(máx 500 chars). El campo `env` (`dict[str, str] | None`) PUEDE estar presente.

Por la restricción `extra="forbid"`, cualquier campo ajeno — incluyendo `headers`,
`header_provider`, `url`, `timeout`, `sse_read_timeout`, `refresh_connection` —
DEBE ser rechazado con `ValidationError` en el boundary. Esto materializa la
decisión 10.5 (stdio no soporta headers) a nivel schema, sin lógica imperativa.

#### Scenario: Golden path — stdio con command

- GIVEN un YAML con `kind: mcp`, `transport: stdio`,
  `command: "uvx mcp-server-git"`, `env: {GIT_REPO_PATH: "/repo"}`
- WHEN la `ToolEntry` union se valida
- THEN la entrada se parsea como `StdioMcpConfig`
- AND `command` se conserva como `"uvx mcp-server-git"`
- AND `env` se conserva como el dict provisto

#### Scenario: RED — stdio con `headers` es rechazado

- GIVEN un YAML con `kind: mcp`, `transport: stdio`,
  `command: "uvx mcp-server-git"`, `headers: {X-Custom: "1"}`
- WHEN la `ToolEntry` union se valida
- THEN se levanta `ValidationError` citando el campo extra `headers`
  (por `extra="forbid"`), no una aserción de runtime

#### Scenario: RED — stdio con `header_provider` es rechazado

- GIVEN un YAML con `kind: mcp`, `transport: stdio`,
  `command: "uvx mcp-server-git"`, `header_provider: "myapp.headers.fn"`
- WHEN la `ToolEntry` union se valida
- THEN se levanta `ValidationError` citando el campo extra `header_provider`

### Requirement: `HttpMcpConfig` (transport streamable-http | sse)

El sistema DEBE modelar la variante HTTP de un servidor MCP con `HttpMcpConfig`.
`model_config` DEBE tener `extra="forbid"`. El campo `transport` DEBE ser
`Literal["streamable-http", "sse"]`. El campo `url` DEBE ser obligatorio. Los
campos `headers` (`dict[str, str] | None`), `timeout`, `sse_read_timeout`,
`header_provider` (`str | None`, dotted-path al callable) y `refresh_connection`
(`bool`, default `False`) PUEDEN estar presentes. Cualquier campo ajeno DEBE ser
rechazado con `ValidationError`.

#### Scenario: Golden path — streamable-http con headers

- GIVEN un YAML con `kind: mcp`, `transport: streamable-http`,
  `url: "https://docs.agno.com/mcp"`, `headers: {Authorization: "Bearer x"}`,
  `refresh_connection: true`
- WHEN la `ToolEntry` union se valida
- THEN la entrada se parsea como `HttpMcpConfig`
- AND `transport`, `url`, `headers` y `refresh_connection` se conservan

#### Scenario: Golden path — SSE con timeout

- GIVEN un YAML con `kind: mcp`, `transport: sse`,
  `url: "http://localhost:8000/sse"`, `timeout: 5.0`, `sse_read_timeout: 300.0`
- WHEN la `ToolEntry` union se valida
- THEN la entrada se parsea como `HttpMcpConfig` con `transport: "sse"`
- AND `timeout` y `sse_read_timeout` se conservan como números

### Requirement: `McpToolConfig` unión discriminada por `transport`

`McpToolConfig` DEBE ser una unión discriminada (`Annotated[StdioMcpConfig |
HttpMcpConfig, Field(discriminator="transport")]`) que enruta a la subclase
correcta durante la validación. El dispatch DEBE ocurrir en validación (no en
runtime de Agno). Un `transport` ausente o fuera del conjunto permitido DEBE
producir `ValidationError`.

#### Scenario: Discriminación por transport

- GIVEN dos entradas `kind: mcp` con `transport: stdio` y
  `transport: streamable-http` respectivamente
- WHEN la `ToolEntry` union se valida
- THEN la primera se parsea como `StdioMcpConfig` y la segunda como `HttpMcpConfig`

### Requirement: `McpMultiToolConfig` (lista de servidores)

El sistema DEBE modelar la variante multi-servidor con `McpMultiToolConfig`.
`model_config` DEBE tener `extra="forbid"`. El campo `servers` DEBE ser
`list[McpToolConfig]` con `min_length=1` (al menos un servidor). El campo
`allow_partial_failure` (`bool`, default `False`) PUEDO estar presente. El campo
`refresh_connection` (`bool`, default `False`) PUEDO estar presente y aplica
uniformemente a todos los servidores.

#### Scenario: McpMulti con servers list

- GIVEN un YAML con `kind: mcp_multi`, `servers: [{transport: stdio,
  command: "npx airbnb"}, {transport: stdio, command: "npx gmaps"}]`,
  `allow_partial_failure: true`
- WHEN la `ToolEntry` union se valida
- THEN la entrada se parsea como `McpMultiToolConfig`
- AND `servers` tiene dos elementos `StdioMcpConfig`
- AND `allow_partial_failure` se conserva como `True`

#### Scenario: RED — servers vacío rechazado

- GIVEN un YAML con `kind: mcp_multi`, `servers: []`
- WHEN la `ToolEntry` union se valida
- THEN se levanta `ValidationError` por violar `min_length=1`

### Requirement: `MCPResolver.resolve_single` retorna instancia NO conectada

`MCPResolver` DEBE exponer un método SYNC `resolve_single(config: McpToolConfig)
-> MCPTools` que construye una instancia de `agno.tools.mcp.MCPTools` **sin
llamar `connect()`**. Para `StdioMcpConfig` DEBE pasar `command` y `env` al
constructor. Para `HttpMcpConfig` DEBE construir el `*ClientParams` apropiado
(`StreamableHTTPClientParams` o `SSEClientParams`) con `url`, `headers`,
`timeout` y `sse_read_timeout`, y pasarlo vía `server_params` junto con
`transport`, `refresh_connection` y `header_provider` (si está presente). El
resolver DEBE NO ser asíncrono.

#### Scenario: resolve_single retorna UNCONNECTED (sin connect)

- GIVEN un `StdioMcpConfig(command: "uvx mcp-server-git")`
- WHEN `MCPResolver.resolve_single(config)` se ejecuta
- THEN retorna una instancia de `MCPTools`
- AND NO se llamó `connect()` sobre la instancia (no se invoca await alguno)
- AND el resolver es una función síncrona (no coroutine)

#### Scenario: resolve_single http construye ClientParams

- GIVEN un `HttpMcpConfig(transport: "streamable-http",
  url: "https://docs.agno.com/mcp", headers: {Authorization: "Bearer x"})`
- WHEN `MCPResolver.resolve_single(config)` se ejecuta
- THEN se construye un `StreamableHTTPClientParams` con la `url` y `headers`
- AND la instancia `MCPTools` se construye con `server_params` y
  `transport="streamable-http"`
- AND NO se llama `connect()`

### Requirement: `MCPResolver.resolve_multi` retorna `MultiMCPTools` NO conectada

`MCPResolver` DEBE exponer un método SYNC `resolve_multi(config:
McpMultiToolConfig) -> MultiMCPTools` que construye una instancia de
`agno.tools.mcp.MultiMCPTools` **sin llamar `connect()`**. El resolver DEBE
soportar los tres modos de construcción de Agno: `commands` (servidores
stdio), `urls` + `urls_transports` (servidores http), `server_params_list`
(ClientParams pre-construidos). DEBE forwardear
`allow_partial_failure` y `refresh_connection`. NO DEBE limitarse a `commands`
(corrige la incompletitud de SPEC_11 §9.6 que sólo usaba `commands`).
NOTE: ``env`` compartido NO se modela en ``McpMultiToolConfig`` (el env es
per-server en ``StdioMcpConfig.env``); MultiMCPTools.__init__ acepta un env
compartido pero yaml-agno no lo expone (los usuarios que necesiten env
compartido usan múltiples ``kind: mcp`` con el mismo env por servidor).

#### Scenario: resolve_multi con servidores stdio

- GIVEN un `McpMultiToolConfig` con dos `StdioMcpConfig`
- WHEN `MCPResolver.resolve_multi(config)` se ejecuta
- THEN se construye `MultiMCPTools` con `commands` derivado de los dos `command`
- AND `allow_partial_failure` se forwardea
- AND NO se llama `connect()`

### Requirement: Tipo de timeout difiere por transport (SSE=float, StreamableHTTP=timedelta)

El resolver DEBE construir los `*ClientParams` con el tipo correcto de `timeout`:
`SSEClientParams.timeout` es `float` (segundos), mientras
`StreamableHTTPClientParams.timeout` es `datetime.timedelta`. Si el YAML provee
un número para ambos, el resolver DEBE envolverlo en `timedelta(seconds=N)` para
el transport streamable-http. Esta divergencia de tipos (confirmada contra Agno
v2.6.22) DEBE reflejarse en la construcción — NO pasar un float donde se espera
timedelta.

#### Scenario: timeout streamable se envuelve en timedelta

- GIVEN un `HttpMcpConfig(transport: "streamable-http", url: "...",
  timeout: 30.0)`
- WHEN `MCPResolver.resolve_single(config)` construye los `ClientParams`
- THEN el `timeout` del `StreamableHTTPClientParams` es una instancia de
  `timedelta` (no `float`)
- AND equivale a `timedelta(seconds=30)`

#### Scenario: timeout SSE permanece float

- GIVEN un `HttpMcpConfig(transport: "sse", url: "...", timeout: 5.0)`
- WHEN `MCPResolver.resolve_single(config)` construye los `ClientParams`
- THEN el `timeout` del `SSEClientParams` es `5.0` (float, no timedelta)

### Requirement: `header_provider` str → Callable vía allowlist; stdio lo rechaza

El campo `header_provider` del YAML es un dotted-path (`str`). El resolver DEBE
resolverlo a un `Callable[..., dict]` reutilizando el mismo mecanismo de
allowlist que `CustomToolLoader._resolve_dotted` (`security.is_module_allowed` +
`AgnoResolver.resolve_class`). Un módulo no allowlisted DEBE provocar
`SecurityError`. Como `StdioMcpConfig` usa `extra="forbid"`, `header_provider`
en un config stdio DEBE ser rechazado a nivel schema (antes de llegar al
resolver). Agno mismo rechaza `header_provider` con transport stdio lanzando
`ValueError`; el schema de yaml-agno DEBE preceder esa validación con
`ValidationError`.

#### Scenario: header_provider se resuelve vía allowlist

- GIVEN un `HttpMcpConfig(transport: "streamable-http", url: "...",
  header_provider: "myapp.mcp_headers.run_headers")` con el módulo allowlisted
- WHEN `MCPResolver.resolve_single(config)` se ejecuta
- THEN `header_provider` se resuelve a un `Callable` vía el mecanismo de
  allowlist (no un string crudo)
- AND el callable se pasa al constructor de `MCPTools`

#### Scenario: RED — header_provider no allowlisted

- GIVEN un `HttpMcpConfig` con `header_provider: "evil.steal"` (no allowlisted)
- WHEN `MCPResolver.resolve_single(config)` se ejecuta
- THEN se levanta `SecurityError` y NO se importa el módulo

### Requirement: `DeprecationWarning` de `MultiMCPTools` documentada

`MultiMCPTools` emite un `DeprecationWarning` incondicional al construirse
(confirmado Agno v2.6.22). El resolver DEBE NO silenciar esta advertencia
(los tests del caller la filtran con `pytest.warns` o
`warnings.filterwarnings`). La deuda DEBE documentarse: los nuevos configs
SHOULD usar múltiples entradas `kind: mcp` en lugar de `kind: mcp_multi`.

#### Scenario: DeprecationWarning al construir multi

- GIVEN un `McpMultiToolConfig` válido con un servidor stdio
- WHEN `MCPResolver.resolve_multi(config)` se ejecuta
- THEN la construcción de `MultiMCPTools` emite `DeprecationWarning`
- AND el resolver NO la suprime (el caller decide cómo manejarla)

### Requirement: `load_mcp` / `load_mcp_multi` delegan a `MCPResolver`

`CustomToolLoader.load_mcp(config)` y `load_mcp_multi(config)` DELEGAN la
resolución a `MCPResolver` (removiendo el `NotImplementedError` de slice A).
Los métodos DEBEN retornar lo que el resolver retorna (instancia NO conectada).
El loader DEBE NO duplicar la lógica de construcción del resolver.

#### Scenario: load_mcp delega al resolver

- GIVEN un `McpToolConfig` stdio válido y un `CustomToolLoader` con su resolver
- WHEN `CustomToolLoader.load_mcp(config)` se ejecuta
- THEN delega a `MCPResolver.resolve_single(config)`
- AND retorna la instancia `MCPTools` NO conectada
- AND NO levanta `NotImplementedError`

## MODIFIED Requirements

### Requirement: Placeholders `McpToolConfig` / `McpMultiToolConfig`

Los placeholders `McpToolConfig` y `McpMultiToolConfig` (slice A, `extra="allow"`,
sólo campo `kind`) DEBEN ser reemplazados por los schemas completos: `McpToolConfig`
como unión discriminada por `transport` (`StdioMcpConfig | HttpMcpConfig`), y
`McpMultiToolConfig` con `servers`, `allow_partial_failure` y
`refresh_connection`. Ambos DEBEN tener `extra="forbid"`.

(Previously: `McpToolConfig` y `McpMultiToolConfig` eran placeholders vacíos con
`extra="allow"` y sólo el campo `kind`; `load_mcp` / `load_mcp_multi` levantaban
`NotImplementedError`.)

#### Scenario: Los placeholders se reemplazan por schemas con campos

- GIVEN el código entregado por este slice
- WHEN se inspecciona `yaml_agno.tools.schema`
- THEN `McpToolConfig` es `Annotated[StdioMcpConfig | HttpMcpConfig,
  Field(discriminator="transport")]`
- AND `McpMultiToolConfig` tiene los campos `servers`, `allow_partial_failure`,
  `refresh_connection`
- Y ambos modelos tienen `extra="forbid"`

#### Scenario: load_mcp / load_mcp_multi ya no levantan NotImplementedError

- GIVEN un `McpToolConfig` y un `McpMultiToolConfig` válidos
- WHEN se llama `load_mcp` / `load_mcp_multi`
- THEN NO se levanta `NotImplementedError`
- AND delegan al `MCPResolver`

## REMOVED Requirements

### Requirement: `connect()` dentro del resolver

SPEC_11 §9.6 muestra `await tools.connect()` dentro de `MCPResolverImpl`.
Esta línea DEBE ser eliminada del resolver: el Agent de Agno maneja
connect/close en su lifecycle asíncrono. El resolver DEBE ser SYNC y retornar
instancias NO conectadas.

(Reason: el Agent auto-conecta vía `connect_mcp_tools` en `aget_tools`; llamar
`connect()` en el resolver forzaría al resolver a ser async y acoplaría la
resolución al I/O de red, rompiendo el patrón sync de `CustomToolLoader`.)
