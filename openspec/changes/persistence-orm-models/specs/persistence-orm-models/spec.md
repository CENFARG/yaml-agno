# Spec: persistence-orm-models

## Requirements

### Requirement 1: DeclarativeBase package layout

The system SHALL provide a `yaml_agno.db` package with a single
`DeclarativeBase` subclass named `Base` (in `db/base.py`) that is the shared
metadata root for every `yamlagno_*` entity. The package SHALL be importable
without side effects (no engine, no session, no DDL at import time).

#### Scenario 1.1: Importing the package does not touch the database

- **GIVEN** a clean Python interpreter with `yaml_agno` installed
- **WHEN** `from yaml_agno.db.base import Base` is executed
- **THEN** no SQLAlchemy `Engine`, `Session`, or `create_all` call occurs
- **AND** `Base` is an instance of `sqlalchemy.orm.DeclarativeBase`

### Requirement 2: Shared mixins (TimestampMixin, TenantMixin)

The system SHALL provide two reusable mixins in `db/base.py`:
`TimestampMixin` (declares non-null `created_at` and `updated_at`
`Mapped[datetime]` columns with `server_default=text("NOW()")` and
`onupdate=text("NOW()")` for `updated_at`) and `TenantMixin` (declares a
non-null `tenant_id: Mapped[UUID]` column with a `ForeignKey` to
`yamlagno.yamlagno_tenants.id` `ON DELETE CASCADE`).

#### Scenario 2.1: Mixin columns appear on concrete records

- **GIVEN** `AgentConfigRecord` inherits `TimestampMixin` and `TenantMixin`
- **WHEN** inspecting `AgentConfigRecord.__table__.columns`
- **THEN** `tenant_id`, `created_at`, and `updated_at` columns are present
- **AND** `tenant_id` is non-nullable with `ondelete="CASCADE"` on its FK

### Requirement 3: Seven `yamlagno_*` tables with `schema="yamlagno"`

The system SHALL define exactly seven ORM record classes — `TenantRecord`,
`AgentConfigRecord`, `TeamConfigRecord`, `WorkflowConfigRecord`,
`DiVariableCacheRecord`, `ConfigChangeLogRecord`, `SchemaVersionRecord` — each
declaring `__tablename__` with the `yamlagno_` prefix and `__table__.schema ==
"yamlagno"`. After importing `yaml_agno.db.models`, `Base.metadata.tables`
SHALL contain exactly these seven tables.

#### Scenario 3.1: All seven tables register on the shared Base

- **GIVEN** `from yaml_agno.db.models import Base`
- **WHEN** `Base.metadata.tables.keys()` is inspected
- **THEN** the set equals `{"yamlagno.tenant_tenants", ...}` (namespaced by
  schema) for all seven tables listed above
- **AND** no additional tables are registered

### Requirement 4: Column types, FKs, and constraints per SPEC_03 §3

Each record SHALL declare the columns, foreign keys, UNIQUE constraints, and
CHECK constraints exactly as specified in SPEC_03 §3.1–§3.7. In particular:

- `TenantRecord`: UUID PK default `uuid4`, `name VARCHAR(255)` non-null, `slug
  VARCHAR(100)` non-null UNIQUE with CHECK `slug ~ '^[a-z0-9-]+$'`,
  `tenant_kind VARCHAR(20)` default `'org'` with CHECK in
  `('org','org_user_roles','user')`, self-FK `parent_org_id` `ON DELETE SET
  NULL`, `settings JSONB` non-null default `{}`, CHECK `org_has_no_parent`
  (`tenant_kind <> 'org' OR parent_org_id IS NULL`).
- `AgentConfigRecord`: UUID PK, `TenantMixin`, `name VARCHAR(100)` non-null,
  `version INTEGER` default 1 CHECK `version >= 1`, `config_yaml TEXT`
  non-null, `config_jsonb JSONB` non-null, `description TEXT` nullable, `tags
  ARRAY(String)` non-null default `{}`, `metadata_` (Python attr) mapped to
  column `metadata` JSONB non-null default `{}`, `created_by VARCHAR(255)`
  nullable, `is_active BOOLEAN` non-null default TRUE, UNIQUE
  `(tenant_id, name)`.
- `TeamConfigRecord`: same column set and constraints as
  `AgentConfigRecord` with `__tablename__ = "yamlagno_team_configs"` and
  UNIQUE name `ya_team_tenant_name_unique`.
- `WorkflowConfigRecord`: same as `AgentConfigRecord` **without** `tags` and
  with `__tablename__ = "yamlagno_workflow_configs"`, UNIQUE
  `ya_wf_tenant_name_unique`.
- `DiVariableCacheRecord`: UUID PK, `TenantMixin`, `provider_name VARCHAR(100)`
  non-null, `variable_key VARCHAR(255)` non-null, `variable_value JSONB`
  non-null, `metadata_` → column `metadata` JSONB non-null default `{}`,
  `expires_at TIMESTAMPTZ` non-null, UNIQUE
  `(tenant_id, provider_name, variable_key)`, CHECK
  `expires_at > created_at`.
- `ConfigChangeLogRecord`: UUID PK, `event_type VARCHAR(255)` non-null,
  `event_version VARCHAR(50)` default `'1.0'`, `payload JSONB` non-null,
  `tenant_id` (no `TenantMixin`; explicit FK `ON DELETE CASCADE`),
  `correlation_id UUID` nullable, `causation_id UUID` nullable,
  `TimestampMixin` (`created_at`, `updated_at`), `processed_at TIMESTAMPTZ`
  nullable, `processing_attempts INTEGER` default 0 CHECK `>= 0`.
- `SchemaVersionRecord`: composite PK `(component VARCHAR(100), version
  VARCHAR(50))`, `applied_at TIMESTAMPTZ` non-null server_default NOW(); **no
  mixins**.

#### Scenario 4.1: TenantRecord enforces slug format and tenant_kind

- **GIVEN** an in-memory engine with the seven tables created
- **WHEN** a `TenantRecord(name="X", slug="UPPER_CASE")` is constructed
- **THEN** the `slug_format` CHECK constraint exists on the table
- **AND** the `valid_tenant_kind` CHECK exists enumerating
  `('org','org_user_roles','user')`
- **AND** the `org_has_no_parent` CHECK exists

#### Scenario 4.2: AgentConfigRecord has UNIQUE (tenant_id, name) and version CHECK

- **GIVEN** `AgentConfigRecord.__table__`
- **WHEN** constraints are inspected
- **THEN** a UNIQUE constraint named `ya_agent_tenant_name_unique` covers
  exactly `(tenant_id, name)`
- **AND** a CHECK constraint `ya_agent_version_positive` asserts `version >= 1`

#### Scenario 4.3: metadata_ attribute maps to metadata column

- **GIVEN** an `AgentConfigRecord` instance
- **WHEN** accessing `record.metadata_`
- **THEN** it returns the JSONB payload value
- **AND** `AgentConfigRecord.__table__.c.metadata` exists (the DB column)
- **AND** `record.metadata` is **not** the JSONB payload (it is the SQLAlchemy
  `MetaData` on the class)

### Requirement 5: Tables create cleanly in a SQLite in-memory engine

For unit-test purposes, every record's table definition SHALL compile and
create against a SQLite in-memory engine (`create_engine("sqlite:///:memory:")`)
without raising dialect-incompatibility errors for the columns, FKs, and CHECK
constraints in scope (Postgres-only GIN/partial indexes are excluded from this
requirement). All non-null columns with defaults SHALL accept their default
values on insert.

#### Scenario 5.1: Round-trip insert and read of an AgentConfigRecord

- **GIVEN** a SQLite in-memory engine with all seven tables created
- **WHEN** a row is inserted into `yamlagno_agent_configs` with all required
  columns populated (including `config_jsonb`, `config_yaml`, `tags`,
  `metadata`)
- **AND** the row is re-read via `select(AgentConfigRecord)`
- **THEN** the re-read row's `name`, `version`, `is_active`, `tags`, and
  `metadata_` match the inserted values
- **AND** `is_active` defaults to `True` when omitted on insert

### Requirement 6: Re-export surface

`yaml_agno.db.models.__init__` SHALL re-export `Base` and all seven record
classes so downstream code can write
`from yaml_agno.db.models import AgentConfigRecord, Base` without reaching into
individual modules. Importing `yaml_agno.db.models` SHALL register every table
on `Base.metadata`.

#### Scenario 6.1: Single import line yields all records

- **GIVEN** the interpreter has imported `yaml_agno.db.models`
- **WHEN** `from yaml_agno.db.models import (Base, TenantRecord,
  AgentConfigRecord, TeamConfigRecord, WorkflowConfigRecord,
  DiVariableCacheRecord, ConfigChangeLogRecord, SchemaVersionRecord)` is run
- **THEN** all nine names resolve
- **AND** `len(Base.metadata.tables) == 7`

### Requirement 7: No runtime DDL or engine binding in this slice

The slice SHALL NOT add any module that calls `Base.metadata.create_all`,
`engine.begin()`, or instantiates a `sqlalchemy.Engine` outside of unit-test
fixtures. All runtime persistence wiring is deferred to SPEC_03 slices B–E.

#### Scenario 7.1: No production module triggers DDL

- **GIVEN** the `src/yaml_agno/db/` tree (excluding tests)
- **WHEN** each module is imported in turn
- **THEN** no `create_all`, `drop_all`, `engine.begin`, `Engine(`, or
  `create_engine(` call is executed
- **AND** only type/class/`__init__` definitions run at import time
