---
Spec_ID: "SPEC_08"
Title: "TDD Microtasks - Master Catalog"
Version: "0.2.0-iter1"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#TDD", "#Microtasks", "#MasterCatalog", "#Traceability"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02", "SPEC_03", "SPEC_04", "SPEC_05", "SPEC_06", "SPEC_07", "SPEC_09", "SPEC_15"]
Last_Updated: "2026-06-17"
Revision_Note: "Iteration 1 - rewritten as a master catalog that aggregates the microtasks already defined by their owning SPECs (00-07, plus 09/15 referenced for delegation). Removed all tasks that created classes eliminated in this iteration (SessionContext, SessionState, AgentInstance, ModelId, SessionKey, WorkflowExecution, domain events, native EngramMemoryManager). The only own model = *Config schemas (SPEC_02) + DIReference. Factories live in SPEC_01 with DependencyManager. Long-term memory via LongTermMemoryPort (Engram = optional adapter). Code/descriptions in English."
---

# SPEC_08_TDD_MICROTASKS

> **Purpose**: Master catalog that consolidates, for traceability, the TDD microtasks already defined inside their owner SPECs. This spec does NOT redefine tasks; it aggregates them grouped by owner SPEC so the full RED/GREEN/REFACTOR execution path is visible in one place.
>
> **@ai-directive (catalog, not source of truth)**: The authoritative definition of each microtask lives in its **owner SPEC** (column `Owner SPEC` below). Every entry here is a pointer. If a task is missing details, read the owner SPEC section, never invent a new task here. Concrete RED steps, GREEN implementation notes, file paths and commit messages are copied verbatim from the owner SPECs and must stay in sync with them.

---

## 1. TDD MICRO-TASK EXECUTION PROTOCOL

### 1.1 Full Protocol

```
+-------------------------------------------------------------+
|                    TDD EXECUTION PROTOCOL                    |
+-------------------------------------------------------------+
|  1. RED     -> Write a failing test against an empty impl    |
|  2. GREEN   -> Minimum implementation to make the test pass  |
|  3. REFACTOR-> Clean code without changing behavior          |
|  4. COMMIT  -> Descriptive conventional commit message       |
+-------------------------------------------------------------+
```

### 1.2 Golden Rules

- **Never write code without a test first.**
- **Write only the minimum code required to pass the test.**
- **Refactor only after GREEN.**
- **One atomic commit per task.**
- **Keep tests under 100 lines.**

### 1.3 @ai-directive - Classes that MUST NOT be created

The following classes were removed in iteration 1 of SPEC_00-02 and MUST NOT appear as tasks to create anywhere in this catalog. They are listed here only as a negative list so reviewers can catch regressions:

- `SessionContext`, `SessionState`, `AgentInstance` - yaml-agno does NOT own a session/agent runtime; Agno manages these natively.
- `ModelId`, `SessionKey` - value objects removed in SPEC_02. `model` is a plain validated `str`; `user_id`+`session_id` are Agno first-class keys.
- `WorkflowExecution`, `WorkflowState`, `WorkflowStateMachine` - workflow runtime is Agno native; yaml-agno only declares `WorkflowConfig`/`StepConfig` (SPEC_02) and builds via `WorkflowFactory` (SPEC_01).
- Domain events (e.g. `AgentConfigCreated`, `AgentStateChanged`) - removed; no proprietary domain event surface.
- `EngramMemoryManager` as a native memory component - Engram is an OPTIONAL adapter implementing `LongTermMemoryPort`; the default backend is the Agno `LearningMachine`.

---

## 2. CASCADING TASK CHECKLIST (MASTER CATALOG)

> Grouping order follows the dependency graph: `SPEC_02` schemas -> `SPEC_01` factories -> `SPEC_03` persistence -> `SPEC_04` memory -> `SPEC_05` workflows -> `SPEC_06` API. `SPEC_00` contributes the DI/templates Core mechanism (no inline TDD tasks; referenced as cross-cutting dependency). `SPEC_07` (dashboard) consumes the API and contributes no backend microtasks in this catalog.

### 2.1 Owner SPEC_02 - Domain Schemas (Pydantic V2)

> @ai-directive: these are the ONLY data model yaml-agno owns. `AgentConfig`, `TeamConfig`, `WorkflowConfig`, `StepConfig`, `DIReference`. Enums (`TeamMode`, `StepType`) are IMPORTED from Agno, never redefined.

| Catalog ID | Owner SPEC task | Component | File | Test |
|------------|-----------------|-----------|------|------|
| S02-T01 | SPEC_02 TASK_001 | `AgentConfig` schema | `src/models/config/agent_config.py` | `tests/unit/models/test_agent_config.py` |
| S02-T02 | SPEC_02 TASK_002 | `AgentConfig` model format + name validation | `src/models/config/agent_config.py` | `tests/unit/models/test_agent_config.py` |
| S02-T03 | SPEC_02 TASK_003 | `TeamConfig` (Agno `TeamMode` import) | `src/models/config/team_config.py` | `tests/unit/models/test_team_config.py` |
| S02-T04 | SPEC_02 TASK_004 | `TeamConfig` member uniqueness + mode requirements | `src/models/config/team_config.py` | `tests/unit/models/test_team_config.py` |
| S02-T05 | SPEC_02 TASK_005 | `WorkflowConfig` + `StepConfig` (Agno `StepType` import) | `src/models/config/workflow_config.py` | `tests/unit/models/test_workflow_config.py` |
| S02-T06 | SPEC_02 TASK_006 | `WorkflowConfig` branch reference validation | `src/models/config/workflow_config.py` | `tests/unit/models/test_workflow_config.py` |
| S02-T07 | SPEC_02 TASK_007 | `DIReference` value object (`${provider.key}`) | `src/models/value_objects/di_reference.py` | `tests/unit/value_objects/test_di_reference.py` |

### 2.2 Owner SPEC_01 - Runtime Factories + DependencyManager

> @ai-directive: factories translate validated YAML (SPEC_02 schemas) into native Agno objects. All factories are `async` and receive a `DependencyManager`. `DependencyManager` resolves providers/DBs/primitives lazily, validated, cached, with allowlist + entry_points. `SessionConfig`/`SessionManager` configure the Agno `db=`, they do NOT model a session runtime.

| Catalog ID | Owner SPEC task | Component | File | Test |
|------------|-----------------|-----------|------|------|
| S01-T01 | SPEC_01 TASK_001 | `AgentConfig` Pydantic model (factory input) | `src/models/config/agent_config.py` | `tests/unit/models/test_agent_config.py` |
| S01-T02 | SPEC_01 TASK_002 | `AgentFactory.create()` (async) | `src/factories/agent_factory.py` | `tests/unit/factories/test_agent_factory.py` |
| S01-T03 | SPEC_01 TASK_003 | Model resolution via `DependencyManager.resolve_model()` | `src/factories/agent_factory.py` | `tests/unit/factories/test_agent_factory.py` |
| S01-T04 | SPEC_01 TASK_004 | `TeamConfig` Pydantic model (factory input) | `src/models/config/team_config.py` | `tests/unit/models/test_team_config.py` |
| S01-T05 | SPEC_01 TASK_005 | `TeamFactory.create()` (async) | `src/factories/team_factory.py` | `tests/unit/factories/test_team_factory.py` |
| S01-T06 | SPEC_01 TASK_006 | Team mode mapping (4 modes: coordinate/route/broadcast/tasks) | `src/factories/team_factory.py` | `tests/unit/factories/test_team_factory.py` |
| S01-T07 | SPEC_01 TASK_007 | `SessionConfig` Pydantic model (`storage_type` = registry key, not enum) | `src/models/session.py` | `tests/unit/test_session_models.py` |
| S01-T08 | SPEC_01 TASK_008 | `SessionManager.validate()` (delegates to `DependencyManager` registry) | `src/core/session_manager.py` | `tests/unit/test_session_manager.py` |

> @ai-directive (cross-cutting): `WorkflowFactory` lives in SPEC_01 section 4 but its microtasks are catalogued under SPEC_05 below because they are co-located with the workflow execution tasks. The factory + step builder build native `agno.Workflow` via lazy primitive resolution in `DependencyManager` - there is NO proprietary workflow runtime.

### 2.3 Owner SPEC_03 - Persistence (Config Store)

> @ai-directive: persistence stores CONFIG rows, NOT runtime models. `AgentConfigRow` is the SQLAlchemy row whose `config_jsonb` is validated against the Pydantic `AgentConfig` (imported from SPEC_02, not redefined). `TransactionManager` wraps the config-store, not a session history.

| Catalog ID | Owner SPEC task | Component | File | Test |
|------------|-----------------|-----------|------|------|
| S03-T01 | SPEC_03 TASK_001 | `Tenant` model (SQLAlchemy) | `src/db/models/tenant.py` | `tests/unit/db/test_tenant_model.py` |
| S03-T02 | SPEC_03 TASK_002 | `AgentConfigRow` model (persistence row; validates JSONB against Pydantic `AgentConfig`) | `src/db/models/agent_config.py` | `tests/unit/db/test_agent_config_model.py` |
| S03-T03 | SPEC_03 TASK_003 | Migration - `tenants` table | `migrations/versions/001_create_tenants.py` | `tests/integration/test_migrations.py` |
| S03-T04 | SPEC_03 TASK_004 | Migration - `agent_configs` table | `migrations/versions/002_create_agent_configs.py` | `tests/integration/test_migrations.py` |
| S03-T05 | SPEC_03 TASK_005 | `TransactionManager.transaction()` (config-store ACID) | `src/db/transaction.py` | `tests/unit/db/test_transaction_manager.py` |
| S03-T06 | SPEC_03 TASK_006 | `TransactionManager` rollback on error | `src/db/transaction.py` | `tests/unit/db/test_transaction_manager.py` |
| S03-T07 | SPEC_03 TASK_007 | `AgentConfigRepository.create()` | `src/repositories/agent_config_repository.py` | `tests/integration/repositories/test_agent_config_repository.py` |
| S03-T08 | SPEC_03 TASK_008 | `AgentConfigRepository.get_by_name()` | `src/repositories/agent_config_repository.py` | `tests/integration/repositories/test_agent_config_repository.py` |

### 2.4 Owner SPEC_04 - Long-term Memory (Port + Adapters)

> @ai-directive: yaml-agno does NOT own a session runtime or memory FIFO - that is Agno native. SPEC_04 only adds a `LongTermMemoryPort` Protocol and two adapters: the DEFAULT Agno `LearningMachine` adapter and an OPTIONAL Engram adapter. Compression (`ContextCompressor`) lives in SPEC_15; PII/secret sanitization lives in SPEC_16 - NOT here.

| Catalog ID | Owner SPEC task | Component | File | Test |
|------------|-----------------|-----------|------|------|
| S04-T01 | SPEC_04 TASK_001 | `LongTermMemoryPort` Protocol (save_decision/save_discovery/save_bugfix/search_relevant) | `src/memory/long_term_port.py` | `tests/unit/memory/test_long_term_port.py` |
| S04-T02 | SPEC_04 TASK_002 | Default Agno memory adapter (`AgnoLearningMemoryAdapter`) | `src/memory/agno_memory_adapter.py` | `tests/unit/memory/test_agno_memory_adapter.py` |
| S04-T03 | SPEC_04 TASK_003 | `build_memory_config()` - YAML memory block -> Agno constructor flags | `src/memory/agno_memory_config.py` | `tests/unit/memory/test_agno_memory_config.py` |
| S04-T04 | SPEC_04 TASK_004 | `recall_on_start()` through the `LongTermMemoryPort` | `src/memory/agno_memory_config.py` | `tests/integration/memory/test_recall_on_start.py` |
| S04-T05 | SPEC_04 TASK_005 | Optional Engram adapter implementing `LongTermMemoryPort` | `src/memory/engram_manager.py` | `tests/integration/memory/test_engram_manager.py` |
| S04-T06 | SPEC_04 TASK_006 | `AutosaveManager` (depends on `LongTermMemoryPort`) | `src/memory/autosave.py` | `tests/unit/memory/test_autosave.py` |

### 2.5 Owner SPEC_05 - Workflows and Teams

> @ai-directive: workflow declaration uses `WorkflowConfig`/`StepConfig` from SPEC_02 (single source of truth). Execution delegates to Agno primitives resolved lazily via `DependencyManager`. NO `WorkflowExecution`/`WorkflowState`/`WorkflowStateMachine` - removed. Retry classification is delegated to Core Infra (SPEC_09), retry is applied at the workflow level.

| Catalog ID | Owner SPEC task | Component | File | Test |
|------------|-----------------|-----------|------|------|
| S05-T01 | SPEC_05 TASK_001 | Workflow declaration via `WorkflowConfig`/`StepConfig` (SPEC_02) + `WorkflowFactory` build | `src/factories/workflow_factory.py` | `tests/unit/factories/test_workflow_factory.py` |
| S05-T02 | SPEC_05 TASK_002 | Step executor (delegates to Agno primitive) | `src/workflows/step_executor.py` | `tests/unit/workflows/test_step_executor.py` |
| S05-T03 | SPEC_05 TASK_003 | Parallel step executor (`asyncio.gather`) | `src/workflows/step_executor.py` | `tests/unit/workflows/test_step_executor.py` |
| S05-T04 | SPEC_05 TASK_004 | Condition evaluator (CEL) | `src/workflows/condition_evaluator.py` | `tests/unit/workflows/test_condition_evaluator.py` |
| S05-T05 | SPEC_05 TASK_005 | Step-level retry policy | `src/workflows/retry_policy.py` | `tests/unit/workflows/test_retry_policy.py` |
| S05-T06 | SPEC_05 TASK_006 | Retry decision (classification delegated to Core Infra) | `src/workflows/retry_policy.py` | `tests/unit/workflows/test_retry_policy.py` |
| S05-T07 | SPEC_05 TASK_007 | Team message protocol (`TeamMessage` Pydantic model) | `src/workflows/message_protocol.py` | `tests/unit/workflows/test_message_protocol.py` |
| S05-T08 | SPEC_05 TASK_008 | Verify Agno delegation (no proprietary workflow runtime) | `tests/integration/workflows/test_agno_delegation.py` | (same) |

### 2.6 Owner SPEC_06 - API and AX

> @ai-directive: `AgentRunRequest`/`AgentRunResponse` are DTOs owned by SPEC_06 (the API layer), not duplicated from a runtime model. Readiness probe does NOT depend on Engram (Engram is optional). SPEC_06 depends on SPEC_02 schemas for request validation.

| Catalog ID | Owner SPEC task | Component | File | Test |
|------------|-----------------|-----------|------|------|
| S06-T01 | SPEC_06 TASK_001 | `AgentRunRequest` model (API DTO) | `src/api/models/agents.py` | `tests/unit/api/test_agent_models.py` |
| S06-T02 | SPEC_06 TASK_002 | `AgentRunResponse` model (API DTO) | `src/api/models/agents.py` | `tests/unit/api/test_agent_models.py` |
| S06-T03 | SPEC_06 TASK_003 | `POST /api/v1/agents/{name}/run` endpoint | `src/api/endpoints/agents.py` | `tests/integration/api/test_agent_endpoints.py` |
| S06-T04 | SPEC_06 TASK_004 | `GET /health` endpoint | `src/api/endpoints/health.py` | `tests/integration/api/test_health_endpoints.py` |
| S06-T05 | SPEC_06 TASK_005 | `GET /health/readiness` probe (Engram-independent) | `src/api/endpoints/health.py` | `tests/integration/api/test_health_endpoints.py` |
| S06-T06 | SPEC_06 TASK_006 | AX schema definitions | `src/api/ax/schemas.py` | `tests/unit/api/test_ax_schemas.py` |

### 2.7 Owner SPEC_00 - Core DI / Templates (cross-cutting, no inline TDD tasks)

> @ai-directive: SPEC_00 defines the Core mechanism that SPEC_01 factories depend on: `DependencyManager` (lazy, validated, cached loading with allowlist + `entry_points`) and `DIFactory` (`${provider.key}` resolution against `DIReference`). These are cross-cutting infrastructure; their TDD microtasks are NOT enumerated in SPEC_00 as a task checklist. When implementing, derive RED/GREEN tasks directly from the `DependencyManager` contract in SPEC_01 section 1.3 (the canonical spec for the manager). `TemplateManager` (50+ auto-prompted templates with heritable frontmatter) is part of SPEC_00 but is content/tooling, not backend code tasks in this catalog.

### 2.8 Integration / End-to-End (derived from the catalog)

> @ai-directive: these E2E tasks exercise the assembled stack (SPEC_02 schemas -> SPEC_01 factories -> Agno native runtime -> SPEC_03 persistence -> SPEC_06 API). They are derived here because they span multiple owner SPECs; each one references the components it wires together.

| Catalog ID | Scope | Test file | Wires together |
|------------|-------|-----------|----------------|
| E2E-T01 | Agent lifecycle (create YAML -> validate -> `AgentFactory.create()` -> run) | `tests/integration/e2e/test_agent_lifecycle.py` | SPEC_02 + SPEC_01 + SPEC_03 |
| E2E-T02 | Team lifecycle (validate -> `TeamFactory.create()` -> run) | `tests/integration/e2e/test_team_lifecycle.py` | SPEC_02 + SPEC_01 + SPEC_05 |
| E2E-T03 | Workflow lifecycle (declare -> `WorkflowFactory` -> execute via Agno) | `tests/integration/e2e/test_workflow_lifecycle.py` | SPEC_02 + SPEC_01 + SPEC_05 |
| E2E-T04 | API run flow (`POST /agents/{name}/run` end-to-end) | `tests/integration/api/test_agent_endpoints.py` | SPEC_06 + SPEC_01 + SPEC_03 |
| E2E-T05 | Long-term recall on start (port-backed, default Agno adapter) | `tests/integration/memory/test_recall_on_start.py` | SPEC_04 (S04-T04) |

> @ai-directive (removed E2E tasks): the previous iteration listed E2E tasks for "memory compression" and "workflow error recovery" as standalone lifecycle tests. Compression E2E is owned by SPEC_15; workflow retry E2E is covered by S05-T05/T06 unit tests plus an optional integration test in SPEC_05. They are NOT standalone E2E tasks here to avoid duplicating owners.

---

## 3. ADOPTED TECHNICAL ASSUMPTIONS

### [Decision 1] Catalog as aggregator, not source of truth

**Justification**:
- Owner SPECs (01-07) hold the authoritative task definitions with full RED/GREEN/REFACTOR detail.
- This catalog consolidates them for traceability and sequencing without duplicating logic.
- Any divergence must be fixed in the owner SPEC, then propagated here.

### [Decision 2] Atomic commits per microtask

**Justification**:
- Easy rollback to any single RED/GREEN step.
- Clean conventional-commit history.
- Enables per-task code review.

### [Decision 3] Tests as living specification

**Justification**:
- Executable documentation of behavior.
- Prevents regressions across the YAML -> Agno translation path.
- RED steps double as acceptance criteria for each owner SPEC task.

### [Decision 4] No tasks for removed classes

**Justification**:
- Iteration 1 of SPEC_00-02 removed `SessionContext`, `SessionState`, `AgentInstance`, `ModelId`, `SessionKey`, `WorkflowExecution`, `WorkflowState`, domain events and a native `EngramMemoryManager`.
- Cataloguing tasks to create them would contradict the corrected baseline. They are listed only in section 1.3 as a negative list.

---

## 4. STRATEGIC CALIBRATION QUESTIONS

### [Question 1] Task granularity

**Is the per-owner-SPEC granularity sufficient, or do we need finer decomposition?**

Implications:
- **Per owner task**: larger steps, more context per commit.
- **Finer**: more atomic commits, more overhead.
- **Trade-off**: granularity vs commit overhead.

### [Question 2] Task parallelization

**Which catalog groups can run in parallel?**

Implications:
- **Independent**: SPEC_02 schemas; SPEC_03 persistence models; SPEC_04 port/adapter.
- **Sequential**: SPEC_02 -> SPEC_01 factories -> SPEC_06 API; SPEC_03 -> SPEC_06 API.
- **Trade-off**: speed vs dependency order.

### [Question 3] Test strategy balance

**Unit-heavy vs balanced unit/integration?**

Implications:
- **Unit-heavy**: faster, lower confidence on the Agno boundary.
- **Integration-heavy**: slower, higher confidence.
- **Balance**: best coverage of the YAML -> Agno translation and config-store ACID path.

---

*Do you want to deepen the technical specification to **Level 6** for a specific component group, or authorize execution of this catalog by the agent team?*
