"""RED tests for AgnoResolver — fail until ``src/yaml_agno/di/agno_resolver.py`` exists.

Uses the official ``InMemoryDependencyAdapter`` test double from core-cenf plus
lightweight stubs for Agno classes (OpenAIChat / InMemoryDb / PostgresDb). No
network, no real imports of agno. Each test is tagged ``@pytest.mark.unit``.

These tests assert the 8 behavioral scenarios of SPEC_01 §Dependency Facade:
golden-path resolve_model, unknown provider, build_db conn_str semantics,
allowlist strict-mode rejection, and register idempotency.
"""

from __future__ import annotations

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.dependency import InMemoryDependencyAdapter

from yaml_agno.di.agno_resolver import AgnoResolver
from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    STORAGE_REGISTRY,
)


# ---------------------------------------------------------------------------
# Stub Agno classes — stand-ins for real agno models/dbs. They record how they
# were instantiated so tests can assert constructor-arg semantics.
# ---------------------------------------------------------------------------


class OpenAIChat:
    """Stub for agno.models.openai.OpenAIChat."""

    def __init__(self, id: str | None = None) -> None:
        self.id = id


class InMemoryDb:
    """Stub for agno.db.in_memory.InMemoryDb — no constructor args."""

    def __init__(self) -> None:
        pass


class PostgresDb:
    """Stub for agno.db.postgres.PostgresDb — requires conn_str."""

    def __init__(self, conn_str: str | None = None) -> None:
        self.conn_str = conn_str


class _FakeStep:
    pass


# Mapping seed for the InMemoryDependencyAdapter: maps the (module, class) keys
# used by MODEL_REGISTRY / STORAGE_REGISTRY to the stub classes above.
_MAPPING: dict[tuple[str, str], type] = {
    (MODEL_REGISTRY["openai"][0], MODEL_REGISTRY["openai"][1]): OpenAIChat,
    (STORAGE_REGISTRY["memory"][0], STORAGE_REGISTRY["memory"][1]): InMemoryDb,
    (STORAGE_REGISTRY["postgres"][0], STORAGE_REGISTRY["postgres"][1]): PostgresDb,
}


def _build_resolver() -> AgnoResolver:
    """Construct an AgnoResolver backed by the in-memory double with stubs."""
    adapter = InMemoryDependencyAdapter(mapping=_MAPPING)
    return AgnoResolver(adapter)


# ---------------------------------------------------------------------------
# resolve_model scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_model_openai_returns_openaichat_class() -> None:
    """Golden path: resolve_model('openai') returns the OpenAIChat class."""
    resolver = _build_resolver()
    cls = resolver.resolve_model("openai")
    assert cls is OpenAIChat


@pytest.mark.unit
def test_resolve_model_unknown_provider_raises_keyerror() -> None:
    """Unknown provider key is not in MODEL_REGISTRY → KeyError."""
    resolver = _build_resolver()
    with pytest.raises(KeyError):
        resolver.resolve_model("desconocido")


# ---------------------------------------------------------------------------
# build_db scenarios (conn_str semantics)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_db_memory_no_conn_str() -> None:
    """memory storage instantiates with no connection string."""
    resolver = _build_resolver()
    db = resolver.build_db("memory")
    assert isinstance(db, InMemoryDb)


@pytest.mark.unit
def test_build_db_postgres_with_conn_str() -> None:
    """postgres storage is constructed with the provided conn_str."""
    resolver = _build_resolver()
    db = resolver.build_db("postgres", conn_str="postgresql://u:p@h/db")
    assert isinstance(db, PostgresDb)
    assert db.conn_str == "postgresql://u:p@h/db"


@pytest.mark.unit
def test_build_db_postgres_without_conn_str_raises_validation_error() -> None:
    """postgres without conn_str is rejected — ValidationError."""
    resolver = _build_resolver()
    with pytest.raises(ValidationError):
        resolver.build_db("postgres", conn_str=None)


@pytest.mark.unit
def test_build_db_unknown_storage_raises_keyerror() -> None:
    """Unknown storage backend → KeyError (not present in STORAGE_REGISTRY)."""
    resolver = _build_resolver()
    with pytest.raises(KeyError):
        resolver.build_db("oracle", conn_str="conn")


# ---------------------------------------------------------------------------
# resolve_class + allowlist (strict-mode) scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_class_allowlisted_permitted() -> None:
    """An allowlisted (module, class) pair resolves via the adapter."""
    resolver = _build_resolver()
    cls = resolver.resolve_class(
        MODEL_REGISTRY["openai"][0],
        MODEL_REGISTRY["openai"][1],
    )
    assert cls is OpenAIChat


@pytest.mark.unit
def test_resolve_class_non_allowlisted_rejected() -> None:
    """resolve_class on a non-allowlisted path must raise ValidationError.

    Uses the REAL ImportlibDependencyAdapter (not the in-memory double) so the
    strict allowlist prefix-match is exercised against an empty allowlist.
    """
    from core_infrastructure.config.adapters import InMemoryConfigAdapter
    from core_infrastructure.dependency import ImportlibDependencyAdapter
    from core_infrastructure.errors.adapters import CapturingErrorAdapter
    from core_infrastructure.logger.adapters import InMemoryLoggerAdapter
    from core_infrastructure.observability.adapters import NoopObservabilityAdapter

    cfg = InMemoryConfigAdapter()
    # Empty allowlist → strict mode rejects everything except permissive.
    logger = InMemoryLoggerAdapter()
    obs = NoopObservabilityAdapter()
    errors = CapturingErrorAdapter(cfg, logger, obs)
    adapter = ImportlibDependencyAdapter(cfg, logger, errors)
    resolver = AgnoResolver(adapter)

    with pytest.raises(ValidationError):
        resolver.resolve_class("os", "system")


# ---------------------------------------------------------------------------
# register idempotency scenario (design A5: register lives on the adapter, not
# on AgnoResolver — bootstrap wiring seeds the adapter's discovery namespace).
# The design's AgnoResolver class exposes only 4 resolve_* methods; register()
# is invoked on the underlying DependencyManager during build_agno_resolver().
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_register_idempotent() -> None:
    """Registering the same namespace twice on the adapter does not duplicate.

    The design places register() on the adapter (used in bootstrap wiring),
    not on AgnoResolver. This test verifies the idempotency invariant of that
    seeding at the adapter level — the real concern behind spec scenario
    'idempotencia de register'.
    """
    adapter = InMemoryDependencyAdapter(mapping=_MAPPING)
    # Seed the 'models' namespace from MODEL_REGISTRY (what wiring does).
    for key, (module_path, class_name, packages) in MODEL_REGISTRY.items():
        adapter.register("models", key, (module_path, class_name, packages))
    first_count = len(adapter.list_keys("models"))
    # Re-seed — idempotent: register overwrites the same key, no duplication.
    for key, (module_path, class_name, packages) in MODEL_REGISTRY.items():
        adapter.register("models", key, (module_path, class_name, packages))
    second_count = len(adapter.list_keys("models"))
    assert first_count == second_count
    assert first_count == len(MODEL_REGISTRY)
