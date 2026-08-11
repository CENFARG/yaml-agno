"""Runtime db_ref resolver. Owner: SPEC_03 §7.4.

Turns YAML ``db_ref`` / ``vector_db`` strings into the live Agno ``Db`` /
``VectorDb`` they reference. Instances are built once at bootstrap (see
``build_db_registry``) and held by ref. This is a pure lookup table — no
connection management, no SQL.

yaml-agno does NOT re-implement Agno's Db/VectorDb construction (rule 1);
it builds them from config and registers them by ref, following the same
core-cenf contract as §7.1: DSN from ConfigManager, password from
SecretManager.

Contract (SPEC_03 §7.4): a missing ref fails fast with a ``ValueError``
naming the ref (consumed by SPEC_31 / SPEC_32 fail-fast paths).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.secrets.ports import SecretManager

__all__ = ["DbRegistry", "InMemoryDbRegistry", "build_db_registry"]

# ---------------------------------------------------------------------------
# Protocol + default implementation (canonical from SPEC_03 §7.4)
# ---------------------------------------------------------------------------


class DbRegistry(Protocol):
    """Resolves named database refs to live Agno objects.

    Implementations hold pre-built agno.db.Db and agno.vectordb.VectorDb
    instances keyed by their YAML ref. Lookup is O(1); a missing ref raises
    ``ValueError`` naming the ref.
    """

    def get(self, db_ref: str) -> object:
        """Return the agno.db.Db registered under ``db_ref``.

        Args:
            db_ref: the YAML ref string (e.g. ``"primary_pg"``).

        Returns:
            The live agno.db.Db instance.

        Raises:
            ValueError: if ``db_ref`` was not registered.
        """
        ...

    def get_vector_db(self, db_ref: str) -> object:
        """Return the agno.vectordb.VectorDb registered under ``db_ref``.

        Args:
            db_ref: the YAML ref string (e.g. ``"kb_vectors"``).

        Returns:
            The live agno.vectordb.VectorDb instance.

        Raises:
            ValueError: if ``db_ref`` was not registered.
        """
        ...


class InMemoryDbRegistry:
    """Default DbRegistry implementation: two dicts keyed by ref.

    Built once at bootstrap from config; immutable afterwards. Thread/async
    safe because it is read-only after construction.
    """

    def __init__(self) -> None:
        self._dbs: dict[str, object] = {}
        self._vector_dbs: dict[str, object] = {}

    def register_db(self, db_ref: str, db: object) -> None:
        self._dbs[db_ref] = db

    def register_vector_db(self, db_ref: str, vector_db: object) -> None:
        self._vector_dbs[db_ref] = vector_db

    def get(self, db_ref: str) -> object:
        if db_ref not in self._dbs:
            raise ValueError(f"Unknown db_ref: {db_ref!r} (not registered)")
        return self._dbs[db_ref]

    def get_vector_db(self, db_ref: str) -> object:
        if db_ref not in self._vector_dbs:
            raise ValueError(f"Unknown vector_db ref: {db_ref!r} (not registered)")
        return self._vector_dbs[db_ref]


# ---------------------------------------------------------------------------
# Default factories (DI-swappable: tests inject fakes, no asyncpg/pgvector
# required; a missing driver fails fast with a clear ImportError)
# ---------------------------------------------------------------------------

DbFactory = Callable[[str, str], object]  # (db_ref, dsn) -> agno Db
VectorDbFactory = Callable[[str, str, str], object]  # (db_ref, dsn, table_name)


def _default_db_factory(db_ref: str, dsn: str) -> object:
    """Build an Agno ``PostgresDb`` from a DSN.

    Lazily imported so yaml-agno stays importable without asyncpg; building
    a real engine requires the driver installed at runtime.
    """
    try:
        from agno.db.postgres import PostgresDb
    except ImportError as exc:
        raise ImportError(f"Cannot build db_ref {db_ref!r}: agno is not installed (pip install agno==2.8.7)") from exc
    try:
        return PostgresDb(db_url=dsn)
    except ImportError as exc:
        raise ImportError(
            f"Cannot build db_ref {db_ref!r}: the DSN driver package is "
            f"missing (pip install 'agno[postgres]' or asyncpg)"
        ) from exc


def _default_vector_db_factory(
    db_ref: str,
    dsn: str,
    table_name: str,
) -> object:
    """Build an Agno ``PgVector`` (pgvector, NO Qdrant — decision 2.9)."""
    try:
        from agno.vectordb.pgvector import PgVector
    except ImportError as exc:
        raise ImportError(
            f"Cannot build vector_db ref {db_ref!r}: pgvector is not installed "
            "(pip install 'pgvector' + 'psycopg[binary]')"
        ) from exc
    try:
        return PgVector(table_name=table_name, db_url=dsn)
    except ImportError as exc:
        raise ImportError(
            f"Cannot build vector_db ref {db_ref!r}: the DSN driver package is "
            f"missing (pip install 'agno[postgres]' or asyncpg)"
        ) from exc


# ---------------------------------------------------------------------------
# Bootstrap wiring (SPEC_03 §7.4)
# ---------------------------------------------------------------------------


async def _resolve_dsn(
    db_ref: str,
    entry: dict[str, Any],
    secrets: SecretManager,
) -> str:
    """Resolve the DSN for one config entry, substituting the password from
    SecretManager when ``password_ref`` is declared.

    Config entry shape::

        dsn: postgresql+asyncpg://user:{password}@host:5432/db
        password_ref: db.primary.password   # optional

    Fail-fast rules:
        - ``dsn`` is required (a missing one is a config error).
        - ``{password}`` in the DSN requires ``password_ref``.
        - ``password_ref`` without a ``{password}`` placeholder is dead config.
    """
    dsn = entry.get("dsn")
    if not isinstance(dsn, str) or not dsn:
        raise ValueError(f"db_ref {db_ref!r} entry is missing required 'dsn' (string)")
    password_ref = entry.get("password_ref")
    has_placeholder = "{password}" in dsn
    if has_placeholder and not isinstance(password_ref, str):
        raise ValueError(f"db_ref {db_ref!r}: DSN contains '{{password}}' but no 'password_ref' is declared")
    if password_ref is not None and not has_placeholder:
        raise ValueError(f"db_ref {db_ref!r}: 'password_ref' declared but DSN has no '{{{{password}}}}' placeholder")
    if has_placeholder:
        password = await secrets.get_secret(password_ref)
        dsn = dsn.replace("{password}", password)
    return dsn


async def build_db_registry(
    config: ConfigManager,
    secrets: SecretManager,
    *,
    db_factory: DbFactory | None = None,
    vector_db_factory: VectorDbFactory | None = None,
) -> InMemoryDbRegistry:
    """Build the runtime DbRegistry from the ``databases`` / ``vector_databases``
    config blocks (SPEC_03 §7.4 bootstrap wiring).

    For each ``databases`` entry, resolves the DSN (ConfigManager) + password
    (SecretManager), builds the Agno ``Db`` via ``db_factory`` (default:
    ``PostgresDb``) and registers it under its ref. Same for
    ``vector_databases`` via ``vector_db_factory`` (default: ``PgVector``,
    pgvector-backed — decision 2.9, NO Qdrant).

    Factories are DI-injectable so callers can substitute fakes or other Agno
    Db/VectorDb classes without touching this module. The resulting registry
    is a singleton passed to SPEC_31 ``CultureManager`` / SPEC_32
    ``RegistryPopulator``; a ref absent from the registry fails fast with a
    ``ValueError`` naming the ref.
    """
    registry = InMemoryDbRegistry()
    db_factory = db_factory or _default_db_factory
    vector_db_factory = vector_db_factory or _default_vector_db_factory

    databases: dict[str, Any] = config.get_section("databases") or {}
    for ref, entry in databases.items():
        if not isinstance(entry, dict):
            raise ValueError(f"db_ref {ref!r} must be a mapping, got {type(entry).__name__}")
        dsn = await _resolve_dsn(ref, entry, secrets)
        registry.register_db(ref, db_factory(ref, dsn))

    vector_databases: dict[str, Any] = config.get_section("vector_databases") or {}
    for ref, entry in vector_databases.items():
        if not isinstance(entry, dict):
            raise ValueError(f"vector_db ref {ref!r} must be a mapping, got {type(entry).__name__}")
        dsn = await _resolve_dsn(ref, entry, secrets)
        table_name = entry.get("table_name")
        if not isinstance(table_name, str) or not table_name:
            raise ValueError(f"vector_db ref {ref!r} is missing required 'table_name' (string)")
        registry.register_vector_db(ref, vector_db_factory(ref, dsn, table_name))

    return registry
