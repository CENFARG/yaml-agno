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
from core_infrastructure.config.adapters.pydantic_config_adapter import (
    PydanticConfigAdapter,
)
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.dependency import (
    DependencyManager,
    ImportlibDependencyAdapter,
)
from core_infrastructure.errors.adapters import ClassificationAdapter
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.adapters import StructlogAdapter
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.adapters import NoopObservabilityAdapter
from core_infrastructure.observability.ports import ObservabilityManager

from yaml_agno.di.registries import (
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
        >>> cls = resolver.resolve_model("openai")
        >>> cls.__name__
        'OpenAIChat'
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

    def resolve_model(self, provider: str) -> type:
        """Resolver el provider de modelo lógico a su clase Agno.

        Args:
            provider: Clave lógica ("openai", "anthropic", ...). Debe existir
                en MODEL_REGISTRY.

        Returns:
            La clase Agno correspondiente (e.g. ``OpenAIChat``).

        Raises:
            KeyError: Si ``provider`` no está en MODEL_REGISTRY.
            ValidationError: Si el module_path no está en el allowlist (strict).
            ModuleNotFoundError/AttributeError: propagados por el adapter.
        """
        module_path, class_name, _packages = self._models[provider]
        return self._adapter.resolve_class(module_path, class_name)  # type: ignore[no-any-return]

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
        return cls(conn_str)

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
        return self._adapter.resolve_class(module_path, class_name)  # type: ignore[no-any-return]

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
        return self._adapter.resolve_class(module_path, class_name)  # type: ignore[no-any-return]


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
