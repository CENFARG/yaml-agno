# Model Config Schema Specification (SPEC_14 slice #2)

> **Alcance**: Esquemas Pydantic V2 standalone que validan la configuración
> declarativa de modelos. Slice #2 NO toca `AgentConfig.model` (queda `str`),
> NO introduce runtime de fallback/Circuit Breaker (eso es slice #4), y NO
> acopla `FallbackConfig` a SPEC_09. Frontera estricta con SPEC_05
> (`RetryPolicy` es step-level, no model-level).

---

## ADDED Requirements

### Requirement: ModelStringSpec valida formato `provider:id`

El schema `ModelStringSpec` MUST aceptar strings con gramática
`provider:id` o `provider:id:alias` (2 o 3 segmentos separados por `:`).
El campo `raw` MUST preservar el string original sin normalizar.
La validación del `provider` (primer segmento) MUST consultar el
`frozenset` `SUPPORTED_PROVIDERS` importado de
`yaml_agno.di.provider_capabilities` (única fuente de verdad del catálogo,
derivada de `PROVIDER_REGISTRY`). Un `provider` ausente del catálogo
MUST provocar un `ValidationError` cuyo mensaje nombra el provider
ofendente. La validación de formato (cantidad de segmentos) MUST
ejecutarse antes de la validación de catálogo para producir mensajes
distintos y accionables. El schema NO MUST realizar resolución de alias
ni expansión a `ModelExpandedSpec` — esa responsabilidad es de
`ProviderResolver`.

#### Scenario: ModelStringSpec golden path

- GIVEN el catálogo `SUPPORTED_PROVIDERS` contiene `"anthropic"`
- WHEN se instancia `ModelStringSpec(raw="anthropic:claude-sonnet-4-5")`
- THEN la instancia se crea sin error
- AND `.raw == "anthropic:claude-sonnet-4-5"`

#### Scenario: ModelStringSpec con alias (3 segmentos)

- GIVEN `SUPPORTED_PROVIDERS` contiene `"openai_responses"`
- WHEN se instancia `ModelStringSpec(raw="openai_responses:gpt-4o:fb-openai")`
- THEN la instancia se crea sin error
- AND `.raw.count(":") == 2`

#### Scenario: RED — provider desconocido

- GIVEN `SUPPORTED_PROVIDERS` NO contiene `"acme"`
- WHEN se instancia `ModelStringSpec(raw="acme:gpt-x")`
- THEN se lanza `ValidationError`
- AND el mensaje menciona `"acme"` como provider desconocido

#### Scenario: RED — formato inválido (sin dos puntos)

- GIVEN cualquier catálogo
- WHEN se instancia `ModelStringSpec(raw="no_colon")`
- THEN se lanza `ValidationError`
- AND el mensaje exige el formato `provider:id` o `provider:id:alias`

#### Scenario: RED — formato inválido (4 segmentos)

- GIVEN cualquier catálogo
- WHEN se instancia `ModelStringSpec(raw="a:b:c:d")`
- THEN se lanza `ValidationError` por exceso de segmentos

### Requirement: ModelStringSpec acepta providers vía alias

Dado que `PROVIDER_ALIASES` (en `yaml_agno.di.registries`) mapea
`"openai"` → `"openai_chat"`, y que `"openai"` es además una clave directa
de `PROVIDER_REGISTRY` (por lo tanto miembro de `SUPPORTED_PROVIDERS`),
`ModelStringSpec` MUST aceptar `raw="openai:gpt-4o"` sin error de
catálogo. La validación a nivel de schema sólo chequea pertenencia al
catálogo; la canonicalización (`openai` → `openai_chat`) es
responsabilidad de `ProviderResolver`, no del schema.

#### Scenario: Alias `openai` aceptado a nivel de schema

- GIVEN `SUPPORTED_PROVIDERS` contiene `"openai"` (clave directa + alias de `openai_chat`)
- WHEN se instancia `ModelStringSpec(raw="openai:gpt-4o")`
- THEN la instancia se crea sin error
- AND `.raw == "openai:gpt-4o"` (sin canonicalizar)

### Requirement: ModelExpandedSpec — forma expandida con parámetros

`ModelExpandedSpec` MUST modelar la forma expandida del modelo con:
campos de identificación (`provider`, `id`, `alias`), parámetros de
generación (`temperature` 0.0–2.0, `max_tokens` ≥1, `top_p` 0.0–1.0,
`top_k` ≥0, `stop_sequences`, `seed`), razonamiento (`reasoning_effort`
∈ `minimal|low|medium|high`, `thinking`), caching (`cache_response`
default `False`), campos de retry Agno-native (ver Requirement
"Retry boundary"), `fallback` (`FallbackConfig | None`), `provider_kwargs`
(default `{}`), y overrides de cliente (`timeout` >0, `base_url`). El
campo `provider` MUST validarse contra `SUPPORTED_PROVIDERS` vía
`field_validator` — NO vía `Literal[...]` hardcoded (evita duplicar el
catálogo y derivar en un segundo SSOT que se desincroniza al agregar
providers). Los rangos numéricos MUST hacerse cumplir por `Field(ge=, le=)`.

#### Scenario: ModelExpandedSpec golden path

- GIVEN `SUPPORTED_PROVIDERS` contiene `"anthropic"`
- WHEN se instancia con `provider="anthropic"`, `id="claude-sonnet-4-5"`,
  `temperature=0.7`, `max_tokens=4096`, `cache_response=True`
- THEN la instancia se crea sin error
- AND `.provider == "anthropic"` y `.temperature == 0.7`

#### Scenario: RED — temperature fuera de rango

- GIVEN cualquier provider válido
- WHEN se instancia `ModelExpandedSpec(provider="anthropic", id="x", temperature=2.5)`
- THEN se lanza `ValidationError` por exceder `le=2.0`

#### Scenario: RED — top_p fuera de rango

- GIVEN cualquier provider válido
- WHEN se instancia con `top_p=1.5`
- THEN se lanza `ValidationError`

#### Scenario: RED — retries excede el tope

- GIVEN cualquier provider válido
- WHEN se instancia con `retries=11`
- THEN se lanza `ValidationError` por exceder `le=10`

#### Scenario: RED — provider ausente del catálogo

- GIVEN `SUPPORTED_PROVIDERS` NO contiene `"nonexistent"`
- WHEN se instancia `ModelExpandedSpec(provider="nonexistent", id="x")`
- THEN se lanza `ValidationError` mencionando el provider desconocido

#### Scenario: `provider_kwargs` default vacío

- GIVEN cualquier provider válido
- WHEN se instancia sin pasar `provider_kwargs`
- THEN `.provider_kwargs == {}`

### Requirement: Retry boundary — sólo campos Agno-native

`ModelExpandedSpec` MUST exponer únicamente los campos de retry que
existen en la clase base `Model` de Agno: `retries` (int, 0–10, default
0), `delay_between_retries` (float, ≥0, default 1.0), `exponential_backoff`
(bool, default `True`), `retry_with_guidance` (bool, default `False`) y
`retry_with_guidance_limit` (int, ≥0, default 0). El schema MUST NOT
definir `retry_delay`, `wait_on_rate_limit`, ni `retry_jitter` a nivel
de modelo — esos son knobs yaml-agno propios del path de fallback-probe
(slice #4) o del `RetryPolicy` step-level (SPEC_05). Duplicarlos aquí
rompería la invariante "exactamente UNA abstracción de retry por nivel".
Los nombres de los campos MUST coincidir 1:1 con los campos nativos de
Agno `Model` para permitir forwarding verbatim sin traducción de nombres.

#### Scenario: Defaults Agno-native

- GIVEN un provider válido
- WHEN se instancia `ModelExpandedSpec(provider="anthropic", id="x")` sin overrides
- THEN `.retries == 0`
- AND `.delay_between_retries == 1.0`
- AND `.exponential_backoff is True`
- AND `.retry_with_guidance is False`
- AND `.retry_with_guidance_limit == 0`

#### Scenario: Ausencia de knobs yaml-agno

- GIVEN la definición de `ModelExpandedSpec`
- WHEN se inspecciona el set de campos del modelo
- THEN NO contiene `retry_delay`
- AND NO contiene `wait_on_rate_limit`
- AND NO contiene `retry_jitter`

### Requirement: FallbackConfig — schema autocontenido

`FallbackConfig` MUST ser un schema standalone con sus propios enums,
listas y escalares. MUST NOT importar ni depender de tipos definidos en
SPEC_09 (Circuit Breaker) ni de `RetryPolicy` de SPEC_05. Los campos de
routing (`on_rate_limit`, `on_context_overflow`, `on_error`) MUST ser
`Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"]`
con defaults `route_fallback`, `route_fallback`, `retry_then_fallback`
respectivamente. `fallback_models` MUST aceptar una lista de referencias
mixtas (`str | dict`) para flexibilidad YAML; la resolución de cada
referencia a `ModelExpandedSpec` NO es responsabilidad de este schema.
`max_fallback_hops` MUST ser `int ≥ 1` (default 3). `propagate_session`
MUST ser `bool` (default `True`). `fallback_callback` MUST ser
`str | None` (ruta importable, default `None`).

#### Scenario: FallbackConfig golden path

- GIVEN cualquier catálogo
- WHEN se instancia `FallbackConfig(fallback_models=["openai_responses:gpt-4o"], on_rate_limit="route_fallback", on_error="retry_then_fallback", max_fallback_hops=3)`
- THEN la instancia se crea sin error
- AND `.max_fallback_hops == 3`

#### Scenario: RED — valor de enum inválido

- GIVEN cualquier catálogo
- WHEN se instancia `FallbackConfig(on_rate_limit="banana")`
- THEN se lanza `ValidationError` por enum fuera del set permitido

#### Scenario: RED — max_fallback_hops menor que 1

- GIVEN cualquier catálogo
- WHEN se instancia `FallbackConfig(max_fallback_hops=0)`
- THEN se lanza `ValidationError` por violar `ge=1`

#### Scenario: Defaults aplicados

- GIVEN cualquier catálogo
- WHEN se instancia `FallbackConfig()` sin argumentos
- THEN `.fallback_models == []`
- AND `.on_rate_limit == "route_fallback"`
- AND `.on_error == "retry_then_fallback"`
- AND `.propagate_session is True`
- AND `.fallback_callback is None`

### Requirement: ModelSpec — unión discriminada str | dict

`ModelSpec` MUST ser una unión que acepte `str` (derivando a
`ModelStringSpec`) O `dict` (derivando a `ModelExpandedSpec`). La
discriminación MUST ocurrir por tipo del nodo YAML (str vs mapping), no
por un campo discriminador explícito. Un nodo que no sea ni str ni dict
MUST ser rechazado por el parser (no por el schema).

#### Scenario: ModelSpec path str → ModelStringSpec

- GIVEN el parser recibe `model: "anthropic:claude-sonnet-4-5"`
- WHEN se valida el nodo contra `ModelSpec`
- THEN el resultado es una instancia de `ModelStringSpec`
- AND `.raw == "anthropic:claude-sonnet-4-5"`

#### Scenario: ModelSpec path dict → ModelExpandedSpec

- GIVEN el parser recibe `model: {provider: anthropic, id: claude-sonnet-4-5}`
- WHEN se valida el nodo contra `ModelSpec`
- THEN el resultado es una instancia de `ModelExpandedSpec`
- AND `.provider == "anthropic"` y `.id == "claude-sonnet-4-5"`

### Requirement: ProviderResolver — resolución y canonicalización

`ProviderResolver` MUST aceptar `str`, `dict` o `ModelExpandedSpec` y
devolver siempre un `ModelExpandedSpec` normalizado. Para inputs `str`,
MUST delegar la validación de gramática a `ModelStringSpec`. Antes de
indexar `PROVIDER_REGISTRY`, MUST aplicar `PROVIDER_ALIASES` (p.ej.
`"openai"` → `"openai_chat"`) de modo que la canonicalización ocurra en
un único punto. Un provider que, tras aplicar aliases, no exista en
`PROVIDER_REGISTRY` MUST provocar un error explícito. Para inputs `dict`,
MUST construir un `ModelExpandedSpec` (lo que dispara validación de
campos). Para inputs `ModelExpandedSpec`, MUST retornarlos sin
reconstruir. `ProviderResolver` MUST mantener un índice `_by_alias` de
modelos declarados para resolver referencias `alias: <name>` en fallback
chains (uso de slice #4); una alias no declarada MUST provocar
`UndefinedAliasError`.

#### Scenario: Resolver — string con alias canonicalizado

- GIVEN `PROVIDER_ALIASES == {"openai": "openai_chat"}` y `PROVIDER_REGISTRY` contiene `"openai_chat"`
- WHEN `ProviderResolver({}).resolve("openai:gpt-4o")`
- THEN retorna un `ModelExpandedSpec`
- AND `.provider == "openai_chat"` (canonicalizado, no `"openai"`)

#### Scenario: Resolver — string con provider canónico

- GIVEN `PROVIDER_REGISTRY` contiene `"anthropic"`
- WHEN `ProviderResolver({}).resolve("anthropic:claude-sonnet-4-5")`
- THEN retorna un `ModelExpandedSpec`
- AND `.provider == "anthropic"` y `.id == "claude-sonnet-4-5"`

#### Scenario: RED — Resolver rechaza provider desconocido

- GIVEN `PROVIDER_ALIASES` y `PROVIDER_REGISTRY` no contienen `"acme"`
- WHEN `ProviderResolver({}).resolve("acme:gpt-x")`
- THEN se lanza un error nombrando el provider desconocido

#### Scenario: Resolver — path dict

- GIVEN cualquier catálogo
- WHEN `ProviderResolver({}).resolve({"provider": "anthropic", "id": "x"})`
- THEN retorna un `ModelExpandedSpec` con `.provider == "anthropic"`

#### Scenario: Resolver — passthrough ModelExpandedSpec

- GIVEN un `ModelExpandedSpec` ya construido
- WHEN se pasa a `ProviderResolver({}).resolve(spec)`
- THEN retorna el mismo objeto sin reconstruir

### Requirement: SSOT — catálogo único desde `SUPPORTED_PROVIDERS`

El catálogo de providers válidos MUST derivarse de una única fuente:
`SUPPORTED_PROVIDERS` (`frozenset[str]` importable de
`yaml_agno.di.provider_capabilities`, derivado a su vez de
`PROVIDER_REGISTRY.keys()`). `ModelStringSpec._validate` y el
`field_validator` de `ModelExpandedSpec.provider` MUST consultar este
`frozenset`. El módulo de schemas MUST NOT definir un `Literal[...]`
hardcodeado de 26 entradas que duplique el catálogo — tal duplicación
derivaría en dos SSOT que se desincronizan al agregar un provider.

#### Scenario: Importabilidad del catálogo

- GIVEN el entorno de runtime de yaml-agno
- WHEN se ejecuta `from yaml_agno.di.provider_capabilities import SUPPORTED_PROVIDERS`
- THEN la importación tiene éxito
- AND `isinstance(SUPPORTED_PROVIDERS, frozenset)` es `True`
- AND `"anthropic" in SUPPORTED_PROVIDERS` y `"openai_chat" in SUPPORTED_PROVIDERS`

#### Scenario: Sin Literal hardcodeado

- GIVEN el módulo de schemas `models/model_spec.py`
- WHEN se inspecciona la definición de `ModelExpandedSpec.provider`
- THEN la validación se realiza por `field_validator` contra `SUPPORTED_PROVIDERS`
- AND NO existe `Literal["anthropic", "openai_chat", ...]` como anotación del campo `provider`

### Requirement: AgentConfig.model permanece `str` (invariante de slice #2)

El slice #2 NO MUST modificar el tipo del campo `AgentConfig.model` (que
permanece `str`, alias `ModelReference`). Las schemas de este slice son
standalone: `AgentConfig`, `AgentFactory.build()` y los tests existentes
(`test_agent_config.py`, `test_agent_factory.py`) MUST permanecer
inalterados. El acoplamiento de `AgentConfig.model` a la unión
`str | ModelExpandedSpec` es una evolución de schema coordinada que
pertenece a un slice posterior (3 o 4), no a este. Esta invariante
existe porque `AgentFactory.build()` hace passthrough `model=cfg.model`
a `agno.Agent(model=...)` y Agno realiza parsing nativo de strings;
cambiar el tipo ahora rompería el passthrough y los ~14 tests asociados
sin mecanismo de coordinación.

#### Scenario: AgentConfig.model sigue siendo str (regresión)

- GIVEN el código de `src/yaml_agno/models/config/agent_config.py`
- WHEN se inspecciona la anotación del campo `model`
- THEN la anotación es `str` (no `ModelSpec`, no `ModelExpandedSpec`, no unión)

#### Scenario: Ningún módulo importa las schemas nuevas

- GIVEN los módulos `models/config/agent_config.py` y `factories/agent_factory.py`
- WHEN se inspeccionan sus imports
- THEN ninguno importa de `models/model_spec.py` ni referencia `ModelStringSpec`, `ModelExpandedSpec`, `ModelSpec`, o `ProviderResolver`
