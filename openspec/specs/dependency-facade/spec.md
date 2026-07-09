# Dependency Facade Specification

## Purpose

Fachada de dominio Agno sobre el motor de carga de clases de `core-cenf`
(`ImportlibDependencyAdapter`). Expone resolución de modelos, construcción de
almacenamiento y resolución de clases Agno, más un `ValueResolver` que traduce
la sintaxis propia `${provider.key}` al diccionario que `DIReference.resolve()`
consume. El motor (importlib + allowlist + cache) SE IMPORTA; yaml-agno NO lo
reimplementa.

## Requirements

### Requirement: AgnoResolver envuelve el motor importado

`AgnoResolver` DEBE contener una instancia de `ImportlibDependencyAdapter`
(construida con `(config, logger, error_handler)`) y NO DEBE reimplementar
importlib, allowlist ni cache. Todos sus métodos de dominio DELEGAN al adapter.

#### Scenario: resolve_class delega al adapter y cachea

- GIVEN un `AgnoResolver` con allowlist sembrado con `agno.models.`
- WHEN se invoca `resolve_class("agno.models.openai.chat", "OpenAIChat")`
- THEN retorna la clase `OpenAIChat` (cached) sin reimportar en la 2da llamada

### Requirement: build_agno_resolver instancia managers en orden del grafo

`build_agno_resolver()` DEBE instanciar los 3 managers core-cenf en orden
`Config → Logger → Errors → Dependency` e inyectar el ConfigManager ya
construido en Logger y Errors. DEBE sembrar los prefijos Agno del allowlist
(`agno.models.`, `agno.db.`, `agno.workflow.`, `agno.team.`, `agno.agent`)
ANTES de construir el adapter.

#### Scenario: bootstrap sin excepción con doubles in-memory

- GIVEN `InMemoryConfigAdapter` con sección `dependency.allowlist_paths`
- WHEN se ejecuta `build_agno_resolver()`
- THEN retorna un `AgnoResolver` funcional sin lanzar excepciones

#### Scenario: idempotencia de register

- GIVEN un `AgnoResolver` ya inicializado
- WHEN se llama `register()` dos veces con los mismos namespaces
- THEN el adapter NO duplica entradas de registro

### Requirement: resolve_model con sintaxis provider:id

`resolve_model(spec)` DEBE aceptar el formato `"provider:id"` (COLON, formato
nativo Agno), partir en `(provider, model_id)`, buscar el target en
`MODEL_REGISTRY`, resolver la clase vía el adapter e instanciarla con
`id=model_id`. El resultado DEBE ser una instancia de `Model`.

#### Scenario: golden path openai:gpt-4o

- GIVEN `MODEL_REGISTRY["openai"] = ("agno.models.openai.chat", "OpenAIChat")`
- WHEN `resolve_model("openai:gpt-4o")`
- THEN retorna `OpenAIChat(id="gpt-4o")` instancia de `Model`

#### Scenario: provider desconocido

- GIVEN un provider no presente en `MODEL_REGISTRY`
- WHEN `resolve_model("desconocido:foo")`
- THEN lanza un error indicando provider no registrado

### Requirement: build_db con semántica de connection-string

`build_db(kind, conn_str)` DEBE distinguir backends que NO requieren conexión
(`memory`, `sqlite` in-memory) de los que SÍ (`postgres`, `redis`).
- Para `memory`/`sqlite` sin `conn_str`: instancia el backend sin pasar
  connection string.
- Para `postgres`/`redis`: REQUIERE `conn_str` o lanza.
- Backend desconocido: lanza.

#### Scenario: memory sin conn_str

- GIVEN `STORAGE_REGISTRY["memory"] = ("agno.db.in_memory.in_memory_db", "InMemoryDb")`
- WHEN `build_db("memory", None)`
- THEN retorna `InMemoryDb()` (constructor sin args)

#### Scenario: postgres con conn_str

- GIVEN `STORAGE_REGISTRY["postgres"] = ("agno.db.postgres.postgres", "PostgresDb")`
- WHEN `build_db("postgres", "postgresql://user:pass@host/db")`
- THEN retorna `PostgresDb(db_url="postgresql://...")`

#### Scenario: postgres sin conn_str rechazado

- GIVEN `STORAGE_REGISTRY` con `postgres`
- WHEN `build_db("postgres", None)`
- THEN lanza indicando que `conn_str` es obligatorio para `postgres`

#### Scenario: storage desconocido

- GIVEN `STORAGE_REGISTRY` sin la clave `oracle`
- WHEN `build_db("oracle", "conn")`
- THEN lanza indicando backend no soportado

### Requirement: resolve_class validada por allowlist en strict mode

`resolve_class(module, class)` DEBE delegar al adapter. En strict mode
(default), un path NO cubierto por los prefijos del allowlist DEBE ser
rechazado.

#### Scenario: path allowlisted permitido

- GIVEN allowlist con prefijo `agno.models.`
- WHEN `resolve_class("agno.models.openai.chat", "OpenAIChat")`
- THEN retorna la clase `OpenAIChat`

#### Scenario: path no allowlisted rechazado

- GIVEN allowlist con prefijos Agno únicamente
- WHEN `resolve_class("os", "system")`
- THEN lanza (path fuera del allowlist, strict mode)

### Requirement: register de namespaces Agno en bootstrap

El wiring de bootstrap (`build_agno_resolver`) DEBE registrar los namespaces
Agno (models, storage) VÍA el adapter inyectado, usando su método
`register(namespace, key, target)` y los datos declarativos de `MODEL_REGISTRY`
y `STORAGE_REGISTRY`. `AgnoResolver` no expone `register()` como método propio
— el registro vive en el `DependencyManager` (adapter). El invariante probado
es que no se duplican entradas al re-sembrar.

#### Scenario: registro de model namespace

- GIVEN `MODEL_REGISTRY = {"openai": ("agno.models.openai.chat", "OpenAIChat")}`
- WHEN el wiring invoca `adapter.register("models", "openai", target)` durante bootstrap
- THEN el adapter NO duplica entradas al re-sembrar el mismo namespace (idempotencia)

### Requirement: ValueResolver produce dict para DIReference.resolve

`ValueResolver.resolve(ref)` DEBE iterar `ref.tokens` (lista de
`(provider, key)`), resolver cada par contra el provider correspondiente y
producir un `dict[str, Any]` plano `"provider.key" -> value` consumible por
`DIReference.resolve(resolved_values)`. MVP: `env.<key>` vía
`ConfigManager.get_string(key)`.

#### Scenario: env provider resuelve via ConfigManager

- GIVEN un `DIReference(template="${env.api_key}")` y `ConfigManager` con `api_key="sk-xxx"`
- WHEN `ValueResolver.resolve(ref)`
- THEN retorna `{"env.api_key": "sk-xxx"}` y `DIReference.resolve(dict)` produce `"sk-xxx"`

#### Scenario: db provider lanza NotImplementedError (deferido)

- GIVEN un `DIReference(template="${db.user_db.name}")`
- WHEN `ValueResolver.resolve(ref)`
- THEN lanza `NotImplementedError` (provider `db` diferido a SPEC_23)

#### Scenario: api y file providers diferidos

- GIVEN un `DIReference` con token `api.*` o `file.*`
- WHEN `ValueResolver.resolve(ref)`
- THEN lanza `NotImplementedError` indicando SPEC_23

### Requirement: ValueResolver y AgnoResolver son abstracciones distintas

`ValueResolver` (resolución de VALORES `${provider.key}`) y `AgnoResolver`
(carga de CLASES Agno) DEBEN ser clases separadas con responsabilidades no
overlapping. NINGUNA DEBE depender de la otra para su función central.

#### Scenario: separación de concerns

- GIVEN un `ValueResolver` y un `AgnoResolver` construidos independientemente
- WHEN se invoca `ValueResolver.resolve(ref)` sin un `AgnoResolver`
- THEN la resolución de valores funciona sin tocar carga de clases

#### Scenario: DIReference integration end-to-end

- GIVEN `DIReference(template="key=${env.api_key}")` y un `ValueResolver` con ConfigManager
- WHEN se encadenan `ValueResolver.resolve(ref)` -> `DIReference.resolve(dict)`
- THEN el resultado es `"key=sk-xxx"` (valor real del ConfigManager)
