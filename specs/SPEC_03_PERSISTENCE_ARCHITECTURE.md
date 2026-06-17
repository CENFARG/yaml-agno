---
Spec_ID: "SPEC_03"
Title: "Persistence Architecture - Database Schema and Storage"
Version: "0.2.0-iter1"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#PostgreSQL", "#DDL", "#Indexes", "#Transactions"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02"]
Last_Updated: "2026-06-17"
Revision_Note: "Iter 1 alignment with SPEC_00-02 baseline. Redrew the persistence boundary: yaml-agno connects to Agno's native storage for agent/session/memory/event runtime and keeps its own ACID transactions only for the control-plane config store. Renamed the SQLAlchemy persistence models to *ConfigRow to avoid collision with the Pydantic *Config schemas from SPEC_02 (Single Source of Truth). Marked retention/purge and time-based partitioning as a future non-blocking extension; retained tenant_id-based partitioning. Clarified Engram as an optional external MCP adapter, not a native storage layer. Fixed internal section numbering."
---

# SPEC_03_PERSISTENCE_ARCHITECTURE

> **Purpose**: Define the physical persistence schema, storage mapping, optimization indexes and transactional control for the yaml-agno control-plane config store, following ACID and Zero-Trust Security principles. Runtime persistence of agents/sessions/memory/events is delegated to Agno's native storage.

---

## 1. PERSISTENCE STRATEGY AND STORAGE MAPPING

### 1.1 Storage Architecture

```mermaid
graph TB
    subgraph APP ["Application Layer"]
        YAF["yaml-agno Factory"]
        AI["AgentInstance"]
        SC["SessionContext"]
    end

    subgraph PERS ["Persistence Layer"]
        PG["PostgreSQL"]
        SL["SQLite Dev"]
    end

    subgraph CACHE ["Cache Layer"]
        REDIS["Redis Optional"]
    end

    subgraph EXT ["External Adapters (Optional)"]
        ENG["Engram MCP"]
    end

    YAF -->|Config store (control plane)| PG
    AI -->|Runtime: session/memory| AGNODB["Agno native db (PostgresDb/RedisDb via db=)"]
    SC -->|Runtime: message history| AGNODB
    PG -.->|Replicate| SL
    PG <-->|Cache| REDIS
    AI -.->|Long-term memory via MCP adapter| ENG
```

> **Storage boundary note**: Runtime persistence of agent sessions, memory and run events is provided natively by Agno (via its `db=` PostgresDb/RedisDb). yaml-agno owns the **control-plane config store** (tenant configs, `*_configs` rows, DI cache, audit) in its own PostgreSQL schema. `Engram` is an **optional external MCP adapter** for long-term memory; it is NOT a native Agno storage layer (the `LongTermMemoryPort` detail lives in SPEC_04).

### 1.2 Data-to-Storage Mapping

| Data Type | Primary Storage | Backup Storage | Retention | Justification |
|-----------|-----------------|----------------|-----------|----------------|
| **Config Yaml** | PostgreSQL | Git (versioned) | Permanent | Source of truth, multi-tenant |
| **Session State** | PostgreSQL (Agno native runtime) | - | Future* | Runtime state owned by Agno |
| **Message History** | PostgreSQL (Agno native runtime) | - | Future* | Conversation history owned by Agno |
| **DI Variables** | PostgreSQL (config-store cache) | API/DB source | 1 hour | Cached values, TTL |
| **Agent Execution Logs** | PostgreSQL (Agno native) | - | Future* | Debugging, observability |
| **Domain Events** | PostgreSQL (Agno RunEvents) | - | Future* | Owned by Agno run lifecycle |

> *Retention for session/message/event data is a **future, non-blocking extension** post-MVP (job scheduler). Agno has no native retention mechanism; the values above describe intended policy, not MVP scope. Runtime ownership of session/message/event data belongs to Agno; yaml-agno only persists its **control-plane config store** with ACID guarantees.

### 1.3 Multi-Tenant Isolation Strategy

**Strategy**: Tenant isolation by `tenant_id` + Row Level Security (RLS). Multi-tenant (`tenant_id`, RLS) is a Core Infra concept; Agno itself isolates by `user_id` + `session_id`, so RLS applies to the yaml-agno control-plane config store.

```sql
-- RLS policy for every table with tenant_id
CREATE POLICY tenant_isolation_policy ON all_tables
USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

**Benefits**:
- Complete isolation between tenants
- Data-leakage prevention
- GDPR-compliant by default

---

## 2. DATABASE SCHEMA (FULL DDL)

### 2.1 Table: tenants

**Purpose**: Tenant metadata (clients/organizations)

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Settings
    settings JSONB NOT NULL DEFAULT '{}',

    -- Constraints
    CONSTRAINT slug_format CHECK (slug ~ '^[a-z0-9-]+$')
);

-- Index for slug lookup
CREATE INDEX idx_tenants_slug ON tenants(slug);
```

### 2.2 Table: agent_configs

**Purpose**: Agent configurations per tenant.

> `@ai-directive`: The SQLAlchemy persistence model for this table is named `AgentConfigRow` (the **persistence row**), NOT `AgentConfig`. The Pydantic schema `AgentConfig` defined in SPEC_02 is the Single Source of Truth for the JSONB payload and is **imported, never redefined**. `config_jsonb` must validate against `AgentConfig` at the adapter boundary; do not duplicate its fields here.

```sql
CREATE TABLE agent_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identity
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,

    -- Configuration (YAML serialized)
    config_yaml TEXT NOT NULL,
    config_jsonb JSONB NOT NULL,

    -- Metadata
    description TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Constraints
    CONSTRAINT tenant_name_unique UNIQUE (tenant_id, name),
    CONSTRAINT version_positive CHECK (version >= 1)
);

-- Indexes
CREATE INDEX idx_agent_configs_tenant_name ON agent_configs(tenant_id, name);
CREATE INDEX idx_agent_configs_tags ON agent_configs USING GIN(tags);
CREATE INDEX idx_agent_configs_active ON agent_configs(tenant_id, is_active);

-- Trigger for updated_at
CREATE TRIGGER update_agent_configs_updated_at
BEFORE UPDATE ON agent_configs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### 2.3 Table: team_configs

**Purpose**: Team configurations per tenant.

> `@ai-directive`: SQLAlchemy persistence model `TeamConfigRow` (persistence row). JSONB validates against the Pydantic `TeamConfig` from SPEC_02 (Single Source of Truth, imported, not redefined).

```sql
CREATE TABLE team_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identity
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,

    -- Configuration
    config_yaml TEXT NOT NULL,
    config_jsonb JSONB NOT NULL,

    -- Metadata
    description TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Constraints
    CONSTRAINT tenant_name_unique UNIQUE (tenant_id, name)
);

-- Indexes
CREATE INDEX idx_team_configs_tenant_name ON team_configs(tenant_id, name);
CREATE INDEX idx_team_configs_tags ON team_configs USING GIN(tags);
```

### 2.4 Table: workflow_configs

**Purpose**: Workflow configurations per tenant.

> `@ai-directive`: SQLAlchemy persistence model `WorkflowConfigRow` (persistence row). JSONB validates against the Pydantic `WorkflowConfig` from SPEC_02 (Single Source of Truth, imported, not redefined).

```sql
CREATE TABLE workflow_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identity
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,

    -- Configuration
    config_yaml TEXT NOT NULL,
    config_jsonb JSONB NOT NULL,

    -- Metadata
    description TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT tenant_name_unique UNIQUE (tenant_id, name)
);

-- Indexes
CREATE INDEX idx_workflow_configs_tenant_name ON workflow_configs(tenant_id, name);
```

### 2.5 Table: agent_sessions (DEPRECATED — runtime owned by Agno)

> `@ai-directive`: yaml-agno does **not** persist its own agent runtime/session table. Agent session lifecycle, state and runs are managed natively by Agno (via `db=` PostgresDb/RedisDb), isolated by `user_id` + `session_id`. The DDL below is retained only as an **optional read-only mirror/index** for control-plane management queries (e.g. listing sessions per tenant). It is **out of MVP scope**; do not implement unless a concrete control-plane query requirement is identified. Agno remains the source of truth for session data.

```sql
-- DEPRECATED / OUT OF MVP SCOPE
-- Optional read-only mirror of Agno-managed sessions for control-plane queries only.
-- Agno is the source of truth; this table MUST NOT own runtime state.
CREATE TABLE agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Session identity (mirrors Agno session)
    session_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,

    -- Reference to config
    agent_config_id UUID NOT NULL REFERENCES agent_configs(id) ON DELETE CASCADE,

    -- Status (mirrored, not authoritative)
    state VARCHAR(50) NOT NULL, -- created|initialized|running|completed|failed
    current_iteration INTEGER NOT NULL DEFAULT 0,

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Results
    result TEXT,
    error TEXT,

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Constraints
    CONSTRAINT tenant_user_session_unique UNIQUE (tenant_id, user_id, session_id),
    CONSTRAINT valid_state CHECK (state IN ('created', 'initialized', 'running', 'completed', 'failed')),
    CONSTRAINT iteration_non_negative CHECK (current_iteration >= 0)
);

-- Indexes
CREATE INDEX idx_agent_sessions_tenant_user ON agent_sessions(tenant_id, user_id);
CREATE INDEX idx_agent_sessions_session_id ON agent_sessions(session_id);
CREATE INDEX idx_agent_sessions_state ON agent_sessions(state);
CREATE INDEX idx_agent_sessions_created ON agent_sessions(created_at DESC);

-- Time-based partitioning for retention is a FUTURE non-blocking extension (Agno has no native retention).
-- Tenant_id-based partitioning (multi-tenant) is legitimate and retained for Core Infra.
-- CREATE TABLE agent_sessions_2026_06 PARTITION OF agent_sessions
-- FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
```

### 2.6 Table: session_contexts (DEPRECATED — runtime owned by Agno)

> `@ai-directive`: Same boundary as §2.5. Message history and per-agent runtime state are owned by Agno natively; yaml-agno does not persist its own session-context runtime table. The DDL below is retained only as an **optional read-only mirror** for control-plane queries and is **out of MVP scope**.

```sql
-- DEPRECATED / OUT OF MVP SCOPE
-- Optional read-only mirror of Agno-managed session context for control-plane queries only.
CREATE TABLE session_contexts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Identity
    session_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,

    -- Status (mirrored)
    session_state VARCHAR(50) NOT NULL DEFAULT 'active', -- active|paused|closed

    -- History (mirrored; Agno is authoritative)
    message_history JSONB NOT NULL DEFAULT '[]', -- Array of messages
    max_history_size INTEGER NOT NULL DEFAULT 100,

    -- Agent states (mirrored)
    agent_states JSONB NOT NULL DEFAULT '{}', -- agent_name -> state JSON

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Constraints
    CONSTRAINT tenant_session_unique UNIQUE (tenant_id, session_id),
    CONSTRAINT valid_session_state CHECK (session_state IN ('active', 'paused', 'closed')),
    CONSTRAINT history_size_positive CHECK (max_history_size >= 1)
);

-- Indexes
CREATE INDEX idx_session_contexts_tenant_session ON session_contexts(tenant_id, session_id);
CREATE INDEX idx_session_contexts_user ON session_contexts(tenant_id, user_id);
CREATE INDEX idx_session_contexts_state ON session_contexts(session_state);
CREATE INDEX idx_session_contexts_last_activity ON session_contexts(last_activity DESC);

-- Time-based retention partitioning is a FUTURE non-blocking extension.
```

### 2.7 Table: di_variable_cache

**Purpose**: DI variable cache (Database, API, File providers). Part of the yaml-agno control-plane config store.

```sql
CREATE TABLE di_variable_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Variable identity
    provider_name VARCHAR(100) NOT NULL, -- user_db|config_api|app_config
    variable_key VARCHAR(255) NOT NULL, -- name|email|preferences

    -- Cached value
    variable_value JSONB NOT NULL,

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Constraints
    CONSTRAINT tenant_provider_key_unique UNIQUE (tenant_id, provider_name, variable_key),
    CONSTRAINT expires_future CHECK (expires_at > created_at)
);

-- Indexes
CREATE INDEX idx_di_cache_tenant_provider ON di_variable_cache(tenant_id, provider_name);
CREATE INDEX idx_di_cache_expires ON di_variable_cache(expires_at);

-- Partition by expires_at (TTL 1 hour)
```

### 2.8 Table: config_change_log (audit for the config store)

**Purpose**: Audit log of changes to the yaml-agno control-plane config store (config create/update/delete, feature-flag toggles, secret-audit events).

> `@ai-directive`: This is an **audit log for the config store only**. It does NOT replicate Agno RunEvents — run/agent events are emitted natively by Agno. The legacy name `domain_events` implied broad event sourcing of agent runtime, which is out of scope; this table is renamed to `config_change_log` to make the boundary explicit. General event sourcing for agent runs is a **future feature**, not MVP.

```sql
CREATE TABLE config_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identification
    event_type VARCHAR(255) NOT NULL,
    event_version VARCHAR(50) NOT NULL DEFAULT '1.0',

    -- Payload
    payload JSONB NOT NULL,

    -- Metadata
    tenant_id UUID,
    correlation_id UUID,
    causation_id UUID,

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Processing
    processed_at TIMESTAMPTZ,
    processing_attempts INTEGER NOT NULL DEFAULT 0,

    -- Constraints
    CONSTRAINT positive_attempts CHECK (processing_attempts >= 0)
);

-- Indexes
CREATE INDEX idx_config_change_log_type ON config_change_log(event_type);
CREATE INDEX idx_config_change_log_tenant ON config_change_log(tenant_id);
CREATE INDEX idx_config_change_log_created ON config_change_log(created_at DESC);
CREATE INDEX idx_config_change_log_correlation ON config_change_log(correlation_id);
CREATE INDEX idx_config_change_log_processed ON config_change_log(processed_at) WHERE processed_at IS NULL;

-- Time-based retention partitioning is a FUTURE non-blocking extension.
```

---

## 3. INDEXES AND PERFORMANCE TUNING

### 3.1 Justified Indexes

| Index | Table | Columns | Type | Justification |
|-------|-------|---------|------|---------------|
| `idx_agent_configs_tenant_name` | agent_configs | (tenant_id, name) | B-tree | Primary config lookup per tenant |
| `idx_agent_configs_tags` | agent_configs | tags | GIN | Tag-based search (config discovery) |
| `idx_agent_sessions_tenant_user` | agent_sessions | (tenant_id, user_id) | B-tree | Session history per user (mirror, optional) |
| `idx_agent_sessions_state` | agent_sessions | state | B-tree | Active-session filtering (mirror, optional) |
| `idx_session_contexts_last_activity` | session_contexts | last_activity DESC | B-tree | Expired-session cleanup (mirror, optional) |
| `idx_di_cache_expires` | di_variable_cache | expires_at | B-tree | Expired-entry eviction |
| `idx_config_change_log_processed` | config_change_log | processed_at WHERE NULL | B-tree Partial | Pending audit events |

### 3.2 Optimized Queries

```sql
-- Q1: Active config lookup by tenant and name
EXPLAIN ANALYZE
SELECT id, config_yaml, config_jsonb
FROM agent_configs
WHERE tenant_id = $1 AND name = $2 AND is_active = true;

-- Expected: Index Scan using idx_agent_configs_tenant_name + Filter

-- Q2: Active sessions per user (optional control-plane mirror; runtime owned by Agno)
EXPLAIN ANALYZE
SELECT id, session_id, state, current_iteration
FROM agent_sessions
WHERE tenant_id = $1 AND user_id = $2 AND state = 'running'
ORDER BY created_at DESC
LIMIT 10;

-- Expected: Index Scan using idx_agent_sessions_tenant_user + idx_agent_sessions_state

-- Q3: Cleanup of expired sessions (>30 days) -- FUTURE retention extension
EXPLAIN ANALYZE
DELETE FROM session_contexts
WHERE last_activity < NOW() - INTERVAL '30 days';

-- Expected: Index Scan using idx_session_contexts_last_activity

-- Q4: Pending config-store audit events
EXPLAIN ANALYZE
SELECT id, event_type, payload
FROM config_change_log
WHERE processed_at IS NULL
ORDER BY created_at ASC
LIMIT 100;

-- Expected: Index Scan using idx_config_change_log_processed
```

### 3.3 Partitioning Strategy

**Time-based partitioning (FUTURE, non-blocking post-MVP)**:
- `agent_sessions` by `created_at` (monthly)
- `session_contexts` by `last_activity` (monthly)
- `di_variable_cache` by `expires_at` (daily)
- `config_change_log` by `created_at` (daily)

> `@ai-directive`: Time-based partitioning and purge/retention are a **future extension** (Agno has no native retention). The DDL above is retained for forward compatibility. **Tenant-based partitioning (multi-tenant isolation) is legitimate Core Infra and stays in scope.**

**Benefits**:
- Fast partition drops for cleanup
- Time-filtered queries use partition pruning
- Smaller indexes per partition

---

## 4. CORE INFRA MANAGER INTEGRATION

> `@ai-directive` (persistence boundary): yaml-agno **connects to Agno's storage** for everything Agno already persists (agents, sessions, memory, run events) — it does not reimplement that runtime. The integration below scopes the ConfigManager / SecretManager / DatabaseManager / TransactionManager / Repository pattern to the **yaml-agno control-plane config store only** (tenant configs, `*_configs` rows, `di_variable_cache`, `config_change_log`, feature flags, secret audit). ACID transactions here are legitimate because PostgreSQL provides them natively. **Do NOT wrap Agno step runtime in these transactions** — that is not a native Agno concept and is treated as a future feature.

### 4.1 ConfigManager Integration

**Responsibility**: Database connection configuration and pooling for the config store.

**Usage in yaml-agno**:
```python
# yaml-agno/src/db/bootstrap.py

class DatabaseBootstrap:
    """Bootstrap for the yaml-agno control-plane config-store engine.

    @ai-directive: This engine serves ONLY the config store schema. Runtime
    agent/session/memory storage is delegated to Agno via its own db= setting.
    """

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    async def create_engine(self) -> AsyncEngine:
        """Create a SQLAlchemy AsyncEngine for the config store from ConfigManager."""
        db_url = self.config.get_string("database.url")
        pool_size = self.config.get_number("database.pool_size", default=10)
        max_overflow = self.config.get_number("database.max_overflow", default=20)

        engine = create_async_engine(
            db_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # verify connections before use
        )
        return engine
```

### 4.2 SecretManager Integration

**Responsibility**: Secure handling of database credentials (Zero-Trust).

**Port (Protocol)**:
```python
from typing import Protocol

class SecretManager(Protocol):
    async def get_secret(self, key: str) -> str: ...
    async def get_secret_json(self, key: str) -> dict: ...
```

**Usage in yaml-agno**:
```python
# yaml-agno/src/db/bootstrap.py

class DatabaseBootstrap:
    def __init__(
        self,
        config_manager: ConfigManager,
        secret_manager: SecretManager
    ):
        self.config = config_manager
        self.secrets = secret_manager

    async def get_db_credentials(self) -> dict:
        """Fetch database credentials from SecretManager."""
        # Never read secrets directly from environment variables.
        password = await self.secrets.get_secret("database.password")

        return {
            "username": self.config.get_string("database.username"),
            "password": password,  # from SecretManager
            "host": self.config.get_string("database.host"),
            "port": self.config.get_number("database.port"),
        }
```

**Do's & Don'ts**:
- Automatic rotation with short TTL
- Access auditing
- Do NOT persist secrets in env vars
- Do NOT list all secrets

### 4.3 DatabaseManager Integration

**Responsibility**: Resilient pooling and factory for config-store repositories.

**Port (Protocol)**:
```python
from typing import Protocol, TypeVar
from contextlib import AbstractAsyncContextManager

T = TypeVar('T')

class TransactionScope(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

class GenericRepository(Protocol[T]):
    async def find_by_id(self, id: str) -> T | None: ...
    async def insert(self, entity: T) -> None: ...

class DatabaseManager(Protocol):
    def transaction(self, tenant_id: UUID | None = None) -> AbstractAsyncContextManager[TransactionScope]: ...
    def get_repository(self, name: str) -> GenericRepository: ...
```

**Usage in yaml-agno with Repository Pattern (config store only)**:
```python
# yaml-agno/src/repositories/base_repository.py

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

class BaseRepository:
    """Base repository for the config store.

    @ai-directive: Scoped to the control-plane config store. Transactions here
    guarantee ACID for config rows only; they do NOT cover Agno runtime steps.
    """

    def __init__(self, db_manager: DatabaseManager, tenant_id: UUID):
        self.db = db_manager
        self.tenant_id = tenant_id

    async def create(self, entity_data: dict) -> UUID:
        """Create an entity within an automatic transaction."""
        async with self.db.transaction(tenant_id=self.tenant_id) as session:
            # Boundary validation with the Pydantic schema from SPEC_02.
            validated = self._validate(entity_data)

            result = await session.execute(
                insert(self.model).values(**validated).returning(self.model.id)
            )
            return result.scalar_one()

    async def find_by_id(self, entity_id: UUID) -> dict | None:
        """Find an entity by ID."""
        async with self.db.transaction(tenant_id=self.tenant_id) as session:
            result = await session.execute(
                select(self.model).where(
                    self.model.id == entity_id,
                    self.model.tenant_id == self.tenant_id
                )
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None
```

**Do's & Don'ts**:
- Manage transactions via Async Context Managers
- Boundary Validation with Pydantic at adapters
- Hide driver details (SQLAlchemy)
- Do NOT expose raw sessions to the domain
- Do NOT accept dynamic SQL from the domain

**Dependencies**: ConfigManager, SecretManager, LoggerManager, ObservabilityManager, ErrorHandlingManager

---

## 5. TRANSACTION MANAGER CONTRACT (config store)

> `@ai-directive`: The `TransactionManager` below is scoped to the **config store**. ACID guarantees apply to config-store rows (tenants, `*_configs`, `di_variable_cache`, `config_change_log`). It does NOT manage Agno runtime step transactions.

### 5.1 Async Context Manager

```python
# yaml-agno/src/db/transaction.py

from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text

class TransactionManager:
    """Transaction manager with automatic rollback for the config store."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    @asynccontextmanager
    async def transaction(self, tenant_id: UUID | None = None) -> AsyncIterator[AsyncSession]:
        """Context manager for a transaction with automatic rollback.

        Args:
            tenant_id: Tenant ID for RLS (optional).

        Yields:
            AsyncSession: SQLAlchemy async session.

        Raises:
            Exception: Any error during the transaction triggers rollback.
        """
        async with self.session_factory() as session:
            try:
                # Set tenant_id for RLS.
                if tenant_id:
                    await session.execute(
                        text("SET LOCAL app.current_tenant = :tenant_id"),
                        {"tenant_id": str(tenant_id)}
                    )

                yield session

                # Explicit commit.
                await session.commit()

            except Exception:
                # Automatic rollback.
                await session.rollback()
                raise
```

### 5.2 Usage Example (config store repository)

```python
# yaml-agno/src/repositories/agent_config_repository.py

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

class AgentConfigRepository:
    """Repository for the agent_configs config-store table.

    @ai-directive: The persisted row maps to the SQLAlchemy model AgentConfigRow.
    The config_jsonb payload validates against the Pydantic AgentConfig schema
    imported from SPEC_02 (Single Source of Truth).
    """

    def __init__(self, transaction_manager: TransactionManager):
        self.tm = transaction_manager

    async def create(
        self,
        tenant_id: UUID,
        name: str,
        config_yaml: str,
        config_jsonb: dict,
    ) -> UUID:
        """Create an agent configuration row."""
        async with self.tm.transaction(tenant_id=tenant_id) as session:
            result = await session.execute(
                text("""
                    INSERT INTO agent_configs (tenant_id, name, config_yaml, config_jsonb)
                    VALUES (:tenant_id, :name, :config_yaml, :config_jsonb)
                    RETURNING id
                """),
                {
                    "tenant_id": str(tenant_id),
                    "name": name,
                    "config_yaml": config_yaml,
                    "config_jsonb": config_jsonb,
                },
            )
            return result.scalar_one()

    async def get_by_name(
        self,
        tenant_id: UUID,
        name: str,
    ) -> dict | None:
        """Get an active config by name."""
        async with self.tm.transaction(tenant_id=tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT id, config_yaml, config_jsonb
                    FROM agent_configs
                    WHERE tenant_id = :tenant_id AND name = :name AND is_active = true
                """),
                {"tenant_id": str(tenant_id), "name": name},
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None
```

---

## 6. BEHAVIOR DELTA - BDD SCENARIOS

### 6.1 Acceptance Scenarios

#### Scenario 1: Golden Path - Create AgentConfig

```gherkin
GIVEN a valid tenant_id and agent config YAML
AND the YAML is validated
WHEN the config is saved to PostgreSQL
THEN the agent_configs row is created
AND the config_jsonb contains all fields
AND the created_at timestamp is set
AND the tenant_id matches the input
```

#### Scenario 2: Golden Path - Query Active Configs

```gherkin
GIVEN a tenant with 5 agent configs
AND 2 configs have is_active=false
WHEN querying for active configs
THEN exactly 3 configs are returned
AND all returned configs have is_active=true
AND the results are ordered by name ASC
```

#### Scenario 3: Error Case - Duplicate Config Name

```gherkin
GIVEN a tenant with existing config "my_agent"
WHEN creating a new config with the same name
THEN a unique constraint violation occurs
AND the transaction is rolled back
AND the error message mentions "tenant_name_unique"
```

#### Scenario 4: Error Case - Invalid JSONB

```gherkin
GIVEN a config_yaml with invalid structure
WHEN attempting to insert with invalid config_jsonb
THEN a JSONB validation error occurs
AND the transaction is rolled back
```

---

## 7. TDD MICRO-TASK EXECUTION PROTOCOL

### 7.1 Cascading Task Checklist

#### TASK_001: Define Tenant Model

- **File**: `yaml-agno/src/db/models/tenant.py`
- **Test**: `tests/unit/db/test_tenant_model.py`
- **RED**:
  ```python
  def test_tenant_creation():
      tenant = Tenant(name="Test Corp", slug="test-corp")
      assert tenant.slug == "test-corp"
  ```
- **GREEN**: Implement `Tenant` with SQLAlchemy
- **Commit**: `feat: add Tenant SQLAlchemy model`

#### TASK_002: Define AgentConfigRow Model (persistence)

- **File**: `yaml-agno/src/db/models/agent_config.py`
- **Test**: `tests/unit/db/test_agent_config_model.py`
- **RED**:
  ```python
  def test_agent_config_row_creation():
      # @ai-directive: AgentConfigRow is the PERSISTENCE row.
      # The Pydantic AgentConfig (SPEC_02) is the JSONB validator, imported not redefined.
      row = AgentConfigRow(
          tenant_id=uuid4(),
          name="test_agent",
          config_yaml="agent:\n  name: test",
          config_jsonb={"agent": {"name": "test"}},
      )
      assert row.name == "test_agent"
  ```
- **GREEN**: Implement `AgentConfigRow` with foreign keys; validate `config_jsonb` against the imported Pydantic `AgentConfig` (SPEC_02)
- **Commit**: `feat: add AgentConfigRow SQLAlchemy model`

#### TASK_003: Create Migration for Tenants

- **File**: `yaml-agno/migrations/versions/001_create_tenants.py`
- **Test**: `tests/integration/test_migrations.py`
- **RED**:
  ```python
  async def test_tenants_table_exists(session):
      result = await session.execute(text("""
          SELECT EXISTS (
              SELECT FROM information_schema.tables
              WHERE table_name = 'tenants'
          )
      """))
      assert result.scalar_one() is True
  ```
- **GREEN**: Create migration with the `tenants` DDL
- **Commit**: `feat: add tenants table migration`

#### TASK_004: Create Migration for AgentConfigs

- **File**: `yaml-agno/migrations/versions/002_create_agent_configs.py`
- **Test**: `tests/integration/test_migrations.py`
- **RED**:
  ```python
  async def test_agent_configs_table_exists(session):
      result = await session.execute(text("""
          SELECT EXISTS (
              SELECT FROM information_schema.tables
              WHERE table_name = 'agent_configs'
          )
      """))
      assert result.scalar_one() is True
  ```
- **GREEN**: Create migration with the `agent_configs` DDL
- **Commit**: `feat: add agent_configs table migration`

#### TASK_005: Implement TransactionManager

- **File**: `yaml-agno/src/db/transaction.py`
- **Test**: `tests/unit/db/test_transaction_manager.py`
- **RED**:
  ```python
  async def test_transaction_commits_on_success(tm, session_factory):
      async with tm.transaction() as session:
          await session.execute(text("SELECT 1"))
      # Verify commit happened (no exception)
  ```
- **GREEN**: Implement `TransactionManager.transaction()`
- **Commit**: `feat: add TransactionManager context manager`

#### TASK_006: Implement Rollback on Error

- **File**: `yaml-agno/src/db/transaction.py`
- **Test**: `tests/unit/db/test_transaction_manager.py`
- **RED**:
  ```python
  async def test_transaction_rollback_on_error(tm):
      with pytest.raises(Exception):
          async with tm.transaction() as session:
              await session.execute(text("SELECT 1/0"))
      # Verify rollback happened
  ```
- **GREEN**: Add `try/except/rollback` to `transaction()`
- **Commit**: `feat: add automatic rollback on error`

#### TASK_007: Implement AgentConfigRepository

- **File**: `yaml-agno/src/repositories/agent_config_repository.py`
- **Test**: `tests/integration/repositories/test_agent_config_repository.py`
- **RED**:
  ```python
  async def test_create_agent_config(repo, tenant_id):
      config_id = await repo.create(
          tenant_id=tenant_id,
          name="test",
          config_yaml="agent:\n  name: test",
          config_jsonb={"agent": {"name": "test"}},
      )
      assert config_id is not None
  ```
- **GREEN**: Implement `AgentConfigRepository.create()`
- **Commit**: `feat: add AgentConfigRepository.create()`

#### TASK_008: Implement Get By Name

- **File**: `yaml-agno/src/repositories/agent_config_repository.py`
- **Test**: `tests/integration/repositories/test_agent_config_repository.py`
- **RED**:
  ```python
  async def test_get_by_name(repo, tenant_id):
      result = await repo.get_by_name(tenant_id, "test")
      assert result is not None
      assert result["name"] == "test"
  ```
- **GREEN**: Implement `AgentConfigRepository.get_by_name()`
- **Commit**: `feat: add AgentConfigRepository.get_by_name()`

---

## 8. TECHNICAL ASSUMPTIONS ADOPTED

### [Decision 1] PostgreSQL for Production

**Justification**:
- ACID compliance for transactions (config store)
- JSONB for flexible config + strict schema validation (via Pydantic from SPEC_02)
- RLS (Row Level Security) for multi-tenant isolation
- Native time-based partitioning (future retention extension)
- Full-text search over configs

### [Decision 2] SQLite for Development

**Justification**:
- Zero configuration for developers
- SQLAlchemy-compatible (same code base)
- Sufficient for unit tests
- No external dependencies

### [Decision 3] UUID v4 for IDs

**Justification**:
- Does not leak sequencing information
- Globally unique for distributed systems
- Native PostgreSQL support
- Better security than auto-increment integers

---

## 9. STRATEGIC CALIBRATION QUESTIONS

### [Question 1] Data Retention

**Is 30-day retention sufficient for session_state and message_history?**

Note: these data types are owned by Agno at runtime; retention is a future yaml-agno extension.

Implications:
- **Yes**: Meets GDPR, reduces storage costs
- **No**: Requires extended retention for compliance
- **Trade-off**: Storage cost vs compliance/analytics value

### [Question 2] Partition vs Separate Table

**Use time-based partitions or separate tables per tenant?**

Implications:
- **Partitions**: Simpler, better for temporal cleanup
- **Tables**: Better per-tenant isolation, more complex
- **Trade-off**: Schema simplicity vs maximum isolation

### [Question 3] Sync vs Async Replication

**Require synchronous replication for production configs?**

Implications:
- **Yes**: Strong consistency, higher latency
- **No**: Eventual consistency, better performance
- **Trade-off**: Write latency vs consistency guarantees

---

*Do you want to deepen the technical specification to **Level 6** for a specific component, or authorize execution of these tasks by the agent team?*
