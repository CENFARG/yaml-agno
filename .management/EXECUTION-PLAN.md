# Execution Plan: yaml-agno Fase 1

> **Fecha**: 2026-08-10 · **Autor**: Code Architect (development-team, CENF)
> **Fuentes**: ROADMAP_yaml-agno.md (2026-08-08, datos desactualizados) reconciliado con los 4 technical re-evals (2026-08-09) + STRATEGIC_yaml-agno.md + RISK-MATRIX_yaml-agno.md + verificación directa del código (2026-08-10).
> **Regla de oro**: Los technical re-evals SON LA VERDAD. El roadmap se construyó con datos incorrectos ($401/mes, Fly.io, Qdrant, 10 semanas, RLS, extracción core-cenf). Este documento los corrige.
> **Para un agente de desarrollo**: leé SOLO este documento. Todo lo que hay que hacer, en qué orden, y cómo verificarlo está acá.

---

## Estado Real (post-corrección, verificado en código 2026-08-10)

| Métrica | Valor |
|---------|-------|
| SPECs completas | **10 de 34** (SPEC_00, 01, 02, 06, 09, 11-A, 12, 14, 26, 30) |
| SPECs parciales con código real | **5** (SPEC_03, 04, 05, 19, 23) |
| SPECs sin código (stubs vacíos) | **19** (12 directorios `__init__.py` en 0 líneas) |
| Fase 1 cierra/completa | **4 parciales + 2 cierres + 1 fix** → 16/34 a fin de Fase 1 |
| Días-agente estimados | **10–17 core** (13–22 si SPEC_19 se incluye) — 20–24hs/día |
| Días calendario | **~1.5–2.5 semanas** de ejecución continua (NO 10 semanas) |
| Costo tokens estimado | **~$90–180** (derivado de burn real $134/mes; los $32–63/SPEC del roadmap quedan obsoletos) |
| Infra | **Google Cloud Run + Supabase** (free tier Fase 1: ~$0–15/mes) — NO Fly.io |
| Pin Agno | **2.8.3 → 2.8.7** (diff verificado: 0 breaking en superficie de 42 imports) |
| Tests | 657 passed, **6 failed** (MCP resolver, deuda preexistente), 1 skipped |
| Horas humano | **INVERSIÓN, no costo directo** — fuera de la tabla de cash |

### Correcciones aplicadas al roadmap (tabla de reconciliación)

| Tema | Roadmap (INCORRECTO) | Truth técnica | Impacto en plan |
|---|---|---|---|
| Burn rate | $401/mes (G-03 violado) | **$134/mes real**, bajando con modelos free | R-03 pasa de "urgencia crítica" a "monitoreo tokscale"; G-03 ya se cumple |
| Timeline | 10 semanas calendario | **días-agente** (20–24hs/día) → ~1.5–2.5 semanas | Fase 1 = sprint corto, no trimestre |
| SPEC_26 A2A | "construir en MVP1" | **YA HECHA** (agentos/a2a_interface.py, 195 líneas) | Cerrar + validar round-trip, no construir |
| SPEC_14 Model Resilience | "construir" | **YA HECHA** (models/fallback_chain.py + di/*) | Cerrar contra 2.8.7 |
| SPEC_19 Tenant | "crítica S2" | **Postergable a Fase 2 si G-04 es interno** (3 personas CENF no necesitan JWT/RBAC externo) | Condicional; tenant básico (parse+filtro) ya existe |
| RLS | RLS como opción | **NO-RLS**: pgvector + filtros explícitos `WHERE tenant_id = ?` (Decisión 2.9 inviolable) | SPEC_19 = composite user_id + filtro en repos; storage Agno aislado por user_id |
| Core-cenf | "extraer interface minimal (P-003)" | **NO extraer por ahora**: solo 17 líneas de import en 6 archivos; golden rule ya respetada | Mantener dependencia privada; solo CI con token hasta OSS |
| Agno pin | "2.8.3, re-evaluar upgrade post-Fase 1" | **Safe upgrade a 2.8.7** (0 breaking, 22 commits aditivos; incluye fix MCP #9379 + rehydration #9395) | S0 unifica pin a 2.8.7 |
| Infra | Fly.io ($28–38/mes) | **Google Cloud Run + Supabase** (free tier) | Costo infra ≈ $0–15 Fase 1 |
| Vector DB | Qdrant (spike P-002) | **pgvector + JSONB** (en Supabase) | SPEC_10 RAG usa pgvector; P-002 cancelado |
| Horas humano | $14.7–16.4K "costo económico" | **Inversión** (Gonzalo/Pablo/Flor + agentes = capital) | Fuera de la tabla de cash; se reportan como esfuerzo |
| Scheduling/Monitoring/Docker | SPEC_13/20/22/24 en Fase 1 | Re-priorizado: no entran al top 7 crítico | Fase 2 (post-G-04); solo CI mínimo de deploy en S6 |
| G-04 | "2–3 clientes externos" | **"nuestros agentes programan/analizan/deciden mejor"** (interno CENF) | Gate alcanzable sin ventas: demo de equipo interno (facturación/email) |

### Estado verificado por directorio (2026-08-10, conteo de líneas)

| Dir `src/yaml_agno/` | Líneas | SPEC | Estado |
|---|---|---|---|
| factories/ | 1.404 | SPEC_01 (+05 factories) | ✅ hecha |
| tools/ | 1.681 | SPEC_11 | ✅ slice A / ⚠️ MCP B/C/D |
| models/ (+config/ 623) | 906 + 623 | SPEC_02 | ✅ hecha |
| di/ | 1.208 | SPEC_14, 23 | ✅ / ⚠️ parcial |
| agentos/ | 950 | SPEC_12 (+26 A2A) | ✅ hecha |
| api/ (+middleware/ 149, runtime/ 100) | 503 + 249 | SPEC_06 | ✅ hecha |
| db/ (+repositories/ 130) | 160 + 130 | SPEC_03 | ⚠️ parcial (persistence/ vacía) |
| workflows/ | 415 | SPEC_05 | ⚠️ parcial |
| resilience/ | 163 | SPEC_09 | ✅ hecha |
| skills/ | 121 | SPEC_30 | ✅ hecha |
| memory/ | 89 | SPEC_04 | ⚠️ parcial (leaf) |
| tenant/ | 73 | SPEC_19 | ⚠️ parcial (parse+filtro) |
| ports/, value_objects/ | 39 + 70 | SPEC_06/12 | ✅ helper |
| **Stubs 0 líneas**: scheduler/, hitl/, guardrails/, knowledge/, media/, evals/, tracing/, reasoning/, templates/, culture/, config/, persistence/ | 0 | 13, 16, 10, 17, 18, 27, 28, 33, 31, 23, 03 | 🔴 sin código |

---

## Checklist Ejecutable (orden SECUENCIAL — días-agente 20–24hs)

### S0: Pre-flight + Cierres (día 0 · 2 días-agente)

Desbloquea todo lo demás. Cierra las 2 SPECs hechas y unifica el pin ANTES de tocar cualquier parcial.

- [ ] **0.1 — Unificar pin Agno 2.8.3 → 2.8.7** (~0.25 d-a)
  - `pyproject.toml:22`: `agno==2.8.3` → `agno==2.8.7`
  - `AGENTS.md` ("Agno 2.6.22") y `DECISIONES.md` §1 ("Agno v2.6.18"): sincronizar a 2.8.7
  - **Verificación**: `pip install -e ".[dev]"` ; `pip show agno | grep Version` → 2.8.7
- [ ] **0.2 — Regenerar `agno.db` y stores de memoria** (~0.1 d-a)
  - El revamp de entity memory (2.8.4–2.8.7, `learn/stores/entity_memory.py`) NO migra datos de 2.8.3. Borrar `agno.db` raíz y stores de memoria locales; regenerar desde cero.
  - **Verificación**: arranca sin errores de schema en stores de memoria
- [ ] **0.3 — Cerrar SPEC_26 (A2A ya implementada)** (~0.5–1 d-a)
  - Test de integración round-trip: `A2AInterfaceFactory` (agentos/a2a_interface.py:149-157) → `agno.os.interfaces.a2a.A2A` → server responde a un peer real
  - Declarar dep opcional `a2a-sdk` en `pyproject.toml` (hoy solo mypy override)
  - `python scripts/spec_gate.py all` + commit de cierre
  - **Verificación**: `pytest tests/unit/agentos -q` + round-trip A2A PASS contra 2.8.7 → **Gate G-01**
- [ ] **0.4 — Cerrar SPEC_14 (Model Resilience ya implementada)** (~0.5 d-a)
  - Re-verificar fallback_chain/circuit_breaker contra 2.8.7 (models/base.py solo cambió encoding — no breaking)
  - Test de fallback con modelos free (OpenRouter `:free`, DeepSeek, Gemini) — clave para sostener $134/mes
  - `python scripts/spec_gate.py all` + commit de cierre
  - **Verificación**: `pytest -m unit tests/unit/models tests/unit/resilience -q`
- [ ] **0.5 — Fix deuda MCP: 6 tests fallando** (~0.5 d-a, independiente del pin)
  - `tests/unit/tools/test_mcp_resolver.py`: comandos `"echo hi"` no permitidos por `ALLOWED_COMMANDS` (agno utils/mcp.py) → usar comandos de la allowlist (`uvx`, `python`) o mockear `prepare_command`
  - **Verificación**: `pytest tests/unit/tools/test_mcp_resolver.py -q` → 0 failed
- [ ] **0.6 — Crear LICENSE Apache 2.0** (~0.1 d-a, prep OSS no bloqueante)
  - `LICENSE` (Apache 2.0 full text) en raíz; `pyproject.toml` sigue MIT hasta decisión OSS post-Fase 1 (G-04)
  - **Verificación**: archivo presente; no tocar clasificadores de licencia aún

> **Gate G-01 (fin S0)**: round-trip A2A PASS contra agno 2.8.7 real. FAIL → re-verificar pin unificado; plan B: runtime mínimo (SPEC_01/06 ya hechas) sin A2A.

### S1: SPEC_23 — Config & Secrets (1–2 días-agente)

Completa la capa de config/secrets; habilita deploy en Cloud Run (paralelo con S2).

- [ ] 1.1 Hot-reload de config: `ResyncManager` existe para AgentOS; falta para ConfigManager (`di/agno_resolver.py`)
- [ ] 1.2 Feature flags: integrar `FeatureFlagManager` de core-cenf (sin hardcodear flags)
- [ ] 1.3 SecretManager async en prod: Cloud Run secrets / Supabase (hoy `ConfigSecretResolver` lee env síncrono)
- [ ] 1.4 Clasificación env vs runtime según SPEC_03 §2 (qué se lee al boot vs por request)
- **Depende de**: S0 (pin)
- **Verificación**: `pytest tests/unit/di -q` + test de hot-reload (cambio de config → agente lo refleja sin restart)
- **Costo est.**: ~$15–30 tokens

### S2: SPEC_03 — Persistencia PostgreSQL (3–5 días-agente)

El backbone de Fase 1: sin Postgres no hay multi-tenant durable ni demo G-04.

- [ ] 2.1 **DbRegistry** (`src/yaml_agno/persistence/registry.py` — hoy 0 bytes): implementar SPEC_03 §7.2, con `get_vector_db()` inyectable por DI (requisito corrección pgvector)
- [ ] 2.2 Wiring del storage de Agno a Postgres: `PgAgentStorage` / `PgTeamStorage` (agno `db/postgres/` — API estable, verificado en diff §4.5)
- [ ] 2.3 `PgVectorDb` con **pgvector** (no Qdrant) + JSONB para metadatos
- [ ] 2.4 Swap de vector DB fácil por DI: factories consumen `DbRegistry.get_vector_db()`, no el proveedor directo
- [ ] 2.5 Health check de Postgres real: `api/health.py` hoy declara "real Postgres ping arrives with SPEC_03 B-E"
- [ ] 2.6 Integración Supabase/Cloud Run: connection string vía SecretManager (no env directo — inviolable rule 4)
- **Depende de**: S0; S1 parcial (connection strings)
- **Verificación**: `pytest tests/unit/db tests/unit/persistence -q` + integration test: `AgentFactory.build(cfg)` persiste y recupera en Postgres real (pgvector) → **Gate G-05 SPEC_03**
- **Costo est.**: ~$30–60 tokens

### S3: SPEC_05 — Workflows y Teams (2–4 días-agente)

"Equipos" es el core del producto (facturación, email, profiler) y el vehículo de la demo G-04.

- [ ] 3.1 Validación end-to-end de equipos: `TeamFactory` (factories/team_factory.py) → `agno.team.Team` con `TeamMode` coordinate/route/broadcast/tasks contra 2.8.7
- [ ] 3.2 Workflows con templates YAML (prepara SPEC_33) y DAGs: `WorkflowFactory` + `workflows/step_executor.py`
- [ ] 3.3 Tests de integración de equipos REALES (no solo factories): 2+ agentes coordinados resolviendo una tarea
- [ ] 3.4 Gotcha config (diff §4.1): NO combinar `enable_agentic_memory: true` con LearningMachine store `user_memory` (colisión `update_user_memory`) — validar en configs de team
- **Depende de**: S0 (SPEC_01/02 hechas; SPEC_14 cerrada en 0.4)
- **Verificación**: `pytest tests/unit/factories tests/unit/workflows -q` + integration test de TeamMode real → **Gate G-05 SPEC_05**
- **Costo est.**: ~$20–45 tokens

### S4: SPEC_04 — Memoria (1–2 días-agente)

Memoria larga = **Agno native** (LearningMachine/MemoryManager — Decisión 4, sin código propio). Es lo que hace a los agentes "aprender" entre sesiones (demo G-04).

- [ ] 4.1 Validar wiring `MemoryConfig` → LearningMachine/MemoryManager contra **2.8.7** (el revamp de entity memory cambió el store interno — diff §4.4)
- [ ] 4.2 Tests de integración: memoria larga + session memory (persistir → nueva sesión → recuperar)
- [ ] 4.3 Decidir gotcha `enable_agentic_memory` vs learning `user_memory` (elegir uno solo por config; documentar en DECISIONES.md)
- [ ] 4.4 `memory/user_identity.py` ya resuelve composite user_id; verificar que filtra por `tenant_id` en recuperación (conecta con S2)
- **Depende de**: S2 (el store de memoria usa la DB configurada)
- **Verificación**: integration test: agente aprende en sesión 1 → recuerda en sesión 2 (contra Postgres)
- **Costo est.**: ~$10–25 tokens

### S5: SPEC_19 — Security/Auth/Tenant (3–5 días-agente · CONDICIONAL)

**DECISIÓN CLAVE**: si G-04 se valida solo internamente (3 personas CENF) → **postergar a Fase 2**. Los JWT/RBAC/scopes son requerimiento de clientes externos, no de uso interno. El tenant básico (parse + filtro) ya está en `tenant/resolver.py` + `api/middleware/tenant_context.py`.

- [ ] 5.1 **Si se ejecuta**: middleware JWT real (`JWT_VERIFICATION_KEY`, Decisión "Secret JWT")
- [ ] 5.2 RBAC/scopes: `ScopeEnforcer` + catálogo de scopes + endpoint catalog
- [ ] 5.3 Audit trail + CORS/security headers
- [ ] 5.4 **Si se posterga**: cerrar con nota en DECISIONES.md: aislamiento garantizado por (a) composite user_id, (b) filtro `tenant_id` en repos `yamlagno_*`, (c) storage Agno aislado por user_id. **NO RLS** (Decisión 2.9 inviolable)
- **Depende de**: S2 (tenant rows); S0
- **Verificación (si se ejecuta)**: integration test: 2 tenants en la misma instancia → 0 fugas cross-tenant → **Gate L-03**
- **Costo est.**: $30–60 tokens (si se posterga: $5, solo doc)

### S6: Infra + Demo G-04 (1–2 días-agente)

- [ ] 6.1 Deploy mínimo: **Google Cloud Run** (servicio API `api/app.py`) + **Supabase** (Postgres + pgvector). NO Fly.io, NO K8s, NO VPS
- [ ] 6.2 CI mínimo de deploy: test + lint + mypy + gitleaks + pip-audit (SPEC_22 formal queda Fase 2; acá solo el gate que protege el deploy)
- [ ] 6.3 `core-cenf-py` sigue privada → CI con `GIT_AUTH_TOKEN` documentado (G-02 difiere a OSS; **NO** extraer interface, ver reconciliación)
- [ ] 6.4 **Demo G-04 interna**: correr un equipo yaml-agno real (facturación AFIP o email) contra Postgres real con modelos free → medir "nuestros agentes programan/analizan/deciden mejor"
- **Depende de**: S2, S3, S4 (demo usa Postgres + Team + Memoria)
- **Verificación**: Cloud Run URL responde `/health` con Postgres ping real + demo del team ejecutando tarea real → **Gate G-04**
- **Costo est.**: ~$10–20 tokens + $0–15 infra

---

## DAG de Fase 1 (resumen)

```
S0 (pin 2.8.7 + cerrar SPEC_26/14 + fix MCP)  ──►  Todo
S1 SPEC_23 (config/secrets) ──┬──► S2 SPEC_03 (Postgres + pgvector) ──► S4 SPEC_04 (memoria)
S0 (SPEC_01/02/14 hechas) ────┴──► S3 SPEC_05 (equipos) ──────────────┤
                                                         S5 SPEC_19 (auth — CONDICIONAL, Fase 2 si G-04 interno)
                                                                       ▼
                                                         S6 Infra (Cloud Run + Supabase) + Demo G-04
```

**Ruta crítica**: S0 → S2 (SPEC_03) → S4 → S6. S1 corre en paralelo con S2. S3 desbloquea la demo junto con S4. S5 es colchón (se posterga entera si G-04 es interno).

---

## Gates de Decisión

| Gate | Después de | Criterio GO | Criterio HOLD |
|------|-----------|-------------|---------------|
| **G-01** | S0 | Round-trip A2A PASS contra agno 2.8.7 real (SPEC_26 cerrada) | FAIL → re-verificar pin; plan B: runtime mínimo sin A2A |
| **G-05** | por SPEC runtime | Integration test de la SPEC contra Agno REAL (S2, S3, S4) | 1 fallo por drift Agno → congelar esa SPEC + revisar pin (W-05) |
| **L-03** | S5 (si se ejecuta) | Integration test SPEC_19: 0 fugas cross-tenant (2 tenants, misma instancia) | FAIL → no conectar clientes externos sin aislamiento |
| **G-04** | S6 | Equipo interno CENF (facturación/email) ejecutando tarea real sobre Postgres + Agno 2.8.7, con mejora medible | Demo no corre → extender S6 2–3 días antes de tocar SPEC_19 |
| **G-03** | semanal (viernes) | tokscale: burn total CENF ≤$300/mes (hoy **$134 ✅**), yaml-agno ≤$160/mes | 2 meses seguidos sobre tope → congelar no críticas (T-02) |
| **G-06** | trimestral (~nov 2026) | Revisión del pin Agno documentada en DECISIONES.md + calendar | Sin entrada → riesgo drift R-01 sube |
| **T-05** | si G-04 es externo | Retainer cliente #1 firmado antes de procesar datos reales | Sin retainer → HOLD clientes; Fase 1 interna no se detiene |

---

## Riesgos Activos (top 5 que afectan ejecución)

| Riesgo | Prob | Mitigación en este plan |
|--------|------|------------------------|
| **R-09** Burn sin revenue | 85% → **mitigado**: $134/mes real (no $401) | R-03 ya ejecutado (modelos free); monitoreo tokscale semanal (G-03); tope $160 yaml-agno |
| **R-36** Monitoreo inactivo (multiplicador) | 75% | Watchlist viernes 30 min (W-01..W-08); automatizar W-07/W-02/W-05; S0 no cierra sin calendario |
| **R-01** Drift Agno | 50% | Pin 2.8.7 verificado (0 breaking, diff §8); G-05 integration tests por SPEC; G-06 trimestral |
| **R-28** Bus factor 1 | 50% | Rotación ownership schema/validación → Pablo/Flor; DECISIONES.md al día (W-07); S0 cierra con docs sincronizadas |
| **R-10** Fase 1 sin cliente → insolvencia | 55% | G-04 re-definido como interno: la demo interna ES el éxito; retainer solo si se escala a externo (T-05) |
| **R-07** Moat seguridad roto por drift | 55% | Suite regression seguridad vs Agno REAL en el próximo bump (ventana G-06); S0 ya sube el pin con la suite corriendo |

---

## Out of Scope (Fase 1)

- **SPEC_10 RAG**: Fase 2 — usa **pgvector + JSONB** (Supabase), no Qdrant. Spike P-002 cancelado (la base vectorial se construye en S2).
- **SPEC_13 Scheduler**: Fase 2 (stub vacío; requiere SPEC_05 estable primero).
- **SPEC_16 HITL/Guardrails**: Fase 2 (stubs hitl/, guardrails/ vacíos). Necesario solo si hay clientes externos con datos reales.
- **SPEC_20 Docker / SPEC_22 CI/CD formal / SPEC_24 Monitoring**: Fase 2 post-G-04. En Fase 1 solo CI mínimo de deploy (S6.2) + health check.
- **SPEC_19 completo (JWT/RBAC)**: postergado si G-04 es interno (decisión en S5).
- **Extracción interface core-cenf**: NO — solo 17 líneas de import; se mantiene privada hasta OSS (re-evaluar en release 1.0).
- **Provider OpenCode en Agno**: NO existe ni corresponde crear (OpenCode es cliente, no proveedor; OpenAILike cubre cualquier endpoint). Evaluación completa en OPENCODE-PROVIDER-EVALUATION.md.
- **SPEC_21 K8s**: NO implementar nunca — documentar trigger (SLA ≥99.9%, ≥2 tenants dedicados, GPU, bill >$100/mes).
- **Cierres de Fase 2**: SPEC_15, 17, 18, 27, 28, 29, 31, 32, 33, 07, 08, 25 (stubs) — post-G-04.
- **Apertura OSS / Apache 2.0 completo / NOTICE / CONTRIBUTING / SBOM**: post-G-04, con checklist STRATEGIC §8.1.

---

## Orden de ejecución recomendado (resumen de una línea)

Cerrar (S0: SPEC_26 + SPEC_14 + pin 2.8.7 + fix MCP) → SPEC_03 en paralelo con SPEC_23 → SPEC_05 → SPEC_04 → decidir SPEC_19 según G-04 interno → infra Cloud Run/Supabase + demo interna (G-04).

*Execution Plan reconciliado por Code Architect — 2026-08-10 · Fuente única de verdad de ejecución para yaml-agno Fase 1. Roadmap 2026-08-08 queda obsoleto salvo sus secciones estratégicas (PMF, pricing, OSS) y la watchlist W-01..W-08.*
