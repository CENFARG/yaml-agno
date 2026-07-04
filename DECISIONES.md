# DECISIONES — yaml-agno (LEER PRIMERO al retomar el proyecto)

> **Propósito**: Documento ejecutivo acotado (1 pantalla) que recupera TODO el
> contexto post-compactación o sesión nueva. NO reemplaza a los 33 SPECs; los
> resume para que no tengas que releerlos. Si necesitás detalle de una decisión,
> el topic_key de Engram o el SPEC está citado.
>
> **Última actualización**: 2026-07-04 · **HEAD git**: `cb27e5f` · **Rama**: `feature/specs-agno-coverage-10-25` · **Commits**: 118

---

## 1. QUÉ ES yaml-agno (visión)

Capa de abstracción **YAML → Agno Objects**. Define agentes/teams/workflows de
Agno en YAML, con plantillas heredables + DI System. Se construye **ON TOP** de
Agno v2.6.18 + AgentOS y **consume** `core-cenf-py` (`core_infrastructure`) para
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

- **33 SPECs** en `specs/`, gate verde 33/33 (`python scripts/spec_gate.py all`).
- **Índice**: `specs/INDEX.md` agrupa en 10 grupos temáticos (G1-G10) + campo
  `Read_Order` en cada frontmatter. Los archivos **NO se renombraron**
  (trazabilidad intacta).
- **Revisión profunda 33/33 COMPLETA**, todas verificadas contra Agno v2.6.18 +
  core-cenf-py **reales** ( APIs inventadas cazadas en todas). CERO deudas abiertas.
- **Auditoría cross-SPEC completa** (72 hallazgos, Waves 1-6, 11 contradicciones resueltas).
- git LOCAL (sin GitHub todavía — decisión del usuario).

### Grupos temáticos (mapa rápido)
- **G1 Fundaciones**: SPEC_00 · **G2 Runtime-Core**: 01,02,03
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
