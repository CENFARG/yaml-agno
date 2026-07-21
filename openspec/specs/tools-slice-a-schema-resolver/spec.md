# Delta Specification — tools-slice-a-schema-resolver

> **Slice A de SPEC_11**: schema de Tools (unión discriminada por `kind`) + resolutores NO-async
> (builtin / function / toolkit_class). Funda el `ToolEntry` que consumirán los slices B, C y D.
>
> **DEFERRED (fuera de alcance de este slice)**: MCP (slice B), `ToolFactory` orchestrator +
> wiring de `AgentFactory` (slice C), hooks/caching/concurrency/registro de 120+ (slice D),
> y el envoltorio `@tool(...)` sobre los callables resueltos (slice C).

## ADDED Requirements

### Requirement: Discriminación de `ToolEntry` por `kind`

El sistema DEBE modelar `AgentConfig.tools` como una lista de `ToolEntry`, una unión
discriminada Pydantic (PEP 695) por el campo `kind` con las variantes `builtin`,
`function` y `toolkit_class` en este slice. El discriminador `kind` DEBE ser `Literal`
y obligatorio. Cada variante SÓLO DEBE aceptar los campos que le son propios; el
dispatch por `kind` DEBE producirse en validación (no en runtime de Agno).

El nombre `ToolEntry` DEBE reemplazar al previo `ToolConfig` opaco
(`dict[str, Any]`) en el slot `AgentConfig.tools`. El alias `ToolConfig` DEBE
permanecer exportado como alias obsoleto de `dict[str, Any]` por compatibilidad hacia
atrás con consumers externos de SPEC_02.

#### Scenario: Discriminación por kind (builtin / function / toolkit_class)

- GIVEN un documento YAML con tres entradas bajo `agent.tools` con `kind: builtin`,
  `kind: function` y `kind: toolkit_class` respectivamente
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN cada entrada se parsea a la subclase concreta correspondiente
  (`BuiltinToolConfig`, `CustomToolConfig`, `CustomToolkitConfig`)
- AND `kind` es accesible en cada instancia con el valor literal correcto

#### Scenario: Entrada sin `kind` es rechazada

- GIVEN una entrada `agent.tools` sin el campo `kind`
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN se levanta `ValidationError` citando la falta del discriminador `kind`

#### Scenario: `kind` desconocido es rechazado

- GIVEN una entrada con `kind: mcp` (variante DEFERRED a slice B)
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN se levanta `ValidationError` indicando que `kind` no pertenece a las variantes
  permitidas en este slice

#### Scenario: `ToolConfig` permanece como alias obsoleto

- GIVEN un consumer externo que importa `ToolConfig`
- WHEN referencia `yaml_agno.models.config.agent_config.ToolConfig`
- THEN obtiene `dict[str, Any]` (compatibilidad hacia atrás)
- AND el símbolo DEBE emitir oportunar `DeprecationWarning` al usarse fuera del núcleo
  (permitido como alias silencioso sólo dentro de `AgentConfig.tools` previo a la
  validación de `ToolEntry`)

### Requirement: `BuiltinToolConfig` (variantes builtin validadas contra el catálogo)

`BuiltinToolConfig` DEBE modelar la variante `kind: builtin`. DEBE tener `model_config`
con `extra="allow"` para que los parámetros específicos de cada toolkit fluyan al adapter
sin requerir 120+ modelos. El campo `name` DEBE ser obligatorio y DEBE validarse contra
el conjunto de claves de `BUILTIN_REGISTRY`; un `name` ausente del catálogo DEBE ser
rechazado con `ValidationError` en el boundary. Los campos comunes
`cache_results`, `include_tools`, `exclude_tools` y `add_instructions` PUEDEN estar
presentes.

#### Scenario: Golden Path — builtin `calculator`

- GIVEN un YAML con `kind: builtin`, `name: calculator`,
  `include_tools: ["add", "multiply", "exponentiate"]`
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN la entrada se parsea como `BuiltinToolConfig`
- AND `name` se resuelve a `CalculatorTools` (del módulo `agno.tools.calculator`)
  vía `BUILTIN_REGISTRY["calculator"]`
- AND `include_tools` se conserva para pasar al adapter

#### Scenario: RED — builtin desconocido

- GIVEN un YAML con `kind: builtin`, `name: inventado_no_existe`
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN se levanta `ValidationError` indicando que `name` no es un builtin conocido
  (no está en `BUILTIN_REGISTRY`)

#### Scenario: `extra="allow"` deja flujar kwargs del toolkit

- GIVEN un YAML con `kind: builtin`, `name: duckduckgo`, `fixed_max_results: 5`
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN `fixed_max_results` se conserva en el modelo sin disparar `ValidationError`
  (gracias a `extra="allow"`)

### Requirement: `CustomToolConfig` (variante function, callable vía `path`)

`CustomToolConfig` DEBE modelar la variante `kind: function`. DEBE tener
`model_config` con `extra="forbid"`. El campo `path` DEBE ser una cadena
dotted-path obligatoria (máx 400 chars). El campo se resuelve vía
`CustomToolLoader.load_callable` (retorna el callable CRUDO, sin envolver
con `@tool`).

**DEFER a slice C (ToolFactory)**: los campos de comportamiento HITL
(`requires_confirmation`, `requires_user_input`, `external_execution`,
`show_result`, `stop_after_tool_call`, `cache_*`, `tool_hooks`) y su
exclusividad mutua NO se modelan en slice A. Se agregan en slice C cuando
el `@tool(...)` wrapping los consume (consistente con ADR A2: el loader
retorna callable crudo; los flags viven con el wrapping). Esto evita
modelar flags que nada consume aún.

#### Scenario: Golden Path — function (dotted-path)

- GIVEN un YAML con `kind: function`, `path: myapp.tools.fetch_order`
- WHEN se valida la ToolEntry union
- THEN la entrada se parsea como `CustomToolConfig` con `path` conservado

#### Scenario: RED — path faltante

- GIVEN un YAML con `kind: function` (sin `path`)
- WHEN se valida
- THEN se levanta `ValidationError` (path es obligatorio)

### Requirement: `CustomToolkitConfig` (variante toolkit_class)

`CustomToolkitConfig` DEBE modelar la variante `kind: toolkit_class`. DEBE tener
`model_config` con `extra="allow"` para que `init_args` y otros flags fluyan. El campo
`module` DEBE ser una cadena `module.path.ClassName` obligatoria (máx 400 chars) que
referencie una subclase de `agno.tools.Toolkit`. Los campos `init_args`, `cache_results`,
`include_tools` y `exclude_tools` PUEDEN estar presentes.

#### Scenario: Golden Path — toolkit_class

- GIVEN un YAML con `kind: toolkit_class`,
  `module: myapp.toolkits.ShellTools`, `init_args: {working_directory: "/workspace"}`,
  `cache_results: true`, `exclude_tools: ["rm"]`
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN la entrada se parsea como `CustomToolkitConfig`
- AND `init_args` y `exclude_tools` se conservan para pasar al resolver

### Requirement: `CustomToolLoader` devuelve el callable CRUDO

`CustomToolLoader.load(config)` DEBE devolver el callable referenciado por
`CustomToolConfig.module` tal cual existe en su módulo (callable "raw"). DEBE NO aplicar
el decorator `@tool(...)` ni ningún flag de configuración (`requires_confirmation`,
`cache_results`, `cache_ttl`, `tool_hooks`): esa responsabilidad es del `ToolFactory`
(slice C). La resolución DEBE delegar el import a `AgnoResolver.resolve_class(module_path,
name)` (el escape hatch público de `di/agno_resolver.py`), y NO reimplementar importlib
ad-hoc.

#### Scenario: CustomToolLoader devuelve callable sin envolver

- GIVEN un `CustomToolConfig` con `module: myapp.tools.fetch_order` y el módulo en la
  whitelist, y `requires_confirmation: true`
- WHEN `CustomToolLoader.load(config)` se ejecuta
- THEN se obtiene el objeto callable `fetch_order` SIN haberse envuelto con `@tool(...)`
- AND el callable retornado es `callable()` pero NO es una instancia de `agno.tools.Function`
- AND `requires_confirmation` y los demás flags NO han sido aplicados al objeto retornado

### Requirement: `BUILTIN_REGISTRY` con 5 adapters y filtrado por signature

El sistema DEBE mantener un `BUILTIN_REGISTRY` mapeando nombres cortos a adapters para
exactamente cinco toolkits en este slice: `calculator`, `yfinance`, `hackernews`,
`duckduckgo` y `shell` (target clases: `agno.tools.calculator.CalculatorTools`,
`agno.tools.yfinance.YFinanceTools`, `agno.tools.hackernews.HackerNewsTools`,
`agno.tools.duckduckgo.DuckDuckGoTools`, `agno.tools.shell.ShellTools` respectivamente).

Cada adapter DEBE construir la instancia del toolkit filtrando los kwargs del YAML
contra `inspect.signature(cls.__init__)`, porque los Toolkits son clases regulares (NO
dataclasses) y el enfoque `dataclasses.fields()` usado en `ProviderFactory` NO aplica.
Los kwargs ausentes del `__init__` DEBEN descartarse (con advertencia opcional), no
provocar `TypeError`.

Los adapters con alias (p.ej. `YFinanceTools`) DEBEN normalizar los alias YAML cortos
(`stock_price`, `company_info`, `company_news`, `analyst_prices`, `income_statement`) a
los nombres canónicos Agno (`enable_stock_price`, `enable_company_info`, etc.) ANTES del
filtrado por signature. Los alias NO reconocidos y NO presentes en la signature DEBEN
descartarse.

#### Scenario: Alias normalization — yfinance `stock_price` → `enable_stock_price`

- GIVEN un YAML con `kind: builtin`, `name: yfinance`, `stock_price: true`,
  `company_news: true`, `cache_results: true`
- WHEN el adapter de `yfinance` construye la instancia
- THEN se llama `YFinanceTools(enable_stock_price=True, enable_company_news=True,
  cache_results=True)`
- AND el alias `stock_price` NO se pasa literalmente (se normaliza a `enable_stock_price`)

#### Scenario: Kwargs filtering — se descarta el parámetro que el Toolkit no acepta

- GIVEN un YAML con `kind: builtin`, `name: duckduckgo`, `fixed_max_results: 5`,
  `parametro_inventado: true`
- WHEN el adapter de `duckduckgo` construye la instancia
- THEN `fixed_max_results=5` se pasa a `DuckDuckGoTools.__init__` (existe en la signature)
- AND `parametro_inventado` se descarta silenciosamente (no está en la signature)
- Y NO se levanta `TypeError` por el kwarg desconocido

### Requirement: Guarda de seguridad con allowlist (`is_module_allowed`)

Toda resolución de `module` dotted-path (`CustomToolConfig.module` o
`CustomToolkitConfig.module`) DEBE estar precedida por la guarda `is_module_allowed`
ubicada en `yaml_agno.security`. La guarda DEBE cargar la whitelist desde
`ConfigManager` (clave `security.import_whitelist`, lista de prefijos de módulo) y DEBE
fallar cerrada: una whitelist vacía rechaza TODOS los módulos personalizados (los custom
tools son opt-in por configuración explícita). La verificación DEBE ser match por prefijo
(un prefijo `myapp.tools.` permite cualquier submódulo bajo ese paquete). Un módulo no
permitido DEBE provocar `SecurityError` y DEBE NO ejecutar ningún import.

#### Scenario: RED — módulo no allowlisted es rechazado

- GIVEN un YAML con `kind: function`, `module: os.system` (no en la whitelist)
- WHEN `CustomToolLoader.load(config)` se ejecuta
- THEN se levanta `SecurityError` con mensaje citando `os.system` fuera de la whitelist
- Y NO se ejecuta `importlib.import_module("os")` ni `getattr` alguno sobre él

#### Scenario: Whitelist vacía rechaza todo custom (fail closed)

- GIVEN una `ConfigManager` con `security.import_whitelist` vacío o ausente
- WHEN se intenta resolver cualquier `module` personalizado
- THEN `is_module_allowed` retorna `False` para todos los dotted-paths no vacíos
- Y la resolución aborta con `SecurityError`

#### Scenario: Match por prefijo habilita submódulos

- GIVEN una whitelist `["myapp.tools."]` y un `module: myapp.tools.fetch_order`
- WHEN `is_module_allowed("myapp.tools.fetch_order")` se evalúa
- THEN retorna `True` (match por prefijo de paquete)

### Requirement: Invariantes DEFERRED (exclusiones negativas de este slice)

Este slice DEBE NO introducir ninguno de los siguientes elementos (su ausencia es una
propiedad exigible del slice):

- La variante `kind: mcp` y `kind: mcp_multi`, y todo tipo `McpToolConfig` /
  `McpMultiToolConfig` (slice B).
- El orchestrator `ToolFactory.build(tool_set)` que ensambla la lista final de tools
  Agno (slice C).
- El envoltorio `@tool(**config_flags)` sobre los callables resueltos por
  `CustomToolLoader` (slice C).
- El wiring de `AgentFactory` (SPEC_01) para forwardear las tools resueltas al
  `agno.Agent` (slice C).
- Hooks (`ToolHookRef`), `cache_callables`, y ejecución concurrente vía
  `asyncio.TaskGroup` (slice D).
- La expansión de `BUILTIN_REGISTRY` más allá de los 5 adapters citados (slice D).

`CustomToolLoader` DEBE NO usar `asyncio`, `aiohttp` ni realizar I/O de red. La
resolución builtin/toolkit DEBE ser síncrona y pura (Pydantic + `inspect` + importlib).

#### Scenario: Slice A no implementa `ToolFactory.build`

- GIVEN el código entregado por este slice
- WHEN se inspecciona el módulo `yaml_agno.tools`
- THEN NO existe un objeto/protocolo `ToolFactory` con método `build(tool_set) -> list`
- Y NO existe `MCPResolver` ni tipos `McpToolConfig`

#### Scenario: Slice A no envuelve con `@tool`

- GIVEN un `CustomToolConfig` y el `CustomToolLoader` de este slice
- WHEN `load(config)` retorna
- THEN el objeto retornado NO está decorado con `@tool(...)` (no es `agno.tools.Function`)
- Y los flags del config permanecen sólo en el objeto config, no aplicados al callable

## MODIFIED Requirements

### Requirement: Tipo de `AgentConfig.tools`

`AgentConfig.tools` DEBE tener tipo `list[ToolEntry]` (unión discriminada por `kind` con
variantes `builtin`, `function`, `toolkit_class` en este slice), reemplazando el previo
`list[ToolConfig]` opaco (`dict[str, Any]`). La validación discriminada DEBE ocurrir al
parsear el documento YAML, de modo que cada entrada se reduzca a una subclase concreta
antes de cualquier resolución. El límite `max_length=50` DEBE conservarse.

(Previously: `AgentConfig.tools` era `list[ToolConfig]` con `ToolConfig = dict[str, Any]`,
lista opaca sin validación interna — cada entrada se trataba como diccionario libre.)

#### Scenario: `tools` ahora valida con `ToolEntry`

- GIVEN un documento YAML válido con `agent.tools` conteniendo dos entradas
  bien-tipadas (`kind: builtin`, `kind: function`)
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN `config.tools` es una `list[ToolEntry]` donde cada elemento es instancia de la
  subclase concreta correspondiente
- Y `max_length=50` sigue vigente (más de 50 entradas provoca `ValidationError`)

#### Scenario: Entrada malformada se rechaza donde antes pasaba

- GIVEN un documento YAML con una entrada `agent.tools` que no contiene `kind`
  (previamente aceptada como dict opaco)
- WHEN `AgentConfig.model_validate` se ejecuta
- THEN se levanta `ValidationError` por la falta del discriminador `kind`
