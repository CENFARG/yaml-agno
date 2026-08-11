# SPEC Index — Thematic Grouping & Reading Order

This index groups the 34 SPECs by theme and gives a recommended reading order. SPECs are NOT renamed (filenames stable); use Read_Order to sequence.

---

## Grouped View (G1 → G10)

Within each group, SPECs are sorted by Read_Order ascending.

### G1 — Fundaciones

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_00_SYSTEM_STRATEGY.md | System Strategy - Vision, Principles and Strategic Constraints | 1 | yes | B | Vision, principles, strategic constraints, roadmap framing. |

### G2 — Runtime Core

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_01_AGNO_RUNTIME_ARCHITECTURE.md | Agno Runtime Architecture | 2 | no | A | Runtime architecture, session management, workflow primitives. |
| SPEC_02_DOMAIN_MODEL.md | Domain Model - YAML Configuration Schemas (Pydantic V2) | 3 | yes | M | Pydantic V2 YAML config schemas (Agent/Team/Workflow/Step). |
| SPEC_33_TEMPLATES.md | Templates - Heritable YAML Templates, Registry and Resolution Pipeline | 3.5 | no | A | Heritable templates, registry (FS+DB), resolution pipeline over *Config. |
| SPEC_03_PERSISTENCE_ARCHITECTURE.md | Persistence Architecture - Config Store on core-cenf DatabaseManager | 4 | no | A | Config store on core-cenf DatabaseManager. |
| SPEC_14_MODEL_RESILIENCE_AND_CONFIG.md | Model Resilience & Configuration | 4 | no | A | Model fallback, retry, circuit breaker, providers. |

### G3 — Capacidades del Agente

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_11_TOOLS_AND_MCP.md | Tools & MCP Architecture - Toolkits, Custom Tools and Model Context Protocol | 5 | no | A | Toolkits, custom tools, MCP integration. |
| SPEC_10_KNOWLEDGE_AND_RAG.md | Knowledge & RAG Architecture - Vector DBs, Embedders, Chunkers and Retrieval | 6 | no | A | Vector DBs, embedders, chunkers, retrieval. |
| SPEC_15_CONTEXT_ENGINEERING_AND_COMPRESSION.md | Context Engineering & Compression | 7 | no | M | Context compression and engineering strategies. |
| SPEC_02_DOMAIN_MODEL.md | (shared schema reference) | — | — | — | *(Schema SSOT; see G2)* |
| SPEC_17_MULTIMODAL_IO.md | Multimodal I/O - Images, Audio, Video and Files Processing and Generation | 13 | no | M | Multimodal input/output and generation. |
| SPEC_30_SKILLS_MANAGEMENT.md | Skills Management - Downloadable Domain Expertise and Progressive Discovery | 14 | yes | B | Skills download and progressive discovery. |

> Note: SPEC_02 appears under G2 (its home group for Read_Order=3). It is referenced by G3 as the schema SSOT but is not duplicated in Read_Order.

### G4 — Memoria y Aprendizaje

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_04_MEMORY_ARCHITECTURE.md | Memory Architecture - Session, Working Memory and Long-term Storage | 8 | no | A | Session, working, and long-term memory. |
| SPEC_31_CULTURE_MANAGER.md | Culture Manager - Experimental Cross-Session Cultural Knowledge (LLM-Extractive) | 9 | no | B | Cross-session cultural knowledge extraction. |
| SPEC_28_REASONING_ARCHITECTURE.md | Reasoning Architecture - Declarative Step-based and Native Model Reasoning | 10 | no | M | Declarative step-based and native model reasoning. |

### G5 — Oversight, Seguridad Aplicada

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_16_HITL_APPROVALS_GUARDRAILS.md | HITL, Approvals & Guardrails - Human Oversight, Input Validation and Safety Boundaries | 11 | no | A | Human oversight, approvals, guardrails. |
| SPEC_29_WORKFLOW_HITL.md | Workflow-level HITL - HumanReview, Step Pauses and Executor Bubbling | 12 | no | M | Workflow-level HumanReview, step pauses, bubbling. |

### G6 — Orquestación

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_05_WORKFLOWS_AND_TEAMS.md | Workflows and Teams - Complex Runtime Coordination | 15 | no | A | Workflows and teams coordination. |
| SPEC_13_SCHEDULER_BACKGROUND_LIFECYCLE.md | Scheduler, Background Execution & Run Lifecycle | 16 | no | M | Scheduler, background execution, run lifecycle. |
| SPEC_32_REGISTRY_AND_COMPONENTS.md | Registry & Components - Code-Defined Runtime Catalog vs Versioned Persistent Catalog | 17 | no | M | Runtime vs persistent component registry. |

### G7 — Control Plane & API

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_06_API_AND_AX.md | API and AX - YamlAgentOS(AgentOS) Inheritance Layer | 18 | no | A | API/AX inheritance layer over AgentOS. |
| SPEC_12_AGENTOS_CONTROL_PLANE.md | AgentOS Control Plane | 19 | no | A | AgentOS control plane. |
| SPEC_26_A2A_INTERFACE.md | A2A (Agent-to-Agent) Interface | 20 | yes | B | Agent-to-agent interface. |
| SPEC_19_SECURITY_AUTH_API_SURFACE.md | Security, Auth and API Surface - JWT, RBAC, Per-User Isolation and Endpoint Catalog | 21 | no | M | JWT, RBAC, per-user isolation, endpoint catalog. |

### G8 — Ops & Observabilidad

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_09_OBSERVABILITY_AND_SRE.md | Observability and SRE - Metrics, Tracing and Resilience | 22 | no | A | Metrics, tracing, resilience, SRE. |
| SPEC_27_TRACING_ARCHITECTURE.md | Tracing Architecture | 23 | no | M | Distributed tracing architecture. |
| SPEC_18_EVALS_AND_OBSERVABILITY.md | Evals and Observability Integrations - Agno Evals and OTel Provider Catalog | 24 | no | M | Agno evals, OTel provider catalog. |
| SPEC_23_CONFIG_AND_SECRETS.md | Config & Secrets Management - ConfigManager, Zero-Trust SecretManager, Feature Flags and Hot-Reload | 25 | no | M | Config/secrets, feature flags, hot-reload. |

### G9 — Deploy, UI & Periferica

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_07_DASHBOARD_ARCHITECTURE.md | Dashboard Architecture - UI Strategy: Playground and agent-ui | 26 | yes | B | Dashboard UI strategy. |
| SPEC_20_DOCKER_BUILD.md | Docker Build | 27 | yes | M | Docker image build. |
| SPEC_22_CICD_PIPELINE.md | CI/CD Pipeline - GitHub Actions, Security Gates, SBOM and GitOps Deploy | 28 | yes | M | CI/CD pipeline, security gates, SBOM, GitOps. |
| SPEC_21_KUBERNETES_DEPLOYMENT.md | Kubernetes Deployment | 29 | no | A | Kubernetes deployment manifests. |
| SPEC_24_MONITORING_STACK.md | Monitoring Stack - Prometheus, Grafana, Loki, Alertmanager y Tracing | 30 | no | A | Monitoring stack (Prometheus/Grafana/Loki). |
| SPEC_25_SECURITY_HARDENING.md | Security Hardening - Pod Security, Network Policies, RBAC, Supply Chain y Compliance | 31 | no | A | Pod security, network policies, supply chain. |

### G10 — Meta

| SPEC | Title | Read_Order | Quickwin | Complexity | Covers |
|---|---|---|---|---|---|
| SPEC_08_TDD_MICROTASKS.md | TDD Microtasks - Master Catalog | 32 | no | M | TDD microtask master catalog. |

---

## Recommended Reading Order (flat, 1..34)

Sequence by Read_Order. This is a reading guide; the real dependency structure is the DAG in each SPEC's `Dependency_Hashes`.

| # | Read_Order | SPEC file | Title |
|---|---|---|---|
| 1 | 1 | SPEC_00_SYSTEM_STRATEGY.md | System Strategy |
| 2 | 2 | SPEC_01_AGNO_RUNTIME_ARCHITECTURE.md | Agno Runtime Architecture |
| 3 | 3 | SPEC_02_DOMAIN_MODEL.md | Domain Model (Pydantic V2) |
| 4 | 3.5 | SPEC_33_TEMPLATES.md | Templates |
| 5 | 4 | SPEC_03_PERSISTENCE_ARCHITECTURE.md | Persistence Architecture |
| 6 | 4 | SPEC_14_MODEL_RESILIENCE_AND_CONFIG.md | Model Resilience & Configuration |
| 7 | 5 | SPEC_11_TOOLS_AND_MCP.md | Tools & MCP Architecture |
| 8 | 6 | SPEC_10_KNOWLEDGE_AND_RAG.md | Knowledge & RAG |
| 9 | 7 | SPEC_15_CONTEXT_ENGINEERING_AND_COMPRESSION.md | Context Engineering & Compression |
| 10 | 8 | SPEC_04_MEMORY_ARCHITECTURE.md | Memory Architecture |
| 11 | 9 | SPEC_31_CULTURE_MANAGER.md | Culture Manager |
| 12 | 10 | SPEC_28_REASONING_ARCHITECTURE.md | Reasoning Architecture |
| 13 | 11 | SPEC_16_HITL_APPROVALS_GUARDRAILS.md | HITL, Approvals & Guardrails |
| 14 | 12 | SPEC_29_WORKFLOW_HITL.md | Workflow-level HITL |
| 15 | 13 | SPEC_17_MULTIMODAL_IO.md | Multimodal I/O |
| 16 | 14 | SPEC_30_SKILLS_MANAGEMENT.md | Skills Management |
| 17 | 15 | SPEC_05_WORKFLOWS_AND_TEAMS.md | Workflows and Teams |
| 18 | 16 | SPEC_13_SCHEDULER_BACKGROUND_LIFECYCLE.md | Scheduler & Background Lifecycle |
| 19 | 17 | SPEC_32_REGISTRY_AND_COMPONENTS.md | Registry & Components |
| 20 | 18 | SPEC_06_API_AND_AX.md | API and AX |
| 21 | 19 | SPEC_12_AGENTOS_CONTROL_PLANE.md | AgentOS Control Plane |
| 22 | 20 | SPEC_26_A2A_INTERFACE.md | A2A Interface |
| 23 | 21 | SPEC_19_SECURITY_AUTH_API_SURFACE.md | Security, Auth and API Surface |
| 24 | 22 | SPEC_09_OBSERVABILITY_AND_SRE.md | Observability and SRE |
| 25 | 23 | SPEC_27_TRACING_ARCHITECTURE.md | Tracing Architecture |
| 26 | 24 | SPEC_18_EVALS_AND_OBSERVABILITY.md | Evals and Observability |
| 27 | 25 | SPEC_23_CONFIG_AND_SECRETS.md | Config & Secrets |
| 28 | 26 | SPEC_07_DASHBOARD_ARCHITECTURE.md | Dashboard Architecture |
| 29 | 27 | SPEC_20_DOCKER_BUILD.md | Docker Build |
| 30 | 28 | SPEC_22_CICD_PIPELINE.md | CI/CD Pipeline |
| 31 | 29 | SPEC_21_KUBERNETES_DEPLOYMENT.md | Kubernetes Deployment |
| 32 | 30 | SPEC_24_MONITORING_STACK.md | Monitoring Stack |
| 33 | 31 | SPEC_25_SECURITY_HARDENING.md | Security Hardening |
| 34 | 32 | SPEC_08_TDD_MICROTASKS.md | TDD Microtasks |

> Read_Order 3.5 places SPEC_33 (Templates) between the Domain Model (SPEC_02, the SSOT it generates) and the rest of the runtime core; Templates resolves/generates *Config and hands off to factories (SPEC_01). Read_Order 4 is shared by SPEC_03 and SPEC_14 (both foundational, independent reads). All other Read_Orders are unique.

---

## Quickwins (quickwin=yes)

These SPECs are flagged for MVP prioritization (low complexity / high leverage).

| Quickwin | SPEC file | Title | Read_Order |
|---|---|---|---|
| yes | SPEC_00_SYSTEM_STRATEGY.md | System Strategy | 1 |
| yes | SPEC_02_DOMAIN_MODEL.md | Domain Model (Pydantic V2) | 3 |
| yes | SPEC_07_DASHBOARD_ARCHITECTURE.md | Dashboard Architecture | 26 |
| yes | SPEC_20_DOCKER_BUILD.md | Docker Build | 27 |
| yes | SPEC_22_CICD_PIPELINE.md | CI/CD Pipeline | 28 |
| yes | SPEC_26_A2A_INTERFACE.md | A2A Interface | 20 |
| yes | SPEC_30_SKILLS_MANAGEMENT.md | Skills Management | 14 |

---

## MVP Implementation Order (top 10)

Recommended first ten SPECs to implement (by current filename), per the coverage analysis:

1. `SPEC_00_SYSTEM_STRATEGY.md`
2. `SPEC_02_DOMAIN_MODEL.md`
3. `SPEC_01_AGNO_RUNTIME_ARCHITECTURE.md`
4. `SPEC_14_MODEL_RESILIENCE_AND_CONFIG.md`
5. `SPEC_11_TOOLS_AND_MCP.md`
6. `SPEC_30_SKILLS_MANAGEMENT.md`
7. `SPEC_26_A2A_INTERFACE.md`
8. `SPEC_03_PERSISTENCE_ARCHITECTURE.md`
9. `SPEC_05_WORKFLOWS_AND_TEAMS.md`
10. `SPEC_06_API_AND_AX.md`

---

## Group Legend

| Group | Theme | Scope |
|---|---|---|
| G1-Fundaciones | Foundations | Vision, principles, strategic constraints. |
| G2-Runtime-Core | Runtime core | Runtime architecture, domain model, persistence, model resilience. |
| G3-Capacidades-Agente | Agent capabilities | Tools/MCP, RAG, context, multimodal, skills. |
| G4-Memoria-Aprendizaje | Memory & learning | Memory architecture, culture, reasoning. |
| G5-Oversight-Seguridad-App | Oversight & applied security | HITL, approvals, guardrails, workflow-level HITL. |
| G6-Orquestacion | Orchestration | Workflows/teams, scheduler, registry. |
| G7-ControlPlane-API | Control plane & API | API/AX, AgentOS control plane, A2A, security surface. |
| G8-Ops-Observabilidad | Ops & observability | SRE, tracing, evals, config/secrets. |
| G9-Deploy-UI-Periferica | Deploy, UI & periphery | Dashboard, Docker, CI/CD, k8s, monitoring, hardening. |
| G10-Meta | Meta | TDD microtask catalog. |

---

> Filenames are stable. Dependencies form a DAG (see `Dependency_Hashes` in each SPEC), not a strict linear order; Read_Order is a reading guide, not a dependency contract.

---

## Closed SPECs (S0 — Execution Plan 2026-08-10)

SPECs whose implementation already exists in `src/yaml_agno/` and are closed as of S0.
Frontmatter `Status` flipped to `Done` (2026-08-11). Round-trip integration gates remain
pending (G-01 for SPEC_26).

| SPEC | Status | Evidence (code) | Unit verification |
|---|---|---|---|
| SPEC_05_WORKFLOWS_AND_TEAMS.md | **CLOSED** | `src/yaml_agno/workflows/{retry_policy,step_executor,condition_evaluator,a2a_config,models,__init__}.py` — `RetryPolicy` (backoff+jitter, clasificación delegada a core-cenf `ErrorHandlingManager.classify()`, `report()` sync), `StepExecutor` (CB+RetryPolicy, parallel vía `asyncio.TaskGroup`), `ConditionEvaluator` (delega CEL a Agno `_evaluate_cel`), `A2AConfig`/`A2AConfigFactory` (mapea a `agno.remote.BaseRemote` protocol=`a2a`; ACP rechazado); `src/yaml_agno/factories/workflow_factory.py` (matriz 7-primitivas StepType → agno Step/Steps/Parallel/Condition/Router/Loop, resolución híbrida CEL/callable); guard TASK_008 en `tests/contract/test_no_workflow_runtime.py` (no `WorkflowExecution`/`WorkflowState`/`WorkflowStateMachine`) | `pytest tests/unit/workflows tests/unit/factories/test_workflow_factory.py -q` → PASS (81 passed, 1 skipped — guard cel-python); `tests/contract/test_no_workflow_runtime.py` PASS; `scripts/spec_gate.py all` → 34/34 |
| SPEC_26_A2A_INTERFACE.md | **CLOSED** | `src/yaml_agno/agentos/a2a_interface.py` — `A2AInterfaceFactory.build()` instantiates `agno.os.interfaces.a2a.A2A` (línea 149); `src/yaml_agno/agentos/interfaces.py` (mapping + build_all) | `pytest tests/unit/agentos -q` → PASS (G-01 round-trip pendiente) |
| SPEC_23_CONFIG_AND_SECRETS.md | **CLOSED** | `src/yaml_agno/config/{schemas,merge,audit,secrets,rotator,flags_repository,hotreload,bootstrap}.py` — wraps core `ConfigManager`/`SecretManager`/`FeatureFlagManager` (never reimplements); `db/models/feature_flag.py`, `db/models/secret_audit.py` (tablas `yamlagno.feature_flags`, `yamlagno.secret_audit`) | `pytest tests/unit/config tests/unit/db -q` → PASS (58 + 26); `mypy src/yaml_agno --strict` → 0 errores |
| SPEC_14_MODEL_RESILIENCE_AND_CONFIG.md | **CLOSED** | `src/yaml_agno/models/fallback_chain.py`, `models/fallback_classifier.py`, `resilience/circuit_breaker.py`, `di/provider_factory.py`, `di/capabilities_validator.py`, `di/provider_capabilities.py` | `pytest tests/unit/models tests/unit/resilience -q` → PASS |
| SPEC_04_MEMORY_ARCHITECTURE.md | **CLOSED** | `src/yaml_agno/memory/user_identity.py` — `resolve_user_id()` (composite `{tenant_id}:{principal_id}`, único resolver, fail-fast, nunca `None`/`default`); `src/yaml_agno/models/config/memory_config.py` — `MemoryConfig` schema (SPEC_02 SSOT) + validator fail-fast del gotcha Agno 2.8.7 `update_user_memory` (rechaza `enable_agentic_memory=true` + `learning.enabled=true`; D-F1-08) | `pytest tests/yaml_agno/memory tests/yaml_agno/models/config -q` → PASS (18); `mypy --strict` 0 errores; `scripts/spec_gate.py all` → 34/34 |
