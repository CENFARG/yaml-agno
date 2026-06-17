---
Spec_ID: "SPEC_03"
Title: "Persistence Architecture - Config Store on core-cenf DatabaseManager"
Version: "0.3.0-iter2"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#PostgreSQL", "#SQLAlchemy", "#core-cenf", "#MultiTenant", "#ConfigStore"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02"]
Last_Updated: "2026-06-17"
Revision_Note: "Iter 2 - deep rewrite integrating the real core-cenf package (core_infrastructure). SPEC_03 no longer reimplements a TransactionManager or repositories: it CONSUMES DatabaseManager/TransactionScope/GenericRepository[T] from core-cenf and only declares DeclarativeBase ORM models. Dropped agent_sessions/session_contexts entirely (Agno runtime owns those in agno_*). All config-store tables renamed to the yamlagno_* prefix in a dedicated SQL schema to avoid collision with Agno's agno_* tables. Added environment-vs-execution variable classification, per-table JSON row example + illustrative query, three-level multi-tenant model (modeled, not MVP), auto-provisioning with checkfirst mirroring Agno, and a config_change_log retention/compaction future-feature section."
---

# SPEC_03_PERSISTENCE_ARCHITECTURE

> **Purpose**: Define the physical persistence schema of the **yaml-agno control-plane config store** and how it is built **on top of the core-cenf `DatabaseManager`**. Runtime persistence of agents/sessions/memory/run events is owned by Agno (in `agno_*`); yaml-agno does not persist runtime state. yaml-agno only persists declarative configs (tenants, `*_configs`, DI cache, audit) and consumes the core-cenf transaction/repository abstractions instead of reimplementing them.

---

## 1. PERSISTENCE STRATEGY AND BOUNDARY

### 1.1 Three-layer frontier (no overlap)

| Layer | Owner | Tables | What it stores |
|-------|-------|--------|----------------|
| **core-cenf DatabaseManager** | `core_infrastructure` package | (none of its own) | Async SQLAlchemy 2.0 engine, `TransactionScope`, `GenericRepository[T]`. yaml-agno depends on the **Protocol**, never on the concrete adapter. |
| **yaml-agno config store** | this SPEC | `yamlagno_*` (dedicated SQL schema) | Tenants, `agent/team/workflow_configs`, `di_variable_cache`, `config_change_log`, `yamlagno_schema_versions`. Declarative ORM (`DeclarativeBase`) required by the core adapter. |
| **Agno runtime** | Agno framework | `agno_*` (its own schema) | Sessions (`agno_sessions`), memory, run events, evals, metrics, schedules. Provisioned by Agno via `db=` / `auto_provision_dbs`. |

> **@ai-directive (no reimplementation)**: SPEC_03 does **not** define a `TransactionManager`, a `BaseRepository`, or raw `AsyncSession` usage. yaml-agno calls `async with db.transaction() as tx:` and `db.get_repository(EntityType)` from core-cenf. The only thing this SPEC defines is **ORM models** (the `DeclarativeBase` entities the generic repository operates on) and the **schema lifecycle** (auto-provisioning). Everything else is consumed from `core_infrastructure`.

### 1.2 Storage architecture (mermaid)

```mermaid
graph TB
    subgraph APP ["yaml-agno application"]
        YAML["YAML file (SPEC_02 schema)"] --> VAL["Pydantic validation<br/>AgentConfig / TeamConfig / WorkflowConfig"]
        VAL --> REC["AgentConfigRecord<br/>DeclarativeBase ORM entity"]
    end

    subgraph CORE ["core-cenf (core_infrastructure)"]
        DM["DatabaseManager (Protocol)"]
        TX["TransactionScope<br/>commit / rollback (idempotent)"]
        GR["GenericRepository[T]<br/>find_by_id / find_all / insert / update / delete / count"]
        SA["SQLAlchemyAdapter<br/>async SQLAlchemy 2.0 + asyncpg"]
        MEM["MemoryDatabaseAdapter<br/>tests"]
    end

    subgraph STORE ["yaml-agno config store (SQL schema: yamlagno)"]
        T1["yamlagno_tenants"]
        T2["yamlagno_agent_configs"]
        T3["yamlagno_team_configs"]
        T4["yamlagno_workflow_configs"]
        T5["yamlagno_di_variable_cache"]
        T6["yamlagno_config_change_log"]
        T7["yamlagno_schema_versions"]
    end

    subgraph AGNO ["Agno runtime (separate)"]
        AR["agno_sessions / agno_memory / run events<br/>via db= PostgresDb/RedisDb"]
    end

    REC --> GR
    GR --> TX
    TX --> DM
    DM --> SA
    SA --> STORE
    DM -.-> MEM
    AR -.->|"NOT owned by yaml-agno"| STORE
```

> **@ai-directive**: `db.get_repository(T)` MUST be called **inside** `async with db.transaction()` because the core `SQLAlchemyAdapter` binds the session to a contextvar. The repository is obtained per-transaction; it is not a long-lived singleton.

### 1.3 Data-to-storage mapping (config store only)

| Data type | Primary storage | Backup | Retention | Justification |
|-----------|-----------------|--------|-----------|----------------|
| Tenant metadata | `yamlagno_tenants` | Git | Permanent | Identity root for the config store |
| Agent / Team / Workflow configs | `yamlagno_*_configs` | Git (YAML) | Permanent | Config store; JSONB validated against SPEC_02 |
| DI variable cache | `yamlagno_di_variable_cache` | Source DB/API | TTL (1h default) | Cached resolved values with expiry |
| Config audit log | `yamlagno_config_change_log` | S3 archive (future) | `retention_days` (future) | Mutable/append-heavy; compacted eventually |
| Schema version tracking | `yamlagno_schema_versions` | - | Permanent | Auto-provisioning bookkeeping |

> Runtime data (sessions, messages, memory, run events) is NOT mapped here. It lives in `agno_*`, owned by Agno. yaml-agno does not retain, mirror or partition it.

---

## 2. ENVIRONMENT vs EXECUTION VARIABLES

> **@ai-directive (variable classification rule)**: Every configuration knob belongs to exactly one of two classes. **Environment** knobs describe *where and how the process runs* (resolved at bootstrap via `ConfigManager`/`SecretManager` from `core_infrastructure`, never read directly from `os.environ`). **Execution** knobs describe *operational behavior of running agents* and are themselves persisted **in the config store** (DB rows), not in environment variables.

| Variable (config key) | Class | Resolved via | Scope | Notes |
|-----------------------|-------|--------------|-------|-------|
| `database.dsn` | **Environment** | `config.get_string` / `SecretManager` | Process | Postgres async DSN consumed by `SQLAlchemyAdapter` |
| `database.pool_size`, `database.max_overflow` | **Environment** | `config.get_number` | Process | Engine pool tuning |
| `app.env` (dev/staging/prod) | **Environment** | `config.get_string` | Process | Selects adapter, gates dotenv secret adapter |
| `log.level` | **Environment** | `config.get_string` | Process | Forwarded to core logging |
| `tenant.resolution_mode` | **Environment** | `config.get_string` | Process | `org` / `org_user_roles` / `user` (§5); selects TenantResolver strategy |
| `secrets.*` (DB password, vault token) | **Environment** | `SecretManager.get_secret` | Process | Never in env vars; Zero-Trust |
| `configstore.auto_provision` | **Environment** | `config.get_bool` | Process | `true` (default) = `checkfirst` create; `false` = managed schema (§6) |
| `configstore.schema` | **Environment** | `config.get_string` | Process | SQL schema name (`yamlagno`); separate from Agno's |
| `configstore.replication_mode` | **Environment** | `config.get_string` | Process | `sync` (default) / `async`; see §9 |
| `configstore.retention_days` | **Environment** | `config.get_int` | Process | Future: drop partitions older than N days (§8) |
| Agent/team/workflow YAML configs | **Execution** | DB rows (`yamlagno_*_configs`) | Per-tenant | Persisted JSONB; the actual agent behavior |
| `is_active` flag on a config | **Execution** | DB column | Per-row | Enable/disable a config without deleting |
| DI cache TTL per provider | **Execution** | `yamlagno_di_variable_cache.expires_at` | Per-row | Cached value lifetime |
| `tags` / `metadata` on a config | **Execution** | DB columns | Per-row | Organization of persisted configs |

> **Rule**: a value that changes agent **behavior** (model, instructions, tools, retention of a specific agent's logs) is **Execution** and lives in the DB. A value that changes **how the process boots and connects** (DSN, env name, pool size, resolution mode) is **Environment** and lives in `ConfigManager`/`SecretManager`.

---

## 3. SCHEMA: config-store tables (DeclarativeBase)

> **@ai-directive (declarative ORM is mandatory)**: The core `SQLAlchemyAdapter` requires entities to be `DeclarativeBase` subclasses (SQLAlchemy 2.0 ORM). This differs from Agno, which builds its `agno_*` tables with **SQLAlchemy Core** (raw `Table` + dicts). yaml-agno must use declarative ORM because it rides on the core adapter; do not attempt to mimic Agno's Core-only approach for these tables.

> **@ai-directive (prefix + schema)**: Every config-store table uses the prefix `yamlagno_` and lives in the dedicated SQL schema `yamlagno` — distinct from Agno's `agno_*` tables and schema. This prevents any collision when both stores share the same Postgres database. The prefix is the single source of truth for table names in repositories and auto-provisioning.

> **@ai-directive (SSOT for the JSONB payload)**: Each `*_configs` table has a `config_jsonb` column. That JSONB MUST validate against the corresponding Pydantic schema from **SPEC_02** (`AgentConfig` / `TeamConfig` / `WorkflowConfig`), which is **imported, never redefined** here. The ORM entity below is the **persistence record** (`AgentConfigRecord`), not the Pydantic `AgentConfig`. They are different objects by design.

### 3.1 Table: `yamlagno_tenants`

**Purpose**: Tenant metadata (organizations / direct users). Root identity for the config store and the anchor for multi-tenant isolation (§5).

```sql
-- SQL schema: yamlagno
CREATE TABLE yamlagno.yamlagno_tenants (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    slug          VARCHAR(100) NOT NULL UNIQUE,

    -- Multi-tenant model columns (§5); modeled from day 1, enforced post-MVP.
    tenant_kind   VARCHAR(20)  NOT NULL DEFAULT 'org',
        -- 'org' | 'org_user_roles' | 'user'
    parent_org_id UUID REFERENCES yamlagno.yamlagno_tenants(id) ON DELETE SET NULL,
    settings      JSONB        NOT NULL DEFAULT '{}',

    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT slug_format      CHECK (slug ~ '^[a-z0-9-]+$'),
    CONSTRAINT valid_tenant_kind CHECK (tenant_kind IN ('org','org_user_roles','user'))
);
CREATE INDEX idx_yamlagno_tenants_slug ON yamlagno.yamlagno_tenants(slug);
```

**ORM model**:

```python
# yaml-agno/src/db/models/tenant.py
"""Tenant ORM entity for the yaml-agno config store (DeclarativeBase). Consumed by
core-cenf GenericRepository[TenantRecord]; yaml-agno does not manage its own session."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all yamlagno_ ORM entities."""


class TenantRecord(Base):
    """Persistence record for a tenant row (yamlagno_tenants).

    Attributes:
        id: Primary key (UUID v4).
        name: Human-readable tenant name.
        slug: URL-safe unique slug.
        tenant_kind: Multi-tenant strategy level (§5): org | org_user_roles | user.
        parent_org_id: Parent organization when tenant_kind is org_user_roles/user.
        settings: Free-form tenant settings JSONB.
    """

    __tablename__ = "yamlagno_tenants"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9-]+$'", name="slug_format"),
        CheckConstraint(
            "tenant_kind IN ('org','org_user_roles','user')", name="valid_tenant_kind"
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    tenant_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="org")
    parent_org_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), onupdate=text("NOW()"), nullable=False,
    )
```

**Example JSON row**:
```json
{
  "id": "8b1c...e4",
  "name": "CENF",
  "slug": "cenf",
  "tenant_kind": "org",
  "parent_org_id": null,
  "settings": {"plan": "internal", "default_model": "openai/gpt-4o"},
  "created_at": "2026-06-17T10:00:00Z",
  "updated_at": "2026-06-17T10:00:00Z"
}
```

**Illustrative query**:
```sql
-- Resolve a tenant row by slug for the TenantResolver (§5).
SELECT id, tenant_kind, parent_org_id, settings
FROM yamlagno.yamlagno_tenants
WHERE slug = :slug;
```

### 3.2 Table: `yamlagno_agent_configs`

**Purpose**: Persisted agent configurations per tenant. The `config_jsonb` payload validates against the Pydantic `AgentConfig` from SPEC_02 (SSOT, imported).

```sql
CREATE TABLE yamlagno.yamlagno_agent_configs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES yamlagno.yamlagno_tenants(id) ON DELETE CASCADE,

    name          VARCHAR(100) NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,

    config_yaml   TEXT   NOT NULL,
    config_jsonb  JSONB  NOT NULL,

    description   TEXT,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    metadata      JSONB  NOT NULL DEFAULT '{}',

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by    VARCHAR(255),

    is_active     BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ya_agent_tenant_name_unique UNIQUE (tenant_id, name),
    CONSTRAINT ya_agent_version_positive  CHECK (version >= 1)
);

CREATE INDEX idx_yamlagno_agent_configs_tenant_name
    ON yamlagno.yamlagno_agent_configs(tenant_id, name);
CREATE INDEX idx_yamlagno_agent_configs_tags
    ON yamlagno.yamlagno_agent_configs USING GIN(tags);
CREATE INDEX idx_yamlagno_agent_configs_active
    ON yamlagno.yamlagno_agent_configs(tenant_id, is_active);
```

**ORM model** (excerpt; same `Base` as §3.1):

```python
# yaml-agno/src/db/models/agent_config.py
"""AgentConfigRecord ORM entity. config_jsonb validates against the Pydantic
AgentConfig (SPEC_02, imported). This is the persistence row, NOT the schema."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Boolean, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.models.tenant import Base


class AgentConfigRecord(Base):
    """Persistence record for yamlagno_agent_configs.

    The Pydantic ``AgentConfig`` (SPEC_02) is the validator for ``config_jsonb``;
    this class only maps the row. Do not duplicate schema fields here.
    """

    __tablename__ = "yamlagno_agent_configs"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ya_agent_version_positive"),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_yaml: Mapped[str] = mapped_column(nullable=False)
    config_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(default=None)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=text("NOW()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), onupdate=text("NOW()"), nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

**Example JSON row** (`config_jsonb` payload validates against `AgentConfig`):
```json
{
  "id": "a1f...c2",
  "tenant_id": "8b1c...e4",
  "name": "facturacion_afip",
  "version": 1,
  "config_yaml": "agent:\n  name: facturacion_afip\n  model: openai/gpt-4o\n",
  "config_jsonb": {"agent": {"name": "facturacion_afip", "model": "openai/gpt-4o"}},
  "tags": ["fiscal", "afip"],
  "is_active": true,
  "created_at": "2026-06-17T10:05:00Z",
  "updated_at": "2026-06-17T10:05:00Z"
}
```

**Illustrative query**:
```sql
-- Active config lookup by tenant + name (used by AgentFactory via the repository).
SELECT id, config_yaml, config_jsonb
FROM yamlagno.yamlagno_agent_configs
WHERE tenant_id = :tenant_id AND name = :name AND is_active = TRUE;
-- Expected: Index Scan using idx_yamlagno_agent_configs_tenant_name + filter is_active.
```

### 3.3 Table: `yamlagno_team_configs`

**Purpose**: Persisted team configurations per tenant. `config_jsonb` validates against `TeamConfig` (SPEC_02, imported).

```sql
CREATE TABLE yamlagno.yamlagno_team_configs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES yamlagno.yamlagno_tenants(id) ON DELETE CASCADE,

    name          VARCHAR(100) NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,

    config_yaml   TEXT   NOT NULL,
    config_jsonb  JSONB  NOT NULL,

    description   TEXT,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    metadata      JSONB  NOT NULL DEFAULT '{}',

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ya_team_tenant_name_unique UNIQUE (tenant_id, name),
    CONSTRAINT ya_team_version_positive  CHECK (version >= 1)
);

CREATE INDEX idx_yamlagno_team_configs_tenant_name
    ON yamlagno.yamlagno_team_configs(tenant_id, name);
CREATE INDEX idx_yamlagno_team_configs_tags
    ON yamlagno.yamlagno_team_configs USING GIN(tags);
```

**ORM model**: `TeamConfigRecord(Base)` mirrors `AgentConfigRecord` (§3.2) with `__tablename__ = "yamlagno_team_configs"` and `schema="yamlagno"`. Omitted for brevity; same column set.

**Example JSON row**:
```json
{
  "id": "t7d...91",
  "tenant_id": "8b1c...e4",
  "name": "fiscal_team",
  "config_jsonb": {"team": {"name": "fiscal_team", "mode": "coordinate", "members": [
    {"member": "m1", "agent": "facturacion_afip"},
    {"member": "m2", "agent": "consultor_iva"}
  ]}},
  "is_active": true
}
```

**Illustrative query**:
```sql
-- List active teams for a tenant, newest first.
SELECT id, name, config_jsonb
FROM yamlagno.yamlagno_team_configs
WHERE tenant_id = :tenant_id AND is_active = TRUE
ORDER BY updated_at DESC;
```

### 3.4 Table: `yamlagno_workflow_configs`

**Purpose**: Persisted workflow configurations per tenant. `config_jsonb` validates against `WorkflowConfig` (SPEC_02, imported).

```sql
CREATE TABLE yamlagno.yamlagno_workflow_configs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES yamlagno.yamlagno_tenants(id) ON DELETE CASCADE,

    name          VARCHAR(100) NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,

    config_yaml   TEXT   NOT NULL,
    config_jsonb  JSONB  NOT NULL,

    description   TEXT,
    metadata      JSONB  NOT NULL DEFAULT '{}',

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ya_wf_tenant_name_unique UNIQUE (tenant_id, name),
    CONSTRAINT ya_wf_version_positive   CHECK (version >= 1)
);

CREATE INDEX idx_yamlagno_workflow_configs_tenant_name
    ON yamlagno.yamlagno_workflow_configs(tenant_id, name);
```

**ORM model**: `WorkflowConfigRecord(Base)`, `__tablename__ = "yamlagno_workflow_configs"`, `schema="yamlagno"`. Mirrors §3.2 (no `tags` column).

**Example JSON row**:
```json
{
  "id": "w2a...77",
  "tenant_id": "8b1c...e4",
  "name": "emitir_factura_flow",
  "config_jsonb": {"workflow": {"name": "emitir_factura_flow", "steps": [
    {"step": "s1", "type": "Step", "agent": "facturacion_afip"}
  ]}},
  "is_active": true
}
```

**Illustrative query**:
```sql
-- Fetch a workflow config for the WorkflowFactory.
SELECT config_jsonb
FROM yamlagno.yamlagno_workflow_configs
WHERE tenant_id = :tenant_id AND name = :name AND is_active = TRUE;
```

### 3.5 Table: `yamlagno_di_variable_cache`

**Purpose**: Cache of resolved DI variable values (database / API / file providers, see SPEC_00 DI System). TTL-bounded.

```sql
CREATE TABLE yamlagno.yamlagno_di_variable_cache (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES yamlagno.yamlagno_tenants(id) ON DELETE CASCADE,

    provider_name  VARCHAR(100) NOT NULL,   -- user_db | config_api | app_config
    variable_key   VARCHAR(255) NOT NULL,   -- name | email | preferences

    variable_value JSONB NOT NULL,
    metadata       JSONB NOT NULL DEFAULT '{}',

    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ NOT NULL,

    CONSTRAINT ya_di_tenant_provider_key_unique UNIQUE (tenant_id, provider_name, variable_key),
    CONSTRAINT ya_di_expires_future CHECK (expires_at > created_at)
);

CREATE INDEX idx_yamlagno_di_cache_tenant_provider
    ON yamlagno.yamlagno_di_variable_cache(tenant_id, provider_name);
CREATE INDEX idx_yamlagno_di_cache_expires
    ON yamlagno.yamlagno_di_variable_cache(expires_at);
```

**ORM model**: `DiVariableCacheRecord(Base)`, `__tablename__ = "yamlagno_di_variable_cache"`, `schema="yamlagno"`. Columns mirror the DDL.

**Example JSON row**:
```json
{
  "id": "d9c...03",
  "tenant_id": "8b1c...e4",
  "provider_name": "user_db",
  "variable_key": "name",
  "variable_value": {"raw": "Alice"},
  "expires_at": "2026-06-17T11:05:00Z",
  "created_at": "2026-06-17T10:05:00Z"
}
```

**Illustrative query**:
```sql
-- Resolve a DI value if not expired (DIFactory hot path).
SELECT variable_value
FROM yamlagno.yamlagno_di_variable_cache
WHERE tenant_id = :tenant_id
  AND provider_name = :provider
  AND variable_key = :key
  AND expires_at > NOW();
```

### 3.6 Table: `yamlagno_config_change_log`

**Purpose**: Audit log of changes to the config store (config create/update/delete, flag toggles, secret-audit events). This is a **config-store audit log only**; it does NOT replicate Agno RunEvents.

```sql
CREATE TABLE yamlagno.yamlagno_config_change_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    event_type    VARCHAR(255) NOT NULL,          -- config.created | config.updated | config.deleted | flag.toggled
    event_version VARCHAR(50)  NOT NULL DEFAULT '1.0',
    payload       JSONB NOT NULL,

    tenant_id     UUID NOT NULL REFERENCES yamlagno.yamlagno_tenants(id) ON DELETE CASCADE,
    correlation_id UUID,
    causation_id   UUID,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ,
    processing_attempts INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT ya_ccl_positive_attempts CHECK (processing_attempts >= 0)
);

CREATE INDEX idx_yamlagno_ccl_type        ON yamlagno.yamlagno_config_change_log(event_type);
CREATE INDEX idx_yamlagno_ccl_tenant      ON yamlagno.yamlagno_config_change_log(tenant_id);
CREATE INDEX idx_yamlagno_ccl_created     ON yamlagno.yamlagno_config_change_log(created_at DESC);
CREATE INDEX idx_yamlagno_ccl_correlation ON yamlagno.yamlagno_config_change_log(correlation_id);
CREATE INDEX idx_yamlagno_ccl_pending
    ON yamlagno.yamlagno_config_change_log(processed_at) WHERE processed_at IS NULL;
```

**Example JSON row**:
```json
{
  "id": "e3b...ad",
  "event_type": "config.created",
  "payload": {"table": "yamlagno_agent_configs", "name": "facturacion_afip", "by": "ops"},
  "tenant_id": "8b1c...e4",
  "created_at": "2026-06-17T10:05:00Z",
  "processed_at": null,
  "processing_attempts": 0
}
```

**Illustrative query**:
```sql
-- Drain pending audit events for the outbox processor.
SELECT id, event_type, payload
FROM yamlagno.yamlagno_config_change_log
WHERE processed_at IS NULL
ORDER BY created_at ASC
LIMIT 100;
-- Expected: Index Scan using idx_yamlagno_ccl_pending.
```

### 3.7 Table: `yamlagno_schema_versions`

**Purpose**: Track which schema version is provisioned, mirroring Agno's `agno_schema_versions`. Used by auto-provisioning (§6) to decide whether to run `checkfirst` creates.

```sql
CREATE TABLE yamlagno.yamlagno_schema_versions (
    component      VARCHAR(100) NOT NULL,        -- 'config_store'
    version        VARCHAR(50)  NOT NULL,        -- '0.3.0'
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (component, version)
);
```

**Example JSON row**:
```json
{"component": "config_store", "version": "0.3.0", "applied_at": "2026-06-17T10:00:00Z"}
```

**Illustrative query**:
```sql
-- Auto-provisioning gate: has this version already been provisioned?
SELECT 1 FROM yamlagno.yamlagno_schema_versions
WHERE component = 'config_store' AND version = :version;
```

---

## 4. INDEXES AND PERFORMANCE

### 4.1 Justified indexes

| Index | Table | Columns | Type | Justification |
|-------|-------|---------|------|---------------|
| `idx_yamlagno_agent_configs_tenant_name` | agent_configs | (tenant_id, name) | B-tree | Primary config lookup per tenant |
| `idx_yamlagno_agent_configs_tags` | agent_configs | tags | GIN | Tag-based config discovery |
| `idx_yamlagno_agent_configs_active` | agent_configs | (tenant_id, is_active) | B-tree | Active-only listing |
| `idx_yamlagno_di_cache_expires` | di_variable_cache | expires_at | B-tree | Expired-entry eviction |
| `idx_yamlagno_ccl_pending` | config_change_log | processed_at WHERE NULL | B-tree partial | Outbox: pending audit events |
| `idx_yamlagno_ccl_created` | config_change_log | created_at DESC | B-tree | Time-windowed audit queries |

### 4.2 Partitioning (FUTURE, non-blocking)

Time-based partitioning of the append-heavy `yamlagno_config_change_log` (by `created_at`, monthly) and `yamlagno_di_variable_cache` (by `expires_at`, daily) is a **future extension** triggered by a documented row-count threshold. MVP ships with well-designed single-partition indexes (tenant_id, created_at, FKs). See §8 for the retention/compaction roadmap.

---

## 5. MULTI-TENANT MODEL (three levels, modeled not MVP)

> **@ai-directive**: Agno isolates by `user_id` + `session_id` only — it has **no `tenant_id` concept** and **no native RLS**. yaml-agno, riding on Core Infra, models a richer three-level tenant hierarchy in `yamlagno_tenants.tenant_kind`. The columns and the resolution interface are defined **from day 1**, but enforcement (filters wired into every repository call, role checks) is **post-MVP**. Isolation is done at the **application layer via WHERE clauses** (like Agno), NOT via native Postgres RLS.

### 5.1 The three levels

| Level | `tenant_kind` | Isolation unit | Example |
|-------|---------------|----------------|---------|
| (a) Organization | `org` | Whole organization shares one tenant | CENF internal deployment |
| (b) Org + user + roles | `org_user_roles` | Org-scoped, per-user rows, RBAC | Multi-team SaaS: users within an org see their own rows + shared org rows by role |
| (c) Direct user | `user` | Each user is its own tenant | Personal single-user deployment |

### 5.2 TenantResolver interface (maps Agno identity → yaml-agno tenant)

```python
# yaml-agno/src/tenant/resolver.py
"""TenantResolver maps Agno's (user_id, session_id) identity to the yaml-agno
tenant model. This is a yaml-agno domain addition; Agno has no tenant concept.

Strategy is selected by the Environment variable tenant.resolution_mode
(org | org_user_roles | user) read via ConfigManager. The resolver sets the
Core Infra contextvar (set_tenant_id) so repositories can scope WHERE clauses.
Contextvars are NEVER passed as arguments (core-cenf AGENTS.md rule)."""

from __future__ import annotations
from typing import Protocol
from uuid import UUID

from core_infrastructure.common.context import set_tenant_id, set_user_id


class TenantResolver(Protocol):
    """Resolve a yaml-agno tenant from Agno runtime identity."""

    async def resolve(self, user_id: str, session_id: str | None) -> UUID:
        """Return the tenant_id for the given Agno user/session.

        Behavior depends on tenant.resolution_mode:
            org             -> the single org tenant_id (level a)
            org_user_roles  -> org tenant_id; user_id retained for row scoping (level b)
            user            -> one tenant per user_id (level c)

        Side effect: sets Core Infra contextvars (set_tenant_id, set_user_id)
        for **logging/tracing correlation**. These contextvars do NOT scope DB
        queries automatically — callers MUST still pass tenant_id explicitly in
        repository ``filters`` (see §5.3).
        """
        ...
```

> **@ai-directive**: `tenant_id` is a **Core Infra** column, present on every `yamlagno_*` row. It is **not** an Agno-native column and is **not** added to any `agno_*` table. The resolver is the single seam between Agno's `(user_id, session_id)` world and yaml-agno's tenant world.

### 5.3 Isolation mechanism (explicit WHERE filter, no native RLS)

```python
# Every config-store query is scoped by an EXPLICIT tenant_id filter.
# This mirrors Agno's app-layer isolation (WHERE user_id=?); Postgres RLS is
# NOT used (MVP). The core GenericRepository does NOT auto-scope by the tenant
# contextvar, so tenant_id MUST be a filter on every read/write.
async with db.transaction() as tx:                 # core-cenf TransactionScope
    set_tenant_id(tenant_id)                       # Core Infra contextvar (telemetry only)
    repo = db.get_repository(AgentConfigRecord)    # core-cenf GenericRepository[T]
    # find_all filters are exact-match by column; tenant_id scoping is EXPLICIT.
    rows = await repo.find_all(filters={"tenant_id": tenant_id, "is_active": True})
```

---

## 6. AUTO-PROVISIONING (checkfirst, mirroring Agno)

> **@ai-directive**: yaml-agno replicates Agno's on-demand provisioning pattern (`Table.create(checkfirst=True)` equivalent) for the `yamlagno_*` schema, gated by the Environment flag `configstore.auto_provision` (default `true`). When `false`, the schema is expected to be managed externally (migration tooling) and provisioning is skipped — this matches Agno's `auto_provision_dbs=False` for managed DBs.

### 6.1 Provisioner

```python
# yaml-agno/src/db/provisioner.py
"""Schema provisioner for the yamlagno config store. Uses SQLAlchemy ORM
metadata.create_all(checkfirst=True). Version-tracked in yamlagno_schema_versions.
This is the ONLY place yaml-agno touches DDL; core-cenf owns sessions/transactions."""

from __future__ import annotations
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine

from core_infrastructure import ConfigManager
from yaml_agno.db.models.tenant import Base
from yaml_agno.db.models.schema_version import SchemaVersionRecord

CONFIG_STORE_VERSION = "0.3.0"


class ConfigStoreProvisioner:
    """Creates the yamlagno schema and tables on demand.

    Attributes:
        config: ConfigManager (Environment variables: configstore.auto_provision,
            configstore.schema).
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config

    async def provision(self, engine: AsyncEngine) -> None:
        """Create schema + tables if missing and not already versioned.

        Args:
            engine: Core-cenf async engine (same DSN as DatabaseManager).

        Note:
            checkfirst=True makes this idempotent. When configstore.auto_provision
            is False, this method is a no-op (externally managed schema).
        """
        if not self._config.get_bool("configstore.auto_provision", default=True):
            return  # schema managed externally; do not touch DDL

        schema = self._config.get_string("configstore.schema", default="yamlagno")
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, checkfirst=True)
            )
            await self._mark_version(conn)

    async def _mark_version(self, conn) -> None:
        exists = await conn.execute(
            select(SchemaVersionRecord).where(
                SchemaVersionRecord.component == "config_store",
                SchemaVersionRecord.version == CONFIG_STORE_VERSION,
            )
        )
        if exists.first() is None:
            await conn.execute(
                SchemaVersionRecord.__table__.insert().values(
                    component="config_store", version=CONFIG_STORE_VERSION,
                )
            )
```

### 6.2 Gap: Alembic not in core

> **@ai-directive (gap)**: core-cenf does **not** ship an Alembic migration runner. yaml-agno therefore manages its own `yamlagno_*` schema lifecycle via the provisioner above (`create_all(checkfirst=True)`) plus the `yamlagno_schema_versions` table. For environments that require reversible migrations (`configstore.auto_provision=false`), an Alembic layer scoped to the `yamlagno` schema is a **future** addition; MVP relies on idempotent `create_all`.

---

## 7. CONSUMING core-cenf (no reimplementation)

> **@ai-directive**: yaml-agno imports `DatabaseManager`, `TransactionScope`, `GenericRepository`, `ConfigManager` and `SecretManager` from `core_infrastructure`. It does NOT define its own `TransactionManager`, `BaseRepository`, or session factory. All persistence code is written against the **Protocol**, so the concrete `SQLAlchemyAdapter` (prod) and `MemoryDatabaseAdapter` (tests) are swappable without code changes.

### 7.1 Imports and bootstrap

```python
# yaml-agno/src/db/bootstrap.py
"""Bootstrap for the yaml-agno config store on top of core-cenf. yaml-agno only
declares ORM models and asks DatabaseManager for a repository; it never opens
a raw session and never reimplements the TransactionScope."""

from __future__ import annotations
import asyncio

from core_infrastructure import ConfigManager, DatabaseManager, SecretManager
from core_infrastructure.bootstrap import BootstrapOrchestrator  # asyncio.TaskGroup


async def build_database_manager(
    config: ConfigManager, secrets: SecretManager
) -> DatabaseManager:
    """Return a configured DatabaseManager (Protocol).

    The core SQLAlchemyAdapter reads the DSN from config.get_string("database.dsn");
    secrets (password) come from SecretManager. yaml-agno does NOT build the engine.
    """
    # BootstrapOrchestrator wires managers with dependency ordering (asyncio.TaskGroup).
    orchestrator = BootstrapOrchestrator(config, secrets)
    managers = await orchestrator.start()
    return managers.database  # DatabaseManager (Protocol)
```

### 7.2 Repository usage pattern (config store only)

```python
# yaml-agno/src/repositories/agent_config_repository.py
"""AgentConfigRepository wraps the core-cenf GenericRepository for the config store.
yaml-agno does NOT subclass a BaseRepository or manage transactions directly."""

from __future__ import annotations
from typing import Any
from uuid import UUID

from core_infrastructure import DatabaseManager
from core_infrastructure.common.context import set_tenant_id

from yaml_agno.db.models.agent_config import AgentConfigRecord
# Pydantic validator (SSOT) imported, not redefined:
from yaml_agno.models.config.agent_config import AgentConfig


class AgentConfigRepository:
    """CRUD over yamlagno_agent_configs using core-cenf GenericRepository.

    Note:
        - get_repository() MUST be called inside `async with db.transaction()`
          because the core adapter binds the session to a contextvar.
        - config_jsonb is validated against the imported Pydantic AgentConfig
          (SPEC_02) before insert; this class performs no schema redefinition.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    async def create(self, tenant_id: UUID, record: AgentConfigRecord) -> UUID:
        """Insert an agent config row inside a core-cenf transaction."""
        set_tenant_id(tenant_id)  # Core Infra contextvar: telemetry/correlation only
        async with self._db.transaction() as tx:
            # get_repository() is on DatabaseManager (core ports.py), NOT on the scope.
            repo = self._db.get_repository(AgentConfigRecord)  # GenericRepository[T]
            await repo.insert(record)
            await tx.commit()
            return record.id

    async def get_active_by_name(self, tenant_id: UUID, name: str) -> dict[str, Any] | None:
        """Return the active config for a tenant+name, or None."""
        set_tenant_id(tenant_id)  # telemetry/correlation only
        async with self._db.transaction() as tx:
            repo = self._db.get_repository(AgentConfigRecord)
            # Multi-tenant isolation is EXPLICIT here: the core GenericRepository
            # does NOT auto-scope by the tenant contextvar, so tenant_id MUST be a
            # filter. (The contextvar above drives logging/tracing, not DB scoping.)
            rows = await repo.find_all(
                filters={"tenant_id": tenant_id, "name": name, "is_active": True},
                limit=1,
            )
            await tx.commit()
            return rows[0] if rows else None
```

### 7.3 Do's and Don'ts (core-cenf AGENTS.md rules)

- ALWAYS `async with db.transaction()`; NEVER open raw sessions.
- Call `db.get_repository(EntityType)` (on `DatabaseManager`, NOT on the `TransactionScope`) **inside** the `async with` block.
- Depend on the `DatabaseManager` Protocol; NEVER import `SQLAlchemyAdapter` directly in domain code.
- Read the DSN via `config.get_string("database.dsn")`; NEVER read `os.environ` directly (only via `ConfigManager`).
- Secrets via `await secrets.get_secret(key)`; NEVER in env vars or logs.
- Multi-tenant isolation is **explicit**: ALWAYS pass `tenant_id` in the `filters={}` dict. The core `GenericRepository` does NOT auto-scope by the tenant contextvar. `set_tenant_id()` (contextvar) drives **logging/tracing** only — never assume it scopes DB queries.
- Use `asyncio.TaskGroup` for concurrent bootstrap; NEVER `asyncio.gather`.

---

## 8. RETENTION AND COMPACTION (future feature)

> **@ai-directive**: Retention, time-based partitioning and S3 archiving are a **future feature**, not MVP. MVP ships with the indexes defined in §4.2. This section documents the intended design and the trigger threshold so the schema is forward-compatible.

### 8.1 Roadmap

1. **MVP**: single-partition tables, indexes on `tenant_id`, `created_at`, FKs. No background jobs.
2. **Trigger**: when `yamlagno_config_change_log` exceeds a documented threshold (e.g. > 5M rows or > 90 days of data), enable monthly time-based partitioning by `created_at`.
3. **Retention**: a background job drops partitions older than `configstore.retention_days` (Environment, configurable, read via `ConfigManager`). Dropping a partition is O(1) versus row-by-row DELETE.
4. **Compaction / archiving (event sourcing + snapshotting)**: keep the latest snapshot + the N most recent deltas in Postgres; compress and ship older deltas to S3. Restoring a historical state replays deltas forward from the nearest snapshot.

### 8.2 Configurable retention knob

| Variable | Class | Default | Notes |
|----------|-------|---------|-------|
| `configstore.retention_days` | **Environment** | `365` | Days of `config_change_log` to keep before partition drop. Read via `config.get_int`. Future feature; ignored by MVP. |

---

## 9. REPLICATION

> **@ai-directive**: For the **config store**, **synchronous** replication is the default (`configstore.replication_mode = sync`). Config rows are low-volume, high-consistency artifacts: a stale replica would serve the wrong agent definition. The trade-off (higher write latency) is acceptable because config writes are infrequent compared to runtime reads.

| Mode | Setting | Trade-off | When to use |
|------|---------|-----------|-------------|
| Synchronous (default) | `configstore.replication_mode = sync` | Strong consistency, higher write latency | Production config store (recommended) |
| Asynchronous | `configstore.replication_mode = async` | Eventual consistency, lower latency | Read-heavy multi-region where brief staleness is tolerable |

> Runtime replication (Agno `agno_*` sessions/memory) is governed by Agno's own `db=` settings and is out of scope here.

---

## 10. BEHAVIOR DELTA - BDD SCENARIOS

### 10.1 Acceptance scenarios

#### Scenario 1: Golden Path - Persist AgentConfig via core repository

```gherkin
GIVEN a validated AgentConfig (Pydantic, SPEC_02) for tenant T
AND a core-cenf DatabaseManager bound to the yamlagno schema
WHEN AgentConfigRepository.create(tenant_id=T, record) is called
THEN an AgentConfigRecord row exists in yamlagno_agent_configs
AND the row tenant_id equals T
AND the row config_jsonb round-trips through AgentConfig validation
AND the transaction was committed via the core TransactionScope
```

#### Scenario 2: Golden Path - Read active configs within a transaction

```gherkin
GIVEN tenant T has 5 agent configs and 2 are is_active=false
WHEN get_active_by_name is called inside async with db.transaction()
THEN only active configs are returned
AND the repository was obtained from db.get_repository(AgentConfigRecord)
```

#### Scenario 3: Error Case - Duplicate config name

```gherkin
GIVEN tenant T has an existing config named "my_agent"
WHEN inserting another config with the same name
THEN the unique constraint ya_agent_tenant_name_unique is violated
AND the core TransactionScope rolls back (idempotent rollback)
AND no partial row is persisted
```

#### Scenario 4: Boundary - Invalid JSONB rejected before insert

```gherkin
GIVEN a config_jsonb that fails AgentConfig validation (SPEC_02)
WHEN the repository attempts to insert
THEN validation raises before any SQL is issued
AND no transaction is left open
```

#### Scenario 5: Multi-tenant isolation via WHERE (no native RLS)

```gherkin
GIVEN tenant A and tenant B each have configs
AND the TenantResolver set contextvar tenant_id = A
WHEN listing configs via find_all
THEN only tenant A rows are returned
AND tenant B rows are never read (app-layer WHERE, not Postgres RLS)
```

#### Scenario 6: Auto-provisioning is idempotent and flag-gated

```gherkin
GIVEN configstore.auto_provision = true
WHEN ConfigStoreProvisioner.provision runs twice
THEN the yamlagno schema and tables exist
AND yamlagno_schema_versions records exactly one row for the version
AND the second run performs no DDL (checkfirst=True)

GIVEN configstore.auto_provision = false
WHEN provision runs
THEN no DDL is executed (schema managed externally)
```

---

## 11. TDD MICRO-TASK EXECUTION PROTOCOL

### 11.1 Cascading task checklist

> **@ai-directive**: Tasks reflect the consume-core model. There is NO task to implement a `TransactionManager` — that comes from core-cenf. Tasks focus on ORM models, auto-provisioning, repository wrappers over `GenericRepository`, and the TenantResolver interface.

#### TASK_001: Define ORM Base + TenantRecord

- **File**: `yaml-agno/src/db/models/tenant.py`
- **Test**: `tests/unit/db/test_tenant_model.py`
- **RED**:
  ```python
  def test_tenant_record_maps_table():
      assert TenantRecord.__tablename__ == "yamlagno_tenants"
      assert TenantRecord.__table__.schema == "yamlagno"
      assert TenantRecord(name="CENF", slug="cenf").slug == "cenf"
  ```
- **GREEN**: Implement `Base(DeclarativeBase)` and `TenantRecord` (§3.1).
- **Commit**: `feat: add yamlagno_tenants ORM model`

#### TASK_002: Define AgentConfigRecord

- **File**: `yaml-agno/src/db/models/agent_config.py`
- **Test**: `tests/unit/db/test_agent_config_model.py`
- **RED**:
  ```python
  def test_agent_config_record_maps_table():
      assert AgentConfigRecord.__tablename__ == "yamlagno_agent_configs"
      assert AgentConfigRecord.__table__.schema == "yamlagno"
  ```
- **GREEN**: Implement `AgentConfigRecord` (§3.2). Validate `config_jsonb` against the imported Pydantic `AgentConfig` (SPEC_02).
- **Commit**: `feat: add yamlagno_agent_configs ORM model`

#### TASK_003: Define Team/Workflow/DiVariable/ConfigChangeLog/SchemaVersion records

- **File**: `yaml-agno/src/db/models/*.py`
- **Test**: `tests/unit/db/test_models.py`
- **RED**: assert `__tablename__` + `schema == "yamlagno"` for each.
- **GREEN**: Implement the remaining ORM entities (§3.3–§3.7).
- **Commit**: `feat: add remaining yamlagno_ ORM models`

#### TASK_004: Auto-provisioning with checkfirst

- **File**: `yaml-agno/src/db/provisioner.py`
- **Test**: `tests/integration/test_provisioner.py`
- **RED**:
  ```python
  async def test_provision_creates_schema_and_tables(memory_db, config):
      prov = ConfigStoreProvisioner(config)
      await prov.provision(memory_db.engine)
      assert await table_exists(memory_db.engine, "yamlagno_tenants")

  async def test_provision_skips_when_disabled(memory_db, config_disabled):
      prov = ConfigStoreProvisioner(config_disabled)
      await prov.provision(memory_db.engine)  # no-op
  ```
- **GREEN**: Implement `ConfigStoreProvisioner` (§6.1) using `Base.metadata.create_all(checkfirst=True)` and `yamlagno_schema_versions`.
- **Commit**: `feat: add config-store auto-provisioner`

#### TASK_005: Repository wrapper over core GenericRepository

- **File**: `yaml-agno/src/repositories/agent_config_repository.py`
- **Test**: `tests/integration/repositories/test_agent_config_repository.py`
- **RED**:
  ```python
  async def test_create_uses_core_transaction(db_manager, tenant_id):
      repo = AgentConfigRepository(db_manager)
      rid = await repo.create(tenant_id, record)
      assert rid is not None

  async def test_get_active_by_name(db_manager, tenant_id):
      repo = AgentConfigRepository(db_manager)
      got = await repo.get_active_by_name(tenant_id, "x")
      assert got is None or got["name"] == "x"
  ```
- **GREEN**: Implement `AgentConfigRepository` (§7.2) using `async with db.transaction()` + `db.get_repository(AgentConfigRecord)` (on `DatabaseManager`, inside the transaction scope).
- **Commit**: `feat: add AgentConfigRepository over core GenericRepository`

#### TASK_006: TenantResolver interface

- **File**: `yaml-agno/src/tenant/resolver.py`
- **Test**: `tests/unit/tenant/test_resolver.py`
- **RED**:
  ```python
  async def test_resolve_user_mode_returns_user_tenant(resolver):
      tid = await resolver.resolve(user_id="u1", session_id="s1")
      assert tid is not None

  def test_resolver_sets_contextvar(resolver):
      # after resolve, get_tenant_id() reflects the resolved tenant
      ...
  ```
- **GREEN**: Implement `TenantResolver` (§5.2) with the three `resolution_mode` strategies and Core Infra contextvar side effects.
- **Commit**: `feat: add TenantResolver mapping Agno identity to yaml-agno tenant`

#### TASK_007: Bootstrap on core-cenf DatabaseManager

- **File**: `yaml-agno/src/db/bootstrap.py`
- **Test**: `tests/integration/test_bootstrap.py`
- **RED**: `build_database_manager(config, secrets)` returns an object satisfying the `DatabaseManager` Protocol.
- **GREEN**: Wire `BootstrapOrchestrator` (§7.1) using `asyncio.TaskGroup`; DSN via `config.get_string("database.dsn")`.
- **Commit**: `feat: bootstrap config store on core-cenf DatabaseManager`

---

## 12. TECHNICAL ASSUMPTIONS AND CALIBRATION

### 12.1 Assumptions adopted

- **[A1] Consume core-cenf, do not reimplement**: yaml-agno declares ORM models and consumes `DatabaseManager`/`TransactionScope`/`GenericRepository[T]`. No local transaction manager or base repository.
- **[A2] Declarative ORM mandatory**: the core `SQLAlchemyAdapter` requires `DeclarativeBase` entities, so yaml-agno uses ORM (unlike Agno's Core-only `agno_*` tables).
- **[A3] `yamlagno_*` prefix + dedicated schema**: avoids collision with `agno_*` when both share one Postgres.
- **[A4] Three-level tenant model from day 1**: columns and resolver interface defined now; enforcement post-MVP.
- **[A5] App-layer WHERE isolation, no native RLS**: mirrors Agno; `tenant_id` is a Core Infra column on `yamlagno_*` only.

### 12.2 Calibration questions

- **[Q1] Retention horizon**: is `retention_days=365` for `config_change_log` adequate, or do compliance needs require longer? (Future feature; MVP ignores.)
- **[Q2] Partition trigger threshold**: at what row count / age should monthly partitioning of `config_change_log` switch on? Proposed: 5M rows or 90 days.
- **[Q3] Synchronous replication latency**: is sync replication acceptable for the config store write path in every target deployment, or do multi-region read-heavy setups need async?

---

*Do you want to deepen the technical specification to **Level 6** for a specific component (e.g. the TenantResolver strategies or the retention/compaction job), or authorize execution of these tasks by the agent team?*
