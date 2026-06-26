# SESSION RESUME — yaml-agno (leer al iniciar la próxima sesión)

> **Propósito**: Este documento es un resumen de estado temporal para que el
> agente (Claude) recupere contexto tras una compactación. No es un SPEC.
> Mantener actualizado mientras se siga corrigiendo/iterando SPECs. Borrar
> cuando el proyecto avance a implementación.

**Última actualización**: 2026-06-22
**HEAD git**: `b1ade11` (rama `feature/specs-agno-coverage-10-25`, 64 commits)
**Estado SPECs**: 33 SPECs (SPEC_00–SPEC_32), gate verde 0 violations.

---

## 1. QUÉ ES yaml-agno

Capa de abstracción **YAML → Agno Objects**. Define agentes/teams/workflows de
Agno enteramente en YAML, con templates heredables y DI System. Se construye
**ON TOP** de Agno (no reimplementa el runtime) y **consume** el paquete
`core-cenf` (`core_infrastructure`) para infraestructura transversal
(DatabaseManager, ConfigManager, SecretManager, DependencyManager, etc.).

- **Repositorio**: `C:\Dropbox\DOC.RECA\06-Software\yaml-agno`
- **Core-cenf (consumido, no se toca)**: `C:\Dropbox\DOC.RECA\06-Software\core-cenf` — ver su `AGENTS.md` (directivas de integración) y `src/core_infrastructure/`.
- **Agno docs**: `C:\Dropbox\DOC.RECA\06-Software\agno-docs\` (y repo código `C:\Dropbox\DOC.RECA\06-Software\agno\libs\agno\`).
- **Engram**: memorias con topic_keys `yaml-agno/*` en proyecto `doc.reca`.

---

## 2. REGLAS DE TRABAJO (del usuario — respetar SIEMPRE)

### Protocolo iterativo
- **REGLA DE INICIO**: antes de tocar nada, commit baseline (máxima
  trazabilidad/rollback). Working tree limpio = baseline implícito.
- Iterativo y acumulativo: NO regenerar todo; lo no corregido es válido/intocable.
- Modificación colateral solo la estrictamente necesaria para coherencia.
- Ante duda de alcance/decisión: **NO generar versión**; aclarar con el usuario.
- Calidad > velocidad.

### Reglas generales (de aplicación a TODOS los SPECs)
- Descripciones **detalladas** (no cortas) para reducir ambigüedad en compactaciones.
- Modificar doc = actualizar **metadatos** (Version, Last_Updated, Revision_Note).
- **Código en INGLÉS**: identifiers, variables, headers, docstrings, comentarios.
  Estándar opensource. (La **narrativa** del SPEC en español está OK por ahora;
  se pasará a inglés después.)
- Textos para agentes con tag **`@ai-directive:`**.
- NO incluir ideas/conceptos del usuario directo en SPECs: **procesarlos o consultar**.
- **Doc limpio**: sin refs a comentarios del usuario (ej. "(punto 10)", "(P2 del usuario)").
- **Mermaid válido**: nodos `ID["texto"]` (con ID), `subgraph ID ["título"]`, `participant Nombre` con espacio. `[*]` solo válido en `stateDiagram-v2`.
- **DRY / SSOT**: no repetir definiciones/constantes/configs entre factory y schemas. Single source of truth.
- **Docstrings + headers Google style** en todo el código.
- **SIEMPRE** analizar SPECs anteriores ya corregidos antes de generar cambios (interrelaciones).
- **Variables ENTORNO vs EJECUCIÓN**: clasificarlas (SPEC_03 §2 es la referencia).

### Reglas técnicas (decisiones de fondo ya tomadas)
- **Build ON TOP**: yaml-agno NO reimplementa runtime/sesión/memoria/eventos de Agno.
- **Schemas *Config** (AgentConfig, TeamConfig, WorkflowConfig, StepConfig, DIReference) = SSOT en **SPEC_02**. Otras SPECs los IMPORTAN, no redefinen.
- **Enums de Agno IMPORTADOS** (no duplicados): TeamMode (4: coordinate/route/broadcast/tasks, NO coroutine), StepType (capitalizado: Step/Parallel/Condition/Router/Loop), RunStatus/RunContext (de `agno.run.base`).
- **DependencyManager**: mecanismo en **Core Infra** (core-cenf `core_infrastructure.dependency`), registrios de Agno en yaml-agno. Carga perezosa (importlib + allowlist + cache + entry_points).
- **Stack heredado** de Agno v2.6.14 (FastAPI/SQLAlchemy/Pydantic). yaml-agno NO reimplementa FastAPI (delega serving a `AgentOS.get_app()`).
- **Engram NO es de Agno** (MCP externo nuestro). NO forma parte del modelo de memoria de yaml-agno. Long-term memory = Agno nativo (LearningMachine/MemoryManager).
- **retention_days / ACID** = feature futura (no nativos de Agno).
- **Multi-tenant** = Core Infra (TenantResolver). Agno NO tiene tenant_id nativo (user_id + session_id). Aislamiento **explícito via filters** (NO RLS, NO auto-scope por contextvar — `set_tenant_id` es solo telemetría/tracing).
- **CircuitBreaker** owner = SPEC_09. API real: `failure_threshold`/`recovery_timeout`/`allow_request()`/`state == CircuitState.OPEN`.
- **asyncio.TaskGroup** (NO asyncio.gather).
- **Deployment dual**: Google Cloud Run PRIMARIO (ahora), Kubernetes FUTURO.
- **Code Review**: multi-LLM paralelo + unificador. **PR Budget**: ≤600 líneas con excepciones justificadas.
- **PII**: Zero-Trust default ON pero **configurable** (`allow_pii: {enabled, reason}`).

---

## 3. ESTADO DE LOS 33 SPECs

Todos en `specs/SPEC_*.md`. Versiones:
- **SPEC_00, 01, 02**: iteración 1 completa (0.2.0-iter1).
- **SPEC_03**: 0.3.0-iter2 — **reescrita de fondo** integrando core-cenf real (consume DatabaseManager/TransactionScope/GenericRepository; elimina runtime de Agno; prefijo `yamlagno_*`; 3 niveles multi-tenant modelados; sección entorno vs ejecución). 10/10.
- **SPEC_04**: 0.2.0-iter2 — corregida API de memoria inventada (agent.memory.add/search_relevant NO existen en Agno v2.6.14). APIs reales verificadas: LearningMachine.arecall/decision_log_store.asave(DecisionLog)/learned_knowledge_store.asave(...); MemoryManager.aget_user_memories/add_user_memory(UserMemory) SYNC. Sin Port ni adapter.
- **SPEC_08**: 0.2.0-iter2 — catálogo TDD realineado a SPEC_04 iter2 (eliminado LongTermMemoryPort/Engram adapter de §2.4 y negative-list).
- **SPEC_17, 18, 23**: 0.2.0-iter2 — corregidas por impacto de SPEC_03.
- **SPEC_05–16, 19–22, 24–32**: 0.2.0-iter1 — corregidas en ronda masiva.
- **SPEC_26–32**: nuevos (A2A, Tracing, Reasoning, Workflow-HITL, Skills, Culture, Registry).

**Gate**: `python scripts/spec_gate.py all` → 33 SPECs, 0 violations.
**Check inter-SPEC (C1–C7)**: limpio (consume core, sin runtime propio, sin auto-scope, os.environ solo inyección controlada, prefijo consistente, CB API consistente, get_repository en DatabaseManager).

### Qué SPECs están CORREGIDAS vs PENDIENTES de revisión profunda
- **Corregidas con revisión profunda (escritor + revisor adversarial + gate)**: SPEC_00, 01, 02, 03, 04 (+ SPEC_08 realineada por impacto).
- **Corregidas en ronda masiva** (con re-audit + gate, pero NO con revisión adversarial individual detallada post-core-cenf): SPEC_05–32.
- **Deuda inter-SPEC conocida** (no bloqueante, se liquida al revisar cada SPEC): SPEC_16 aún define `EngramMemoryManager(LongTermMemoryPort)` (Ports/memory eliminados en SPEC_04 iter2); se limpiará en la iteración de SPEC_16.
- **Próxima a revisar con el sistema nuevo**: **SPEC_05 (Workflows and Teams)**.

---

## 4. SISTEMA DE REVISIÓN (3 capas) — USAR EN CADA SPEC

1. **Gate automático** `scripts/spec_gate.py [N|all]` — 8 checks mecánicos (M1 metadata bumped, M2 mermaid válido, M3 inglés en código, M4 no enums Agno duplicados con owners, M5 no schemas SSOT duplicados, M6 refs existentes, M7 no refs a comentarios usuario, M8 no CJK). Exit 1 bloquea.
2. **Revisor adversarial fresco** — sub-agente (Explore) con contexto limpio que **desmiente** que quedó bien. Detecta bugs de API, inconsistencias, brechas.
3. **Check inter-SPEC por lote** — cambio en SPEC_X no rompe refs en SPEC_Y.

**Flujo por SPEC**: `escritor → gate → revisor adversarial → arreglo → check inter-SPEC → commit → resumen ejecutivo para el usuario`.

**Tu revisión (usuario)**: **resumen ejecutivo** por SPEC (200-300 líneas: decisiones + código clave + BDD, sin prosa). Duda → abre SPEC completo.

---

## 5. MAPA DEL core-cenf REAL (consumido, en `C:\Dropbox\DOC.RECA\06-Software\core-cenf`)

Paquete `core-cenf`, import `core_infrastructure`. **16 managers IMPLEMENTADOS** (no solo Protocol):
config, logger, secrets, observability, errors, auth, cache, database, filestorage, taskqueue, external_api, feature_flags, dependency, dynamic_prompting, alert, ratelimit.

APIs clave (verificar siempre contra `src/core_infrastructure/<m>/ports.py` real):
- **DatabaseManager**: `transaction() -> AsyncContextManager[TransactionScope]`, `get_repository(entity_type) -> GenericRepository[T]`. Todo async.
- **TransactionScope**: `async commit()`, `async rollback()` (idempotentes).
- **GenericRepository[T]**: `find_by_id/find_all(filters,order_by,limit,offset)/insert/update/delete/count`. Filtros exact-match. `get_repository()` **DEBE** llamarse dentro de `async with db.transaction()` (contextvar).
- **ConfigManager**: `get_string/get_number/get_boolean/get_json/get_section` (dot-notation), `async reload()`.
- **SecretManager**: `async get_secret(key)`, `invalidate_cache`, `async rotate_secret`.
- **DependencyManager**: `resolve_class(module, class)`, `register(namespace, key, target)`.
- **Contextvars**: `core_infrastructure.common.context` — `set_tenant_id/get_tenant_id` (telemetría/tracing ONLY, NO DB scoping), `set_correlation_id`.
- **Bootstrap**: `BootstrapOrchestrator(*managers)` con `asyncio.TaskGroup`.
- **Reglas AGENTS.md** (en core-cenf): depender del Protocol (no adapter concreto), `async with db.transaction()` SIEMPRE, `os.environ` solo via ConfigManager, secrets via SecretManager, contextvars NUNCA como argumento, max 250 líneas/archivo.

Tablas de yaml-agno: prefijo `yamlagno_*` + schema SQL `yamlagno` (DeclarativeBase, via GenericRepository). Tablas de Agno: `agno_*` (no tocar). Auto-provisioning `Base.metadata.create_all(checkfirst=True)` (NO Alembic en core).

---

## 6. CÓMO SEGUIR

1. **Próxima SPEC a revisar**: **SPEC_05 (Workflows and Teams)** con el sistema nuevo (gate + adversarial + resumen ejecutivo).
2. Patrón: REGLA DE INICIO (commit baseline) → leer SPEC + SPECs relacionados → escritor con contexto → gate → revisor adversarial → arreglo → check inter-SPEC → commit → resumen ejecutivo.
3. Recordar: narrativa español → inglés se hará DESPUÉS (no en cada corrección ahora).
4. Tras SPEC_04: SPEC_05, 06, 07, ... en orden. SPEC_08 ya está alineada (catálogo).

---

## 7. COMANDOS ÚTILES

```bash
cd "/c/Dropbox/DOC.RECA/06-Software/yaml-agno"
python scripts/spec_gate.py all          # gate de todos los SPECs
python scripts/spec_gate.py 04           # gate de un SPEC
git log --oneline -10                    # historial reciente
git show <commit>                        # ver un commit
```

---

*Actualizar este documento al cerrar cada SPEC. Es la fuente de verdad de
estado entre sesiones (complementa a Engram, que tiene las decisiones de fondo).*
