---
Spec_ID: "SPEC_03"
Title: "Persistence Architecture - Database Schema and Storage"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#PostgreSQL", "#DDL", "#Indexes", "#Transactions"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02"]
Last_Updated: "2026-06-13"
---

# SPEC_03_PERSISTENCE_ARCHITECTURE

> **Propósito**: Definir el esquema físico de persistencia, mapeo de almacenamiento, índices de optimización y control transaccional para yaml-agno siguiendo principios ACID y Zero-Trust Security.

---

## 1. PERSISTENCE STRATEGY AND STORAGE MAPPING

### 1.1 Arquitectura de Storage

```mermaid
graph TB
    subgraph["Application Layer"]
        [yaml-agno Factory]
        [AgentInstance]
        [SessionContext]
    end
    
    subgraph["Persistence Layer"]
        [PostgreSQL]
        [SQLite Dev]
    end
    
    subgraph["Cache Layer"]
        [Redis Optional]
    end
    
    subgraph["Long-term Memory"]
        [Engram]
    end
    
    [yaml-agno Factory] -->|ConfigDB| [PostgreSQL]
    [AgentInstance] -->|Session State| [PostgreSQL]
    [SessionContext] -->|Message History| [PostgreSQL]
    [PostgreSQL] -.->|Replicate| [SQLite Dev]
    [PostgreSQL] <-->|Cache| [Redis Optional]
    [AgentInstance] -->|Learning| [Engram]
```

### 1.2 Mapeo de Datos a Storage

| Tipo de Dato | Storage Primario | Storage Backup | Retención | Justificación |
|--------------|------------------|----------------|-----------|----------------|
| **Config Yaml** | PostgreSQL | Git (versionado) | Permanente | Source of truth, multi-tenant |
| **Session State** | PostgreSQL | - | 30 días | Runtime state, GDPR compliant |
| **Message History** | PostgreSQL | - | 30 días | Conversation history, GDPR |
| **DI Variables** | PostgreSQL (cache) | API/DB source | 1 hora | Cached values, TTL |
| **Agent Execution Logs** | PostgreSQL | - | 90 días | Debugging, observabilidad |
| **Domain Events** | PostgreSQL | - | 7 días | Event sourcing, replay |

### 1.3 Multi-Tenant Isolation Strategy

**Estrategia**: Tenant isolation por `tenant_id` + Row Level Security (RLS)

```sql
-- Policy RLS para todas las tablas con tenant_id
CREATE POLICY tenant_isolation_policy ON all_tables
USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

**Ventajas**:
- Aislamiento completo entre tenants
- Prevención de data leakage
- GDPR compliant por defecto

---

## 2. DATABASE SCHEMA (DDL COMPLETOS)

### 2.1 Tabla: tenants

**Propósito**: Metadata de tenants (clientes/organizaciones)

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

-- Index para lookup por slug
CREATE INDEX idx_tenants_slug ON tenants(slug);
```

### 2.2 Tabla: agent_configs

**Propósito**: Configuraciones de agentes por tenant

```sql
CREATE TABLE agent_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identidad
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Configuración (YAML serializado)
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
    
    -- Estado
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Constraints
    CONSTRAINT tenant_name_unique UNIQUE (tenant_id, name),
    CONSTRAINT version_positive CHECK (version >= 1)
);

-- Indexes
CREATE INDEX idx_agent_configs_tenant_name ON agent_configs(tenant_id, name);
CREATE INDEX idx_agent_configs_tags ON agent_configs USING GIN(tags);
CREATE INDEX idx_agent_configs_active ON agent_configs(tenant_id, is_active);

-- Trigger para updated_at
CREATE TRIGGER update_agent_configs_updated_at
BEFORE UPDATE ON agent_configs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### 2.3 Tabla: team_configs

**Propósito**: Configuraciones de equipos por tenant

```sql
CREATE TABLE team_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identidad
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Configuración
    config_yaml TEXT NOT NULL,
    config_jsonb JSONB NOT NULL,
    
    -- Metadata
    description TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Estado
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Constraints
    CONSTRAINT tenant_name_unique UNIQUE (tenant_id, name)
);

-- Indexes
CREATE INDEX idx_team_configs_tenant_name ON team_configs(tenant_id, name);
CREATE INDEX idx_team_configs_tags ON team_configs USING GIN(tags);
```

### 2.4 Tabla: workflow_configs

**Propósito**: Configuraciones de workflows por tenant

```sql
CREATE TABLE workflow_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identidad
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Configuración
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

### 2.5 Tabla: agent_sessions

**Propósito**: Sesiones activas de agentes (runtime state)

```sql
CREATE TABLE agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identidad de sesión
    session_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    
    -- Referencia a config
    agent_config_id UUID NOT NULL REFERENCES agent_configs(id) ON DELETE CASCADE,
    
    -- Estado
    state VARCHAR(50) NOT NULL, -- created|initialized|running|completed|failed
    current_iteration INTEGER NOT NULL DEFAULT 0,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Resultados
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

-- Partición por created_at (retención 30 días)
-- CREATE TABLE agent_sessions_2026_06 PARTITION OF agent_sessions
-- FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
```

### 2.6 Tabla: session_contexts

**Propósito**: Contexto de sesión con historial de mensajes

```sql
CREATE TABLE session_contexts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identidad
    session_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    
    -- Estado
    session_state VARCHAR(50) NOT NULL DEFAULT 'active', -- active|paused|closed
    
    -- Historial
    message_history JSONB NOT NULL DEFAULT '[]', -- Array de mensajes
    max_history_size INTEGER NOT NULL DEFAULT 100,
    
    -- Estado de agentes
    agent_states JSONB NOT NULL DEFAULT '{}', -- agent_name → state JSON
    
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

-- Partición por last_activity (retención 30 días)
```

### 2.7 Tabla: di_variable_cache

**Propósito**: Cache de variables DI (Database, API, File providers)

```sql
CREATE TABLE di_variable_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identidad de variable
    provider_name VARCHAR(100) NOT NULL, -- user_db|config_api|app_config
    variable_key VARCHAR(255) NOT NULL, -- name|email|preferences
    
    -- Valor cacheado
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

-- Partición por expires_at (TTL 1 hora)
```

### 2.8 Tabla: domain_events

**Propósito**: Event sourcing para debugging y replay

```sql
CREATE TABLE domain_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identificación
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
    
    -- Procesamiento
    processed_at TIMESTAMPTZ,
    processing_attempts INTEGER NOT NULL DEFAULT 0,
    
    -- Constraints
    CONSTRAINT positive_attempts CHECK (processing_attempts >= 0)
);

-- Indexes
CREATE INDEX idx_domain_events_type ON domain_events(event_type);
CREATE INDEX idx_domain_events_tenant ON domain_events(tenant_id);
CREATE INDEX idx_domain_events_created ON domain_events(created_at DESC);
CREATE INDEX idx_domain_events_correlation ON domain_events(correlation_id);
CREATE INDEX idx_domain_events_processed ON domain_events(processed_at) WHERE processed_at IS NULL;

-- Partición por created_at (retención 7 días)
```

---

## 3. INDEXES AND PERFORMANCE TUNING

### 3.1 Índices Justificados

| Índice | Tabla | Columnas | Tipo | Justificación |
|--------|-------|----------|------|---------------|
| `idx_agent_configs_tenant_name` | agent_configs | (tenant_id, name) | B-tree | Lookup primario de configs por tenant |
| `idx_agent_configs_tags` | agent_configs | tags | GIN | Búsqueda por tags (config discovery) |
| `idx_agent_sessions_tenant_user` | agent_sessions | (tenant_id, user_id) | B-tree | Historial de sesiones por usuario |
| `idx_agent_sessions_state` | agent_sessions | state | B-tree | Filtrado de sesiones activas |
| `idx_session_contexts_last_activity` | session_contexts | last_activity DESC | B-tree | Cleanup de sesiones expiradas |
| `idx_di_cache_expires` | di_variable_cache | expires_at | B-tree | Eliminación de entradas expiradas |
| `idx_domain_events_processed` | domain_events | processed_at WHERE NULL | B-tree Partial | Eventos pendientes de procesamiento |

### 3.2 Consultas Optimizadas

```sql
-- Q1: Lookup de config activa por tenant y nombre
EXPLAIN ANALYZE
SELECT id, config_yaml, config_jsonb
FROM agent_configs
WHERE tenant_id = $1 AND name = $2 AND is_active = true;

-- Expected: Index Scan using idx_agent_configs_tenant_name + Filter

-- Q2: Sesiones activas por usuario
EXPLAIN ANALYZE
SELECT id, session_id, state, current_iteration
FROM agent_sessions
WHERE tenant_id = $1 AND user_id = $2 AND state = 'running'
ORDER BY created_at DESC
LIMIT 10;

-- Expected: Index Scan using idx_agent_sessions_tenant_user + idx_agent_sessions_state

-- Q3: Cleanup de sesiones expiradas (>30 días)
EXPLAIN ANALYZE
DELETE FROM session_contexts
WHERE last_activity < NOW() - INTERVAL '30 days';

-- Expected: Index Scan using idx_session_contexts_last_activity

-- Q4: Eventos pendientes de procesamiento
EXPLAIN ANALYZE
SELECT id, event_type, payload
FROM domain_events
WHERE processed_at IS NULL
ORDER BY created_at ASC
LIMIT 100;

-- Expected: Index Scan using idx_domain_events_processed
```

### 3.3 Estrategia de Particionamiento

**Tablas particionadas por tiempo**:
- `agent_sessions` por `created_at` (mensual)
- `session_contexts` por `last_activity` (mensual)
- `di_variable_cache` por `expires_at` (diaria)
- `domain_events` por `created_at` (diaria)

**Ventajas**:
- Drop partitions rápido para cleanup
- Queries con filtro de tiempo usan partition pruning
- Indexes más pequeños por partición

---

## 4. TRANSACTION MANAGER CONTRACT

### 4.1 Async Context Manager

```python
# yaml-agno/src/db/transaction.py

from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text

class TransactionManager:
    """Gestor de transacciones con retry y error handling"""
    
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
    
    @asynccontextmanager
    async def transaction(self, tenant_id: UUID | None = None) -> AsyncIterator[AsyncSession]:
        """
        Context manager para transacción con rollback automático.
        
        Args:
            tenant_id: ID de tenant para RLS (opcional)
            
        Yields:
            AsyncSession: Sesión de SQLAlchemy
            
        Raises:
            Exception: Cualquier error durante la transacción (rollback automático)
        """
        async with self.session_factory() as session:
            try:
                # Set tenant_id para RLS
                if tenant_id:
                    await session.execute(
                        text("SET LOCAL app.current_tenant = :tenant_id"),
                        {"tenant_id": str(tenant_id)}
                    )
                
                yield session
                
                # Commit explícito
                await session.commit()
                
            except Exception as e:
                # Rollback automático
                await session.rollback()
                raise
```

### 4.2 Ejemplo de Uso

```python
# yaml-agno/src/repositories/agent_config_repository.py

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

class AgentConfigRepository:
    """Repositorio para agent_configs"""
    
    def __init__(self, transaction_manager: TransactionManager):
        self.tm = transaction_manager
    
    async def create(
        self,
        tenant_id: UUID,
        name: str,
        config_yaml: str,
        config_jsonb: dict
    ) -> UUID:
        """Crea configuración de agente"""
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
                    "config_jsonb": config_jsonb
                }
            )
            return result.scalar_one()
    
    async def get_by_name(
        self,
        tenant_id: UUID,
        name: str
    ) -> dict | None:
        """Obtiene config por nombre"""
        async with self.tm.transaction(tenant_id=tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT id, config_yaml, config_jsonb
                    FROM agent_configs
                    WHERE tenant_id = :tenant_id AND name = :name AND is_active = true
                """),
                {"tenant_id": str(tenant_id), "name": name}
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None
```

---

## 5. BEHAVIOR DELTA - BDD SCENARIOS

### 5.1 Escenarios de Aceptación

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

## 6. TDD MICRO-TASK EXECUTION PROTOCOL

### 6.1 Cascading Task Checklist

#### TASK_001: Define Tenant Model

- **File**: `yaml-agno/src/db/models/tenant.py`
- **Test**: `tests/unit/db/test_tenant_model.py`
- **RED**:
  ```python
  def test_tenant_creation():
      tenant = Tenant(name="Test Corp", slug="test-corp")
      assert tenant.slug == "test-corp"
  ```
- **GREEN**: Implementar `Tenant` con SQLAlchemy
- **Commit**: `feat: add Tenant SQLAlchemy model`

#### TASK_002: Define AgentConfig Model

- **File**: `yaml-agno/src/db/models/agent_config.py`
- **Test**: `tests/unit/db/test_agent_config_model.py`
- **RED**:
  ```python
  def test_agent_config_creation():
      config = AgentConfig(
          tenant_id=uuid4(),
          name="test_agent",
          config_yaml="agent:\n  name: test",
          config_jsonb={"agent": {"name": "test"}}
      )
      assert config.name == "test_agent"
  ```
- **GREEN**: Implementar `AgentConfig` con foreign keys
- **Commit**: `feat: add AgentConfig SQLAlchemy model`

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
- **GREEN**: Crear migration con DDL de `tenants`
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
- **GREEN**: Crear migration con DDL de `agent_configs`
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
- **GREEN**: Implementar `TransactionManager.transaction()`
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
- **GREEN**: Añadir `try/except/rollback` en `transaction()`
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
          config_jsonb={"agent": {"name": "test"}}
      )
      assert config_id is not None
  ```
- **GREEN**: Implementar `AgentConfigRepository.create()`
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
- **GREEN**: Implementar `AgentConfigRepository.get_by_name()`
- **Commit**: `feat: add AgentConfigRepository.get_by_name()`

---

## 7. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] PostgreSQL para Producción

**Justificación**:
- ACID compliance para transacciones
- JSONB para config flexible + schema estricto
- RLS (Row Level Security) para multi-tenant isolation
- Particionamiento nativo por tiempo
- Full-text search en configs

### [Decisión 2] SQLite para Desarrollo

**Justificación**:
- Zero configuration para devs
- Compatible con SQLAlchemy (mismo code base)
- Suficiente para tests unitarios
- No requiere dependencies externas

### [Decisión 3] UUID v4 para IDs

**Justificación**:
- No expone información de secuencialidad
- Globally unique para distributed systems
- Soporte nativo en PostgreSQL
- Mejor security que auto-increment integers

---

## 8. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Retención de Datos

**¿Es suficiente 30 días de retención para session_state y message_history?**

Implica:
- **Sí**: Cumple GDPR, reduce storage costs
- **No**: Requerir retención extendida para compliance
- **Trade-off**: Storage cost vs compliance/analytics value

### [Pregunta 2] Particion vs Tabla Separada

**¿Usar particiones por tiempo o tablas separadas por tenant?**

Implica:
- **Particiones**: Más simple, mejor para cleanup temporal
- **Tablas**: Mejor aislamiento por tenant, más complejo
- **Trade-off**: Simplicidad de schema vs aislamiento máximo

### [Pregunta 3] Sync vs Async Replication

**¿Requerir replicación síncrona para configs de producción?**

Implica:
- **Sí**: Consistencia fuerte, más latencia
- **No**: Eventual consistency, mejor performance
- **Trade-off**: Latency de writes vs garantías de consistencia

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
