# Delta for tools-hooks-caching (SPEC_11 Slice D — final slice)

Estado: SPEC_11 slice D, el slice final de la capa de herramientas. El scope
se reduce deliberadamente respecto de la exploración original: registry 120+
queda SEPARADO (otro change), el executor de concurrencia queda NEVER (trabajo
de Agno). Este slice añade SOLO hooks de herramienta, `tool_call_limit`, y
documenta el invariante de caching ya entregado en slice C.

## ADDED Requirements

### Requirement: Campos de hooks como referencias dotted-path en CustomToolConfig

`CustomToolConfig` DEBE exponer tres campos opcionales — `pre_hook`,
`post_hook` y `tool_hooks` — cuyos valores son CADENAS en notación
dotted-path (p. ej. `myapp.hooks.audit_pre`), NO callables literales. El
modelo DEBE seguir usando `extra="forbid"`.

- `pre_hook: str | None` — referencia a UN callable (gancho previo).
- `post_hook: str | None` — referencia a UN callable (gancho posterior).
- `tool_hooks: list[str]` — lista de referencias a callables encadenados
  (por defecto `[]`).

La resolución del string a `Callable` NO ocurre en el schema; ocurre en
`ToolFactory` vía `CustomToolLoader._resolve_dotted` (reutiliza la misma
infraestructura ya usada para `function.path` y `header_provider`). El
modelo solo valida la SINTAXIS dotted-path (debe contener al menos un `.`).

#### Scenario: Configuración válida con pre_hook y post_hook

- GIVEN un YAML de herramienta `kind: function` con `pre_hook: "myapp.hooks.audit"` y `post_hook: "myapp.hooks.log"`
- WHEN el diccionario se valida contra `CustomToolConfig`
- THEN la validación ACEPTA el entry sin error
- AND los campos quedan como cadenas dotted-path sin resolver

#### Scenario: tool_hooks como lista vacía por defecto

- GIVEN un YAML de herramienta `kind: function` SIN el campo `tool_hooks`
- WHEN el diccionario se valida contra `CustomToolConfig`
- THEN `tool_hooks` toma el valor `[]` (lista vacía por defecto)
- AND `pre_hook` y `post_hook` son `None`

#### Scenario: tool_hooks con varias referencias

- GIVEN un YAML con `tool_hooks: ["myapp.hooks.a", "myapp.hooks.b"]`
- WHEN el diccionario se valida contra `CustomToolConfig`
- THEN la validación acepta el entry con ambos strings en la lista

#### Scenario: Referencia dotted-path inválida (sin punto)

- GIVEN un YAML con `pre_hook: "hooks_audit"` (sin punto separador)
- WHEN el diccionario se valida contra `CustomToolConfig`
- THEN la validación RECHAZA el entry con un error de sintaxis dotted-path

### Requirement: Resolución y reenvío de hooks en ToolFactory._wrap_tool

`ToolFactory._wrap_tool` DEBE resolver cada referencia dotted-path a un
`Callable` ANTES de invocar el decorador `@tool`. La resolución DEBE usar
`CustomToolLoader._resolve_dotted` (mismo camino que `function.path`), de
modo que el allowlist y `AgnoResolver.resolve_class` se apliquen idénticos a
los de herramientas y `header_provider`.

Los callables resueltos DEBEN reenviarse al decorador como:

- `@tool(pre_hook=<callable>)` cuando `pre_hook` está presente.
- `@tool(post_hook=<callable>)` cuando `post_hook` está presente.
- `@tool(tool_hooks=[<callable>, ...])` cuando `tool_hooks` es no vacío.

Las flags `None` DEBEN omitirse (comportamiento ya existente en `_wrap_tool`).
La lista `tool_hooks` vacía DEBE omitirse también.

#### Scenario: Reenvío dorado de pre_hook a @tool (GOLDEN)

- GIVEN un `CustomToolConfig` con `pre_hook: "myapp.hooks.audit"` cuyo módulo `myapp.hooks` ESTÁ en el allowlist
- WHEN `ToolFactory._wrap_tool(raw_callable, config)` se ejecuta
- THEN `_resolve_dotted` resuelve la referencia a un `Callable`
- AND el decorador `@tool` se invoca con `pre_hook=<callable resuelto>`
- AND el `Function` retornado porta el hook pre-ejecución

#### Scenario: Reenvío dorado de tool_hooks como lista (GOLDEN)

- GIVEN un `CustomToolConfig` con `tool_hooks: ["myapp.hooks.a", "myapp.hooks.b"]`, ambos módulos allowlisted
- WHEN `_wrap_tool` se ejecuta
- THEN cada string se resuelve a un `Callable` distinto
- AND `@tool` se invoca con `tool_hooks=[<callable_a>, <callable_b>]` en el MISMO orden del YAML

#### Scenario: Hooks omitidos cuando están ausentes

- GIVEN un `CustomToolConfig` sin `pre_hook`, `post_hook` ni `tool_hooks`
- WHEN `_wrap_tool` se ejecuta
- THEN `@tool` se invoca SIN las claves `pre_hook`, `post_hook`, ni `tool_hooks`
- AND el resultado es idéntico al comportamiento de slice C (sin regresión)

### Requirement: Rechazo de módulos de hook fuera del allowlist (RED de seguridad)

Si una referencia dotted-path de hook apunta a un módulo NO presente en el
allowlist (`is_module_allowed` retorna `False`), el sistema DEBE lanzar
`SecurityError` (la misma excepción que ya se lanza para `function.path` y
`header_provider` no autorizados). El error DEBE propagarse desde
`_resolve_dotted` sin captura que lo silencie.

#### Scenario: Hook en módulo no allowlisted (RED)

- GIVEN un `CustomToolConfig` con `pre_hook: "evil_pkg.exfil"` donde `evil_pkg` NO está en el allowlist
- WHEN `ToolFactory._wrap_tool` intenta resolver el hook
- THEN se lanza `SecurityError` mencionando el módulo rechazado
- AND `@tool` NO se invoca (la construcción aborta antes)

#### Scenario: Un hook allowlisted y otro no (transacción parcial)

- GIVEN un `CustomToolConfig` con `tool_hooks: ["myapp.hooks.ok", "evil_pkg.bad"]`
- WHEN `_wrap_tool` resuelve la lista
- THEN se lanza `SecurityError` por `evil_pkg.bad`
- AND NO se construye un `Function` con hooks parciales (todo o nada)

### Requirement: tool_call_limit en AgentConfig

`AgentConfig` DEBE añadir un campo `tool_call_limit: int | None` con
`Field(default=None, ge=1)`. El valor `None` significa "sin límite explícito
(dejar el default de Agno)". Los valores `int` DEBEN ser `>= 1`. El campo
pertenece a la AGENTE, no a la herramienta (es un límite por ejecución de
Agent, no por tool).

#### Scenario: tool_call_limit válido

- GIVEN un YAML `agent:` con `tool_call_limit: 5`
- WHEN se valida contra `AgentConfig`
- THEN el campo se acepta como entero `5`

#### Scenario: tool_call_limit ausente (default None)

- GIVEN un YAML `agent:` SIN el campo `tool_call_limit`
- WHEN se valida contra `AgentConfig`
- THEN `tool_call_limit` toma el valor `None`

#### Scenario: tool_call_limit inválido (cero o negativo)

- GIVEN un YAML `agent:` con `tool_call_limit: 0`
- WHEN se valida contra `AgentConfig`
- THEN la validación RECHAZA el entry por violar la restricción `ge=1`

### Requirement: AgentFactory.build reenvía tool_call_limit a Agno

`AgentFactory.build` DEBE reenviar `tool_call_limit` al constructor
`agno.Agent(tool_call_limit=...)` cuando el campo esté presente
(no-`None`). Cuando sea `None`, la flag DEBE omitirse para que Agno aplique
su propio default.

#### Scenario: tool_call_limit reenviado (GOLDEN)

- GIVEN un `AgentConfig` con `tool_call_limit: 10`
- WHEN `AgentFactory.build(cfg, resolver)` construye el `Agent`
- THEN se invoca `Agent(..., tool_call_limit=10)`

#### Scenario: tool_call_limit=None (default, Agent recibe None)

- GIVEN un `AgentConfig` con `tool_call_limit: None`
- WHEN `AgentFactory.build` construye el `Agent`
- THEN la flag `tool_call_limit` SE OMITE de la llamada a `Agent`
- AND el comportamiento es idéntico al de slice C (sin regresión)

## MODIFIED Requirements

### Requirement: Reenvío de flags de caching per-call (invariante slice C)

Los campos `cache_results`, `cache_dir` y `cache_ttl` ya se reenvían en
`_wrap_tool` (slice C, tool_factory.py:170-172). Este slice DECLARA ese
comportamiento como INVARIANTE: la adición de hooks y `tool_call_limit` NO
DEBE romper el reenvío de caching. Las tres flags deben seguir presentes en
el dict `flags` y reenviarse a `@tool` exactamente como hoy.

(Previously: el reenvío de caching era un detalle de slice C sin
invariante declarado; ahora es una protección contra regresión en slice D.)

#### Scenario: Caching sigue reenviado (invariante)

- GIVEN un `CustomToolConfig` con `cache_results: true`, `cache_ttl: 300` y además `pre_hook: "myapp.hooks.audit"`
- WHEN `_wrap_tool` se ejecuta
- THEN `@tool` se invoca con `cache_results=True`, `cache_ttl=300` Y `pre_hook=<callable>`
- AND ninguna de las flags de caching se pierde por la presencia de hooks

#### Scenario: Caching reenviado sin hooks (regresión nula)

- GIVEN un `CustomToolConfig` con `cache_results: true` y SIN hooks
- WHEN `_wrap_tool` se ejecuta
- THEN el resultado es byte-idéntico al de slice C (mismo set de flags)

## REMOVED Requirements

### Requirement: Executor de concurrencia de herramientas (executor.py)

(Reason: Agno ya posee el loop de ejecución de herramientas — `Agent.run()`
/ `arun()` y `aget_tools()` deciden sincronía/asincronía internamente.
`yaml-agno` SOLO CONSTRUYE herramientas, no las ejecuta. Un `executor.py`
con `run_tools_concurrently` reimplementaría el loop de Agno (riesgo
Frankenstein). Verificado en obs-2018.)
(Migration: Ninguna. Quien necesite concurrencia de ejecución debe
configurar el Agent de Agno, no añadir un executor en yaml-agno.)

### Requirement: Registry 120+ (expansión de adaptadores builtin)

(Reason: La expansión de `BUILTIN_REGISTRY` a 120+ toolkits es trabajo de
DATOS puro (alta volumen, baja lógica) que merece su propio change con PRs
encadenados por categoría. Mezclarlo con hooks/`tool_call_limit` inflaría
el diff más allá del presupuesto de 400 líneas.)
(Migration: Se realizará como change separado — p. ej.
`registry-expansion-120`.)

### Requirement: Caching cross-run (cache_callables / callable_tools_cache_key)

(Reason: Caching per-call (`cache_results`) ya está entregado (slice C) y
es declarado invariante arriba. El caching cross-run de objetos-tool
construidos es un LRU de yaml-agno de bajo valor para el MVP (las
herramientas son baratas de construir excepto MCP, que se autoconecta).
Se difiere a post-MVP.)
(Migration: Ninguna para el MVP. Reevaluar post-MVP si el costo de
construcción de herramientas se vuelve medible.)
