---
Spec_ID: "SPEC_08"
Title: "TDD Microtasks - Implementation Checklist"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#TDD", "#Microtasks", "#Checklist", "#Implementation"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02", "SPEC_03"]
Last_Updated: "2026-06-13"
---

# SPEC_08_TDD_MICROTASKS

> **Propósito**: Plan de micro-tareas secuenciales listas para ejecución por agentes TDD con protocolo RED/GREEN/REFACTOR.

---

## 1. TDD MICRO-TASK EXECUTION PROTOCOL

### 1.1 Protocolo Completo

```
┌─────────────────────────────────────────────────────────────┐
│                    TDD EXECUTION PROTOCOL                    │
├─────────────────────────────────────────────────────────────┤
│  1. RED    → Escribir test que falla con implementación vacía│
│  2. GREEN  → Implementación mínima para pasar el test        │
│  3. REFACTOR→ Limpieza de código sin cambiar comportamiento │
│  4. COMMIT → Mensaje descriptivo del cambio                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Reglas de Oro

- **Nunca escribir código sin test primero**
- **Solo escribir el mínimo código para pasar el test**
- **Refactorizar solo después de GREEN**
- **Commits atómicos por task**
- **Mantener tests < 100 lines**

---

## 2. CASCADING TASK CHECKLIST

### 2.1 Fase 1: Core Models (Tasks 001-020)

#### TASK_001: Initialize Project Structure
- **File**: `yaml-agno/pyproject.toml`
- **Test**: `tests/unit/test_project_init.py`
- **RED**: `import yaml_agno` fails
- **GREEN**: Create `pyproject.toml` with Python 3.12+
- **Commit**: `chore: initialize project with pyproject.toml`

#### TASK_002: Create AgentConfig Model
- **File**: `yaml-agno/src/models/config/agent_config.py`
- **Test**: `tests/unit/models/test_agent_config.py`
- **RED**: `AgentConfig(name="test", model="openai/gpt-4o")` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add AgentConfig Pydantic model`

#### TASK_003: Add Model Validation
- **File**: `yaml-agno/src/models/config/agent_config.py`
- **Test**: `tests/unit/models/test_agent_config.py`
- **RED**: Invalid model format doesn't raise error
- **GREEN**: Add `@field_validator("model")`
- **Commit**: `feat: add model format validation`

#### TASK_004: Create TeamConfig Model
- **File**: `yaml-agno/src/models/config/team_config.py`
- **Test**: `tests/unit/models/test_team_config.py`
- **RED**: `TeamConfig(name="test", mode="coordinate")` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add TeamConfig Pydantic model`

#### TASK_005: Create WorkflowConfig Model
- **File**: `yaml-agno/src/models/config/workflow_config.py`
- **Test**: `tests/unit/models/test_workflow_config.py`
- **RED**: `WorkflowConfig(name="test", steps=[...])` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add WorkflowConfig Pydantic model`

#### TASK_006: Create SessionContext Model
- **File**: `yaml-agno/src/models/runtime/session_context.py`
- **Test**: `tests/unit/models/test_session_context.py`
- **RED**: `SessionContext(session_id="s1", user_id="u1", tenant_id="t1")` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add SessionContext Pydantic model`

#### TASK_007: Create AgentInstance Model
- **File**: `yaml-agno/src/models/runtime/agent_instance.py`
- **Test**: `tests/unit/models/test_agent_instance.py`
- **RED**: `AgentInstance(config_name="test")` fails
- **GREEN**: Implement Pydantic model with lifecycle
- **Commit**: `feat: add AgentInstance Pydantic model`

#### TASK_008: Create ModelId Value Object
- **File**: `yaml-agno/src/models/value_objects/model_id.py`
- **Test**: `tests/unit/value_objects/test_model_id.py`
- **RED**: `ModelId(value="openai/gpt-4o")` fails
- **GREEN**: Implement frozen Pydantic model
- **Commit**: `feat: add ModelId value object`

#### TASK_009: Create SessionKey Value Object
- **File**: `yaml-agno/src/models/value_objects/session_key.py`
- **Test**: `tests/unit/value_objects/test_session_key.py`
- **RED**: `SessionKey(user_id="u1", session_name="s1")` fails
- **GREEN**: Implement frozen Pydantic model
- **Commit**: `feat: add SessionKey value object`

#### TASK_010: Create DIReference Value Object
- **File**: `yaml-agno/src/models/value_objects/di_reference.py`
- **Test**: `tests/unit/value_objects/test_di_reference.py`
- **RED**: `DIReference(template="${user_db.name}")` fails
- **GREEN**: Implement frozen Pydantic model
- **Commit**: `feat: add DIReference value object`

### 2.2 Fase 2: Factories (Tasks 011-025)

#### TASK_011: Create AgentFactory
- **File**: `yaml-agno/src/factories/agent_factory.py`
- **Test**: `tests/unit/factories/test_agent_factory.py`
- **RED**: `AgentFactory.create(config)` fails
- **GREEN**: Implement `create()` method
- **Commit**: `feat: add AgentFactory.create()`

#### TASK_012: Add Model Resolution
- **File**: `yaml-agno/src/factories/agent_factory.py`
- **Test**: `tests/unit/factories/test_agent_factory.py`
- **RED**: `_resolve_model("openai/gpt-4o")` fails
- **GREEN**: Implement `_resolve_model()`
- **Commit**: `feat: add model resolution logic`

#### TASK_013: Create TeamFactory
- **File**: `yaml-agno/src/factories/team_factory.py`
- **Test**: `tests/unit/factories/test_team_factory.py`
- **RED**: `TeamFactory.create(config, agents)` fails
- **GREEN**: Implement `create()` method
- **Commit**: `feat: add TeamFactory.create()`

#### TASK_014: Create WorkflowFactory
- **File**: `yaml-agno/src/factories/workflow_factory.py`
- **Test**: `tests/unit/factories/test_workflow_factory.py`
- **RED**: `WorkflowFactory.create(config, agents, teams)` fails
- **GREEN**: Implement `create()` method
- **Commit**: `feat: add WorkflowFactory.create()`

#### TASK_015: Add Step Builder
- **File**: `yaml-agno/src/factories/workflow_factory.py`
- **Test**: `tests/unit/factories/test_workflow_factory.py`
- **RED**: `_build_step(step_config, agents, teams)` fails
- **GREEN**: Implement `_build_step()`
- **Commit**: `feat: add step builder logic`

### 2.3 Fase 3: Persistence (Tasks 026-040)

#### TASK_016: Create Tenant Model
- **File**: `yaml-agno/src/db/models/tenant.py`
- **Test**: `tests/unit/db/test_tenant_model.py`
- **RED**: `Tenant(name="Test", slug="test")` fails
- **GREEN**: Implement SQLAlchemy model
- **Commit**: `feat: add Tenant SQLAlchemy model`

#### TASK_017: Create AgentConfig Model (DB)
- **File**: `yaml-agno/src/db/models/agent_config.py`
- **Test**: `tests/unit/db/test_agent_config_model.py`
- **RED**: `AgentConfigDB(...)` fails
- **GREEN**: Implement SQLAlchemy model
- **Commit**: `feat: add AgentConfigDB SQLAlchemy model`

#### TASK_018: Create SessionContext Model (DB)
- **File**: `yaml-agno/src/db/models/session_context.py`
- **Test**: `tests/unit/db/test_session_context_model.py`
- **RED**: `SessionContextDB(...)` fails
- **GREEN**: Implement SQLAlchemy model
- **Commit**: `feat: add SessionContextDB SQLAlchemy model`

#### TASK_019: Create Migration - Tenants
- **File**: `yaml-agno/migrations/versions/001_create_tenants.py`
- **Test**: `tests/integration/test_migrations.py`
- **RED**: `tenants` table doesn't exist
- **GREEN**: Create migration with DDL
- **Commit**: `feat: add tenants table migration`

#### TASK_020: Create Migration - AgentConfigs
- **File**: `yaml-agno/migrations/versions/002_create_agent_configs.py`
- **Test**: `tests/integration/test_migrations.py`
- **RED**: `agent_configs` table doesn't exist
- **GREEN**: Create migration with DDL
- **Commit**: `feat: add agent_configs table migration`

#### TASK_021: Create TransactionManager
- **File**: `yaml-agno/src/db/transaction.py`
- **Test**: `tests/unit/db/test_transaction_manager.py`
- **RED**: `async with tm.transaction():` fails
- **GREEN**: Implement context manager
- **Commit**: `feat: add TransactionManager context manager`

#### TASK_022: Add Rollback on Error
- **File**: `yaml-agno/src/db/transaction.py`
- **Test**: `tests/unit/db/test_transaction_manager.py`
- **RED**: Exception doesn't trigger rollback
- **GREEN**: Add `try/except/rollback`
- **Commit**: `feat: add automatic rollback`

#### TASK_023: Create AgentConfigRepository
- **File**: `yaml-agno/src/repositories/agent_config_repository.py`
- **Test**: `tests/integration/repositories/test_agent_config_repository.py`
- **RED**: `repo.create(...)` fails
- **GREEN**: Implement `create()` method
- **Commit**: `feat: add AgentConfigRepository.create()`

#### TASK_024: Add Get By Name
- **File**: `yaml-agno/src/repositories/agent_config_repository.py`
- **Test**: `tests/integration/repositories/test_agent_config_repository.py`
- **RED**: `repo.get_by_name(...)` fails
- **GREEN**: Implement `get_by_name()` method
- **Commit**: `feat: add AgentConfigRepository.get_by_name()`

#### TASK_025: Add List Active
- **File**: `yaml-agno/src/repositories/agent_config_repository.py`
- **Test**: `tests/integration/repositories/test_agent_config_repository.py`
- **RED**: `repo.list_active(...)` fails
- **GREEN**: Implement `list_active()` method
- **Commit**: `feat: add AgentConfigRepository.list_active()`

### 2.4 Fase 4: Memory (Tasks 041-055)

#### TASK_026: Create PIISanitizer
- **File**: `yaml-agno/src/memory/pii_sanitizer.py`
- **Test**: `tests/unit/memory/test_pii_sanitizer.py`
- **RED**: `PIISanitizer().sanitize(...)` fails
- **GREEN**: Implement sanitization logic
- **Commit**: `feat: add PII sanitizer`

#### TASK_027: Create SecretSanitizer
- **File**: `yaml-agno/src/memory/secret_sanitizer.py`
- **Test**: `tests/unit/memory/test_secret_sanitizer.py`
- **RED**: `SecretSanitizer().sanitize(...)` fails
- **GREEN**: Implement secret masking
- **Commit**: `feat: add secret sanitizer`

#### TASK_028: Create ContextCompressor
- **File**: `yaml-agno/src/memory/compression.py`
- **Test**: `tests/unit/memory/test_compression.py`
- **RED**: `ContextCompressor().should_compress(...)` fails
- **GREEN**: Implement threshold check
- **Commit**: `feat: add context compressor`

#### TASK_029: Add Important Message Identification
- **File**: `yaml-agno/src/memory/compression.py`
- **Test**: `tests/unit/memory/test_compression.py`
- **RED**: `_identify_important(...)` fails
- **GREEN**: Implement identification logic
- **Commit**: `feat: add important message identification`

#### TASK_030: Create EngramMemoryManager
- **File**: `yaml-agno/src/memory/engram_manager.py`
- **Test**: `tests/integration/memory/test_engram_manager.py`
- **RED**: `manager.save_decision(...)` fails
- **GREEN**: Implement save methods
- **Commit**: `feat: add Engram memory manager`

#### TASK_031: Add Search Relevant
- **File**: `yaml-agno/src/memory/engram_manager.py`
- **Test**: `tests/integration/memory/test_engram_manager.py`
- **RED**: `manager.search_relevant(...)` fails
- **GREEN**: Implement search via Engram
- **Commit**: `feat: add Engram search`

### 2.5 Fase 5: Workflows (Tasks 056-070)

#### TASK_032: Create WorkflowExecution Model
- **File**: `yaml-agno/src/workflows/models.py`
- **Test**: `tests/unit/workflows/test_models.py`
- **RED**: `WorkflowExecution(...)` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add WorkflowExecution model`

#### TASK_033: Create StepExecutor
- **File**: `yaml-agno/src/workflows/step_executor.py`
- **Test**: `tests/unit/workflows/test_step_executor.py`
- **RED**: `executor.execute_step(...)` fails
- **GREEN**: Implement step execution
- **Commit**: `feat: add step executor`

#### TASK_034: Add Parallel Execution
- **File**: `yaml-agno/src/workflows/step_executor.py`
- **Test**: `tests/unit/workflows/test_step_executor.py`
- **RED**: `executor.execute_parallel_step(...)` fails
- **GREEN**: Implement with asyncio.gather
- **Commit**: `feat: add parallel step execution`

#### TASK_035: Create ConditionEvaluator
- **File**: `yaml-agno/src/workflows/condition_evaluator.py`
- **Test**: `tests/unit/workflows/test_condition_evaluator.py`
- **RED**: `evaluator.evaluate(...)` fails
- **GREEN**: Implement CEL evaluation
- **Commit**: `feat: add CEL condition evaluator`

#### TASK_036: Create RetryPolicy
- **File**: `yaml-agno/src/workflows/retry_policy.py`
- **Test**: `tests/unit/workflows/test_retry_policy.py`
- **RED**: `policy.execute_with_retry(...)` fails
- **GREEN**: Implement retry logic
- **Commit**: `feat: add retry policy with exponential backoff`

#### TASK_037: Add Error Categorization
- **File**: `yaml-agno/src/workflows/retry_policy.py`
- **Test**: `tests/unit/workflows/test_retry_policy.py`
- **RED**: `policy.categorize_error(...)` fails
- **GREEN**: Implement categorization
- **Commit**: `feat: add error categorization`

#### TASK_038: Create TeamMessage Protocol
- **File**: `yaml-agno/src/workflows/message_protocol.py`
- **Test**: `tests/unit/workflows/test_message_protocol.py`
- **RED**: `TeamMessage(...)` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add team message protocol`

#### TASK_039: Create WorkflowStateMachine
- **File**: `yaml-agno/src/workflows/state_machine.py`
- **Test**: `tests/unit/workflows/test_state_machine.py`
- **RED**: `sm.transition_to(...)` fails
- **GREEN**: Implement state transitions
- **Commit**: `feat: add workflow state machine`

### 2.6 Fase 6: API (Tasks 071-085)

#### TASK_040: Create AgentRunRequest Model
- **File**: `yaml-agno/src/api/models/agents.py`
- **Test**: `tests/unit/api/test_agent_models.py`
- **RED**: `AgentRunRequest(...)` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add AgentRunRequest model`

#### TASK_041: Create AgentRunResponse Model
- **File**: `yaml-agno/src/api/models/agents.py`
- **Test**: `tests/unit/api/test_agent_models.py`
- **RED**: `AgentRunResponse(...)` fails
- **GREEN**: Implement Pydantic model
- **Commit**: `feat: add AgentRunResponse model`

#### TASK_042: Create Run Agent Endpoint
- **File**: `yaml-agno/src/api/endpoints/agents.py`
- **Test**: `tests/integration/api/test_agent_endpoints.py`
- **RED**: `POST /api/v1/agents/{name}/run` fails
- **GREEN**: Implement endpoint
- **Commit**: `feat: add run agent endpoint`

#### TASK_043: Create Health Check Endpoint
- **File**: `yaml-agno/src/api/endpoints/health.py`
- **Test**: `tests/integration/api/test_health_endpoints.py`
- **RED**: `GET /health` fails
- **GREEN**: Implement endpoint
- **Commit**: `feat: add health check endpoint`

#### TASK_044: Create Readiness Probe
- **File**: `yaml-agno/src/api/endpoints/health.py`
- **Test**: `tests/integration/api/test_health_endpoints.py`
- **RED**: `GET /health/readiness` fails
- **GREEN**: Implement endpoint
- **Commit**: `feat: add readiness probe`

#### TASK_045: Define AX Schemas
- **File**: `yaml-agno/src/api/ax/schemas.py`
- **Test**: `tests/unit/api/test_ax_schemas.py`
- **RED**: `get_ax_schema("create_agent")` fails
- **GREEN**: Implement schema definitions
- **Commit**: `feat: add AX schema definitions`

### 2.7 Fase 7: Integration Tests (Tasks 086-100)

#### TASK_046: Create Agent End-to-End Test
- **File**: `tests/integration/e2e/test_agent_lifecycle.py`
- **Test**: Full agent creation → execution → deletion
- **RED**: Test fails (no implementation)
- **GREEN**: Implement all components
- **Commit**: `test: add agent e2e test`

#### TASK_047: Create Team End-to-End Test
- **File**: `tests/integration/e2e/test_team_lifecycle.py`
- **Test**: Full team creation → execution → deletion
- **RED**: Test fails (no implementation)
- **GREEN**: Implement all components
- **Commit**: `test: add team e2e test`

#### TASK_048: Create Workflow End-to-End Test
- **File**: `tests/integration/e2e/test_workflow_lifecycle.py`
- **Test**: Full workflow creation → execution → completion
- **RED**: Test fails (no implementation)
- **GREEN**: Implement all components
- **Commit**: `test: add workflow e2e test`

#### TASK_049: Create Memory Compression Test
- **File**: `tests/integration/memory/test_compression_e2e.py`
- **Test**: Full compression cycle
- **RED**: Test fails (no implementation)
- **GREEN**: Implement compression
- **Commit**: `test: add compression e2e test`

#### TASK_050: Create Error Recovery Test
- **File**: `tests/integration/workflows/test_error_recovery.py`
- **Test**: Full retry cycle with transient error
- **RED**: Test fails (no implementation)
- **GREEN**: Implement retry logic
- **Commit**: `test: add error recovery e2e test`

---

## 3. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] 100 Tasks Máximo

**Justificación**:
- Mantener scope manejable
- Permite tracking fino
- Cada task < 50 LOC

### [Decisión 2] Commits Atómicos

**Justificación**:
- Rollback fácil
- Historial limpio
- Code review por task

### [Decisión 3] Tests por Definición

**Justificación**:
- Documentación viva
- Previene regresiones
- Especificación ejecutable

---

## 4. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Task Granularity

**¿50 tasks es suficientemente granular o necesitamos 100+?**

Implica:
- **50**: Tasks más grandes, más contexto
- **100+**: Tasks más atómicas, más commits
- **Trade-off**: Granularidad vs overhead

### [Pregunta 2] Paralelización de Tasks

**¿Qué tasks pueden ejecutarse en paralelo?**

Implicas:
- **Independent**: Models, value objects
- **Sequential**: Factories → Repositories → API
- **Trade-off**: Velocidad vs dependencias

### [Pregunta 3] Testing Strategy

**¿Unit tests > Integration tests o balance 50/50?**

Implica:
- **Unit-heavy**: Más rápido, menos confidence
- **Integration-heavy**: Más lento, más confidence
- **Balance**: Mejor cobertura

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
