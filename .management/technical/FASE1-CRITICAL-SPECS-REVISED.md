# FASE1-CRITICAL-SPECS-REVISED — Re-priorización de las 7 SPECs críticas

- **Fecha**: 2026-08-09
- **Autor**: Code Architect (development-team, CENF)
- **Contexto**: Re-evaluación con las correcciones de Gonzalo (2026-08-09): burn rate real
  $134/mes, pin agno 2.8.3 (docs stale), SPEC_26 A2A ya parcialmente implementada, competencia
  = capa sobre Agno (no LangGraph/CrewAI), timeline corto (agentes 20/24hs), horas humano =
  inversión, PostgreSQL+pgvector+JSONB (no Qdrant), Cloud Run+Supabase (no Fly/VPS/K8s),
  revenue = ArcaMCP + Agente Instalador, G-04 resuelto si funciona internamente.
- **Criterio de priorización**: (a) qué desbloquea agentes funcionando antes, (b) qué ya está
  hecho (cerrar/validar vs construir). Esfuerzo en **días-agente (20-24hs/día)**.

---

## 0. Estado global verificado (2026-08-09)

- **Tests**: `657 passed, 6 failed, 1 skipped` (`pytest -m unit`, agno 2.8.3 instalado).
  Los 6 fallos son de MCP resolver (comandos no permitidos por `ALLOWED_COMMANDS`) — deuda
  preexistente, independiente de la subida de agno (ver `AGNO-283-DIFF-ANALYSIS.md` §6).
- **Implementación por SPEC** (evidencia en `src/yaml_agno/` + `openspec/changes/archive/`):
  - HECHAS: SPEC_00 (docs), SPEC_01 (factories), SPEC_02 (domain model), SPEC_14 (model
    resilience), SPEC_06 (YamlAgentOS slice A+B), SPEC_09 (circuit breaker), SPEC_12
    (control plane slices 1-3), SPEC_26 (A2A), SPEC_30 (skills slice A), SPEC_11 (tools slice A).
  - PARCIALES: SPEC_03 (persistencia), SPEC_04 (memoria leaf), SPEC_05 (workflows/teams),
    SPEC_19 (tenant/security), SPEC_23 (config/secrets), SPEC_11 (MCP slices B/C/D).

---

## 1. Ranking revisado de las 7 SPECs de Fase 1

### #1 — SPEC_03 Persistencia PostgreSQL (persistencia real) — PARCIAL → COMPLETAR
- **Estado**: ORM + provisioner + bootstrap + repos hechos. Evidencia: `src/yaml_agno/db/`
  (base.py DeclarativeBase, models/ `yamlagno_agent_config`, `yamlagno_team_config`,
  `yamlagno_workflow_config`, `yamlagno_tenant`, `yamlagno_config_change_log`,
  `yamlagno_di_variable`, `yamlagno_schema_version`; `bootstrap.py`, `provisioner.py`,
  `repositories/agent_config_repository.py`). `src/yaml_agno/persistence/registry.py` vacío
  (0 bytes) — el DbRegistry no está. `api/health.py` declara "real Postgres ping arrives
  with SPEC_03 B-E".
- **Qué falta**: wiring del storage de **Agno** a Postgres (PgAgentStorage/PgTeamStorage +
  PgVectorDb con pgvector), el DbRegistry (SPEC_03 §7.2), swap de vector DB fácil por DI
  (corrección 7: pgvector + JSONB, **sin Qdrant**), integración Supabase/Cloud Run,
  health check de Postgres real.
- **Esfuerzo**: 3-5 días-agente. **Depende de**: SPEC_04 (composite user_id → filtro
  explícito `tenant_id`), SPEC_23 (connection strings vía SecretManager).
- **Por qué primero**: sin Postgres no hay multi-tenant real ni storage durable; es el
  backbone de G-04 (2-3 clientes) y de la decisión RLS (ver §3).

### #2 — SPEC_05 Workflows y Teams (equipos) — PARCIAL → COMPLETAR
- **Estado**: `src/yaml_agno/workflows/` (step_executor.py, retry_policy.py,
  condition_evaluator.py, a2a_config.py, models.py) + `factories/team_factory.py` y
  `workflow_factory.py` (openspec archive: `team-factory`, `workflow-factory`,
  `workflows-loop-body-fix`).
- **Qué falta**: validación end-to-end de equipos (TeamMode coordinate/route/broadcast/
  tasks) contra agno 2.8.6+, workflows con templates YAML (SPEC_33) y DAGs, tests de
  integración de equipos reales (no solo factories).
- **Esfuerzo**: 2-4 días-agente. **Depende de**: SPEC_01/02 (hechas), SPEC_14 (model
  resilience — los equipos usan el resolver de modelos).
- **Por qué segundo**: "equipos" es el core del producto (facturación, email, profiler).
  Sin equipos funcionando no hay demo interna (G-04).

### #3 — SPEC_04 Memoria — PARCIAL (leaf) → VALIDAR/COMPLETAR
- **Estado**: `memory/user_identity.py` (resolve_user_id + UserIdentityResolutionError)
  hecho; `api/middleware/tenant_context.py` delega (SPEC_06 §3.2). Memoria larga =
  **Agno native** (Decisión 4: LearningMachine/MemoryManager — sin código propio).
- **Qué falta**: validar que el wiring `MemoryConfig` → LearningMachine/MemoryManager
  funciona contra **agno 2.8.6/2.8.7** (el revamp de entity memory cambió el store interno,
  ver diff-analysis §4.4); tests de integración de memoria larga + session memory;
  decidir el gotcha `enable_agentic_memory` vs learning user_memory (colisión
  `update_user_memory`).
- **Esfuerzo**: 1-2 días-agente (mayormente validación + tests). **Depende de**: SPEC_03
  (el store de memoria de Agno usa la DB configurada).
- **Por qué**: la memoria es lo que hace a los agentes "aprender" entre sesiones — clave
  para la demo de G-04.

### #4 — SPEC_23 Config y Secrets — PARCIAL → COMPLETAR
- **Estado**: `di/secret_resolver.py` (ConfigSecretResolver lee OPENROUTER_API_KEY etc.),
  `di/agno_resolver.py` (ConfigManager seedea defaults sin .env). ConfigManager/SecretManager
  de core-cenf ya consumidos (agno_resolver.py:23, secret_resolver.py:28).
- **Qué falta**: hot-reload de config (ResyncManager existe para AgentOS, falta para config),
  feature flags (FeatureFlagManager core-cenf), SecretManager async en prod (Cloud Run
  secrets / Supabase), clasificación env vs runtime (SPEC_03 §2).
- **Esfuerzo**: 1-2 días-agente. **Depende de**: nada (paralelo con SPEC_03/05).
- **Por qué**: sin config/secrets sanos no hay deploy en Cloud Run ni multi-tenant.

### #5 — SPEC_26 A2A — HECHO (construcción) → VALIDAR/CERRAR
- **Estado**: `agentos/a2a_interface.py` (195 líneas: A2AInterfaceConfig + A2AInterfaceFactory
  + A2APrefix + errores) y `workflows/a2a_config.py`. Factory resuelve refs vía registries
  y construye `agno.os.interfaces.a2a.A2A` (a2a_interface.py:149-157). Exports en
  `agentos/__init__.py`.
- **Qué falta (validar/cerrar)**: test de integración del A2A server con AgentOS,
  verificación del dep opcional `a2a-sdk` (no declarado en pyproject, solo mypy override),
  cierre de la SPEC en el gate (`scripts/spec_gate.py all`), commit de cierre.
- **Esfuerzo**: 0,5-1 día-agente. **Depende de**: SPEC_05/12 (refs a equipos/control plane).
- **Por qué**: la corrección 3 pide explícitamente "validar, no construir desde cero" — ya
  está construida; queda cerrarla.

### #6 — SPEC_19 Security/Auth/Tenant — PARCIAL → COMPLETAR (o Fase 2 si G-04 es interno)
- **Estado**: `tenant/resolver.py` (TenantResolver parsea composite user_id), 
  `api/middleware/tenant_context.py` (TenantContextMiddleware), `tools/security.py`
  (SecurityError + allowlist), `agentos/authorization_adapter.py` (AuthorizationSettings,
  SPEC_12 slice 3).
- **Qué falta**: middleware JWT real (JWT_VERIFICATION_KEY, Decisión "Secret JWT"),
  RBAC/scopes (ScopeEnforcer + catálogo de scopes), endpoint catalog con scopes, audit
  trail, CORS/security headers.
- **Esfuerzo**: 3-5 días-agente. **Depende de**: SPEC_06/12 (hechas), SPEC_03 (tenant rows).
- **Nota timeline**: si G-04 se valida solo internamente (3 personas CENF), SPEC_19 puede
  posponerse a Fase 2 (los scopes/JWT son requerimiento de clientes externos, no de uso
  interno). El tenant básico (parse + filtro) ya está.
- **Decisión RLS**: ver §3.

### #7 — SPEC_14 Model Resilience — HECHO → CERRAR (contra 2.8.6)
- **Estado**: `models/fallback_chain.py`, `models/fallback_classifier.py`,
  `resilience/circuit_breaker.py`, `di/agno_model_adapter.py`, `di/provider_factory.py`,
  `di/provider_capabilities.py`, `di/capabilities_validator.py`, `di/registries.py`
  (openspec archive: `model-resilience-runtime`, `provider-factory-adapter`,
  `provider-catalog-expansion`, `circuit-breaker-foundation`).
- **Qué falta**: re-verificar contra agno 2.8.6 (models/base.py solo cambió encoding),
  tests de fallback con modelos free (OpenRouter/DeepSeek/Gemini — clave para el burn rate
  $134/mes), cerrar SPEC.
- **Esfuerzo**: 0,5 día-agente. **Depende de**: SPEC_23 (API keys).
- **Por qué**: es lo que permite usar modelos free/baratos y bajar el burn rate. Ya hecho;
  cerrar y usar como base de la demo.

---

## 2. Dependencias entre las 7 (DAG resumido)

```
SPEC_23 (config/secrets) ──────┐
SPEC_04 (memoria) ─────────────┼──► SPEC_03 (persistencia Postgres) ──► G-04 demo interna
SPEC_01/02 (hechas) ──► SPEC_05 (equipos) ──► SPEC_26 (A2A cerrar)        │
SPEC_14 (hecha, cerrar) ───────┘                                          ▼
                                                        SPEC_19 (auth, Fase 2 si interno)
```

## 3. DECISIÓN DOCUMENTADA: RLS → pgvector + filtros explícitos (NO RLS)

**Conflicto resuelto**: `DECISIONES.md` §2.9 dice "Multi-tenant: explicit WHERE filters,
NO RLS, NO tenant_id en `agno_*`" mientras el roadmap de `SPEC.md`/`SPEC_19` contemplaba
RLS como opción. **Resolución (preferencia Gonzalo, coherente con la corrección 7)**:

- **Se adopta**: PostgreSQL + **pgvector** + **JSONB** + **filtros explícitos**
  (`WHERE tenant_id = ?`) en la capa de aplicación. **NO RLS**.
- Justificación:
  1. **Coherencia con la Decisión 2.9 ya inviolable** — no contradecir el código existente
     (TenantResolver/TenantContextMiddleware ya implementan el patrón de filtro explícito).
  2. **Un solo mecanismo de aislamiento** — el composite `{tenant_id}:{principal_id}`
     (SPEC_04) resuelve el tenant en la capa de aplicación; RLS duplicaría el mecanismo.
  3. **Agno storage**: el storage de Agno (PgAgentStorage/PgVectorDb) no usa RLS; integrar
     RLS con los `yamlagno_*` config rows y el storage de Agno en la misma conexión añade
     complejidad de set-up (rol de app vs rol set-tenant) sin beneficio real a esta escala.
  4. **Escala G-04 (2-3 clientes)** — el costo operativo de RLS (policies por tabla,
     privilegios, testing) excede el beneficio; los filtros explícitos son suficientes.
- **Consecuencia para SPEC_19**: el aislamiento per-user/per-tenant se logra con
  (a) composite user_id, (b) filtro `tenant_id` en repos `yamlagno_*`, (c) storage de Agno
  configurado con `user_id` composite (aislamiento native de AgentOS, SPEC_19 §4).
- **Cambiar de vector DB debe ser fácil por DI** (corrección 7): el DbRegistry (SPEC_03)
  debe exponer `get_vector_db()` con inyección por DI — el proveedor actual pgvector puede
  reemplazarse sin tocar factories.

## 4. Nota de timeline corto

- Los agentes trabajan **20/24hs/día**: la Fase 1 completa (4 parciales ≈ 8-12 días-agente
  + 3 cierres ≈ 1,5-2 días-agente) equivale a **≈ 1-1,5 semanas calendario** de ejecución
  continua, no a 4-6 meses.
- Orden de ejecución recomendado: (1) cerrar SPEC_14 y SPEC_26 (desbloquean la demo),
  (2) SPEC_03 en paralelo con SPEC_23, (3) SPEC_05, (4) SPEC_04, (5) SPEC_19 según decisión
  de G-04 (interna vs externa).
- **Gate de éxito (G-04)**: "nuestros propios agentes programan, analizan, deciden mejor"
  — con SPEC_01/02/14/06 ya hechas + SPEC_03/05 completadas, CENF puede correr un equipo
  interno (facturación o email) contra Postgres real y medir esa mejora. Ese es el MVP de
  Fase 1.

## 5. Fuera del top 7 (pero anotado)

- **SPEC_11 Tools/MCP**: slice A hecho, pero **6 tests fallan** (MCP resolver). Fix rápido
  (~0,5 día-agente) antes o junto con la subida a 2.8.6. No entra al top 7 porque el
  tooling básico ya funciona; el arreglo es deuda, no bloqueante.
- **SPEC_06 API**: hecha (YamlAgentOS + health + tenant middleware) — es la base de la
  API de Fase 1; no requiere trabajo nuevo salvo validación con storage Postgres (SPEC_03).
- **SPEC_30 Skills**: slice A hecho (skills-foundation/wiring archive).
