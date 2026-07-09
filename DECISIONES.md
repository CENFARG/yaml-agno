# DECISIONES — yaml-agno (LEER PRIMERO al retomar el proyecto)

> **Propósito**: Documento ejecutivo acotado (1 pantalla) que recupera TODO el
> contexto post-compactación o sesión nueva. NO reemplaza a los 33 SPECs; los
> resume para que no tengas que releerlos. Si necesitás detalle de una decisión,
> el topic_key de Engram o el SPEC está citado.
>
> **Última actualización**: 2026-07-06 · **HEAD git**: `ea177f1` · **Rama**: `feature/specs-agno-coverage-10-25` · **Commits**: 121

---

## 1. QUÉ ES yaml-agno (visión)

Capa de abstracción **YAML → Agno Objects**. Define agentes/teams/workflows de
Agno en YAML, con plantillas heredables + DI System. Se construye **ON TOP** de
Agno v2.6.22 + AgentOS y **consume** `core-cenf-py` (`core_infrastructure`) para
infra transversal.

**Para qué**: herramienta interna CENF para acelerar la creación de equipos
agénticos autónomos (facturación, emails, etc.) + futura integración a amBOTHS
para clientes + posible open-source. **Enfoque**: agentes AUTÓNOMOS / equipos /
flujos (NO chat interactivo — eso lo hace Agno nativo).

---

## 2. LAS 12 DECISIONES DE ARQUITECTURA (inviolables — no contradecir)

1. **user_id SIEMPRE composite** `{tenant_id}:{principal_id}`. Único resolver
   `resolve_user_id()` en SPEC_04. `TenantContextMiddleware` (SPEC_06) delega.
   `TenantResolver` (SPEC_03) solo PARSEA. NUNCA None, NUNCA "default" bucket,
   NUNCA campo YAML.
2. **YamlAgentOS(AgentOS)** subclass (SPEC_06). NO own `/run`, `/sessions`,
   `/agents-config`, `/health` endpoints (todos nativos AgentOS). Wire contract
   multipart/form-data con `{agent_id}`. `/api/v1/agents/{name}/run` eliminado.
3. **ErrorHandlingManager core-cenf**: `classify()`/`report()` SYNC/`handle()`/
   `handle_errors()`. `ErrorClassification` (TRANSIENT/PERMANENT/VALIDATION/
   AUTH/RATE_LIMIT, **sin CRITICAL**). NO `should_retry`/`categorize_error`.
4. **Memoria 100% Agno native** (LearningMachine/MemoryManager). NO Engram, NO
   LongTermMemoryPort, NO EngramMemoryManager, NO adapter.
5. **A2A = Agno native** (os/interfaces/a2a/). NO message_protocol.py/TeamMessage.
   ACP no existe.
6. **Retry**: model-level = Agno `Model.*`; step-level = yaml-agno RetryPolicy
   (SPEC_05, delega `classify()`); HITL retry Agno-native. CircuitBreaker owner
   SPEC_09 (rate-based min_requests).
7. **Config via core-cenf ConfigManager** (no `os.environ`). Secrets SecretManager
   async. `.env` local / SecretManager prod.
8. **Schemas *Config SSOT = SPEC_02**. AgentConfig tiene slots opacos (reasoning/
   skills/human_review/culture/persistence + los de tools/knowledge/memory/session).
   Enums (TeamMode 4 modos, StepType) IMPORTADOS de Agno.
9. **Multi-tenant**: explicit WHERE filters, NO RLS, NO tenant_id en `agno_*`,
   tenant_id solo en `yamlagno_*` config rows. K8s namespaces = deploy boundary
   NO tenant.
10. **asyncio.TaskGroup** (no gather). Cloud Run PRIMARIO, K8s FUTURO.
    Review: multi-LLM (NO "Opus mandatory").
11. **Backend sanitization/validation MANDATORY** para APIs/JSON.
12. **UI (SPEC_07)**: NO frontend propio en MVP. SaaS Free de Agno (os.agno.com)
    para MVP + fork de `agent-ui` (MIT) POST-MVP. Deploy: cherry-pick
    `agent-platform-railway` (Apache-2.0), reject chat-centric.

**Secret JWT**: `JWT_VERIFICATION_KEY` (Agno lo lee con `getenv`,
app.py:1072). NO `jwt_signing_key`.

---

## 3. ESTADO (2026-07-04)

- **34 SPECs** en `specs/` (SPEC_00–SPEC_33), gate verde 34/34 (`python scripts/spec_gate.py all`).
- **Índice**: `specs/INDEX.md` agrupa en 10 grupos temáticos (G1-G10) + campo
  `Read_Order` en cada frontmatter. Los archivos **NO se renombraron**
  (trazabilidad intacta).
- **Revisión profunda 33/33 COMPLETA**, todas verificadas contra Agno v2.6.22 +
  core-cenf-py **reales** ( APIs inventadas cazadas en todas). CERO deudas abiertas.
- **Auditoría cross-SPEC completa** (72 hallazgos, Waves 1-6, 11 contradicciones resueltas).
- git LOCAL (sin GitHub todavía — decisión del usuario).

### Grupos temáticos (mapa rápido)
- **G1 Fundaciones**: SPEC_00 · **G2 Runtime-Core**: 01,02,03,33(templates)
- **G3 Capacidades-Agente**: 14,11,10,15,17,30
- **G4 Memoria-Aprendizaje**: 04,31,28 · **G5 Oversight**: 16,29
- **G6 Orquestación**: 05,13,32 · **G7 ControlPlane-API**: 06,12,26,19
- **G8 Ops-Observabilidad**: 09,27,18,23 · **G9 Deploy-UI**: 07,20,22,21,24,25
- **G10 Meta**: 08 (catálogo TDD)

### MVP top 10 (orden impl.): SPEC_00, 02, 01, 14, 11, 30, 26, 03, 05, 06

---

## 4. REGLAS DE TRABAJO (del usuario — respetar SIEMPRE)

- **REGLA DE INICIO**: commit baseline antes de tocar nada.
- Iterativo/acumulativo: no regenerar todo; lo no corregido es intocable. Calidad
  > velocidad. Dudas → aclarar antes de generar versión.
- Código en INGLÉS (identifiers/docstrings/comments). Narrativa SPEC en español
  (se pasa a inglés al final). `@ai-directive` en pseudo-código.
- Doc limpio: sin refs a comentarios del usuario ("(punto 10)"). Mermaid válido
  (`ID["text"]`, `subgraph ID ["title"]`). DRY/SSOT. Google docstrings.
- Clasificar variables entorno vs ejecución.
- **Paths**: NUNCA escribir fuera de `C:\Dropbox\DOC.RECA\06-Software\yaml-agno`.
  Sub-agentes advertidos del anti-C:/.
- Commits granulares por cambio (gitflow: rama feature). Engram: memorias con
  topic_keys `yaml-agno/*` en proyecto `doc.reca`.

---

## 4bis. ESTRUCTURA `src/` CANÓNICA (anti-inconsistencia F6)

> @ai-directive: este es el ÁRBOL OFICIAL de carpetas de `yaml-agno/src/`. Los
> SPECs referencian paths con prefijo `src/` (NO `yaml-agno/src/` — el prefijo
> del repo va implícito). Al implementar, este árbol es la fuente de verdad.
> `core_infrastructure` (core-cenf-py) es una DEPENDENCIA PIP (se importa con
> `from core_infrastructure... import ...`) — **NO se copia ni se replica** bajo
> `src/`. Si un SPEC escribió `src/core_infrastructure/...` es un error de
> tipeo: corregir a `from core_infrastructure... import`.

```
yaml-agno/src/
├── yaml_agno/                    # package root (pip-installable: `import yaml_agno`)
│   ├── __init__.py
│   ├── api/                      # SPEC_06: YamlAgentOS, health, middleware
│   │   ├── app.py                # YamlAgentOS(AgentOS) subclass
│   │   ├── health.py             # readiness/liveness routers
│   │   └── middleware/           # rate_limit.py, tenant_context.py
│   ├── factories/                # SPEC_01: YAML → Agno objects
│   │   ├── agent_factory.py
│   │   ├── team_factory.py
│   │   └── workflow_factory.py
│   ├── models/                   # SPEC_02 (SSOT): *Config Pydantic schemas
│   │   └── config/               # agent_config.py, team_config.py, workflow_config.py
│   ├── di/                       # SPEC_01: DependencyManager (lazy importlib)
│   │   └── dependency_manager.py
│   ├── persistence/              # SPEC_03: yamlagno_* config store + DbRegistry
│   │   ├── registry.py           # DbRegistry (get/get_vector_db)
│   │   └── models/               # ORM records (AgentConfigRecord, etc.)
│   ├── memory/                   # SPEC_04: agno_memory_config, user_identity, autosave, scope_mapping
│   ├── workflows/                # SPEC_05/29: retry_policy, step_executor, a2a_config, human_review
│   ├── tools/                    # SPEC_11: tool loaders, MCP resolver, security whitelist
│   ├── knowledge/                # SPEC_10: KnowledgeConfig, chunker/vector resolver
│   ├── media/                    # SPEC_17: MediaInput, converter, MediaArtifact
│   ├── hitl/                     # SPEC_16: guardrails, confirmation, approval manager
│   ├── guardrails/               # SPEC_16: PII/secret sanitizers (BaseGuardrail impls)
│   ├── skills/                   # SPEC_30: SkillsConfig → agno.skills delegation
│   ├── culture/                  # SPEC_31: CultureConfig → agno.culture delegation
│   ├── reasoning/                # SPEC_28: reasoning_effort passthrough (under model:)
│   ├── evals/                    # SPEC_18: eval adapters (yamlagno_eval_runs table)
│   ├── scheduler/                # SPEC_13: schedule adapters, background executor
│   ├── config/                   # SPEC_23: loader (consumes core-cenf ConfigManager)
│   ├── tracing/                  # SPEC_27: tracing config factory (delegates setup_tracing)
│   ├── templates/                # SPEC_33: YAML template registry + inheritance resolver
│   └── runtime/                  # server.py (serve YamlAgentOS on :7777)
└── (NO core_infrastructure/ — es dependencia pip, se importa, no se replica)
```

**Reglas**: (a) todo bajo `yaml_agno/` (underscore, nombre pip); (b) una
carpeta por SPEC dueño; (c) `core_infrastructure` se IMPORTA nunca se copia;
(d) los adapters delgados (no reimplementan Agno); (e) SSOT: schemas solo en
`models/`.

---

## 5. CÓMO SEGUIR (próximos pasos)

1. **Fase actual**: especificaciones COHERENTES y COMPLETAS. Listo para
   **implementación**.
2. **Próximo**: planificar implementación del MVP (empezar por SPEC_00→02→01→14→11).
   SDD/TDD ultra-detallado ya está en cada SPEC (BDD gherkin + TDD microtasks).
3. **GitHub**: pendiente decisión del usuario (cuando quiera, crear repo + remote).

---

## 6. DÓNDE ESTÁ CADA COSA (mapa de recuperación)

- **Visión detallada**: `VISION.md`, `SPEC.md`
- **Estado sesión**: `SESSION_RESUME.md`
- **Índice SPECs**: `specs/INDEX.md`
- **Gate**: `scripts/spec_gate.py [N|all]`
- **Engram** (proyecto `doc.reca`, buscar keyword `yaml-agno`):
  - `yaml-agno/session-state-resume` — estado sesión
  - `yaml-agno/specifics/spec-NN` — decisiones por SPEC
  - `yaml-agno/agno-intel/*` — APIs reales Agno verificadas (A2A, memory, workflows, AgentOS, playground)
  - `yaml-agno/audit-wave-1`, `audit-waves-2-6`, `deep-review-complete`
  - `global/engineering-rules` — reglas globales CENF (seguridad, patrones)

---

*Mantener este documento actualizado al cerrar cada hito. Es la red de seguridad
anti-lobotomización post-compactación.*
