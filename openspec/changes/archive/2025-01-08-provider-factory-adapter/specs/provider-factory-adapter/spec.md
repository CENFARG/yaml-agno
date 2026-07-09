# provider-factory-adapter Specification

Especificación delta del slice #3 de SPEC_14: `ProviderFactory` (construcción
síncrona de `Model` Agno desde `ModelExpandedSpec`), `_compose_kwargs`
(filtrado dinámico contra los campos del dataclass destino),
`AgnoModelAdapter` (cache de instancias por alias),
`ModelCapabilitiesValidator` (validación config-time, datos puros) y
`ConfigSecretResolver` (default síncrono sobre `ConfigManager`, sin
`os.environ`).

El slice COMPOSE alrededor de `AgnoResolver` (delega la resolución de clases)
y NO duplica la lógica de importlib/allowlist. No cablea `AgentConfig.model`
ese cableado es un cambio coordinado posterior (SPEC_02 evolution).

## ADDED Requirements

### Requirement: ProviderFactory.build construye un Model Agno desde ModelExpandedSpec

`ProviderFactory.build(spec: ModelExpandedSpec)` DEBE devolver una instancia
del `Model` Agno correspondiente al `spec.provider` (tras resolución de
alias). El factory DELEGARÁ la resolución de la clase a
`AgnoResolver.resolve_class(module_path, class_name)` (método público,
`agno_resolver.py:184`) — NO DEBE reimplementar `importlib` ni el allowlist.
La instancia resultante SHALL construirse con `id=spec.id` más los kwargs
filtrados por `_compose_kwargs`.

#### Scenario: build golden path — OpenAIChat con temperature

- GIVEN un `ProviderFactory` con un `AgnoResolver` configurado y un
  `ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.7)`
- WHEN se llama `factory.build(spec)`
- THEN el resultado es una instancia de `OpenAIChat`
- AND la instancia tiene `id == "gpt-4o"` y `temperature == 0.7`

#### Scenario: build rechaza provider desconocido

- GIVEN un `ModelExpandedSpec(provider="no_existe", id="x")` — inválido por
  sí mismo, pero asumido construido bypassing validación
- WHEN se llama `factory.build(spec)`
- THEN se lanza `KeyError` (provider ausente en `MODEL_REGISTRY`/
  `PROVIDER_REGISTRY`) o el error de validación se propaga antes del build

### Requirement: COMPOSE — ProviderFactory delega resolución de clases a AgnoResolver

`ProviderFactory` DEBE recibir un `AgnoResolver` inyectado y llamar a
`resolver.resolve_class(module_path, class_name)` para obtener la clase Agno.
NO DEBE existir una segunda ruta de `importlib` paralela. La firma pública
`AgnoResolver.resolve_class` (línea 184) DEBE permanecer pública como punto
de extensión del factory.

#### Scenario: el factory no duplica importlib

- GIVEN el código fuente de `ProviderFactory.build`
- WHEN se inspecciona la resolución de la clase
- THEN la única vía es `self._resolver.resolve_class(...)` — no hay
  `importlib.import_module` directo en el factory

### Requirement: _compose_kwargs filtra dinámicamente contra los campos de la clase destino

`ProviderFactory._compose_kwargs(spec, target_cls)` DEBE inspeccionar los
campos del dataclass `target_cls` (Agno `Model` es `@dataclass`) y reenviar
SOLO los campos declarados en `ModelExpandedSpec` que existan en
`target_cls`. Los campos ausentes en la clase destino DEBEN omitirse
silenciosamente (sin TypeError). Esto evita el fallo por parámetros
provider-específicos (p.ej. `top_k` en OpenAIChat).

**Exclusión explícita de `thinking`**: el campo `thinking` (`bool` en
`ModelExpandedSpec`) se excluye DEL universal forwarding porque el target
`Claude.thinking` espera `Dict[str, Any]` — reenviar el bool causaría
`TypeError`. Los usuarios que quieran thinking lo configuran vía el escape
hatch `provider_kwargs` (campo futuro). Esta exclusión es además de la del
filtro dinámico (campo reservado, no reenviado sin importar la clase).

#### Scenario: temperature se reenvía a OpenAIChat (la tiene)

- GIVEN un `ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.5)`
- WHEN `factory.build(spec)` construye los kwargs contra `OpenAIChat`
- THEN `temperature=0.5` está presente en los kwargs de construcción
- AND la instancia resulta con `temperature == 0.5`

#### Scenario: top_k NO se reenvía a OpenAIChat (no la tiene)

- GIVEN un `ModelExpandedSpec(provider="openai", id="gpt-4o", top_k=40)`
- WHEN `factory.build(spec)` construye los kwargs contra `OpenAIChat`
- THEN `top_k` NO está en los kwargs (filtrado dinámico)
- AND no se lanza `TypeError` por argumento inesperado

### Requirement: api_key se resuelve vía SecretResolver síncrono inyectado

`ProviderFactory` DEBE recibir un `SecretResolver` síncrono inyectado
(`Callable[[str], str | None]`). El factory SHALL usar el `api_key_env`
declarado en `PROVIDER_REGISTRY[provider]` como clave lógica y pasar el
valor resuelto como `api_key=` a la clase Agno. El factory NO DEBE leer
`os.environ` directamente — el `SecretResolver` es la única vía de acceso a
secretos. Los providers locales (`api_key_env is None`) NO DEBEN requerir
secreto.

#### Scenario: api_key resuelto desde SecretResolver

- GIVEN un `ProviderFactory` cuyo `SecretResolver` devuelve `"sk-test"` para
  la clave `"OPENAI_API_KEY"` y un
  `ModelExpandedSpec(provider="openai", id="gpt-4o")`
- WHEN se llama `factory.build(spec)`
- THEN la instancia `OpenAIChat` se construye con `api_key="sk-test"`
- AND el factory no leyó `os.environ`

#### Scenario: provider local no requiere api_key

- GIVEN un `ModelExpandedSpec(provider="ollama", id="llama3")` (provider
  local, `api_key_env is None`)
- WHEN se llama `factory.build(spec)`
- THEN la instancia se construye SIN `api_key=` kwarg
- AND no se consulta el `SecretResolver`

### Requirement: ConfigSecretResolver default lee ConfigManager

El `SecretResolver` por defecto SHALL ser `ConfigSecretResolver(config:
ConfigManager)`. Su implementación DEBE leer
`config.get_string(f"secrets.{key}")` (donde `key` es el `api_key_env`
normalizado a minúsculas) y devolver `None` si no existe. NO DEBE acceder a
`os.environ`. Es compatible-con-pero-más-estrecho-que el `SecretManager`
async de core-cenf; la capa bootstrap adapta async→sync pre-resolviendo.

#### Scenario: ConfigSecretResolver lee config

- GIVEN un `ConfigManager` cuyo `get_string("secrets.openai_api_key")`
  devuelve `"sk-cfg"`
- WHEN se llama `ConfigSecretResolver(config)("OPENAI_API_KEY")`
- THEN devuelve `"sk-cfg"`

#### Scenario: ConfigSecretResolver devuelve None si falta

- GIVEN un `ConfigManager` sin la clave `secrets.openai_api_key`
- WHEN se llama `ConfigSecretResolver(config)("OPENAI_API_KEY")`
- THEN devuelve `None`

### Requirement: AgnoModelAdapter cachea instancias por alias

`AgnoModelAdapter` DEBE cachear la instancia `Model` construida, con clave
`spec.alias or f"{spec.provider}:{spec.id}"`. Una segunda llamada `build`
con el mismo alias SHALL devolver la MISMA instancia (identidad `is`).
`adapter.invalidate(alias=None)` DEBE limpiar la entrada indicada, o todo el
cache si `alias is None`. No hay TTL en este slice.

#### Scenario: build dos veces devuelve la misma instancia

- GIVEN un `AgnoModelAdapter` sobre un `ProviderFactory`
- WHEN se llama `adapter.build(spec)` y luego `adapter.build(spec)` con el
  mismo `spec`
- THEN ambos resultados son el mismo objeto (`is` identity True)

#### Scenario: invalidate limpia el cache

- GIVEN un `AgnoModelAdapter` con una instancia cacheada para el alias
  `"openai:gpt-4o"`
- WHEN se llama `adapter.invalidate("openai:gpt-4o")` y luego
  `adapter.build(spec)` de nuevo
- THEN la segunda instancia es DISTINTA de la primera (`is` False)

### Requirement: ModelCapabilitiesValidator valida datos puros config-time

`ModelCapabilitiesValidator` DEBE ser una validación config-time sobre datos
declarados (`PROVIDER_REGISTRY[provider].capabilities`), SIN instanciar
clases Agno. DEBE rechazar `reasoning_effort`/`thinking` cuando
`capabilities.reasoning is False`. Devuelve una lista de errores (vacía =
OK). No toca el runtime de Agno.

#### Scenario: reasoning_effort rechazado en provider non-reasoning

- GIVEN un `ModelExpandedSpec(provider="mistral", id="...", reasoning_effort="high")`
  (`mistral` tiene `capabilities.reasoning == False`)
- WHEN se llama `ModelCapabilitiesValidator().validate(spec)`
- THEN la lista de errores contiene un mensaje sobre `reasoning_effort`
  no soportado por el provider

#### Scenario: reasoning_effort aceptado en provider reasoning

- GIVEN un `ModelExpandedSpec(provider="openai", id="...", reasoning_effort="high")`
  (`openai` tiene `capabilities.reasoning == True`)
- WHEN se llama `ModelCapabilitiesValidator().validate(spec)`
- THEN la lista de errores está vacía

### Requirement: Campos retry — solo nombres nativos Agno, sin traducción

El slice #3 NO introduce nombres yaml-agno-only de retry
(`retry_delay`, `wait_on_rate_limit`, `retry_jitter`). `_compose_kwargs` SHALL
reenviar los campos nativos Agno declarados en `ModelExpandedSpec`
(`retries`, `delay_between_retries`, `exponential_backoff`,
`retry_with_guidance`, `retry_with_guidance_limit`) 1:1, sin capa de
traducción. Los campos base `Model` universales se reenvían siempre.

### Requirement: Invariante — agent_config sin cambios en el slice #3

El slice #3 NO DEBE cablear `ModelSpec`/`ModelExpandedSpec` en
`AgentConfig.model`. Ese cableado es un cambio coordinado posterior
(SPEC_02 evolution). Los artefactos del slice (`factory.py`, `adapter.py`,
`capabilities.py`) son aditivos y standalone — nada los importa fuera de
tests hasta el cableamiento.

#### Scenario: AgentConfig.model permanece sin cambios

- GIVEN el código fuente del slice #3
- WHEN se inspecciona `AgentConfig`
- THEN `AgentConfig.model` mantiene su tipo actual (no `ModelSpec`)
- AND ningún módulo de producción fuera de `models/` importa el factory
