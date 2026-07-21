---
Spec_ID: "SPEC_00"
Title: "System Strategy - Vision, Principles and Strategic Constraints"
Version: "0.2.0-iter2"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#Strategy", "#Vision", "#Roadmap", "#Principles"]
Dependency_Hashes: []
Group: "G1-Fundaciones"
Read_Order: 1
Last_Updated: "2026-07-02"
Revision_Note: "Iter 2 - Wave 6 hygiene: corrected '5 modos' to '4 modos (coordinate/route/broadcast/tasks)' to match the real Agno Team modes."
---

# SPEC_00_SYSTEM_STRATEGY

> **Propósito**: Definir el marco conceptual y las directrices inmutables de negocio y tecnología del sistema yaml-agno.

---

## 1. PURPOSE AND STRATEGIC INTENT

### 1.1 Propósito del Proyecto

**yaml-agno** es una librería pip-installable que permite definir **agentes, equipos y workflows de Agno enteramente en YAML**, con **50+ templates auto-prompted**, **Dependency Injection System** para variables dinámicas, y abstracción completa de **80+ parámetros de Agent()**, **Team()**, y **6 primitivas de Workflow**.

### 1.2 Problema que Resuelve

- **Complejidad de Agno Framework**: Agno tiene 80+ parámetros de configuración que requieren código Python
- **Curva de aprendizaje empinada**: Nuevo usuarios deben aprender Python + Agno internals
- **Falta de estandarización**: No existe un formato canónico para compartir configuraciones de agentes
- **Dificultad de versioning**: Configuraciones en código son difíciles de versionar y comparar

### 1.3 Solución Propuesta

- **YAML-First**: Todo se configura vía YAML, no código Python
- **Templates Auto-Prompted**: 50+ templates con frontmatter que describen uso
- **DI System**: Variables dinámicas desde DB/API/Env sin modificar YAML
- **Interconocimiento Cognitivo**: Teams conocen sus I/O schemas
- **Caja Negra**: Clientes ven I/O, desarrolladores ven YAML

---

## 2. VISION AND FUTURE EVOLUTION

### 2.1 Fase 1: Herramienta Interna CENF (Ahora)

- yaml-agno como herramienta interna para CENF
- Meta-agentes de apoyo (Agno Docs Expert, Prompting Expert)
- Validación con casos reales (Facturación AFIP, Excel Processing)

### 2.2 Fase 2: Ambots-Hs (Futuro)

- Sistema agéntico open-source basado en agno que busca resolver problemas a traves de bajar nivels de abtraccion de usuarios no expertos hasta la Ia a traves de la hyperpesonalizacion de usuario y sus procesos. Se definen en un conjunto de agentes de IA sincronicos y asincronicos que analizan al usuario y sus proceosso para poder automatizarlos mediante nuevos equipos agenticos de manera recursiva.
- Community contributions: El sistema permite que usuarios inexpertos compartan su knowhow ocn su agente y que luego este mismo sea compartido con otros agentes de otros usaurios. Cada usuario en su nivel de abtraccion puede mejorar el sistema en diferentes partes. 

### 2.3 Evolución del Producto

```
Semilla (Ahora) → Estándar (3 meses) → Élite (8 meses) → Futuro (12 meses)
```

---

## 3. CORE PRINCIPLES

### 3.1 Principios Inmutables

1. **YAML-First**: Todo config vía YAML, no Python code para users
2. **Caja Negra**: Clientes ven I/O, developers ven YAML
3. **Interconocimiento Cognitivo**: Teams conocen sus I/O schemas
4. **DI System**: Variables dinámicas desde DB/API/Env
5. **Templates Auto-Prompted**: Frontmatter describe uso
6. **CEL + Callables**: Ambos desde día uno
7. **Multi-tenant Ready**: ConfigDB + hot-reload
8. **Zero-Trust Security (configurable)**: PII sanitization y secret masking **activados por defecto**, pero **configurables por agente/equipo**. Algunos agentes requieren legítimamente procesar PII (asesor legal, médico, financiero). La política se declara en YAML (ver SPEC_16): default `enabled: true`, con `allow_pii: true` + `reason` para excepciones auditadas

### 3.2 Principios Arquitectónicos

- **Clean Architecture**: Dependencias hacia adentro (dominio)
- **DDD Táctico**: Bounded contexts, aggregates, value objects
- **CQRS**: Separación de commands (escritura) y queries (lectura)
- **Hexagonal**: Ports y adapters para infraestructura
- **Event-Loop Safety (run + arun)**: yaml-agno soporta **ambas** APIs de Agno: `Agent.run()` (síncrono) y `Agent.arun()` (asíncrono). `arun()` es el default para producción (concurrency, streaming SSE, background execution). La elección del método es del **caller de runtime**, no del spec YAML del agente
- **Boundary Validation**: Validación en frontera con Pydantic V2

---

## 4. MANDATORY ECOSYSTEM PRIMITIVES

### 4.1 Agno Framework Primitives (inventario completo)

Cada primitiva se clasifica por **nivel de abstracción** en yaml-agno:

- **ABSTRAER**: se exponen parámetros en YAML (configuración frecuente del usuario)
- **REFERENCIAR**: Agno lo maneja nativo; yaml-agno solo lo activa/referencia con un flag o id
- **DELEGAR**: interna de Agno; yaml-agno no la toca (evita reinventar)

#### Agent / Team core (ABSTRAER)

| Primitiva | Nivel | Especificación |
|-----------|-------|----------------|
| Agent() constructor (45+ params) | ABSTRAER | SPEC_01, SPEC_02 |
| Team() constructor (25+ params, 4 modos (coordinate/route/broadcast/tasks)) | ABSTRAER | SPEC_01, SPEC_05 |
| Workflow primitives (Step, Parallel, Condition, Router, Loop) | ABSTRAER | SPEC_01, SPEC_05 |
| Database `db=` (SqliteDb/PostgresDb/InMemoryDb) | ABSTRAER | SPEC_03 |
| Session storage (= db=) | ABSTRAER | SPEC_03 |
| Chat history (`add_history_to_context`, `num_history_runs`, `read_chat_history`) | ABSTRAER | SPEC_04 |
| Memory flags (`enable_agentic_memory`, `update_memory_on_run`, `add_memories_to_context`) | ABSTRAER | SPEC_04 |
| MemoryManager (modelo, instructions, strategy) | REFERENCIAR | SPEC_04 |
| session_state (dict inicial) | ABSTRAER | SPEC_15 |
| Reasoning (`reasoning`, `reasoning_model`, `reasoning_effort`) | ABSTRAER | SPEC_14 |
| HITL flags por step (`requires_confirmation`, `requires_user_input`) | ABSTRAER | SPEC_16 |
| Guardrails (PII, PromptInjection, Moderation + custom) | ABSTRAER | SPEC_16 |

#### Knowledge / Tools (ABSTRAER)

| Primitiva | Nivel | Especificación |
|-----------|-------|----------------|
| Vector DBs (19: LanceDb, PgVector, Pinecone, Qdrant, Weaviate, Chroma, etc.) | ABSTRAER | SPEC_10 |
| Embedders (17: OpenAI, Cohere, SentenceTransformers, Ollama, etc.) | ABSTRAER | SPEC_10 |
| Chunkers (9: fixed, document, recursive, semantic, markdown, csv, code, agentic, custom) | ABSTRAER | SPEC_10 |
| Knowledge (search modes: vector/keyword/hybrid/rerank) | ABSTRAER | SPEC_10 |
| Toolkits (120+: HackerNews, YFinance, DuckDb, Slack, etc.) | ABSTRAER | SPEC_11 |
| `@tool` custom functions | ABSTRAER | SPEC_11 |
| MCPTools (3 transports: stdio, streamable-http, SSE) | ABSTRAER | SPEC_11 |
| Skills (`Skills(loaders=[LocalSkills(path)])`) | ABSTRAER (ligero) | SPEC_11 |

#### Context / Compression (ABSTRAER)

| Primitiva | Nivel | Especificación |
|-----------|-------|----------------|
| Context flags (`add_*_to_context`: datetime, name, location, memories, session_state, dependencies, knowledge) | ABSTRAER | SPEC_15 |
| Dependencies (dict, callables, template `{name}`) | ABSTRAER | SPEC_15 |
| Context compression (`compress_tool_results`, `compression_ratio_threshold`) | ABSTRAER | SPEC_15 |
| CompressionManager custom | REFERENCIAR | SPEC_15 |
| Context providers / callable factories | REFERENCIAR | SPEC_15 |

#### Model / Runtime resilience (ABSTRAER)

| Primitiva | Nivel | Especificación |
|-----------|-------|----------------|
| Models (26 providers: Anthropic, OpenAI, Google, Ollama, Bedrock, OpenRouter, etc.) | ABSTRAER | SPEC_14 |
| Model-as-string (`provider:id`) | ABSTRAER | SPEC_14 |
| cache_response | ABSTRAER | SPEC_14 |
| Fallback models / FallbackConfig | ABSTRAER | SPEC_14 |
| Scheduler (cron, ScheduleManager) | ABSTRAER (cronos declarativos) | SPEC_13 |
| Background execution (`background=True`) | REFERENCIAR (flag) | SPEC_13 |

#### Hooks / Oversight (REFERENCIAR / DELEGAR)

| Primitiva | Nivel | Especificación |
|-----------|-------|----------------|
| Hooks (`pre_hooks`, `post_hooks`, `@hook(run_in_background)`) | REFERENCIAR (lista de funciones Python) | SPEC_16 |
| Run cancellation (`cancel_run()`) | DELEGAR (runtime nativo) | SPEC_13 |
| CultureManager (shared cultural knowledge) | REFERENCIAR (id del manager) | — |
| Multimodal (images/audio/video input, generation) | REFERENCIAR (flag `multimodal: true`) | SPEC_17 |
| Tracing (OpenTelemetry → DB) | REFERENCIAR (flag `tracing: true`) | SPEC_09 |
| Custom logging (`configure_agno_logging`) | DELEGAR (código app) | SPEC_09 |
| Evals (Accuracy, Agent-as-Judge, Performance, Reliability) | DELEGAR (offline/testing) | SPEC_18 |

#### AgentOS Control Plane (ABSTRAER)

| Primitiva | Nivel | Especificación |
|-----------|-------|----------------|
| AgentOS (18 params: authorization, interfaces, MCP server, scheduler, tracing) | ABSTRAER | SPEC_12 |
| Interfaces (AG-UI, Slack, WhatsApp, Telegram, A2A) | ABSTRAER | SPEC_12 |
| Session managers (lifecycle AgentOS) | DELEGAR (interno AgentOS) | SPEC_12 |

**Regla de oro**: yaml-agno **nunca reimplementa** lo DELEGADO. Construye los objetos Agno y deja que Agno/AgentOS manejen el runtime.

### 4.2 External Primitives

- **CEL (Common Expression Language)**: Para condiciones en workflows
- **MCP (Model Context Protocol)**: Para tool exposure
- **CodeGraph**: External repo con Agno code semantic graph
- **Pydantic V2**: Para validación de datos
- **FastAPI (prioritario, no opcional)**: yaml-agno **delega el serving HTTP a `AgentOS.get_app()`**, que produce una app FastAPI stateless con 50+ endpoints, RBAC, sessions, streaming SSE. yaml-agno **NO reimplementa FastAPI**: aporta declaración (YAML) + factory de objetos Agno, y deja que AgentOS sirva el runtime. Construir sobre Agno = máxima reutilización de lo que Agno/AgentOS proveen
- **PostgreSQL (prioritario, no opcional)**: Agno usa SQLAlchemy 2.0 nativamente (`create_async_engine`); yaml-agno hereda esa dependencia en vez de re-pinnearla. PostgreSQL es el backend de producción para sessions, memory, tracing y knowledge (PgVector)

---

## 5. BOUNDED CONTEXTS

### 5.1 Contexto: yaml-agno Core

**Responsabilidad**: Traducir YAML → Agno Objects + provisión de templates heredables

- **AgentFactory**: YAML → Agent()
- **TeamFactory**: YAML → Team()
- **WorkflowFactory**: YAML → Workflow()
- **DIFactory**: Resolver `${provider.key}`
- **TemplateManager**: templates con frontmatter, **jerarquía heredable** (un template puede extender/componerse de otros, como código orientado a objetos: partes ya configuradas y extensibles)

### 5.2 Contexto: Equipos Agénticos Validación (internos CENF)

**Responsabilidad**: yaml-agno se valida internamente en CENF contra equipos agénticos reales.

**Importante**: Los equipos nombrados a continuación (Facturación, Excel, Email, Meetings) son **ejemplos de casos de uso internos** que ya tenemos pensados para probar el sistema. **No son los únicos, ni necesariamente los primeros, ni la prioridad**. La prioridad real de qué equipos se construyen primero **no está definida aún**: se decidirá cuando el funcionamiento del sistema esté claro. Es más probable que los primeros equipos agénticos sean **productos para clientes** (necesitamos flujo de caja) que herramientas internas. La columna del roadmap referencia **qué parte del sistema yaml-agno se prueba**, no el caso particular de negocio.

Casos internos de prueba (a definir orden/prioridad):
- Procesamiento de Facturación (AFIP)
- Processing de Excel files
- Processing de Emails
- Meeting Summarization

### 5.3 Contexto: Meta-Agentes de Apoyo (futuro amBotHs)

**Responsabilidad**: Apoyar a usuarios finales a crear configs sin conocimiento profundo de Agno.

- **Agno Docs Expert**: Es un equipo agentico, que tambien se hara con agno como base, que permite a un agente de programacion (opencode, claudecode, gemini-cli, antigravity, etc) definir estrategias en conjunto sobre como funciona agno. El equipo agentico AgBúsqueda en docs de **Agno Docs Expert** tiene dos mcp de busqueda semantica a traves de FTS5 para encontrar patrones de diseño, logicas de porgramación, features, funcionalidades, etc de agno y poder dialogar con el agente de programación sobre que el agente o equipo agentico a contruir para resolver un problema. No siempre, pero normalmente se basara en yaml-agno para desrrollarlo.
- **Prompting Expert**: Es un equipo agentico, que tambien se hara con agno como base, que permite a un agente de programacion (opencode, claudecode, gemini-cli, antigravity, etc) definir estrategias en conjunto sobre cuales son las mejores estrategias de prompts, ingeniería de contexto, ingeiería de arnes y ingeniría de loops para los agentes o equipo agentico a contruir para resolver un problema.
- **Code Expert**: CodeGraph integration es una herramienta externa de codigo abierto que permite desarrollar grafos de conocimiento de codigo fuente. El repositorio original es https://github.com/colbymchenry/codegraph. Esto ayudara a los agentes de programación (opencode, claudecode, gemini-cli, antigravity, etc), y al **Agno Docs Expert** a tener mucha mas claridad de como funciona, como esta desarrollado, etc agno. Pero ademas en el desarrollo de yaml-agno iremos creando un grafo que lo explique como herramienta de documentacion extra del propio proyecto. Así los agentes de programacion tendran mas conocimiento y contexto de como usarlo.

**Objetivo de producto**: El fin último de yaml-agno es, primero, **ayudarnos a nosotros (CENF)** a generar equipos agénticos nuevos reduciendo ~50% del esfuerzo mediante agentes de programación de IA (Claude Code / OpenCode) soportados sobre Agno + AgentOS; y luego, **integrarse a amBotHs** para que cualquier usuario pueda crear equipos agénticos sin conocimiento profundo de Agno ni de equipos agénticos.

---

## 6. STRATEGIC CONSTRAINTS

### 6.1 Constraints de Desarrollo

- **Strict TDD**: 100%+ coverage (protocolo RED/GREEN/REFACTOR). Se deberan hacer todos los test unitarios, integrados y E2E, asi como tambien todos los text y evaluaciones (usando evals de agno también) para verficar el codigo generado en cad auno de los pasos y elementos que contituyen yaml-agno.
- **Feature-Branch-Chain**: Git workflow con commits granulares para maxima trazabilidad y rollback posible (work-unit commits).
- **Code Review (Multi-LLM)**: Para el desarrollo utilizaremos la metodologia integrada de subagentes delegados de SDD y TDD que trae gentle-ai. Para cada uno de los pasos, mejora o modificacion SIEMPRE se realizara una el flujo de agentes completos desde SDD-init (para iniciar el proyecto) hasta el SD-archive para archivar. IMPOSIBLE SALTEARSE UN PASO, ASI COMO TAMPOCO SE PUEDE REALIZAR SIN DELEGACION EN SUBAGENTES.
- **PR Budget (tejado flexible)**: PR ≤ **600 líneas por defecto**, con **excepciones justificadas** para features que lo requieran. La granularidad de rollback es la **feature atómica**, no el micro-paso. Fundamento: trabajamos con agentes de programación (Claude Code/OpenCode) que manejan contextos grandes;  Requiere disciplina: cada PR cubre una funcionalidad completa y verificable

### 6.2 Constraints de Diseño

- **No reimplementar Agno**: Build ON TOP (máxima reutilización de lo que Agno provee)
- **No AgentOS internals**: lifespan, session, run loop
- **No env vars directos**: Deployment-level
- **YAML válido**: Schema validation estricta
- **No duplicar dependencias de Agno**: yaml-agno **hereda** FastAPI/SQLAlchemy/Pydantic de Agno (no las re-pinnea con versiones que puedan chocar)

### 6.3 Constraints de Deployment

- **Multi-tenant**: Tenant isolation obligatorio (definido en Core Infra, consumido por yaml-agno)
- **Hot-reload**: Config changes sin restart
- **Máxima trazabilidad, granularidad y rollback**: toda iteración de corrección parte de un **commit baseline** previo, de modo que cualquier cambio (del usuario o detectado por el sistema) sea reversible. Estructura de versionado completa (tags/branches) para volver atrás en cualquier punto
- **Rollback**: capacidad de rollback rápido por feature atómica

---

## 7. TECHNICAL ASSUMPTIONS ADOPTED

### 7.1 Assumptions de Stack

- **Python 3.12+**: Versión mínima (Agno `requires-python >=3.7,<4`, usamos 3.12+ para type hints modernos PEP 695)
- **Agno 2.6.14 (pinneado)**: versión verificada en `agno/libs/agno/pyproject.toml`. Debe ser **estable y sin vulnerabilidades conocidas**. Antes de cada bump de versión de Agno, verificar changelog + CVE
- **PostgreSQL 16+**: versión soportada nativamente por Agno (PostgresDb) y **sin vulnerabilidades conocidas**. Es la base de sessions, memory, tracing y PgVector
- **Pydantic V2**: dependencia nativa de Agno; yaml-agno la hereda (no la re-pinnea)
- **SQLAlchemy 2.0**: dependencia **nativa de Agno** (usa `sqlalchemy.ext.asyncio` / `create_async_engine`). yaml-agno **NO la re-pinnea con una versión exacta**: declara rango `>=2.0,<3` y deja que Agno resuelva, para **evitar choque de versiones** con el SQLAlchemy que Agno ya integra
- **FastAPI**: dependencia nativa de Agno vía AgentOS (`fastapi[standard]`). yaml-agno **la hereda de Agno** y **delega el serving HTTP a `AgentOS.get_app()`**. No re-pinnea ni reimplementa: máxima reutilización de lo que Agno provee

### 7.2 Assumptions de Agno

- **Agno estable**: API no cambia entre minor versions (pinned 2.6.14)
- **Agent.run() y Agent.arun()**: **ambos soportados**. `run()` síncrono, `arun()` asíncrono (default producción: concurrency, streaming SSE, background). Emiten los mismos eventos. La elección es del caller de runtime, no del spec YAML
- **Teams supports 4 modes**: coordinate, route, broadcast, tasks (verified in `agno/team/mode.py`; no `coroutine` mode exists in Agno)
- **Workflows support 6 primitives**: Step, Steps, Parallel, Condition, Router, Loop
- **Multi-tenant nativo**: Agno **NO** tiene `tenant_id` first-class ni RLS nativo. La isolation es por `user_id` + `session_id`. El sistema multi-tenant (TenantResolver, RLS, RBAC por tenant) se define en **Core Infra** (reutilizable por todos los programas CENF) y yaml-agno lo consume: `tenant_id` se modela como claim JWT / metadata y se propaga vía `header_provider`

### 7.3 Assumptions de Deployment (dual strategy)

**Estrategia primaria (ahora): Google Cloud Run**
- Los agentes se ejecutan **serverless**: prenden, hacen su trabajo, persisten en DB / storage (local o cloud) y se apagan
- Ideal para cargas event-driven de yaml-agno
- Sin gestión de servidores ni orquestación manual

**Estrategia futura (cuando dominemos K8s): Kubernetes self-managed**
- Montar y correr en servidores locales o cloud mediante Kubernetes que levante infraestructura directamente
- Para cargas de alta concurrencia o estado persistente de larga duración
- Especificado en SPEC_21 (Helm/Kustomize manifests listos para cuando se adopte)

**Común a ambas estrategias**:
- **Docker**: para containers (SPEC_20)
- **GitOps**: para deployments declarativos
- **Managed DB** (Cloud SQL / equivalent) preferido sobre PVC local

---

## 8. ROADMAP (12 SEMANAS - MVPS SEMANALES)

> **Nota**: La columna "Sistema yaml-agno probado" indica **qué parte del sistema** se valida cada semana, **no** un caso de negocio particular. Los equipos agénticos concretos (Facturación, Excel, Email, Meetings, o productos para clientes) se eligen al inicio de cada semana según prioridad de negocio. La prioridad real de qué equipos se construyen primero **no está definida**: se decide cuando el sistema funcione.

| Semana | MVP | Sistema yaml-agno probado | Validación del sistema |
|--------|-----|---------------------------|------------------------|
| **1** | yaml-agno Core | Agent config + Templates (jerarquía heredable) + DI System | Crear 1 agent desde YAML sin código Python |
| **2** | Teams + Workflow primitives | Team config (4 modos (coordinate/route/broadcast/tasks)) + Workflow (6 primitivas) | 1 team se orquesta desde YAML |
| **3** | Prompting + Context Engineering | cognitive_profile + deployment.mode + context flags + dependencies | 1 team con contexto inyectado dinámicamente |
| **4** | Tools + Knowledge + MCP | Toolkits + Knowledge (vector DB + embedders) + MCP (3 transports) | 1 team usa tools + RAG + MCP server |
| **5** | Models + Resilience + Multimodal | Model-as-string + fallback + cache + multimodal I/O | 1 team con fallback de modelos y entrada multimodal |
| **6** | Guardrails + Hooks + PII | Guardrails (PII configurable) + hooks + secret masking | 1 team con guardrails y políticas de seguridad |
| **7** | HITL + Scheduler + Background | HITL flags + approvals + scheduler (cron) + background execution | 1 workflow con HITL y job programado |
| **8** | Templates jerarquía + Meta-agentes | Template inheritance + CodeGraph + Docs Expert | 1 template hereda de otro + agente asiste creación |
| **9** | Multi-tenant + Hot-reload | Core Infra TenantResolver + RLS + RBAC + ConfigDB + hot-reload | 2 tenants aislados con mismo codebase |
| **10** | Observability + Evals | OpenTelemetry + tracing + evals (4 dimensiones) + providers | 1 team con trazabilidad completa + eval suite |
| **11** | AgentOS + Deployment | AgentOS control plane + interfaces + Cloud Run deploy | 1 AgentOS desplegado y accesible |
| **12** | Release 1.0 | pip installable + tests 100%+ + docs + examples | 2 equipos CENF/clientes en producción |

---

## 9. CORE INFRA MANAGER INTEGRATION

### 9.1 Naturaleza de Core Infra

**Core Infra** (`MASTER_OpenSpec_Core_Infra_SOTA_2026.md`) es un conjunto de **managers horizontales transversales** (ConfigManager, SecretManager, LoggerManager, ObservabilityManager, DatabaseManager, ErrorHandlingManager, CacheManager, FileStorageManager, TaskQueueManager, etc.) que se va a convertir en **código abstracto, heredable y reutilizable en Python y TypeScript** para **todos los desarrollos de CENF**.

**Objetivo**: estructurar toda la parte transversal de nuestros programas de forma estandarizada, de modo que **cualquier agente que conozca Core pueda auditar nuestros programas de manera estandarizada**.

**Estado actual**: hoy Core es especificación, no código. **Aún no se convirtió en código**. Será esta especificación + un agente de programación quienes lo creen siguiendo esos lineamientos.

**Integración con yaml-agno**: una vez que existan tanto yaml-agno como Core como código, **el agente de programación debe programar usando ambos de manera totalmente integrada**. Ambos mejorarán con el tiempo pero **siempre estarán integrados entre sí**.

### 9.2 Implicancia para los SPECs de yaml-agno

**IMPORTANTE**: dado que Core aún no existe como código, los SPECs de yaml-agno **NO deben codificar definiciones concretas** de los managers (clases, firmas exactas, implementaciones). Deben:

- **Referenciar el Port (Protocol) abstracto** de cada manager como interfaz consumida
- **Declarar la dependencia** (inyectada vía constructor / DI)
- **NO fijar la implementación** (eso lo define Core cuando se codee)
- **Alinear la firma del Port** con lo especificado en `MASTER_OpenSpec_Core_Infra_SOTA_2026.md`

Las definiciones de código Python que aparecen en los SPECs (ej: ConfigManager Protocol abajo) son **contratos de interfaz (Ports) referenciales**, no implementaciones. Si Core evoluciona su interfaz, los SPECs se ajustan.

### 9.3 ConfigManager Integration

**Responsabilidad**: Fuente única de verdad para configuración inmutable de entorno.

**Port (Protocol) referencial** (alineado a Core Infra; la implementación la provee Core):
```python
from __future__ import annotations
from typing import Protocol, Literal

Env = Literal['local', 'dev', 'staging', 'prod']

class ConfigManager(Protocol):
    """@ai-directive: No accedas a os.environ directamente; siempre usa ConfigManager."""
    def get_env(self) -> Env: ...
    def get_string(self, key: str, default_value: str | None = None) -> str: ...
    def get_number(self, key: str, default_value: float | None = None) -> float: ...
    def get_boolean(self, key: str, default_value: bool | None = None) -> bool: ...
    def get_json[T](self, key: str, default_value: T | None = None) -> T: ...
    def get_section[T: dict](self, namespace: str) -> T: ...
    async def reload(self) -> None: ...
```

**Patrón de consumo en yaml-agno** (esquemético; la factory inyecta ConfigManager por DI):
```python
# yaml-agno consume ConfigManager (lo provee Core via DI); no lo implementa
class AgentFactory:
    def __init__(self, config_manager: ConfigManager, secret_manager: SecretManager):
        self.config = config_manager
        self.secrets = secret_manager

    async def create_agent(self, yaml_path: str) -> Agent:
        env = self.config.get_env()                      # local|dev|staging|prod
        tenant_id = self.config.get_string("tenant_id")  # de Core TenantResolver
        # ... resolver YAML + DI variables
        return Agent(**resolved)
```

**Do's & Don'ts**:
- ✅ Resolver precedencia: Env vars > Remoto (ConfigDB) > Ficheros > Defaults
- ✅ Validar con Pydantic V2 en bootstrap
- ❌ NO leer secretos (usar SecretManager)
- ❌ NO escribir configuración (read-only)
- ❌ NO implementar ConfigManager en yaml-agno (lo provee Core)

### 9.4 SecretManager Integration (dual: local .env + cloud SM)

**Responsabilidad**: Gestión Zero-Trust de credenciales. **Nunca** se persisten secretos en código ni en variables de entorno en producción.

**Modo dual (definido en Core)**:
- **Local / desarrollo**: archivos `.env` cargados con **mejores prácticas SOTA** por un elemento del Core (dotenv seguro). Solo para desarrollo.
- **Producción / despliegue**: sistemas de SecretManager del servidor/proveedor (ej: Google Secret Manager para Cloud Run). **Cada infraestructura tiene el suyo** (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault, Azure Key Vault).

**Port (Protocol) referencial** (la implementación y los adapters los provee Core):
```python
class SecretManager(Protocol):
    """@ai-directive: Nunca leas secretos de env vars en producción; usa SecretManager."""
    async def get_secret(self, key: str) -> str: ...
    async def get_secret_json(self, key: str) -> dict: ...
```

yaml-agno consume `SecretManager` por DI y propaga los secretos a los adapters de Agno (model API keys, DB credentials, MCP tokens) **sin exponerlos nunca** en logs, YAML ni respuestas.

---

## 10. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] YAML-First como Arquitectura Core

**Justificación**: YAML es humano-legible, versionable, y permite templates con frontmatter. Users no necesitan Python.

### [Decisión 2] DI System con múltiples formatos estructurados

**Justificación**: los providers de DI soportan **múltiples formatos estructurados**: `.md`, `.json`, `.yaml`, `.toml`. La idea es que estos formatos son **parseables** y podemos convertirlos entre sí para entregarle la info al usuario o al agente de diferentes maneras. Por ejemplo: si un agente o equipo da su resultado en YAML, podemos **parsearlo a HTML** para que un usuario lo lea de forma más cómoda posteriormente.

Los 4 providers siguen siendo: Database (queries), Env (variables), API (REST), File (JSON/YAML/TOML/MD) — cubren 99% de casos reales.

### [Decisión 3] Templates Auto-Prompted con jerarquía heredable

**Justificación**: el frente clave **no es la cantidad** de templates (50+ es más que suficiente) sino la **arquitectura reutilizable escalable y ampliable**. Los templates deben soportar **jerarquía heredable**: un template puede convertirse en parte de otro (como código orientado a objetos), como **partes ya configuradas y extensibles**. Frontmatter permite programación agent para descubrir y usar templates automáticamente.

### [Decisión 4] MVPs semanales viables

**Justificación**: los MVPs semanales son viables e incluso pueden ser de **menos días** dado que trabajamos con **agentes de programación** que aceleran la generación de código.

### [Decisión 5] Multi-tenant definido en Core Infra

**Justificación**: Agno **NO** tiene `tenant_id` nativo (solo `user_id` + `session_id`) ni RLS nativo (verificado en docs Agno 2.6.14). El sistema multi-tenant (TenantResolver, RLS, RBAC por tenant) se define en **Core Infra** para ser **reutilizable por todos los programas CENF**, y yaml-agno lo consume: `tenant_id` se modela como claim JWT / metadata y se propaga vía `header_provider` de Agno. `user_id` + `session_id` siguen siendo los keys first-class de isolation a nivel Agno.

---

## 11. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Arquitectura de templates heredables

**¿Qué profundidad de herencia soportamos en la jerarquía de templates?**

Implica:
- **Herencia simple (1 nivel)**: template extiende de un padre. Simple, predecible.
- **Herencia múltiple / mixins**: composición de múltiples templates. Poderoso pero complejo (problema del diamante).
- **Trade-off**: flexibilidad de composición vs complejidad de resolución.

### [Pregunta 2] Conversión de formatos en DI

**¿Qué conversiones priorizamos en el parser bidireccional (YAML↔JSON↔TOML↔MD↔HTML)?**

Implica:
- **Mínimo (YAML↔JSON)**: cubre intercambio técnico.
- **Completo (incluye HTML render para usuarios)**: mejor UX pero más trabajo de renderizado.
- **Trade-off**: alcance del parser vs valor de presentación al usuario.

### [Pregunta 3] Estrategia de providers en Multi-LLM review

**¿Usamos providers reales distintos (Anthropic + Google + OpenAI) o un único provider con prompts distintos?**

Implica:
- **Providers distintos**: máxima diversidad, detecta lo que un modelo no ve. Costo 3x.
- **Mismo provider, prompts distintos**: más barato, menos diversidad real.
- **Trade-off**: cobertura de revisión vs costo.