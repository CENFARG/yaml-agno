# model-resilience-runtime Specification

Especificación del slice #4 de SPEC_14 (DOMINIO únicamente): tres
componentes puros que ensamblan la cadena de fallback, generan una clave
de cache determinista y clasifican errores de proveedor para el routing.

**Alcance (NOW)**: `build_fallback_chain`, `CacheKeyBuilder`,
`FallbackErrorClassifier`. Los tres son funciones/métodos estáticos puros
sin I/O ni async.

**DEFER (NO en este slice)**: `call_with_fallback` (runtime executor),
`CircuitBreaker` (estados/min_requests), `RetryPolicy` (step-level,
backoff/jitter), `compute_delay`, `dispatch_fallback_callback`,
`probe_models_health`. Esos viven en SPEC_05 (`RetryPolicy`) y SPEC_09
(CircuitBreaker + runtime). El slice #4 construye la CADENA; no la
ejecuta. Tampoco introduce un cache store: Agno `cache_response` es
nativo; `CacheKeyBuilder` es sólo dedup/observabilidad.

## ADDED Requirements

### Requirement: build_fallback_chain devuelve lista ordenada de instancias Model

`build_fallback_chain(primary: ModelExpandedSpec, factory: ProviderFactory)`
DEBE devolver una lista ordenada de instancias `Model` de Agno (no specs).
El modelo primario SHALL ocupar el índice 0. Cada entrada de
`primary.fallback.fallback_models` (cuando `primary.fallback` no es `None`)
DEBE resolverse a una instancia vía `factory.build(...)` tras parseo y
canonicalización de alias. La lista resultante DEBE truncarse a
`primary.fallback.max_fallback_hops + 1` entradas (primario + N hops). Si
`primary.fallback is None`, la lista DEBE contener únicamente el primario
(una sola entrada).

#### Scenario: cadena dorada — primario + un fallback

- GIVEN un `ModelExpandedSpec(provider="anthropic", id="claude-sonnet-4-5")`
  con `fallback.fallback_models=["openai:gpt-4o"]` y un `factory` inyectado
  que devuelve instancias etiquetadas por provider
- WHEN se llama `build_fallback_chain(primary, factory)`
- THEN el resultado tiene longitud 2
- AND el elemento en el índice 0 corresponde al primario (anthropic)
- AND el elemento en el índice 1 corresponde al fallback (openai/gpt-4o)

#### Scenario: sin fallback devuelve sólo el primario

- GIVEN un `ModelExpandedSpec` con `fallback is None`
- WHEN se llama `build_fallback_chain(primary, factory)`
- THEN la lista resultante tiene exactamente una entrada
- AND esa entrada es la instancia del primario

#### Scenario: truncado a max_fallback_hops

- GIVEN un `ModelExpandedSpec` con `fallback.fallback_models` de 4 elementos
  y `fallback.max_fallback_hops=2`
- WHEN se llama `build_fallback_chain(primary, factory)`
- THEN la lista resultante tiene a lo sumo `2 + 1 = 3` entradas (primario
  más 2 hops)
- AND las entradas más allá del límite son descartadas

### Requirement: build_fallback_chain parsea refs str y dict vía parse_model_spec + ProviderResolver

Cada entrada de `fallback_models` (forma `str` `"provider:id"` o `dict`
`{provider, id, ...}`) DEBE normalizarse vía `parse_model_spec` (dispatch
por tipo) y luego `ProviderResolver().resolve(spec)` para canonicalizar el
alias del provider (p.ej. `"openai"` → `"openai_chat"`) antes de invocar
`factory.build`. El factory recibe SIEMPRE un `ModelExpandedSpec` con
provider ya canónico. NO DEBE existir una segunda ruta de parseo paralela
— `parse_model_spec` y `ProviderResolver` son los únicos puntos de
normalización (reutiliza slice #2).

#### Scenario: ref string se parsea y canonicaliza

- GIVEN una entrada `fallback_models=["openai:gpt-4o"]` (forma string, con
  alias de provider) y un `factory` que registra el `spec.provider` recibido
- WHEN se llama `build_fallback_chain(primary, factory)`
- THEN el factory fue invocado con un `ModelExpandedSpec` cuyo `provider`
  canónico es `"openai_chat"` (alias resuelto por `ProviderResolver`)
- AND la entrada resultante es la instancia construida por el factory

#### Scenario: ref dict expandido se parsea sin alias

- GIVEN una entrada `fallback_models=[{"provider": "google", "id":
  "gemini-2.5-pro"}]` y un `factory` que devuelve una instancia etiquetada
- WHEN se llama `build_fallback_chain(primary, factory)`
- THEN el factory fue invocado con `provider="google"` (sin aliasing) y la
  instancia de Gemini aparece en la cadena

### Requirement: build_fallback_chain rechaza refs {"alias": name} con NotImplementedError

Las refs de la forma `{"alias": "<nombre>"}` requieren un registro de
definiciones (`ModelsConfig.definitions`, TASK_013, NO shippeado todavía).
`build_fallback_chain` DEBE lanzar `NotImplementedError` al encontrar una
entrada `dict` cuya única clave relevante sea `"alias"`, con un mensaje que
indique que el registro de definiciones aún no está disponible. El slice #4
MANEJA únicamente refs inline (`str` o `{provider, id}`). Esto previene un
resolver a medio construir.

#### Scenario: alias-ref rechazado con NotImplementedError

- GIVEN una entrada `fallback_models=[{"alias": "fb-openai"}]` y un
  `ModelExpandedSpec` primario válido
- WHEN se llama `build_fallback_chain(primary, factory)`
- THEN se lanza `NotImplementedError`
- AND el mensaje menciona que el registro de definiciones no está shippeado

### Requirement: CacheKeyBuilder.build devuelve hex sha256 determinista

`CacheKeyBuilder.build(spec, messages, tool_hash, response_model_hash)`
DEBE devolver un string hex sha256 de 64 caracteres derivado de forma
canónica de: identidad del modelo (`provider` + `id`), parámetros de
generación relevantes (`temperature`, `top_p`, `top_k`), los `messages`
serializados de forma estable, `tool_hash` y `response_model_hash`. La
serialización SHALL usar `json.dumps(..., sort_keys=True,
separators=(",", ":"))`. La firma acepta los hashes de tools/response_model
precalculados por el caller (runtime) — `CacheKeyBuilder` NO calcula esos
hashes; sólo los incorpora al digest.

#### Scenario: mismo input produce mismo key

- GIVEN un `ModelExpandedSpec(provider="openai", id="gpt-4o",
  temperature=0.7)`, una lista `messages` fija, `tool_hash="t1"` y
  `response_model_hash="r1"`
- WHEN se llama `CacheKeyBuilder.build(spec, messages, "t1", "r1")` dos
  veces con inputs idénticos
- THEN ambas llamadas devuelven el mismo string hex de 64 caracteres

#### Scenario: temperatura distinta produce key distinto

- GIVEN dos `ModelExpandedSpec` idénticos salvo `temperature` (0.7 vs 0.9)
  y el resto de inputs idénticos
- WHEN se llama `CacheKeyBuilder.build` con cada spec
- THEN los dos keys resultantes son distintos

### Requirement: CacheKeyBuilder recibe hashes pre-computados del caller (ADR A4)

El caller DEBE suministrar `messages_hash`, `tool_defs_hash` y
`response_model_hash` como strings ya hasheados/serializados; el builder NO
serializa ni ordena la lista de mensajes. Esta decisión (design ADR A4)
evita scope-creep hacia los schemas de mensajes de Agno (yaml-agno no
redefine la forma de los mensajes). El stable-canonicalization de mensajes,
si se requiere, es responsabilidad del caller ANTES de pasar el hash.
NO es un cache store: el key es para dedup/observabilidad únicamente.

#### Scenario: mismo messages_hash + spec producen mismo key (determinismo)

- GIVEN un `spec` fijo y un mismo `messages_hash` "mh"
- WHEN se llama `CacheKeyBuilder.build(spec, messages_hash="mh")` dos veces
- THEN ambos keys son idénticos (determinismo del sha256)

#### Scenario: messages_hash distinto produce key distinto

- GIVEN un `spec` fijo
- WHEN se llama con `messages_hash="mh_a"` y luego `messages_hash="mh_b"`
- THEN los keys difieren (el hash de mensajes participa del digest)

### Requirement: FallbackErrorClassifier.classify mapea excepción a Literal de routing

`FallbackErrorClassifier.classify(exc: Exception)` DEBE devolver un
`Literal["rate_limit", "context_overflow", "error"]`. El mapeo SHALL ser:

- `ModelRateLimitError` (de `agno.exceptions`) → `"rate_limit"`
- `ContextWindowExceededError` (de `agno.exceptions`) → `"context_overflow"`
- Cualquier otra excepción → `"error"`

El resultado alimenta los campos `on_rate_limit` /
`on_context_overflow` / `on_error` de `FallbackConfig` (slice #2) en el
runtime DEFERido (SPEC_09).

#### Scenario: classify rate_limit desde ModelRateLimitError

- GIVEN una instancia de `ModelRateLimitError`
- WHEN se llama `FallbackErrorClassifier.classify(exc)`
- THEN devuelve `"rate_limit"`

#### Scenario: classify context_overflow

- GIVEN una instancia de `ContextWindowExceededError`
- WHEN se llama `FallbackErrorClassifier.classify(exc)`
- THEN devuelve `"context_overflow"`

#### Scenario: classify error genérico

- GIVEN una `ValueError` genérica (no Agno)
- WHEN se llama `FallbackErrorClassifier.classify(exc)`
- THEN devuelve `"error"`

### Requirement: FallbackErrorClassifier es un adaptador delgado sobre Agno, no reimplementación

`FallbackErrorClassifier` DELEGARÁ la inspepción de status_code/patrones a
la lógica existente de Agno (`ModelProviderError.classify` en
`agno/exceptions.py`). NO DEBE reimplementar la detección de 429/529 ni el
matcheo de `CONTEXT_WINDOW_PATTERNS`. Una subclase de
`ModelProviderError` que no sea `ModelRateLimitError` ni
`ContextWindowExceededError` SHALL enrutarse vía
`ModelProviderError.classify(exc)` y el resultado se mapea al Literal. La
importación de las excepciones es `from agno.exceptions import
ModelProviderError, ModelRateLimitError, ContextWindowExceededError`
(nombres verificados en `agno/exceptions.py`, estables desde 2.6.x).

#### Scenario: ModelProviderError genérico delega a Agno classify

- GIVEN una subclase de `ModelProviderError` (no RateLimit ni
  ContextWindow) cuya clasificación por Agno devuelve `ModelRateLimitError`
- WHEN se llama `FallbackErrorClassifier.classify(exc)`
- THEN devuelve `"rate_limit"` (mapeo del resultado de Agno)

### Requirement: Invariante — sin CircuitBreaker / RetryPolicy / call_with_fallback en este slice

El slice #4 NO DEBE introducir `CircuitBreaker`, `RetryPolicy`,
`compute_delay`, `call_with_fallback`, `dispatch_fallback_callback` ni
`probe_models_health`. Esos son propiedad de SPEC_05 (`RetryPolicy`,
step-level) y SPEC_09 (CircuitBreaker + runtime executor). El slice
construye la CADENA y los COMPONENTES de soporte, pero no la ejecuta. No
debe existir import de `CircuitBreaker` ni referencia a un loop de
ejecución con guardas de circuito.

#### Scenario: no-circuit-breaker invariant

- GIVEN el código fuente entregado por el slice #4
  (`fallback_chain.py`, `cache_key.py`, `fallback_classifier.py`)
- WHEN se inspeccionan los imports y el cuerpo de los tres módulos
- THEN no aparece `CircuitBreaker`, `call_with_fallback`, `RetryPolicy` ni
  `compute_delay`
- AND ningún módulo de producción fuera de `models/` importa estos tres
  componentes (cableamiento es un cambio coordinado posterior)
