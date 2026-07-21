---
change: persistence-orm-models
spec: SPEC_03
status: proposed
artifact_store: hybrid
depends_on: []
slice: "A (SPEC_03 §3 — ORM models foundation)"
---

# Proposal: Persistence ORM Models (SPEC_03 Slice A)

## Intent

SPEC_03 §3 defines seven `yamlagno_*` config-store tables (tenants, agent/team/
workflow configs, DI variable cache, config change log, schema versions) that
must exist as SQLAlchemy 2.0 `DeclarativeBase` entities before any downstream
SPEC_03 slice (provisioner, repository wrappers, TenantResolver, bootstrap) can
land. Today no `src/yaml_agno/db/` package exists; downstream slices (B
provisioner, C repository, D tenant resolver) all import `Base` and the seven
records from this slice.

This slice delivers **only the ORM models**: the declarative `Base`, two shared
mixins, and the seven record classes — plus the unit tests that assert table
names, schema, column types, FK/CHECK/UNIQUE constraints, and the `metadata_`
trailing-underscore mapping. No DDL is executed at runtime in this slice; only
table creation tests against an in-memory SQLite engine.

## Scope

### In Scope

- `src/yaml_agno/db/__init__.py` (new package marker).
- `src/yaml_agno/db/base.py` (new): `Base(DeclarativeBase)`,
  `TimestampMixin` (`created_at`, `updated_at` with `server_default=NOW()` and
  `onupdate=NOW()`), `TenantMixin` (`tenant_id` FK to
  `yamlagno.yamlagno_tenants.id` `ON DELETE CASCADE`, non-null).
- `src/yaml_agno/db/models/` (new package) with seven files:
  - `tenant.py` → `TenantRecord` (`yamlagno_tenants`): UUID PK, slug UNIQUE +
    CHECK `^[a-z0-9-]+$`, `tenant_kind` CHECK in `('org','org_user_roles','user')`,
    self-referential `parent_org_id` FK `ON DELETE SET NULL`, `settings` JSONB,
    CHECK `org_has_no_parent`.
  - `agent_config.py` → `AgentConfigRecord` (`yamlagno_agent_configs`): UUID PK,
    `tenant_id` via `TenantMixin`, `name`+`version`, `config_yaml` TEXT,
    `config_jsonb` JSONB, `tags` ARRAY(TEXT), `metadata_` (attribute) → column
    `metadata` (JSONB), `created_by`, `is_active` default TRUE, UNIQUE
    `(tenant_id, name)`, CHECK `version >= 1`.
  - `team_config.py` → `TeamConfigRecord` (`yamlagno_team_configs`): same shape
    as agent_config (tags + metadata_) with UNIQUE + version CHECK.
  - `workflow_config.py` → `WorkflowConfigRecord` (`yamlagno_workflow_configs`):
    same shape as agent_config **without** `tags` column (per SPEC_03 §3.4).
  - `di_variable.py` → `DiVariableCacheRecord` (`yamlagno_di_variable_cache`):
    `provider_name`, `variable_key`, `variable_value` JSONB, `metadata_`,
    `expires_at`, UNIQUE `(tenant_id, provider_name, variable_key)`, CHECK
    `expires_at > created_at`.
  - `config_change_log.py` → `ConfigChangeLogRecord`
    (`yamlagno_config_change_log`): `event_type`, `event_version` default `'1.0'`,
    `payload` JSONB, `tenant_id` (no `TenantMixin` — also has correlation/causation
    UUIDs), `processed_at`, `processing_attempts` default 0, CHECK
    `processing_attempts >= 0`.
  - `schema_version.py` → `SchemaVersionRecord` (`yamlagno_schema_versions`):
    composite PK `(component, version)`, `applied_at` server_default NOW() — no
    mixins, no tenant.
- `src/yaml_agno/db/models/__init__.py`: re-export `Base` + all 7 records (so
  downstream `from yaml_agno.db.models import AgentConfigRecord` works and
  `Base.metadata` includes every table).
- `tests/unit/db/__init__.py` + `tests/unit/db/test_orm_models.py` (new):
  table creation in an in-memory engine, table names + schema == `"yamlagno"`,
  column types/dialects, FK targets, CHECK/UNIQUE constraints, `metadata_`
  attribute→column mapping, mixin propagation, default values.

### Out of Scope (deferred to later SPEC_03 slices)

- Slice B: `ConfigStoreProvisioner` (DDL execution against Postgres, version
  marking) — SPEC_03 §6.1.
- Slice C: `AgentConfigRepository` and friends (core-cenf `GenericRepository`
  wrappers, transaction usage) — SPEC_03 §7.2.
- Slice D: `TenantResolver` — SPEC_03 §5.2.
- Slice E: `build_database_manager` bootstrap on core-cenf — SPEC_03 §7.1.
- Postgres-specific GIN/partial indexes (`idx_yamlagno_agent_configs_tags`,
  `idx_yamlagno_ccl_pending`): ORM `create_all()` against SQLite in unit tests
  cannot assert GIN; index definitions are deferred to the provisioner slice
  which runs against real Postgres. This slice asserts the B-tree FK + UNIQUE +
  CHECK constraints only.

## Approach

- **Declarative ORM, not Agno Core**: per SPEC_03 §3 @ai-directive, the core-cenf
  `SQLAlchemyAdapter` requires `DeclarativeBase` entities. We diverge from
  Agno's `Table()` Core approach on purpose; documented in code comments.
- **Two mixins reduce duplication**: `TimestampMixin` and `TenantMixin` cover
  the six tables that need both; `ConfigChangeLogRecord` and
  `SchemaVersionRecord` skip one or both. Mixins are plain
  `dataclass`-style `Mapped` declarations (no custom `__init__`).
- **`metadata_` trailing underscore**: SPEC_03 §3.2 @ai-directive — the Python
  attribute is `metadata_` because `metadata` collides with
  `DeclarativeBase.metadata` (the SQLAlchemy `MetaData`). The DB column is
  `metadata`. A code comment + unit test enforce this.
- **Dialect-portable tests**: tests use SQLite in-memory + SQLAlchemy's PG
  dialect fallback. JSONB columns are declared with
  `from sqlalchemy.dialects.postgresql import JSONB`; SQLite's pysqlite treats
  them as TEXT via SQLAlchemy's type compilation. ARRAY(String) is exercised at
  the type-definition level only (not persisted in SQLite).
- **One `Base`, one `metadata`**: `models/__init__.py` imports every record so
  `Base.metadata.tables` contains all seven tables — required by the future
  provisioner's `Base.metadata.create_all(checkfirst=True)`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| SQLite can't enforce PG-specific GIN/partial indexes or ARRAY | Unit tests assert type definitions and metadata, not PG-only index classes; deferred to provisioner slice. |
| `metadata_` rename is a footgun | Code comment + explicit unit test asserting `record.metadata_` ≠ `Base.metadata`. |
| Mixin inheritance vs. `__table_args__` ordering | Each record passes `{"schema": "yamlagno"}` as the **last** `__table_args__` entry; CHECK constraints precede it. Unit test asserts `__table__.schema`. |
| Self-referential FK on `TenantRecord.parent_org_id` | Use `ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="SET NULL")` with string target (matches SPEC_03 §3.1). |

## Rollback Plan

This slice only **adds** new files; it does not modify existing code. Rollback =
delete `src/yaml_agno/db/` and `tests/unit/db/`. No migration, no data, no
runtime entry point touched. Downstream slices (B–E) have not been written, so
nothing depends on these files yet.

## Success Criteria

- `python -m pytest tests/unit/db/test_orm_models.py` passes with 100% coverage
  of the `db/` package.
- `Base.metadata.tables` contains exactly the seven `yamlagno_*` table names.
- Every record's `__table__.schema == "yamlagno"`.
- `TenantRecord` self-FK, `AgentConfigRecord` UNIQUE + CHECK, and the
  `metadata_` → `metadata` mapping all verified by unit tests.
- No runtime DDL is performed by this slice (no `create_all` in production
  code; only inside unit tests' in-memory engine fixtures).
