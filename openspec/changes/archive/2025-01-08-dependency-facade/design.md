---
change: dependency-facade
spec: SPEC_01
status: designed
artifact_store: hybrid
depends_on:
  - openspec/specs/agent-config-schema         # SPEC_02 (shipped, DIReference)
  - openspec/specs/agent-factory-basic          # SPEC_01 slice #1 (shipped)
  - core_infrastructure.dependency              # ImportlibDependencyAdapter + InMemoryDependencyAdapter
  - core_infrastructure.config                  # ConfigManager Protocol + adapters
  - core_infrastructure.logger                  # LoggerManager Protocol + StructlogAdapter
  - core_infrastructure.errors                  # ErrorHandlingManager Protocol + ClassificationAdapter
  - core_infrastructure.observability           # ObservabilityManager Protocol + NoopObservabilityAdapter
---

# Design: Dependency Facade + ValueResolver

## Technical Approach

Dos abstracciones **separadas** que core-cenf no provee, construidas **sobre** el
motor de carga de clases importado:

1. **`AgnoResolver`** — fachada de dominio Agno. Envuelve un
   `ImportlibDependencyAdapter` (IMPORTADO, no reescrito). Expone 4 métodos de
   dominio (`resolve_model`, `build_db`, `resolve_workflow_primitive`,
   `resolve_class`) que traducen *claves de dominio* (`"openai"`, `"memory"`,
   `"Condition"`) a clases nativas Agno consultando registros declarativos
   (`MODEL_REGISTRY`, `STORAGE_REGISTRY`) y delegando el `importlib` real al
   adapter.
2. **`ValueResolver`** — traduce la sintaxis propia `${provider.key}` (validada
   por `DIReference`, SPEC_02) al diccionario `resolved_values` que
   `DIReference.resolve(resolved_values)` consume. MVP `env.*` vía
   `ConfigManager.get_string()`.

El ensamblaje de los 3 managers transversales de core-cenf (Config → Logger →
Errors → Dependency, grafo documentado en `bootstrap.py`) vive en una fábrica
**propia** `build_agno_resolver()` — yaml-agno no duplica `BootstrapOrchestrator`
(lifecycle async del host). La fábrica es **100% síncrona**: los 4 adaptadores
concretos involucrados (`PydanticConfigAdapter`, `StructlogAdapter`,
`ClassificationAdapter`, `ImportlibDependencyAdapter`) exponen constructores
síncronos (verificado en source). `invalidate_cache()` es el único método async
y se invoca sólo en hot-reload — no bloquea la construcción.

### Hallazgo crítico (verificado contra source core-cenf v0.1.0)

- `ClassificationAdapter.__init__(config, logger, observability)` exige un
  **tercer** argumento `observability: ObservabilityManager`. La proposal lo
  omitía. Para producción sin telemetría real se inyecta `NoopObservabilityAdapter`
  (silencioso, satisface el Protocol). Para tests, lo mismo o
  `InMemoryObservabilityAdapter` si se quiere assertar.
- `ImportlibDependencyAdapter.resolve_class(module, klass)` **no consulta el
  registry**: sólo aplica allowlist prefix-match + `importlib.import_module`.
  `register()` alimenta SOLO `is_known` / `list_keys` / `get_required_packages`
  (descubrimiento y metadatos). Por ende el allowlist es lo que habilita la
  resolución; el registry queda como catálogo declarativo yaml-agno.
- `ImportlibDependencyAdapter.__init__` **snapshotea** `dependency.allowlist_paths`
  desde el ConfigManager al construirse. `PydanticConfigAdapter` **no expone
  mutador** (sólo lee YAML + env en `__init__`). Conclusión: la sembradura del
  allowlist debe ocurrir **antes** de construir el adapter, vía la fuente que el
  ConfigManager ya consume (YAML / `CENF_dependency__allowlist_paths`). En tests
  se usa `InMemoryConfigAdapter`, que sí tiene `set_value()`.

## Architecture Decisions

### A1 — Importar el motor, no reimplementarlo

**Choice**: `AgnoResolver` recibe un `DependencyManager` ya construido (prod:
`ImportlibDependencyAdapter`; tests: `InMemoryDependencyAdapter`) y delega todo
importlib/allowlist/cache a él.
**Alternatives**: reimplementar importlib+lru_cache+allowlist (~200 líneas,
frankenstein).
**Rationale**: core-cenf v0.1.0 ya distribuye exactamente esa funcionalidad
(obs 1936/1942). La regla DECISIONES de yaml-agno es “build ON TOP, never
frankenstein”.

### A2 — Dos abstracciones separadas, no una

**Choice**: `AgnoResolver` (carga de clases) y `ValueResolver` (resolución de
`${provider.key}`) son clases distintas con responsabilidades no solapadas.
**Alternatives**: un solo `DependencyManager` que haga ambas (acoplamiento).
**Rationale**: la carga de clases y la resolución de valores string son
taxonomías diferentes; mezclarlas rompe cohesión. `DIReference.resolve()` ya
dicta el contrato del ValueResolver (dict `provider.key -> value`).

### A3 — `ClassificationAdapter` necesita ObservabilityManager (3er arg)

**Choice**: `build_agno_resolver()` construye/acepta también un
`ObservabilityManager`. Default prod: `NoopObservabilityAdapter()` (sin
telemetría). Default test: idem. El host puede inyectar `OtelAdapter` si exporta
trazas.
**Alternatives**: no construir errores (delegar al host); construir un adapter
casero que prescinda de observabilidad.
**Rationale**: source verificado — `ClassificationAdapter.__init__(config,
logger, observability)`. Sin el 3er arg, `ImportlibDependencyAdapter` no recibe
un `ErrorHandlingManager` válido y el wiring falla. `NoopObservabilityAdapter`
cumple el Protocol sin acoplar a OTEL.

### A4 — El allowlist se siembra en la fuente del ConfigManager, no en runtime

**Choice**: la fábrica `build_agno_resolver()` **exige** que el ConfigManager ya
tenga `dependency.allowlist_paths` poblado antes de construir el adapter. En
tests se usa `InMemoryConfigAdapter.set_value("dependency.allowlist_paths",
AGNO_ALLOWLIST_PREFIXES)`. En prod el host lo provee vía YAML o
`CENF_dependency__allowlist_paths` (env var nested, formato `CENF_` +
`__`-separator — verificado en `_apply_env_overrides`).
**Alternatives**: mutar `_config` internamente (rompe encapsulación de
`PydanticConfigAdapter`); construir el adapter dos veces.
**Rationale**: `ImportlibDependencyAdapter.__init__` lee la sección una sola vez.
`PydanticConfigAdapter` no expone setter. Sembrar en la fuente respeta los
contratos y es idempotente.

### A5 — `resolve_model`/`build_db` consultan REGISTRY, luego `resolve_class` + instancian

**Choice**: `AgnoResolver.resolve_model("openai:gpt-4o")` parte en
`(provider, model_id)` lookup en `MODEL_REGISTRY[provider]`
→ obtiene `(module_path, class_name)` → llama
`adapter.resolve_class(module_path, class_name)` → **INSTANCIA** con
`id=model_id` (retorna un `Model`, no la clase). `register()` se invoca en
bootstrap (VÍA el adapter, no como método de AgnoResolver) sólo para alimentar
`list_keys`/`get_required_packages` (descubrimiento y generación de
`requirements.txt`). `build_db` pasa el conn_str como `db_url=` kwarg (no
posicional): `RedisDb.__init__(id, redis_client, db_url, ...)` — el primer
positional es `id`, así que posicional leak al slot equivocado.
**Alternatives**: registrar los targets como `(module, class)` y resolver vía
`adapter.is_known` (no funciona — `resolve_class` ignora el registry); pasar
conn_str posicional a build_db (rompe redis).
**Rationale**: respeta el contrato verificado del adapter, los contratos
verificados de constructores Agno (`OpenAIChat(id=...)`, `RedisDb(db_url=...)`,
`PostgresDb(db_url=...)`), y mantiene los registros como **datos** declarativos
(no lógica).

### A6 — `build_db` con semántica de connection-string + `db_url=` kwarg

**Choice**: `build_db("memory")` y `build_db("sqlite")` instancian SIN
`connection_string` (constructores verificados: `InMemoryDb()`,
`SqliteDb(db_file=None, ...)`). `build_db("postgres")` / `build_db("redis")`
lanzan `ValidationError` si falta `conn_str`. Cuando se pasa, se inyecta como
`db_url=` kwarg (NO posicional): `RedisDb(id, redis_client, db_url, ...)` tiene
`id` como primer positional — posicional leak al slot equivocado;
`PostgresDb(db_url, ...)` funcionaba posicional por accidente. Kwarg unifica.
**Alternatives**: envolver todo bajo un único kwarg opcional; pasar posicional
(rompe redis).
**Rationale**: contratos verificados divergen — memory/sqlite no requieren
conexión, postgres/redis sí; y los constructors de postgres/redis requieren
`db_url=` (no positional) para evitar el bug de redis.

### A7 — ValueResolver MVP: `env.*` only, resto NotImplementedError ruidoso

**Choice**: `ValueResolver.resolve_provider("env", "API_KEY")` →
`ConfigManager.get_string("API_KEY")`. Otros providers (`db`, `api`, `file`)
lanzan `NotImplementedError` con mensaje explícito diferido a SPEC_23.
**Alternatives**: resolver todo en este slice; retornar `None` silencioso.
**Rationale**: scope acotado y predictible. Un fallo silencioso rompería el
contrato `KeyError`-on-missing de `DIReference.resolve`.

## Data Flow

```
                 YAML (provider:id strings, ${env.FOO} tokens)
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                                            ▼
   AgentConfig (SPEC_02)                       DIReference (SPEC_02)
   model="openai/gpt-4o"                       template="${env.api_key}"
   db="memory"                                 tokens=[("env","api_key")]
            │                                            │
            │ resolve_model("openai:gpt-4o")             │ resolve(resolved_values)
            │   → split → ("openai","gpt-4o")            │   needs dict {"env.api_key": ...}
            │   → MODEL_REGISTRY["openai"]               │
            │   → adapter.resolve_class(                 │  ValueResolver.resolve(ref)
            │       "agno.models.openai",                │   for each (provider,key):
            │       "OpenAIChat")                        │     dispatch on provider
            │   → OpenAIChat(id="gpt-4o") instance ◄─────┤     env.* → config.get_string
            │                                            │     env.* → config.get_string
            ▼                                            ▼
     agno.Agent(model=<OpenAIChat instance>)     ref.resolve(dict) → string final

build_agno_resolver() wiring (sync, graph order):
   config (host-provided, allowlistPaths ya sembrados)
     → logger = StructlogAdapter(config)            [lee get_section("logger")]
     → observability = NoopObservabilityAdapter()   [default prod-safe]
     → errors = ClassificationAdapter(config, logger, observability)
     → dependency = ImportlibDependencyAdapter(config, logger, errors)
     → AgnoResolver(dependency, MODEL_REGISTRY, STORAGE_REGISTRY)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/di/registries.py` | Create | `MODEL_REGISTRY`, `STORAGE_REGISTRY`, `AGNO_ALLOWLIST_PREFIXES`, `WORKFLOW_REGISTRY` como dict literals. |
| `src/yaml_agno/di/agno_resolver.py` | Create | `AgnoResolver` (4 métodos) + `build_agno_resolver()` fábrica. |
| `src/yaml_agno/di/value_resolver.py` | Create | `ValueResolver` MVP `env.*`, resto `NotImplementedError`. |
| `src/yaml_agno/di/__init__.py` | Modify | Re-export `AgnoResolver`, `ValueResolver`, `build_agno_resolver`, `MODEL_REGISTRY`, `STORAGE_REGISTRY`. |
| `tests/unit/di/__init__.py` | Create | Marcador de paquete tests. |
| `tests/unit/di/test_agno_resolver.py` | Create | RED→GREEN con `InMemoryDependencyAdapter` + doubles oficiales. |
| `tests/unit/di/test_value_resolver.py` | Create | RED→GREEN `env.*` + `NotImplementedError` para el resto. |
| `tests/unit/di/test_build_agno_resolver.py` | Create | Verifica wiring síncrono de los 3 managers + allowlist seeding. |

## Interfaces / Contracts

### `src/yaml_agno/di/registries.py`

```python
"""Registros declarativos Agno — catálogos de providers como DATA.

Estos dicts son la única fuente de verdad de qué clases nativas Agno son
alcanzables vía AgnoResolver. Son DATOS, no lógica: AgnoResolver los consulta
y delega el importlib real al ImportlibDependencyAdapter inyectado.

@ai-directive: NO añadir lógica de resolución aquí. Un nuevo provider se agrega
    como una entrada más en el dict correspondiente.
"""

from __future__ import annotations

from typing import Final

# Mapping logico provider-key -> (module_path, class_name, [packages]).
# module_path DEBE estar cubierto por AGNO_ALLOWLIST_PREFIXES para que
# ImportlibDependencyAdapter.resolve_class lo acepte en strict mode.
MODEL_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    "openai": ("agno.models.openai", "OpenAIChat", ["openai>=1.0"]),
    "anthropic": ("agno.models.anthropic", "Claude", ["anthropic>=0.40"]),
    "google": ("agno.models.google", "Gemini", ["google-genai>=1.0"]),
    "groq": ("agno.models.groq", "Groq", ["groq>=0.11"]),
    "mistral": ("agno.models.mistral", "Mistral", ["mistralai>=1.0"]),
    "cohere": ("agno.models.cohere", "Cohere", ["cohere>=5.0"]),
}

# Storage providers. memory/sqlite: sin connection_string (constructores verificados
# InMemoryDb(), SqliteDb(db_file=None)). postgres/redis: requieren conn_str.
STORAGE_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    "memory": ("agno.db.in_memory", "InMemoryDb", []),
    "sqlite": ("agno.db.sqlite", "SqliteDb", ["sqlalchemy>=2.0"]),
    "postgres": ("agno.db.postgres", "PostgresDb", ["sqlalchemy>=2.0", "psycopg[binary]>=3.0"]),
    "redis": ("agno.db.redis", "RedisDb", ["redis>=5.0"]),
}

# Nombres de primitivas de workflow resolubles como clases (slice #4 consumirá
# los que faltan). Mapeo lógico -> (module, class).
WORKFLOW_REGISTRY: Final[dict[str, tuple[str, str]]] = {
    "Step": ("agno.workflow", "Step"),
    "Parallel": ("agno.workflow", "Parallel"),
    "Condition": ("agno.workflow", "Condition"),
    "Router": ("agno.workflow", "Router"),
    "Loop": ("agno.workflow", "Loop"),
    "Workflow": ("agno.workflow", "Workflow"),
}

# Prefijos siembrados en dependency.allowlist_paths. Prefix-match en
# ImportlibDependencyAdapter._is_allowlisted (verificado importlib_dependency_adapter.py:88).
# Todos los module_path de los REGISTRY anteriores caen bajo estos prefijos.
AGNO_ALLOWLIST_PREFIXES: Final[list[str]] = [
    "agno.models.",
    "agno.db.",
    "agno.workflow.",
    "agno.team.",
    "agno.agent",
]

__all__ = [
    "MODEL_REGISTRY",
    "STORAGE_REGISTRY",
    "WORKFLOW_REGISTRY",
    "AGNO_ALLOWLIST_PREFIXES",
]
```

### `src/yaml_agno/di/agno_resolver.py`

```python
"""AgnoResolver — fachada de dominio Agno sobre el DependencyManager de core-cenf.

Dos responsabilidades, NO solapadas con core-cenf:
  1. Traducir claves de dominio Agno ("openai", "memory", "Condition") a clases
     nativas, consultando REGISTRY y delegando importlib+allowlist al adapter.
  2. Encapsular la semantica especial de build_db (conn_str requerido solo para
     postgres/redis).

El motor de carga (importlib, allowlist prefix-match, cache) es IMPORTADO de
core-cenf (ImportlibDependencyAdapter). Este modulo NO lo reimplementa.

@ai-directive: SSOT es openspec/changes/dependency-facade/design.md. Cualquier
    discrepancia con SPEC_01 se resuelve a favor del design (correcciones de
    adapter names verificadas contra core-cenf v0.1.0).
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.dependency import DependencyManager, ImportlibDependencyAdapter
from core_infrastructure.errors.adapters import ClassificationAdapter
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.adapters import StructlogAdapter
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.adapters import NoopObservabilityAdapter
from core_infrastructure.observability.ports import ObservabilityManager

from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    STORAGE_REGISTRY,
    WORKFLOW_REGISTRY,
)

__all__ = ["AgnoResolver", "build_agno_resolver"]

# Storage providers cuyo constructor NO acepta connection_string (verificado
# InMemoryDb() / SqliteDb(db_file=None)). Los demas requieren conn_str.
_NO_CONN_STR_PROVIDERS: frozenset[str] = frozenset({"memory", "sqlite"})


class AgnoResolver:
    """Fachada de dominio Agno sobre un DependencyManager de core-cenf.

    Recibe un adapter ya construido (prod: ImportlibDependencyAdapter;
    tests: InMemoryDependencyAdapter). Expone 4 metodos de dominio que traducen
    claves Agno a clases nativas, consultando los REGISTRY declarativos.

    Attributes:
        _adapter: El DependencyManager inyectado (motor de carga).
        _models: Catálogo provider-key -> (module, class, packages).
        _storage: Catálogo storage-key -> (module, class, packages).
        _workflow: Catálogo primitive-name -> (module, class).

    Example:
        >>> resolver = build_agno_resolver(config)
        >>> model = resolver.resolve_model("openai:gpt-4o")
        >>> model.id
        'gpt-4o'
    """

    def __init__(
        self,
        adapter: DependencyManager,
        models: dict[str, tuple[str, str, list[str]]] | None = None,
        storage: dict[str, tuple[str, str, list[str]]] | None = None,
        workflow: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        """Inicializa la fachada con el adapter y catálogos inyectados.

        Args:
            adapter: DependencyManager ya construido (ImportlibDependencyAdapter
                en prod, InMemoryDependencyAdapter en tests).
            models: Catálogo de modelos (default MODEL_REGISTRY).
            storage: Catálogo de storage (default STORAGE_REGISTRY).
            workflow: Catálogo de primitivas workflow (default WORKFLOW_REGISTRY).
        """
        self._adapter = adapter
        self._models = models if models is not None else MODEL_REGISTRY
        self._storage = storage if storage is not None else STORAGE_REGISTRY
        self._workflow = workflow if workflow is not None else WORKFLOW_REGISTRY

    # ------------------------------------------------------------------
    # Resolución de clases nativas Agno
    # ------------------------------------------------------------------

    def resolve_model(self, spec: str) -> Any:
        """Resolver un string 'provider:id' a un Model Agno instanciado.

        Formato nativo Agno (COLON): parte ``spec`` en ``(provider, model_id)``
        en el primer ':', lookup en ``MODEL_REGISTRY[provider]``, resuelve la
        clase vía el adapter y la INSTANCIA con ``id=model_id``.

        Args:
            spec: String 'provider:id' (e.g. ``"openai:gpt-4o"``).

        Returns:
            Una INSTANCIA de Model (e.g. ``OpenAIChat(id="gpt-4o")``).

        Raises:
            ValueError: Si ``spec`` no contiene ':' (formato inválido).
            KeyError: Si el provider no está en MODEL_REGISTRY.
            ValidationError: Si el module_path no está en el allowlist (strict).
        """
        if ":" not in spec:
            raise ValueError(f"Invalid model spec: {spec!r}. Expected 'provider:id'.")
        provider, model_id = spec.split(":", 1)
        if provider not in self._models:
            raise KeyError(f"Unknown model provider: {provider!r}")
        module_path, class_name, _packages = self._models[provider]
        cls = self._adapter.resolve_class(module_path, class_name)
        return cls(id=model_id)

    def build_db(self, provider: str, conn_str: str | None = None) -> Any:
        """Construir una instancia de storage Agno.

        Semántica especial (A6):
          - memory/sqlite: constructor SIN connection_string.
          - postgres/redis: ``conn_str`` obligatorio.

        Args:
            provider: Clave lógica ("memory", "sqlite", "postgres", "redis").
            conn_str: Cadena de conexión. Requerido para postgres/redis,
                ignorado para memory/sqlite.

        Returns:
            Instancia del storage Agno (e.g. ``InMemoryDb()``).

        Raises:
            KeyError: Si ``provider`` no está en STORAGE_REGISTRY.
            ValidationError: Si postgres/redis sin ``conn_str``.
        """
        if provider not in self._storage:
            raise KeyError(f"Unknown storage provider: {provider!r}")

        if provider not in _NO_CONN_STR_PROVIDERS and not conn_str:
            raise ValidationError(
                f"Storage provider {provider!r} requires conn_str",
                details={"provider": provider},
            )

        module_path, class_name, _packages = self._storage[provider]
        cls = self._adapter.resolve_class(module_path, class_name)

        if provider in _NO_CONN_STR_PROVIDERS:
            return cls()
        # db_url= kwarg (NOT positional): RedisDb's first positional is `id`.
        return cls(db_url=conn_str)

    def resolve_workflow_primitive(self, name: str) -> type:
        """Resolver el nombre de primitiva workflow a su clase Agno.

        Args:
            name: Nombre lógico ("Step", "Parallel", "Condition", "Router",
                "Loop", "Workflow").

        Returns:
            La clase Agno correspondiente.

        Raises:
            KeyError: Si ``name`` no está en WORKFLOW_REGISTRY.
        """
        module_path, class_name = self._workflow[name]
        return self._adapter.resolve_class(module_path, class_name)

    def resolve_class(self, module_path: str, class_name: str) -> type:
        """Punto de escape: resolver cualquier clase allowlisted.

        Útil para resolution ad-hoc fuera de los catálogos de dominio.

        Args:
            module_path: Ruta absoluta del módulo.
            class_name: Nombre de la clase.

        Returns:
            La clase resuelta.

        Raises:
            ValidationError: Si no está en el allowlist (strict mode).
        """
        return self._adapter.resolve_class(module_path, class_name)


def build_agno_resolver(
    config: ConfigManager | None = None,
    *,
    logger: LoggerManager | None = None,
    errors: ErrorHandlingManager | None = None,
    observability: ObservabilityManager | None = None,
    adapter: DependencyManager | None = None,
) -> AgnoResolver:
    """Fábrica síncrona que ensambla los managers de core-cenf y el AgnoResolver.

    Orden del grafo (A3, A4): Config → Logger → Observability → Errors →
    Dependency → AgnoResolver. Los 4 adapters concretos son síncronos (verificado
    en source core-cenf v0.1.0).

    Conveniencia: si ``config`` es None, se construye ``PydanticConfigAdapter()``
    con defaults (env-only). Si ``adapter`` ya viene inyectado (tests), se omite
    el wiring de los 3 managers.

    Args:
        config: ConfigManager con ``dependency.allowlist_paths`` ya sembrados
            (A4). Si None, se crea ``PydanticConfigAdapter()`` — el host DEBE
            entonces exponer ``CENF_dependency__allowlist_paths`` o un YAML.
        logger: LoggerManager. Si None, ``StructlogAdapter(config)``.
        errors: ErrorHandlingManager. Si None,
            ``ClassificationAdapter(config, logger, observability)``.
        observability: ObservabilityManager. Si None, ``NoopObservabilityAdapter()``.
        adapter: DependencyManager ya construido. Si se pasa, se usa directo y
            ``config/logger/errors/observability`` se ignoran.

    Returns:
        Un ``AgnoResolver`` listo para resolver providers Agno.

    Raises:
        ValidationError: Si el allowlist está vacío y el adapter está en strict
            mode (mala siembra de ``dependency.allowlist_paths``).
    """
    if adapter is not None:
        return AgnoResolver(adapter)

    # Config: ya debe traer dependency.allowlist_paths sembrado (A4). Si el
    # caller no proveyó uno, PydanticConfigAdapter lee YAML+CENF_ env.
    resolved_config: ConfigManager = config if config is not None else PydanticConfigAdapter()

    # Guard de siembra: si la sección no tiene allowlist_paths, fallar ruidosamente
    # en lugar de devolver un resolver que rechaza todo en strict mode.
    dep_section = resolved_config.get_section("dependency")
    if not dep_section.get("allowlist_paths"):
        raise ValidationError(
            "dependency.allowlist_paths is empty — seed AGNO_ALLOWLIST_PREFIXES "
            "in the config before calling build_agno_resolver()",
            details={"section": "dependency"},
        )

    resolved_logger: LoggerManager = logger if logger is not None else StructlogAdapter(resolved_config)
    resolved_obs: ObservabilityManager = observability if observability is not None else NoopObservabilityAdapter()
    resolved_errors: ErrorHandlingManager = (
        errors if errors is not None else ClassificationAdapter(resolved_config, resolved_logger, resolved_obs)
    )
    dep_adapter: DependencyManager = ImportlibDependencyAdapter(resolved_config, resolved_logger, resolved_errors)

    return AgnoResolver(dep_adapter)
```

### `src/yaml_agno/di/value_resolver.py`

```python
"""ValueResolver — traduce la sintaxis ``${provider.key}`` a valores concretos.

Contract con DIReference (SPEC_02, ya entregado):
    DIReference.resolve(resolved_values: dict[str, Any]) -> str
    espera un dict plano "provider.key" -> value. Este modulo construye ese dict
    consultando providers. MVP: solo env.* (ConfigManager.get_string). Otros
    providers (db/api/file) lanzan NotImplementedError ruidoso (deferidos a
    SPEC_23) — nunca retornan None silenciosamente.

@ai-directive: La sintaxis ${provider.key} es OWN yaml-agno; no existe en Agno.
    Este modulo NO toca DIReference — solo produce el dict que su resolve() come.
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.config.ports import ConfigManager

from yaml_agno.models.value_objects.di_reference import DIReference

__all__ = ["ValueResolver"]

# Providers con implementación; el resto lanza NotImplementedError.
_SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"env"})


class ValueResolver:
    """Resuelve los tokens ``${provider.key}`` de un ``DIReference``.

    Itera los tokens del template, despacha cada ``provider`` al resolver
    correspondiente, y arma el dict ``provider.key -> value`` consumible por
    ``DIReference.resolve()``.

    Attributes:
        _config: ConfigManager para el provider ``env``.

    Example:
        >>> ref = DIReference(template="key is ${env.api_key}")
        >>> vr = ValueResolver(config)
        >>> resolved = vr.resolve(ref)
        >>> resolved
        {'env.api_key': 'sk-...'}
        >>> ref.resolve(resolved)
        'key is sk-...'
    """

    def __init__(self, config: ConfigManager) -> None:
        """Inicializa el resolver con un ConfigManager.

        Args:
            config: ConfigManager usado por el provider ``env`` para
                ``get_string(key)``.
        """
        self._config = config

    def resolve(self, reference: DIReference) -> dict[str, Any]:
        """Resolver todos los tokens de ``reference`` a un dict provider.key.

        Args:
            reference: ``DIReference`` ya validado (SPEC_02).

        Returns:
            Dict plano ``"provider.key" -> valor`` consumible por
            ``DIReference.resolve()``.

        Raises:
            NotImplementedError: Si algún provider no es ``env`` (MVP).
            ValidationError: Si la clave env no existe en el ConfigManager
                (propagado por ``get_string``).
        """
        resolved: dict[str, Any] = {}
        for provider, key in reference.tokens:
            full_key = f"{provider}.{key}"
            resolved[full_key] = self._resolve_provider(provider, key)
        return resolved

    def _resolve_provider(self, provider: str, key: str) -> Any:
        """Despachar un token (provider, key) a su resolver concreto.

        Args:
            provider: Nombre del provider ("env", "db", "api", "file", ...).
            key: Clave dentro del provider.

        Returns:
            El valor resuelto.

        Raises:
            NotImplementedError: Para providers no soportados en el MVP.
        """
        if provider == "env":
            # ConfigManager.get_string: KeyError → ValidationError si no existe.
            return self._config.get_string(key)
        raise NotImplementedError(
            f"ValueResolver MVP supports only {_SUPPORTED_PROVIDERS}; "
            f"provider {provider!r} is deferred to SPEC_23"
        )
```

### `src/yaml_agno/di/__init__.py`

```python
"""yaml-agno DI package — fachada Agno + ValueResolver.

API pública:
    - AgnoResolver: fachada de dominio sobre ImportlibDependencyAdapter.
    - build_agno_resolver: fábrica síncrona (ensambla managers core-cenf).
    - ValueResolver: traduce ${provider.key} a dict para DIReference.resolve().
    - MODEL_REGISTRY / STORAGE_REGISTRY / WORKFLOW_REGISTRY: catálogos DATA.
    - AGNO_ALLOWLIST_PREFIXES: prefijos para sembrar el allowlist.

@ai-directive: NO re-exportar ImportlibDependencyAdapter aquí — los consumidores
    pasan por AgnoResolver. El adapter es un detalle de implementación.
"""

from __future__ import annotations

from yaml_agno.di.agno_resolver import AgnoResolver, build_agno_resolver
from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    STORAGE_REGISTRY,
    WORKFLOW_REGISTRY,
)
from yaml_agno.di.value_resolver import ValueResolver

__all__ = [
    "AGNO_ALLOWLIST_PREFIXES",
    "AgnoResolver",
    "MODEL_REGISTRY",
    "STORAGE_REGISTRY",
    "ValueResolver",
    "WORKFLOW_REGISTRY",
    "build_agno_resolver",
]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `AgnoResolver.resolve_model("openai:gpt-4o")` retorna instancia `OpenAIChat(id="gpt-4o")` | `InMemoryDependencyAdapter` con mapping `{("agno.models.openai","OpenAIChat"): OpenAIChat}`. Sin red. |
| Unit | `build_db("memory")` instancia sin conn_str; `build_db("postgres","redis")` inyectan `db_url=`; sin conn_str lanza `ValidationError` | Mismo adapter in-memory + clases stub (RedisDb stub graba `id` + `db_url`). |
| Unit | `resolve_class("os","path")` lanza `ValidationError` (no allowlisted) | Con `ImportlibDependencyAdapter` real + `InMemoryConfigAdapter` (allowlist vacío). |
| Unit | `ValueResolver.resolve(DIReference("${env.api_key}"))` retorna `{"env.api_key": <v>}` | `InMemoryConfigAdapter(initial_data={"api_key":"sk-x"})`. |
| Unit | `ValueResolver` con provider `db`/`api`/`file` lanza `NotImplementedError` | Directo sobre `_resolve_provider`. |
| Unit | `build_agno_resolver()` wiring: 3 managers construidos en orden, allowlist vacío lanza `ValidationError` | `InMemoryConfigAdapter` con/sin `dependency.allowlist_paths`. |
| Integration | RED→GREEN con `ImportlibDependencyAdapter` real: `resolve_model("openai:gpt-4o")` retorna `OpenAIChat(id="gpt-4o")` instancia de `Model` (import real) | Fixture: `InMemoryConfigAdapter` + `set_value("dependency.allowlist_paths", AGNO_ALLOWLIST_PREFIXES)` + `InMemoryLoggerAdapter` + `CapturingErrorAdapter` + `NoopObservabilityAdapter`. |

## TDD Approach (RED → GREEN)

Strict TDD mode activo (runner: `pytest`). Por archivo:

### `test_agno_resolver.py`
1. **RED**: `test_resolve_model_openai_returns_model_instance_with_id` — assert
   `resolver.resolve_model("openai:gpt-4o")` retorna instancia con `.id == "gpt-4o"`.
   Sin implementación del split → falla.
2. **GREEN**: implementar `AgnoResolver.resolve_model` (split + instantiate) + `MODEL_REGISTRY`.
3. **RED**: `test_build_db_memory_no_conn_str` + `test_build_db_postgres/redis_uses_db_url_kwarg`.
4. **GREEN**: implementar `build_db` con `_NO_CONN_STR_PROVIDERS` + `db_url=` kwarg.
5. **RED**: `test_resolve_model_unknown_provider_raises` + `test_resolve_model_bad_format_no_colon_raises_valueerror`.
6. **GREEN**: cubierto por el split + lookup.
7. **RED**: `test_resolve_model_integration_real_openai_chat_is_model_instance` —
   `ImportlibDependencyAdapter` real + agno real, `isinstance(result, Model)`.

### `test_value_resolver.py`
1. **RED**: `test_resolve_env_single_token` → dict `{"env.api_key": "sk-x"}`.
2. **GREEN**: implementar `resolve` + `_resolve_provider` con branch `env`.
3. **RED**: `test_resolve_db_raises_not_implemented`.
4. **GREEN**: ya cubierto por `raise NotImplementedError`.

### `test_build_agno_resolver.py`
1. **RED**: `test_build_with_injected_adapter_skips_wiring`.
2. **GREEN**: implementar early-return.
3. **RED**: `test_build_empty_allowlist_raises_validation_error`.
4. **GREEN**: implementar guard.
5. **RED**: `test_build_full_wiring_resolves_openai` (integration con adapter real).
6. **GREEN**: wiring de los 3 managers en orden.

## Verification

Antes de cerrar el slice:

```bash
pytest tests/unit/di/ -v                 # todos los tests pasan
ruff check src/yaml_agno/di/             # sin lint errors
ruff format --check src/yaml_agno/di/    # formato consistente
mypy src/yaml_agno/di/                   # strict sin errores
```

Smoke manual:
```python
from yaml_agno.di import build_agno_resolver, ValueResolver
from yaml_agno.models.value_objects.di_reference import DIReference
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.dependency import InMemoryDependencyAdapter

cfg = InMemoryConfigAdapter()
cfg.set_value("dependency.allowlist_paths",
              ["agno.models.", "agno.db.", "agno.workflow."])
resolver = build_agno_resolver(cfg)
model = resolver.resolve_model("openai:gpt-4o")
assert model.id == "gpt-4o"  # Model INSTANCE, not the class
vr = ValueResolver(cfg)
cfg.set_value("api_key", "sk-test")
assert vr.resolve(DIReference(template="${env.api_key}")) == {"env.api_key": "sk-test"}
```

## Migration / Rollout

No migration required. Todos los archivos son nuevos bajo `di/` salvo
`__init__.py` (hoy vacío). No hay mutación de SPEC_02 (`DIReference`) ni de
`agent-factory-basic`. Sin estado persistente.

Rollback: restaurar `di/__init__.py` a su contenido vacío y eliminar los 3
módulos nuevos + los 3 archivos de tests + `tests/unit/di/__init__.py`.

## Open Questions

- [ ] `WORKFLOW_REGISTRY` incluye `Parallel`/`Condition`/`Router`/`Loop` — el
      slice #4 debe confirmar que esos nombres resuelven vía
      `agno.workflow` (verificado en obs 1942: `from agno.workflow import ...`
      es la ruta correcta). Fuera de scope de este slice; se deja el REGISTRY
      sembrado para que el slice #4 sólo consuma.
- [ ] El guard de allowlist vacío en `build_agno_resolver` es estricto: un host
      que quiera permissive mode debe setear
      `dependency.allowlist_mode="permissive"` Y `allowlist_paths=[]` — pero el
      guard actual rechaza lista vacía sin distinguir modo. Aceptado para MVP
      (strict es el default).
