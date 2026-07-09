"""Unit tests for AgnoResolver — spec contract for resolve_model + build_db.

Uses the official ``InMemoryDependencyAdapter`` test double from core-cenf plus
lightweight stubs for Agno classes (OpenAIChat / InMemoryDb / PostgresDb /
RedisDb). No network, no real imports of agno (except the ONE integration-style
test at the bottom). Each test is tagged ``@pytest.mark.unit``.

These tests assert the corrected SPEC contract (verify pass-1):
  - resolve_model("openai:gpt-4o") splits on ':' → returns a Model INSTANCE
    (not the class) instantiated with id=model_id.
  - resolve_model("desconocido:foo") → raises (unknown provider).
  - resolve_model("openai") (no colon) → raises ValueError (bad format).
  - build_db postgres/redis instantiate with db_url= kwarg (NOT positional).
  - allowlist strict-mode rejection, register idempotency.
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
    """Stub for agno.models.openai.OpenAIChat — records the id kwarg."""

    def __init__(self, id: str | None = None) -> None:
        self.id = id


class InMemoryDb:
    """Stub for agno.db.in_memory.InMemoryDb — no constructor args."""

    def __init__(self) -> None:
        pass


class PostgresDb:
    """Stub for agno.db.postgres.PostgresDb — accepts db_url kwarg.

    Verified real signature (core-cenf v0.1.0 + agno):
        PostgresDb(db_url=None, db_engine=None, ...)
    """

    def __init__(self, db_url: str | None = None) -> None:
        self.db_url = db_url


class RedisDb:
    """Stub for agno.db.redis.RedisDb — accepts db_url kwarg (NOT positional).

    Verified real signature: RedisDb(id=None, redis_client=None, db_url=None, ...)
    The first positional is ``id``, NOT the connection string. The connection
    MUST be passed as ``db_url=``.
    """

    def __init__(self, id: str | None = None, db_url: str | None = None) -> None:
        self.id = id
        self.db_url = db_url


class _FakeStep:
    pass


# Mapping seed for the InMemoryDependencyAdapter: maps the (module, class) keys
# used by MODEL_REGISTRY / STORAGE_REGISTRY to the stub classes above.
_MAPPING: dict[tuple[str, str], type] = {
    (MODEL_REGISTRY["openai"][0], MODEL_REGISTRY["openai"][1]): OpenAIChat,
    (STORAGE_REGISTRY["memory"][0], STORAGE_REGISTRY["memory"][1]): InMemoryDb,
    (STORAGE_REGISTRY["postgres"][0], STORAGE_REGISTRY["postgres"][1]): PostgresDb,
    (STORAGE_REGISTRY["redis"][0], STORAGE_REGISTRY["redis"][1]): RedisDb,
}


def _build_resolver() -> AgnoResolver:
    """Construct an AgnoResolver backed by the in-memory double with stubs."""
    adapter = InMemoryDependencyAdapter(mapping=_MAPPING)
    return AgnoResolver(adapter)


# ---------------------------------------------------------------------------
# resolve_model scenarios (SPEC: "resolve_model con sintaxis provider:id")
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_model_openai_returns_model_instance_with_id() -> None:
    """Golden path: resolve_model('openai:gpt-4o') returns an instance with id.

    SPEC contract: split on ':' → look up MODEL_REGISTRY → instantiate with
    id=model_id. The result is an INSTANCE (not the class).
    """
    resolver = _build_resolver()
    result = resolver.resolve_model("openai:gpt-4o")
    assert isinstance(result, OpenAIChat)
    assert result.id == "gpt-4o"


@pytest.mark.unit
def test_resolve_model_unknown_provider_raises() -> None:
    """Unknown provider key ('desconocido') is not in MODEL_REGISTRY → raises."""
    resolver = _build_resolver()
    with pytest.raises((KeyError, ValueError)):
        resolver.resolve_model("desconocido:foo")


@pytest.mark.unit
def test_resolve_model_bad_format_no_colon_raises_valueerror() -> None:
    """A spec without ':' is invalid format → ValueError.

    SPEC: the input MUST be 'provider:id'. A bare provider name is rejected.
    """
    resolver = _build_resolver()
    with pytest.raises(ValueError):
        resolver.resolve_model("openai")


# ---------------------------------------------------------------------------
# build_db scenarios (conn_str semantics + db_url= kwarg contract)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_db_memory_no_conn_str() -> None:
    """memory storage instantiates with no connection string."""
    resolver = _build_resolver()
    db = resolver.build_db("memory")
    assert isinstance(db, InMemoryDb)


@pytest.mark.unit
def test_build_db_postgres_uses_db_url_kwarg() -> None:
    """postgres storage is constructed with db_url=<conn_str> (NOT positional).

    Verified PostgresDb signature: PostgresDb(db_url=None, ...). Passing
    positionally happens to work for postgres, but the contract is db_url=.
    """
    resolver = _build_resolver()
    db = resolver.build_db("postgres", conn_str="postgresql://u:p@h/db")
    assert isinstance(db, PostgresDb)
    assert db.db_url == "postgresql://u:p@h/db"


@pytest.mark.unit
def test_build_db_redis_uses_db_url_kwarg() -> None:
    """redis storage is constructed with db_url=<conn_str> (NOT positional).

    Verified RedisDb signature: RedisDb(id=None, redis_client=None, db_url=None).
    The first positional is ``id``; passing conn_str positionally would assign
    it to ``id`` — a bug. The connection MUST be passed as db_url=.
    """
    resolver = _build_resolver()
    db = resolver.build_db("redis", conn_str="redis://localhost:6379")
    assert isinstance(db, RedisDb)
    assert db.db_url == "redis://localhost:6379"
    # Critical: the conn_str must NOT leak into the `id` positional slot.
    assert db.id is None


@pytest.mark.unit
def test_build_db_postgres_without_conn_str_raises_validation_error() -> None:
    """postgres without conn_str is rejected — ValidationError."""
    resolver = _build_resolver()
    with pytest.raises(ValidationError):
        resolver.build_db("postgres", conn_str=None)


@pytest.mark.unit
def test_build_db_redis_without_conn_str_raises_validation_error() -> None:
    """redis without conn_str is rejected — ValidationError."""
    resolver = _build_resolver()
    with pytest.raises(ValidationError):
        resolver.build_db("redis", conn_str=None)


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
    from core_infrastructure.config.adapters.in_memory_config_adapter import (
        InMemoryConfigAdapter,
    )
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


# ---------------------------------------------------------------------------
# Integration-style test: REAL ImportlibDependencyAdapter + real agno import.
# Confirms the C1 fix end-to-end (the orchestrator's manual smoke that failed).
# Marked @pytest.mark.unit so it runs with the unit cohort.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_model_integration_real_openai_chat_is_model_instance() -> None:
    """End-to-end: real ImportlibDependencyAdapter + seeded allowlist + agno.

    Constructs AgnoResolver with the REAL ImportlibDependencyAdapter (not the
    in-memory double), seeds dependency.allowlist_paths=['agno.models.'], and
    calls resolve_model('openai:gpt-4o'). Asserts the result is a genuine
    agno Model instance with id='gpt-4o'. This is the smoke that failed before
    the C1 fix (old code returned the class, not an instance).
    """
    from agno.models.base import Model
    from core_infrastructure.config.adapters.in_memory_config_adapter import (
        InMemoryConfigAdapter,
    )
    from core_infrastructure.dependency import ImportlibDependencyAdapter
    from core_infrastructure.errors.adapters import CapturingErrorAdapter
    from core_infrastructure.logger.adapters import InMemoryLoggerAdapter
    from core_infrastructure.observability.adapters import NoopObservabilityAdapter

    cfg = InMemoryConfigAdapter()
    cfg.set_value("dependency.allowlist_paths", AGNO_ALLOWLIST_PREFIXES)
    logger = InMemoryLoggerAdapter()
    obs = NoopObservabilityAdapter()
    errors = CapturingErrorAdapter(cfg, logger, obs)
    adapter = ImportlibDependencyAdapter(cfg, logger, errors)
    resolver = AgnoResolver(adapter)

    result = resolver.resolve_model("openai:gpt-4o")
    assert isinstance(result, Model)
    assert result.id == "gpt-4o"
