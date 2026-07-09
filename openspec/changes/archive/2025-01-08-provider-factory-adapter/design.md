# Design: provider-factory-adapter (SPEC_14 slice #3)

> Diseño técnico del **slice #3** de SPEC_14: el `ProviderFactory` que traduce un
> `ModelExpandedSpec` (slice #2) en una instancia Agno `Model` viva, reusando
> `AgnoResolver` para la carga de clases y agregando composición de kwargs,
> resolución de secrets, cache de instancias y validación de capabilities.

## Technical Approach

**COMPOSE around `AgnoResolver`, NO reemplazarlo.** El `ProviderFactory` delega
la resolución de la clase nativa Agno a `AgnoResolver.resolve_class(module_path,
class_name)` (el punto de escape público en `agno_resolver.py:184-199`) y agrega
cuatro responsabilidades que el resolver no tiene:

1. `_compose_kwargs(spec, cls)` — arma el dict de kwargs filtrando
   dinámicamente contra `dataclasses.fields(cls)` (el `Model` Agno es un
   `@dataclass`, verificado base.py v2.6.22). Solo se forwardean los campos que
   la clase destino declara — evita `TypeError` al pasar `top_k` a `OpenAIChat`
   (que no lo tiene) o `reasoning_effort` a `Claude` (que no lo tiene).
2. Resolución del `api_key` vía un `SecretResolver` **síncrono inyectado** — el
   factory NO toca `os.environ` ni el `SecretManager` async de core-cenf.
3. `AgnoModelAdapter` — cache de instancias por alias (dict proceso-vida) +
   `invalidate()`.
4. `ModelCapabilitiesValidator` — validación **pure-data, config-time** contra
   `PROVIDER_REGISTRY[provider].capabilities` (DECLARED, no runtime-verificado).

El approach mapea 1:1 con los findings del exploration (#1986): factory SYNC,
secrets pre-resueltos por el bootstrap async, sin duplicar importlib/allowlist,
sin inventar nombres de retry (slice #2 ya expone los nombres nativos de Agno:
`retries, delay_between_retries, exponential_backoff, retry_with_guidance,
retry_with_guidance_limit`).

### Flujo de datos (build)

```
                    ┌─────────────────────────────────────────────────────┐
                    │  bootstrap (async, fuera de este slice)              │
                    │  await secret_manager.get_secret(env) -> cache dict  │
                    │  SecretResolver = lambda env: cache[env]   (SYNC)    │
                    └────────────────────────┬────────────────────────────┘
                                             │ inyectado
                                             ▼
  ModelExpandedSpec ──► ProviderFactory.build(spec)
                             │
                             ├─ 1. PROVIDER_REGISTRY[spec.provider] -> entry
                             │     (module_path, class_name, api_key_env, caps)
                             │
                             ├─ 2. resolver.resolve_class(module_path, class_name) -> cls
                             │     (delegado a AgnoResolver; allowlist + cache reusados)
                             │
                             ├─ 3. _compose_kwargs(spec, cls)
                             │     ├─ dataclasses.fields(cls) -> allowed field names
                             │     ├─ spec.model_dump(exclude_none=True) -> candidate kwargs
                             │     ├─ filter: keep only candidates in allowed set
                             │     └─ drop id (se pasa posicional), drop fallback (schema-only)
                             │
                             ├─ 4. if entry.api_key_env: kwargs["api_key"] = secret_resolver(env)
                             │
                             ├─ 5. (opt) ModelCapabilitiesValidator.validate(spec, caps)
                             │
                             └─ 6. return cls(id=spec.id, **kwargs)   <- instancia Agno Model
                                             │
                                             ▼
                              AgnoModelAdapter.get_or_build(alias, builder)
                                             │
                                             ▼
                                  cache[alias] (dict, proceso-vida)
```

## Architecture Decisions

### Decision A1: COMPOSE around AgnoResolver (delegate resolve_class)

- **Choice**: `ProviderFactory.__init__(self, resolver: AgnoResolver,
  secret_resolver: SecretResolver)`; `build()` llama a
  `self._resolver.resolve_class(module_path, class_name)` para obtener la clase.
- **Alternatives considered**:
  - Reemplazar `AgnoResolver.resolve_model` con el factory — rompe los tests de
    slices 1-2 (`test_agno_resolver.py`) que dependen del path
    `"provider:id" -> cls(id=model_id)` minimal.
  - Duplicar importlib+allowlist dentro del factory — viola SSOT, duplica el
    motor de carga, rompe el test path con `InMemoryDependencyAdapter`.
  - Llamar `resolve_model` y re-instanciar — `resolve_model` YA instancia
    `cls(id=model_id)` sin kwargs; habría que descartar la instancia.
- **Rationale**: `resolve_class` (línea 184-199) es el punto de escape público
  explícito del `AgnoResolver` — delega al adapter respetando allowlist + cache.
  Reusarlo da SSOT de carga de clases, reusa el `InMemoryDependencyAdapter` en
  tests, y deja `resolve_model` intacto como path "instantiate by string". El
  factory es una capa *alrededor* del resolver, no una vía paralela.

### Decision A2: Factory SYNC + SecretResolver SYNC inyectado

- **Choice**: `build()` es síncrono. Recibe `api_key` ya resuelto vía un
  `SecretResolver = Callable[[str], str | None]` SYNC inyectado en el
  constructor. El boundary async vive en el bootstrap (que llama
  `await secret_manager.get_secret()` una vez por provider y arma un dict cache).
- **Alternatives considered**:
  - `build()` async llamando `SecretManager.get_secret()` — los constructores
    Agno son SYNC (`@dataclass`), `async` no aporta; además rompe el paralelismo
    con `AgnoResolver` (sync) y complica el `TaskGroup` del bootstrap.
  - `os.environ[env]` directo — viola la `@ai-directive` de SPEC_00 §9.3 ("no
    accedas a os.environ") y decision #7 (secrets fuera de env vars).
  - `ConfigManager.get_string(env)` como única fuente — muy rígido para
    rotation/KMS futuros (SPEC_23 §2.9).
- **Rationale**: Los constructores Agno son SYNC y resuelven el cliente HTTP
  *lazily* al primer request (`openai/chat.py` `_get_client_params`), así que el
  `api_key` puede pasarse al constructor sin bloqueo. Inyectar un callable SYNC
  desacopla el factory del `SecretManager` async (whose ports.py aún no se
  entrega — SPEC_23): el bootstrap adapta async→sync pre-resolviendo. Fail-fast:
  un secret faltante explota en boot, no en el primer request.

### Decision A3: _compose_kwargs filtra dinámicamente con dataclasses.fields

- **Choice**: `_compose_kwargs(spec, cls)` hace
  `allowed = {f.name for f in dataclasses.fields(cls)}` y retiene solo los
  candidatos de `spec.model_dump(exclude_none=True)` cuyo nombre está en
  `allowed`. El `Model` Agno es un `@dataclass` (base.py v2.6.22 verificado), así
  que `dataclasses.fields` es el SSOT de los parámetros aceptados por cada
  subclase concreta (`OpenAIChat`, `Claude`, etc.).
- **Alternatives considered**:
  - Forwardear ciegamente todos los kwargs y dejar que el proveedor raise
    `TypeError` — fail-loud pero ruidoso; el error llega al usuario sin contexto
    de qué campo es provider-specific.
  - Mapeo estático hardcoded por provider — frágil: Agno puede cambiar firmas
    entre minors; maintenance burden de 27 entradas.
  - Gate por `PROVIDER_REGISTRY.capabilities` en vez de por firma — caps dicen
    *intención* (streaming, caching), no *firma*; `top_k` no es una capability.
- **Rationale**: El exploration (#1986) verificó que `top_k`, `stop_sequences`,
  `reasoning_effort`, `thinking` NO son universales: `OpenAIChat` no tiene
  `top_k` ni `thinking`; `Claude` no tiene `reasoning_effort` y su `thinking` es
  `Dict[str, Any]` (no `bool`). Filtrar por `dataclasses.fields(cls)` es
  robusto frente a la divergencia de firmas entre los 27 providers y sobrevive
  upgrades de Agno sin tocar yaml-agno. Los campos no aplicables (e.g.
  `top_k` en OpenAI) se caen silenciosamente del dict — el usuario los pidió, el
  provider no los acepta, no hay error; esto es el comportamiento menos
  sorprendente para overrides provider-specific. El nombre `thinking` (bool en
  spec, Dict en Claude) se cae por mismatch de tipo implícito al no forwardearse
  si el usuario lo setea para un provider no-razonante — documentado en Open
  Questions.

### Decision A4: Cache de instancias por alias + invalidate()

- **Choice**: `AgnoModelAdapter` guarda la instancia Agno `Model` en un
  `dict[str, Any]` indexado por `alias or f"{provider}:{id}"`. `get_or_build(alias,
  builder)` retorna la cacheada o llama `builder()` una vez. `invalidate(alias=None)`
  limpia una entrada o todo el cache. No hay TTL en este slice.
- **Alternatives considered**:
  - Sin cache (re-build por request) — re-importa y re-instancia en cada call;
    desperdicia el cache de `ImportlibDependencyAdapter` (que cachea la *clase*,
    no la *instancia*).
  - `functools.lru_cache` — no permite `invalidate` selectivo ni keys dinámicas.
  - WeakValueDictionary — las instancias Model pueden GC-arse bajo presión;
    rompe la promesa de cache de proceso.
- **Rationale**: SPEC_14 §11.3 pide cache por `alias`. El `Model` Agno construye
  su cliente HTTP *lazily*, así que cachear la instancia es barato y reusarla
  entre agentes comparte el pool de conexiones. `invalidate()` es el hook para
  rotation/audit (SPEC_23 §2.9, slice posterior). Sin TTL: la rotation es
  explícita vía `invalidate` + rebuild, no time-based.

### Decision A5: ConfigSecretResolver default via ConfigManager.get_string

- **Choice**: `ConfigSecretResolver(config: ConfigManager)` implementa el
  Protocol `SecretResolver` leyendo
  `config.get_string(f"secrets.{env.lower()}", default_value=None)`. Es el MVP
  default; el production wiring (SPEC_23) reemplaza este resolver por uno que
  adapta el `SecretManager` async.
- **Alternatives considered**:
  - Definir el resolver inline en el factory — acopla el factory a ConfigManager.
  - Heredar del `SecretManager` Protocol de core — SPEC_23 no está entregado; el
    Protocol async no encaja en un factory sync.
- **Rationale**: SPEC_00 §9.3 prohíbe `os.environ` directo; `ConfigManager` es el
  port mandado. El namespace `secrets.*` es una convención plana y predecible
  (`secrets.openai_api_key`), evita colisión con `dependency.*`, `model.*`. El
  resolver es intercambiable: el bootstrap async puede inyectar un
  `lambda env: pre_resolved_cache[env]` y el factory no cambia.

### Decision A6: ModelCapabilitiesValidator = pure-data, config-time

- **Choice**: `ModelCapabilitiesValidator.validate(spec, capabilities) ->
  list[str]` devuelve una lista de errores (vacía = OK). Lee
  `PROVIDER_REGISTRY[provider].capabilities` (DECLARED, no runtime-verificado per
  provider_capabilities.py docstring). Reglas: `reasoning_effort/thinking` set
  requiere `capabilities.reasoning`; no toca clases Agno.
- **Alternatives considered**:
  - Validar runtime tras instanciar — las caps son declarativas; la prueba real
    es contra una API viva (integration test, otro slice).
  - Raise en vez de devolver lista — el caller (factory) decide si es hard-error
    o warning; devolver lista es más flexible.
- **Rationale**: Las capabilities en `provider_capabilities.py` son DATA
  declarada; el validator solo confirma que la *intención* del spec (reasoning,
  caching) está soportada por la *declaración* del provider. Slice #3 lo invoca
  opcionalmente desde `build()` como warning pre-check (ver Open Questions: si
  es hard-error o warning se decide en tasks).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/di/secret_resolver.py` | Create | Protocol `SecretResolver` (SYNC Callable) + `ConfigSecretResolver(config)` default impl. |
| `src/yaml_agno/di/provider_factory.py` | Create | `ProviderFactory(resolver, secret_resolver)`; `build(ModelExpandedSpec) -> Any`; `_compose_kwargs(spec, cls)`; `ModelConstructionError`. |
| `src/yaml_agno/di/agno_model_adapter.py` | Create | `AgnoModelAdapter` cache dict por alias + `invalidate()`. |
| `src/yaml_agno/di/capabilities_validator.py` | Create | `ModelCapabilitiesValidator` pure-data (lee PROVIDER_REGISTRY caps). |
| `src/yaml_agno/di/__init__.py` | Modify | Re-export `ProviderFactory`, `AgnoModelAdapter`, `SecretResolver`, `ConfigSecretResolver`, `ModelCapabilitiesValidator`. |

## Interfaces / Contracts — LITERAL CODE

### `src/yaml_agno/di/secret_resolver.py`

```python
"""SecretResolver — port SYNC para resolución de API keys (SPEC_14 slice #3).

El ProviderFactory es síncrono (los constructores Agno Model son @dataclass
SYNC). core-cenf SecretManager.get_secret() es async (SPEC_23 §2.4, aún no
entregado). Para evitar acoplar el factory al boundary async, definimos un
Protocol SYNC local: el bootstrap (async) pre-resuelve los secrets una vez por
provider y entrega al factory un callable SYNC (lambda sobre un dict cache).

El default ConfigSecretResolver lee ``config.get_string("secrets.<env>")`` —
NO toca os.environ (SPEC_00 §9.3 @ai-directive). El production wiring (SPEC_23)
reemplaza este resolver por un adaptador async->sync sobre SecretManager.

@ai-directive: NO uses os.environ. NO hagas este resolver async. El factory
    es SYNC por A2.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core_infrastructure.config.ports import ConfigManager

__all__ = ["ConfigSecretResolver", "SecretResolver"]


@runtime_checkable
class SecretResolver(Protocol):
    """Callable SYNC que resuelve un nombre de env-var a su valor de API key.

    Es el contrato que ProviderFactory.consume. NO es el SecretManager async de
    core-cenf — es la adapter SYNC que el bootstrap construye tras pre-resolver.

    Calling convention:
        resolver("OPENAI_API_KEY") -> "sk-..."  |  None  (si no hay secret)
    """

    def __call__(self, env_name: str) -> str | None:
        """Return the secret value for ``env_name``, or None if not configured.

        Args:
            env_name: Logical env-var name (e.g. ``"OPENAI_API_KEY"``). Matches
                ``ProviderRegistryEntry.api_key_env``.

        Returns:
            The secret string, or None if the secret is not configured (e.g.
            local providers like ollama that have ``api_key_env=None`` never
            reach the resolver at all).
        """
        ...


class ConfigSecretResolver:
    """Default SecretResolver backed by ``ConfigManager.get_string``.

    Reads ``secrets.<env_name_lower>`` from the config namespace. ``env_name`` is
    lowercased to match typical YAML key conventions (``secrets.openai_api_key``).

    Attributes:
        _config: ConfigManager port (never os.environ).

    Example:
        >>> resolver = ConfigSecretResolver(config)
        >>> resolver("OPENAI_API_KEY")  # reads config["secrets.openai_api_key"]
        'sk-...'
    """

    def __init__(self, config: ConfigManager) -> None:
        """Initialize the resolver with a ConfigManager.

        Args:
            config: ConfigManager port. MUST expose ``secrets.*`` keys for the
                providers the app uses.
        """
        self._config = config

    def __call__(self, env_name: str) -> str | None:
        """Resolve ``env_name`` to its secret via ``config.get_string``.

        Args:
            env_name: Logical env-var name (e.g. ``"OPENAI_API_KEY"``).

        Returns:
            The secret string, or None if the key is absent from the config.
        """
        key = f"secrets.{env_name.lower()}"
        return self._config.get_string(key, default_value=None)
```

### `src/yaml_agno/di/provider_factory.py`

```python
"""ProviderFactory — traduce ModelExpandedSpec en instancia Agno Model (SPEC_14 #3).

COMPOSE alrededor de AgnoResolver (A1): delega la carga de la clase nativa a
``resolver.resolve_class(module_path, class_name)`` (el punto de escape público
en agno_resolver.py:184-199) y AGREGA:

  1. ``_compose_kwargs(spec, cls)`` — filtra dinámicamente contra
     ``dataclasses.fields(cls)`` para forwardear solo los campos que la clase
     destino declara (A3). Evita TypeError al pasar ``top_k`` a OpenAIChat.
  2. Resolución del ``api_key`` vía un ``SecretResolver`` SYNC inyectado (A2) —
     el factory NO toca os.environ ni el SecretManager async.
  3. (Opcional) ``ModelCapabilitiesValidator`` pre-check contra caps declaradas.

El factory es SYNC (A2): los constructores Agno Model son @dataclass SYNC y
resuelven el cliente HTTP lazily, así que el api_key puede pasarse al
constructor sin bloqueo.

@ai-directive: NO uses os.environ. NO reimplementes importlib/allowlist —
    delega a AgnoResolver.resolve_class. NO inventes nombres de retry (slice #2
    ya expone los Agno-native: retries, delay_between_retries, etc.).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from yaml_agno.di.agno_resolver import AgnoResolver
from yaml_agno.di.provider_capabilities import PROVIDER_REGISTRY
from yaml_agno.di.secret_resolver import SecretResolver
from yaml_agno.models.model_spec import ModelExpandedSpec

__all__ = ["ModelConstructionError", "ProviderFactory"]


class ModelConstructionError(Exception):
    """Raised when a provider class cannot be instantiated from a spec.

    Wraps the underlying TypeError/ValueError from the Agno constructor with
    context about which provider and model id failed, so the caller (bootstrap
    or config-load) can surface a clear error instead of a raw Agno traceback.
    """

    def __init__(self, provider: str, model_id: str, cause: Exception) -> None:
        """Initialize with provider/id context and the wrapped cause.

        Args:
            provider: Provider id (e.g. ``"openai_chat"``).
            model_id: Model id (e.g. ``"gpt-4o"``).
            cause: The underlying exception from the constructor.
        """
        self.provider = provider
        self.model_id = model_id
        self.cause = cause
        super().__init__(
            f"Failed to construct Agno Model for provider={provider!r} "
            f"id={model_id!r}: {type(cause).__name__}: {cause}"
        )


class ProviderFactory:
    """Builds Agno Model instances from ModelExpandedSpec (SPEC_14 slice #3).

    Delegates class resolution to ``AgnoResolver.resolve_class`` (A1) and adds
    kwargs composition, secret resolution, and (optional) capability validation.
    Sync by design (A2): matches Agno's @dataclass Model constructors.

    Attributes:
        _resolver: AgnoResolver (class-loading + allowlist).
        _secret_resolver: SYNC SecretResolver for api_key.
        _validate_capabilities: When True, run ModelCapabilitiesValidator before
            constructing and raise on declared-cap mismatch.

    Example:
        >>> factory = ProviderFactory(resolver, secret_resolver)
        >>> spec = ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.7)
        >>> model = factory.build(spec)
        >>> model.id
        'gpt-4o'
    """

    def __init__(
        self,
        resolver: AgnoResolver,
        secret_resolver: SecretResolver,
        *,
        validate_capabilities: bool = False,
    ) -> None:
        """Initialize the factory with its two injected dependencies.

        Args:
            resolver: AgnoResolver — provides ``resolve_class(module, name)``.
            secret_resolver: SYNC SecretResolver (A2). The bootstrap pre-resolves
                secrets async and hands a sync callable here.
            validate_capabilities: When True, ``build`` runs the pure-data
                ModelCapabilitiesValidator and raises if the spec asks for a
                capability the provider does not declare. Default False (warning
                path); enable for strict config-load validation.
        """
        self._resolver = resolver
        self._secret_resolver = secret_resolver
        self._validate_capabilities = validate_capabilities

    def build(self, spec: ModelExpandedSpec) -> Any:
        """Construct an Agno Model instance from ``spec``.

        Pipeline (see design data-flow diagram):
          1. Look up PROVIDER_REGISTRY[spec.provider] -> entry.
          2. Resolve the class via ``resolver.resolve_class``.
          3. Compose kwargs (filtered against the resolved class's dataclass
             fields).
          4. If ``entry.api_key_env`` is set, resolve it via secret_resolver and
             inject as ``api_key``.
          5. (Optional) capability pre-check.
          6. Instantiate ``cls(id=spec.id, **kwargs)``.

        Args:
            spec: A validated ModelExpandedSpec (slice #2). ``spec.provider``
                MUST be a canonical PROVIDER_REGISTRY key (apply
                ProviderResolver first if the spec may carry an alias).

        Returns:
            An Agno Model INSTANCE (e.g. ``OpenAIChat(id="gpt-4o", ...)``).

        Raises:
            KeyError: If ``spec.provider`` is not in PROVIDER_REGISTRY.
            ModelConstructionError: If the Agno constructor raises (wrapped).
        """
        if spec.provider not in PROVIDER_REGISTRY:
            raise KeyError(f"Unknown provider: {spec.provider!r}")

        entry = PROVIDER_REGISTRY[spec.provider]
        cls = self._resolver.resolve_class(entry.module_path, entry.class_name)
        kwargs = self._compose_kwargs(spec, cls)

        # Secret resolution (A2): local providers (ollama, llamacpp, ...) have
        # api_key_env=None and never reach the resolver. Cloud/gateway providers
        # get their key injected as api_key= kwarg (filtered in step 3 only if
        # the class declares it — all cloud Agno Models do).
        if entry.api_key_env is not None:
            api_key = self._secret_resolver(entry.api_key_env)
            if api_key is not None:
                kwargs["api_key"] = api_key

        # Optional capability pre-check (A6). Imported lazily to avoid a circular
        # import (capabilities_validator imports PROVIDER_REGISTRY too, which is
        # fine, but lazy keeps the module-import graph acyclic under strict TDD).
        if self._validate_capabilities:
            from yaml_agno.di.capabilities_validator import ModelCapabilitiesValidator

            errors = ModelCapabilitiesValidator.validate(spec, entry.capabilities)
            if errors:
                raise ModelConstructionError(
                    spec.provider,
                    spec.id,
                    ValueError(f"capability mismatches: {errors}"),
                )

        try:
            return cls(id=spec.id, **kwargs)
        except (TypeError, ValueError) as exc:
            raise ModelConstructionError(spec.provider, spec.id, exc) from exc

    def _compose_kwargs(self, spec: ModelExpandedSpec, cls: type) -> dict[str, Any]:
        """Build the constructor kwargs dict, filtered against ``cls`` fields.

        Agno Model is a @dataclass (base.py v2.6.22). ``dataclasses.fields(cls)``
        returns the exact set of constructor parameters the concrete subclass
        accepts. We dump the spec (excluding None and the positional `id`) and
        keep only the keys present in that set. This silently drops
        provider-specific fields the target class does not declare — e.g.
        ``top_k`` when building OpenAIChat, ``reasoning_effort`` when building
        Claude (A3).

        Args:
            spec: The validated ModelExpandedSpec.
            cls: The resolved Agno Model subclass (a @dataclass).

        Returns:
            Dict of constructor kwargs safe to splat as ``cls(id=..., **kwargs)``.

        Raises:
            TypeError: If ``cls`` is not a dataclass (defensive — all Agno Models
                are dataclasses; surfaces a non-Agno class slipped into the
                registry). Re-raised as ModelConstructionError by the caller.
        """
        # ``id`` is passed positionally by build(); never include it in kwargs.
        # ``fallback`` is schema-only (slice #4 runtime); never forward it.
        # ``provider`` is a yaml-agno routing key, not an Agno constructor arg.
        excluded: set[str] = {"id", "fallback", "provider"}
        candidates = spec.model_dump(exclude_none=True, exclude=excluded)

        # Defensive: confirm cls is a dataclass before introspecting. If a
        # non-dataclass slips into PROVIDER_REGISTRY, raise explicitly rather
        # than letting dataclasses.fields emit an opaque TypeError.
        if not dataclasses.is_dataclass(cls):
            raise TypeError(
                f"Cannot compose kwargs: {cls.__name__!r} is not a dataclass. "
                f"PROVIDER_REGISTRY entries MUST point at Agno Model subclasses."
            )

        allowed = {f.name for f in dataclasses.fields(cls)}
        return {key: value for key, value in candidates.items() if key in allowed}
```

### `src/yaml_agno/di/agno_model_adapter.py`

```python
"""AgnoModelAdapter — cache de instancias Agno Model por alias (SPEC_14 #3, A4).

Cache simple (dict proceso-vida) que guarda la instancia Agno Model ya
construida indexada por ``alias or f"{provider}:{id}"``. Reusar la instancia
entre agentes comparte el pool de conexiones HTTP que el Model construye
lazily. ``invalidate()`` es el hook para rotation/audit (SPEC_23 §2.9, slice
posterior) — sin TTL en este slice.

@ai-directive: NO agregues TTL aquí. La rotation es EXPLICITA via invalidate().
    El builder siempre se llama a través de get_or_build para mantener una sola
    via de entrada al cache.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["AgnoModelAdapter"]


class AgnoModelAdapter:
    """Process-lifetime cache of Agno Model instances, keyed by alias.

    Attributes:
        _cache: Dict ``alias -> Agno Model instance``.

    Example:
        >>> adapter = AgnoModelAdapter()
        >>> model = adapter.get_or_build("openai_chat:gpt-4o", lambda: factory.build(spec))
        >>> same = adapter.get_or_build("openai_chat:gpt-4o", lambda: factory.build(spec))
        >>> model is same
        True
    """

    def __init__(self) -> None:
        """Initialize an empty cache."""
        self._cache: dict[str, Any] = {}

    def get_or_build(self, alias: str, builder: Callable[[], Any]) -> Any:
        """Return the cached instance for ``alias``, or build+cache it.

        ``builder`` is invoked at most once per alias for the lifetime of the
        adapter (unless invalidated). This guarantees a single Agno Model
        instance per alias — sharing its lazy HTTP client across consumers.

        Args:
            alias: Cache key. Convention: ``f"{provider}:{id}"`` or a user-set
                alias from the spec.
            builder: Zero-arg callable that constructs the instance (typically
                ``lambda: factory.build(spec)``). Called ONLY on cache miss.

        Returns:
            The cached or freshly-built Agno Model instance.
        """
        if alias not in self._cache:
            self._cache[alias] = builder()
        return self._cache[alias]

    def invalidate(self, alias: str | None = None) -> None:
        """Drop one entry (``alias`` set) or the whole cache (``alias=None``).

        Used by the future secret-rotation path (SPEC_23 §2.9): after rotating a
        key, call ``invalidate("openai_chat:gpt-4o")`` so the next
        ``get_or_build`` rebuilds with the new secret.

        Args:
            alias: Specific alias to drop, or None to clear the entire cache.
        """
        if alias is None:
            self._cache.clear()
        else:
            self._cache.pop(alias, None)

    def __len__(self) -> int:
        """Return the number of cached entries (useful for tests/diagnostics)."""
        return len(self._cache)

    def __contains__(self, alias: str) -> bool:
        """Return True if ``alias`` is cached."""
        return alias in self._cache
```

### `src/yaml_agno/di/capabilities_validator.py`

```python
"""ModelCapabilitiesValidator — validación pure-data, config-time (SPEC_14 #3, A6).

Lee ``PROVIDER_REGISTRY[provider].capabilities`` (DECLARED, no runtime-verificado
— ver provider_capabilities.py docstring) y confirma que la *intención* del
ModelExpandedSpec (reasoning, caching) está soportada por la *declaración* del
provider. NO toca clases Agno. NO hace calls de red.

Reglas (slice #3):
  - ``spec.reasoning_effort`` o ``spec.thinking`` seteados requieren
    ``capabilities.reasoning == True``.
  - ``spec.cache_response`` o ``spec.cache_ttl`` o ``spec.cache_dir`` seteados
    requieren ``capabilities.caching == True``.

El validator devuelve ``list[str]`` de errores (vacía = OK). El caller decide
si es hard-error (ProviderFactory con ``validate_capabilities=True``) o warning.

@ai-directive: Las capabilities son DECLARED, NOT RUNTIME-VERIFIED. Este
    validator confirma intención vs declaración, NO garantiza que la API viva
    lo acepte.
"""

from __future__ import annotations

from yaml_agno.di.provider_capabilities import ProviderCapabilities
from yaml_agno.models.model_spec import ModelExpandedSpec

__all__ = ["ModelCapabilitiesValidator"]


class ModelCapabilitiesValidator:
    """Pure-data validator of ModelExpandedSpec intent vs declared capabilities.

    Stateless. Every method is a classmethod that reads the spec + the declared
    ProviderCapabilities and returns a list of human-readable error strings.

    Example:
        >>> errors = ModelCapabilitiesValidator.validate(spec, caps)
        >>> if errors:
        ...     raise ValueError(errors)
    """

    @staticmethod
    def validate(spec: ModelExpandedSpec, capabilities: ProviderCapabilities) -> list[str]:
        """Run all declared-capability checks and return the accumulated errors.

        Args:
            spec: The model spec expressing intent.
            capabilities: The declared ProviderCapabilities for the provider.

        Returns:
            List of error strings. Empty list means the spec's intent is fully
            covered by the provider's declared capabilities.
        """
        errors: list[str] = []
        errors.extend(ModelCapabilitiesValidator._check_reasoning(spec, capabilities))
        errors.extend(ModelCapabilitiesValidator._check_caching(spec, capabilities))
        return errors

    @staticmethod
    def _check_reasoning(
        spec: ModelExpandedSpec, capabilities: ProviderCapabilities
    ) -> list[str]:
        """Reasoning intent (reasoning_effort/thinking) requires declared reasoning.

        Args:
            spec: The model spec.
            capabilities: Declared capabilities.

        Returns:
            Error list (empty if OK or if no reasoning intent was expressed).
        """
        if (spec.reasoning_effort is not None or spec.thinking is not None) and not capabilities.reasoning:
            return [
                f"Provider declares reasoning=False but spec sets "
                f"reasoning_effort={spec.reasoning_effort!r} or thinking={spec.thinking!r}."
            ]
        return []

    @staticmethod
    def _check_caching(
        spec: ModelExpandedSpec, capabilities: ProviderCapabilities
    ) -> list[str]:
        """Caching intent (cache_response/cache_ttl/cache_dir) requires declared caching.

        Args:
            spec: The model spec.
            capabilities: Declared capabilities.

        Returns:
            Error list (empty if OK or if no caching intent was expressed).
        """
        caching_intent = (
            spec.cache_response is not None
            or spec.cache_ttl is not None
            or spec.cache_dir is not None
        )
        if caching_intent and not capabilities.caching:
            return [
                f"Provider declares caching=False but spec sets cache_response="
                f"{spec.cache_response!r}, cache_ttl={spec.cache_ttl!r}, or "
                f"cache_dir={spec.cache_dir!r}."
            ]
        return []
```

### `src/yaml_agno/di/__init__.py` (modified — re-export additions)

The existing `__init__.py` (47 lines) is extended with five new re-exports.
Additions appended to the existing imports and `__all__`:

```python
# --- Existing imports unchanged (AgnoResolver, build_agno_resolver, etc.) ---
# Add after the existing agno_resolver import:
from yaml_agno.di.agno_model_adapter import AgnoModelAdapter
from yaml_agno.di.capabilities_validator import ModelCapabilitiesValidator
from yaml_agno.di.provider_factory import ModelConstructionError, ProviderFactory
from yaml_agno.di.secret_resolver import ConfigSecretResolver, SecretResolver

# --- __all__ additions (append to the existing list) ---
__all__ = [
    # ... existing entries unchanged ...
    "AgnoModelAdapter",
    "ConfigSecretResolver",
    "ModelCapabilitiesValidator",
    "ModelConstructionError",
    "ProviderFactory",
    "SecretResolver",
]
```

## Testing Strategy

Strict TDD project (`rules.apply.tdd: true`, `tdd: true` in config.yaml). Every
behavior ships RED first. Coverage target 100%.

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `_compose_kwargs` filters against dataclass fields | Stub `@dataclass` with a subset of fields (e.g. `temperature`, `max_tokens` but NO `top_k`); assert `top_k` is dropped, `temperature` passes. Use real `dataclasses.fields` on the stub. |
| Unit | `ProviderFactory.build` golden path | `InMemoryDependencyAdapter` (core-cenf double) + stub `OpenAIChat` dataclass; `ModelExpandedSpec(provider="openai_chat", id="gpt-4o", temperature=0.7)` -> instance with `id="gpt-4o"`, `temperature=0.7`. |
| Unit | api_key injection | Stub entry with `api_key_env="OPENAI_API_KEY"`; inject a `lambda env: "sk-test"` SecretResolver; assert instance received `api_key="sk-test"`. |
| Unit | Local provider skips secret resolver | `api_key_env=None` provider (ollama); assert SecretResolver NEVER called (use a callable that raises if invoked). |
| Unit | `ModelConstructionError` wraps constructor TypeError | Stub class whose `__init__` raises; assert `build` raises `ModelConstructionError` with provider/id context. |
| Unit | Unknown provider raises KeyError | `spec.provider="banana"` -> KeyError. |
| Unit | `AgnoModelAdapter.get_or_build` caches | Two calls same alias -> builder invoked once; same instance returned. |
| Unit | `AgnoModelAdapter.invalidate(alias)` + `invalidate(None)` | Selective + full clear; `__len__`/`__contains__` assertions. |
| Unit | `ModelCapabilitiesValidator.validate` | Reasoning intent on non-reasoning provider -> error; caching intent on non-caching provider -> error; no intent -> empty list. |
| Unit | `ConfigSecretResolver.__call__` | Stub ConfigManager; assert reads `secrets.<env_lower>`; returns None on missing. |
| Unit | capabilities_validator is pure-data | No Agno import; only reads ProviderCapabilities dataclass. |
| Integration | Real OpenAIChat instantiation | Real `ImportlibDependencyAdapter` + seeded allowlist + real `agno.models.openai.OpenAIChat`; build from spec; assert `isinstance(result, Model)` and `id` set. (Mirrors `test_resolve_model_integration_real_openai_chat_is_model_instance`.) |

### TDD ordering (RED-GREEN-REFACTOR per behavior)

1. `secret_resolver.py` — RED: `test_config_secret_resolver_reads_secrets_namespace`.
2. `provider_factory.py` — RED: `test_build_openai_forwards_filtered_kwargs`.
3. `provider_factory.py` — RED: `test_build_injects_api_key_when_entry_has_env`.
4. `provider_factory.py` — RED: `test_build_local_provider_skips_secret_resolver`.
5. `provider_factory.py` — RED: `test_build_wraps_constructor_error`.
6. `provider_factory.py` — RED: `test_compose_kwargs_drops_provider_specific_unsupported_fields`.
7. `agno_model_adapter.py` — RED: `test_get_or_build_caches_instance`.
8. `agno_model_adapter.py` — RED: `test_invalidate_selective_and_full`.
9. `capabilities_validator.py` — RED: `test_validate_reasoning_intent_on_non_reasoning_provider`.
10. `capabilities_validator.py` — RED: `test_validate_caching_intent_on_non_caching_provider`.
11. Integration RED: `test_build_integration_real_openai_chat_is_model_instance`.

## Migration / Rollout

No migration required. Slice #3 is **additive**: five new files under
`src/yaml_agno/di/`, one modified `__init__.py`. No existing module imports the
new code yet — wiring `ProviderFactory` into `AgentConfig`/`AgentFactory` is a
later coordinated change (SPEC_02 evolution, slice #5+). Slices 1-2
(`AgnoResolver.resolve_model`, `ModelExpandedSpec`) are untouched.

**Rollback**: delete the five files, revert the `__init__.py` additions. No
data, no config schema, no public API consumed downstream. Zero blast radius.

**Verification** (per `rules.verify`):
- `python -m pytest` — all unit + the one integration test GREEN.
- `ruff check src/yaml_agno/di/ tests/unit/di/` — clean.
- `mypy src/yaml_agno/di/` — clean under `strict = true`.
- Coverage target 100% on the five new files.

## Open Questions

- [ ] **`thinking` type mismatch**: `ModelExpandedSpec.thinking` is `bool | None`
      but `Claude.thinking` is `Dict[str, Any]`. Dynamic filtering by field NAME
      passes it through, but the type is wrong → Claude constructor may reject.
      Options: (a) coerce in a provider-specific shim (deferred), (b) drop
      `thinking` from universal forwarding and document `provider_kwargs` as the
      escape hatch (needs adding `provider_kwargs` to spec — slice #2 dropped it).
      Recommend (b) for slice #3: exclude `thinking` from `_compose_kwargs` and
      document. Decision deferred to tasks phase.
- [ ] **`stop_sequences` vs `stop` naming**: OpenAI uses `stop`, Claude uses
      `stop_sequences`. Filtering by name drops `stop_sequences` on OpenAI
      silently. Acceptable for slice #3 (no rename layer); document. Per-provider
      rename is a later enhancement.
- [ ] **capabilities validator as hard-error vs warning**: The factory exposes
      `validate_capabilities: bool` (default False). Whether the bootstrap wiring
      turns it on (strict config-load) is a tasks-phase decision tied to
      SPEC_02 config validation strategy.
- [ ] **Async builder variant**: SPEC_00 conventions say "sync AND async
      variants for public methods". `build()` is sync by A2. An async variant is
      NOT needed here because the async boundary is the SecretResolver (pre-
      resolved by bootstrap), not the construction itself. Documented as a
      deliberate deviation.
