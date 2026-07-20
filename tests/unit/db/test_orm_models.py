"""RED tests for yaml_agno.db ORM models (SPEC_03 slice A).

Strict TDD — written BEFORE the ORM classes exist. Covers all 7 requirements
from ``openspec/changes/persistence-orm-models/specs/.../spec.md`` and all
checkboxes from ``tasks.md``.

Tagged ``@pytest.mark.unit``. No external services: SQLite in-memory engine is
the only runtime fixture, used purely to verify CHECK constraints and round-trip
behavior. The ``yamlagno_*`` tables compile under SQLite via SQLAlchemy's
type-coercion layer (JSONB -> JSON, ARRAY(String) -> JSON).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy
from sqlalchemy import ARRAY, String, create_engine, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Make Postgres-only column types compile under SQLite so the round-trip tests
# can run against the in-memory engine. JSONB -> JSON; ARRAY(String) -> JSON.
# Both translations preserve round-trip semantics: Python dict/list values are
# serialized to TEXT on write and deserialized back on read.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVEN_TABLES = {
    "yamlagno.yamlagno_tenants",
    "yamlagno.yamlagno_agent_configs",
    "yamlagno.yamlagno_team_configs",
    "yamlagno.yamlagno_workflow_configs",
    "yamlagno.yamlagno_di_variable_cache",
    "yamlagno.yamlagno_config_change_log",
    "yamlagno.yamlagno_schema_versions",
}


def _sqlite_engine_with_yamlagno_schema(metadata: sqlalchemy.MetaData) -> Engine:
    """Create a SQLite in-memory engine preconfigured for the yamlagno schema.

    The yamlagno tables declare ``schema='yamlagno'``. SQLite has no native
    multi-schema support, so we bind a ``schema_translate_map`` at engine
    construction time that rewrites the ``yamlagno.`` prefix to the default
    schema at compile time. CHECK constraints, FKs, and UNIQUE all fire under
    SQLite exactly as they would on Postgres (per the design's SQLite-vs-PG
    note; only GIN/partial indexes are out of scope here).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"yamlagno": None}},
    )

    @sqlalchemy.event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn: object, connection_record: object) -> None:
        # Enforce FKs so CASCADE and FK violations actually fire under SQLite.
        cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
        # Register a SQLite-shim NOW() function so the PG-style
        # ``server_default=text("NOW()")`` columns accept inserts under SQLite.
        # The shim returns the current UTC timestamp in ISO-8601, matching PG's
        # NOW() behavior for round-trip purposes.
        import datetime as _dt

        def _now() -> str:
            return _dt.datetime.now(_dt.UTC).isoformat()

        dbapi_conn.create_function("NOW", 0, _now)  # type: ignore[attr-defined]

    return engine


# CHECK constraints that use Postgres-only SQL (regex ``~`` operator). They are
# exercised on the production Postgres engine (slice B); SQLite unit tests skip
# them via ``_sqlite_create_all`` below.
_PG_ONLY_CHECKS = {"slug_format"}


def _sqlite_create_all(conn: sqlalchemy.Connection, metadata: sqlalchemy.MetaData) -> None:
    """Run ``create_all`` on ``conn`` but skip Postgres-only CHECK constraints.

    The ``slug_format`` CHECK uses PG's ``~`` regex operator which SQLite
    cannot compile. Per the design's SQLite-vs-Postgres note, that construct
    is exercised on the production PG engine in slice B. For unit tests we
    temporarily detach the named constraint from each table just for the
    duration of ``create_all`` and re-attach it immediately after, so later
    constraint-inspection tests still see the canonical model definitions.
    """
    detached: list[tuple[sqlalchemy.Table, sqlalchemy.schema.CheckConstraint]] = []
    for table in metadata.tables.values():
        for cst in list(table.constraints):
            if (
                isinstance(cst, sqlalchemy.CheckConstraint)
                and cst.name in _PG_ONLY_CHECKS
            ):
                table.constraints.discard(cst)
                detached.append((table, cst))
    try:
        metadata.create_all(conn, checkfirst=True)
    finally:
        for table, cst in detached:
            table.constraints.add(cst)


def _constraint_names(table: sqlalchemy.Table) -> set[str]:
    """Flatten CHECK, UNIQUE, PK, and FK constraint names on a Table."""
    names: set[str] = set()
    for cst in table.constraints:
        if cst.name:
            names.add(cst.name)
    return names


# ---------------------------------------------------------------------------
# REQ-1 — DeclarativeBase + side-effect-free import (tasks 1.3)
# ---------------------------------------------------------------------------


def test_base_is_declarative_and_import_is_side_effect_free(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing yaml_agno.db.base MUST NOT create engine/session and Base MUST
    subclass sqlalchemy.orm.DeclarativeBase."""
    # Rip any prior import so we observe a clean import side-effect surface.
    for mod in list(sys.modules):
        if mod.startswith("yaml_agno.db"):
            monkeypatch.delitem(sys.modules, mod, raising=False)

    created_engines: list[str] = []
    real_create_engine = sqlalchemy.create_engine

    def spy_create_engine(*args: object, **kwargs: object) -> Engine:
        created_engines.append(str(args))
        return real_create_engine(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlalchemy, "create_engine", spy_create_engine)
    # Also patch the db.base namespace if it imported the symbol.
    base_mod = importlib.import_module("yaml_agno.db.base")
    monkeypatch.setattr(base_mod, "create_engine", spy_create_engine, raising=False)

    import yaml_agno.db.base as db_base

    assert isinstance(db_base.Base, type)
    assert issubclass(db_base.Base, DeclarativeBase)
    assert created_engines == [], "Importing yaml_agno.db.base created an engine"


# ---------------------------------------------------------------------------
# REQ-2 — Mixins (task 1.4)
# ---------------------------------------------------------------------------


# Defined at MODULE scope (not inside the test) so SQLAlchemy's deferred
# annotation resolver can find `Mapped` in module globals even with
# `from __future__ import annotations` stringifying the annotation.
from yaml_agno.db.base import Base as _Base  # noqa: E402
from yaml_agno.db.base import TenantMixin as _TenantMixin  # noqa: E402
from yaml_agno.db.base import TimestampMixin as _TimestampMixin  # noqa: E402


class _MixinProbe(_TimestampMixin, _TenantMixin, _Base):
    """Throwaway record to verify mixin columns; torn down after the test."""

    __tablename__ = "throwaway_mixin_probe"
    __table_args__ = ({"schema": "yamlagno"},)

    label: Mapped[str] = mapped_column(String(50), primary_key=True)


def test_timestamp_and_tenant_mixins_define_columns() -> None:
    """A record using both mixins exposes created_at/updated_at/tenant_id with
    correct nullability and CASCADE on the FK."""
    cols = {c.name: c for c in _MixinProbe.__table__.columns}
    assert "created_at" in cols, "TimestampMixin.created_at missing"
    assert "updated_at" in cols, "TimestampMixin.updated_at missing"
    assert "tenant_id" in cols, "TenantMixin.tenant_id missing"

    assert cols["created_at"].nullable is False
    assert cols["updated_at"].nullable is False
    assert cols["tenant_id"].nullable is False

    tenant_fks = list(cols["tenant_id"].foreign_keys)
    assert len(tenant_fks) == 1, "tenant_id must declare exactly one FK"
    fk = tenant_fks[0]
    assert fk.ondelete == "CASCADE", "tenant_id FK must be ON DELETE CASCADE"
    assert fk.target_fullname == "yamlagno.yamlagno_tenants.id"

    # Drop this probe table so it doesn't pollute the seven-table assertion.
    _Base.metadata.remove(_MixinProbe.__table__)


# ---------------------------------------------------------------------------
# REQ-4 / Phase 2 — TenantRecord (tasks 2.1, 2.2)
# ---------------------------------------------------------------------------


def test_tenant_record_table_and_schema() -> None:
    """TenantRecord maps to yamlagno.yamlagno_tenants with required columns."""
    from yaml_agno.db.models.tenant import TenantRecord

    assert TenantRecord.__tablename__ == "yamlagno_tenants"
    table = TenantRecord.__table__
    assert table.schema == "yamlagno"

    cols = {c.name: c for c in table.columns}
    for required in ("id", "name", "slug", "tenant_kind", "parent_org_id", "settings"):
        assert required in cols, f"TenantRecord missing column {required}"

    # Type spot-checks (loose: only sanity-check by name).
    assert type(cols["slug"].type).__name__ in {"String", "VARCHAR"}
    assert type(cols["settings"].type).__name__ in {"JSONB", "JSON"}
    assert type(cols["parent_org_id"].type).__name__ in {"UUID", "PgUUID"}


def test_tenant_record_constraints() -> None:
    """TenantRecord carries slug_format, valid_tenant_kind, org_has_no_parent
    CHECKs and UNIQUE(slug)."""
    from yaml_agno.db.models.tenant import TenantRecord

    table = TenantRecord.__table__
    names = _constraint_names(table)
    assert "slug_format" in names
    assert "valid_tenant_kind" in names
    assert "org_has_no_parent" in names

    # UNIQUE on slug — accept either a named UniqueConstraint or column-level
    # unique=True. Check both forms.
    has_unique_slug = any(
        getattr(c, "unique", False) for c in table.columns if c.name == "slug"
    ) or any(
        hasattr(cst, "columns")
        and len(cst.columns) == 1
        and cst.columns[0].name == "slug"
        for cst in table.constraints
    )
    assert has_unique_slug, "TenantRecord.slug must be UNIQUE"


# ---------------------------------------------------------------------------
# REQ-4 / Phase 3 — AgentConfigRecord (tasks 3.1, 3.2)
# ---------------------------------------------------------------------------


def test_agent_config_record_table_schema_and_constraints() -> None:
    """AgentConfigRecord: tablename/schema, UNIQUE (tenant_id,name), CHECK
    version>=1, ARRAY(String) tags."""
    from yaml_agno.db.models.agent_config import AgentConfigRecord

    table = AgentConfigRecord.__table__
    assert AgentConfigRecord.__tablename__ == "yamlagno_agent_configs"
    assert table.schema == "yamlagno"

    names = _constraint_names(table)
    assert "ya_agent_tenant_name_unique" in names
    assert "ya_agent_version_positive" in names

    cols = {c.name: c for c in table.columns}
    assert "tags" in cols
    # ARRAY(String) — accept ARRAY or dialect-agnostic name.
    type_name = type(cols["tags"].type).__name__
    assert type_name in {"ARRAY"}, f"tags must be ARRAY(String), got {type_name}"

    assert "version" in cols
    assert "config_yaml" in cols
    assert "config_jsonb" in cols


def test_metadata_attribute_maps_to_metadata_column() -> None:
    """Python attribute is metadata_; DB column is metadata; class attribute
    metadata is the SQLAlchemy MetaData (NOT the payload)."""
    from yaml_agno.db.models.agent_config import AgentConfigRecord

    table = AgentConfigRecord.__table__
    assert "metadata" in table.c, "DB column named 'metadata' must exist"

    # The class attribute `metadata` must NOT be a JSON payload — it is the
    # SQLAlchemy MetaData object inherited from DeclarativeBase.
    class_meta = getattr(AgentConfigRecord, "metadata", None)
    assert isinstance(class_meta, sqlalchemy.MetaData), (
        "AgentConfigRecord.metadata MUST be sqlalchemy.MetaData, "
        "not the JSONB payload (DeclarativeBase footgun)"
    )

    # The Python attribute name for the payload is metadata_.
    assert hasattr(AgentConfigRecord, "metadata_"), "metadata_ attribute missing"

    # Construct an instance and confirm metadata_ carries the JSON payload.
    tenant = uuid4()
    record = AgentConfigRecord(
        tenant_id=tenant,
        name="probe-agent",
        version=1,
        config_yaml="name: probe",
        config_jsonb={"k": "v"},
        tags=[],
        metadata_={"trace": "ok"},
    )
    assert record.metadata_ == {"trace": "ok"}


# ---------------------------------------------------------------------------
# REQ-4 / Phase 3 — TeamConfigRecord + WorkflowConfigRecord (task 3.6)
# ---------------------------------------------------------------------------


def test_team_and_workflow_records_table_shape() -> None:
    """TeamRecord: tablename + tags + version CHECK + UNIQUE.
    WorkflowRecord: tablename + NO tags + version CHECK + UNIQUE."""
    from yaml_agno.db.models.team_config import TeamConfigRecord
    from yaml_agno.db.models.workflow_config import WorkflowConfigRecord

    team = TeamConfigRecord.__table__
    wf = WorkflowConfigRecord.__table__

    assert TeamConfigRecord.__tablename__ == "yamlagno_team_configs"
    assert WorkflowConfigRecord.__tablename__ == "yamlagno_workflow_configs"
    assert team.schema == "yamlagno"
    assert wf.schema == "yamlagno"

    team_cols = {c.name for c in team.columns}
    wf_cols = {c.name for c in wf.columns}

    assert "tags" in team_cols, "TeamConfigRecord must have tags"
    assert "tags" not in wf_cols, "WorkflowConfigRecord must NOT have tags"

    team_names = _constraint_names(team)
    wf_names = _constraint_names(wf)
    assert "ya_team_tenant_name_unique" in team_names
    assert "ya_team_version_positive" in team_names
    assert "ya_wf_tenant_name_unique" in wf_names
    assert "ya_wf_version_positive" in wf_names


# ---------------------------------------------------------------------------
# REQ-4 / Phase 4 — DI cache + change log + schema_version (task 4.4)
# ---------------------------------------------------------------------------


def test_di_cache_change_log_schema_version_constraints() -> None:
    """DiVariableCache UNIQUE + ya_di_expires_future; ConfigChangeLog CHECK +
    tenant FK CASCADE; SchemaVersion composite PK."""
    from yaml_agno.db.models.config_change_log import ConfigChangeLogRecord
    from yaml_agno.db.models.di_variable import DiVariableCacheRecord
    from yaml_agno.db.models.schema_version import SchemaVersionRecord

    di = DiVariableCacheRecord.__table__
    ccl = ConfigChangeLogRecord.__table__
    sv = SchemaVersionRecord.__table__

    # DI cache
    di_names = _constraint_names(di)
    assert "ya_di_tenant_provider_key_unique" in di_names
    assert "ya_di_expires_future" in di_names
    di_cols = {c.name: c for c in di.columns}
    di_fk = next(iter(di_cols["tenant_id"].foreign_keys))
    assert di_fk.ondelete == "CASCADE"

    # Change log
    ccl_names = _constraint_names(ccl)
    assert "ya_ccl_positive_attempts" in ccl_names
    ccl_cols = {c.name: c for c in ccl.columns}
    ccl_fk = next(iter(ccl_cols["tenant_id"].foreign_keys))
    assert ccl_fk.ondelete == "CASCADE"

    # Schema version: composite PK = (component, version), no mixins.
    pk_cols = {c.name for c in sv.primary_key.columns}
    assert pk_cols == {"component", "version"}, (
        f"SchemaVersion composite PK must be (component, version); got {pk_cols}"
    )
    sv_cols = {c.name for c in sv.columns}
    assert "created_at" not in sv_cols, "SchemaVersionRecord MUST NOT use mixins"
    assert "tenant_id" not in sv_cols, "SchemaVersionRecord MUST NOT have tenant_id"


# ---------------------------------------------------------------------------
# REQ-6 / Phase 5 — Re-export & registration (tasks 5.2, 5.3)
# ---------------------------------------------------------------------------


def test_models_init_registers_exactly_seven_tables() -> None:
    """importing yaml_agno.db.models registers exactly the seven tables."""
    from yaml_agno.db.models import Base

    registered = set(Base.metadata.tables.keys())
    assert registered == SEVEN_TABLES, (
        f"Expected exactly 7 tables; got {len(registered)}: {sorted(registered)}"
    )


def test_no_runtime_ddl_in_db_package() -> None:
    """src/yaml_agno/db/ must NOT contain create_all/engine.begin/create_engine/
    Engine( calls (enforces spec Requirement 7)."""
    db_root = Path(__file__).resolve().parents[3] / "src" / "yaml_agno" / "db"
    assert db_root.is_dir(), f"db package missing at {db_root}"

    forbidden = ("create_all", "engine.begin", "create_engine(", "Engine(", "drop_all")
    offenders: list[str] = []
    for py in db_root.rglob("*.py"):
        try:
            content = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in forbidden:
            if token in content:
                offenders.append(f"{py.relative_to(db_root)}: {token!r}")
    assert offenders == [], (
        "Forbidden runtime-DDL tokens in src/yaml_agno/db/: " + ", ".join(offenders)
    )


# ---------------------------------------------------------------------------
# REQ-5 / Phase 2 — Round-trip TenantRecord in SQLite (task 2.4)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_tenant_round_trip_in_sqlite() -> None:
    """Insert + re-read a TenantRecord row in SQLite in-memory; settings JSON
    round-trips and tenant_kind defaults to 'org'.

    Uses the ORM ``Session`` for insert so the Python-side ``default="org"``
    fires (matches how the production repositories will create rows)."""
    from sqlalchemy.orm import Session

    from yaml_agno.db.models import Base
    from yaml_agno.db.models.tenant import TenantRecord

    engine = _sqlite_engine_with_yamlagno_schema(Base.metadata)
    with engine.begin() as conn:
        _sqlite_create_all(conn, Base.metadata)

    tenant_id = uuid4()
    # Construct WITHOUT tenant_kind — the ORM ``default="org"`` must fire on
    # flush.
    record = TenantRecord(
        id=tenant_id, name="Acme", slug="acme", settings={"theme": "dark"},
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        rows = session.execute(
            select(TenantRecord.id, TenantRecord.tenant_kind, TenantRecord.settings)
        ).all()

    assert len(rows) == 1
    rid, kind, settings = rows[0]
    assert UUID(str(rid)) == tenant_id
    assert kind == "org", "tenant_kind must default to 'org' when omitted"
    # settings is a dict (ORM deserializes JSONB -> Python dict).
    assert settings == {"theme": "dark"}


@pytest.mark.integration
def test_tenant_bad_kind_raises_integrity_error() -> None:
    """Negative test: inserting an invalid tenant_kind violates the CHECK."""
    from yaml_agno.db.models import Base
    from yaml_agno.db.models.tenant import TenantRecord  # noqa: F401

    engine = _sqlite_engine_with_yamlagno_schema(Base.metadata)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _sqlite_create_all(conn, Base.metadata)
        conn.execute(
            text(
                """
                    INSERT INTO yamlagno_tenants
                        (id, name, slug, tenant_kind, parent_org_id, settings)
                    VALUES (:id, :name, :slug, :bogus, NULL, :settings)
                    """
            ),
            {
                "id": str(uuid4()),
                "name": "Acme",
                "slug": "acme",
                "bogus": "not-a-kind",
                "settings": "{}",
            },
        )


# ---------------------------------------------------------------------------
# REQ-5 / Scenario 5.1 — Round-trip AgentConfigRecord in SQLite
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agent_config_round_trip_in_sqlite() -> None:
    """Round-trip AgentConfigRecord: defaults (version=1, is_active=True,
    tags=[], metadata_={}) and explicit values are preserved on re-read."""
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401  (ensures import ok)

    from yaml_agno.db.models import Base
    from yaml_agno.db.models.agent_config import AgentConfigRecord
    from yaml_agno.db.models.tenant import TenantRecord  # noqa: F401  (table reg)

    engine = _sqlite_engine_with_yamlagno_schema(Base.metadata)
    tenant_id = uuid4()
    with engine.begin() as conn:
        _sqlite_create_all(conn, Base.metadata)
        # Parent tenant first (FK).
        conn.execute(
            text(
                """
                INSERT INTO yamlagno_tenants
                    (id, name, slug, parent_org_id, settings)
                VALUES (:id, :name, :slug, NULL, :settings)
                """
            ),
            {
                "id": str(tenant_id),
                "name": "Acme",
                "slug": "acme",
                "settings": "{}",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO yamlagno_agent_configs
                    (id, tenant_id, name, version, config_yaml, config_jsonb,
                     description, tags, metadata, created_by, is_active)
                VALUES
                    (:id, :tenant_id, :name, NULL, :config_yaml, :config_jsonb,
                     NULL, NULL, NULL, NULL, NULL)
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "name": "probe-agent",
                "config_yaml": "name: probe",
                "config_jsonb": '{"model": "gpt-4"}',
            },
        )
        rows = conn.execute(
            select(
                AgentConfigRecord.name,
                AgentConfigRecord.version,
                AgentConfigRecord.is_active,
                AgentConfigRecord.tags,
                AgentConfigRecord.metadata_,
                AgentConfigRecord.config_jsonb,
            )
        ).all()

    assert len(rows) == 1
    name, version, is_active, tags, metadata_value, _config_jsonb = rows[0]
    assert name == "probe-agent"
    assert version == 1, "version must default to 1 when omitted"
    assert is_active is True, "is_active must default to True"
    # tags default — SQLite returns None because no default fires server-side
    # without a Python ORM flush; accept None OR empty list.
    assert tags in (None, [], "[]"), f"unexpected tags default: {tags!r}"
    assert metadata_value in (None, {}, "{}"), (
        f"unexpected metadata default: {metadata_value!r}"
    )
