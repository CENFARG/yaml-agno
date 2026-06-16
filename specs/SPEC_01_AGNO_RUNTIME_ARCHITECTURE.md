---
Spec_ID: "SPEC_01"
Title: "Agno Runtime Architecture"
Version: "0.2.0-iter1"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#Agno", "#Runtime", "#SessionManagement", "#WorkflowPrimitives"]
Dependency_Hashes: ["SPEC_00"]
Last_Updated: "2026-06-16"
Revision_Note: "Iteración 1 - correcciones de revisión del usuario (coroutine, Engram, dynamic loading, factories como esquemas); sub-iteración: DependencyManager split Core/yaml-agno, retention aclarado, escalabilidad y cache decididos"
---

# SPEC_01_AGNO_RUNTIME_ARCHITECTURE

> **Propósito**: Definir la infraestructura de agentes y orquestación en runtime para yaml-agno, incluyendo configuración del ciclo de vida (soporte dual `run()`/`arun()`), contratos de equipos especializados, gobernanza de estado y disparadores de workflows cognitivos.

> **@ai-directive**: El código Python de este SPEC es **pseudo-código esquemático** que ilustra el PATRÓN de factory (YAML → Agno Objects), NO la implementación completa. El `AgentFactory`/`TeamFactory`/`WorkflowFactory` mapean los **80+ parámetros** del constructor de Agno, delegando la construcción detallada de cada sub-sistema a su SPEC dedicado: tools → SPEC_11, knowledge → SPEC_10, memory → SPEC_04, session/storage → SPEC_03 + SPEC_13, models → SPEC_14, guardrails/HITL → SPEC_16. Este SPEC es **una sola fuente de verdad para el runtime core** y NO duplica el contenido de los SPECs dedicados.

---

## 1. RUNTIME CORE CONFIGURATION

### 1.1 Ciclo de Vida de Ejecución de Agentes

El runtime de yaml-agno se construye SOBRE Agno Framework, no reimplementa sus internos. La configuración YAML se traduce a objetos Agno mediante el patrón Factory.

#### Componentes del Runtime

```mermaid
graph TD
    [YAML Config] --> |Pydantic Validation| [yaml-agno Factory]
    [yaml-agno Factory] --> |Agent:run:| [Agno Agent Instance]
    [Agno Agent Instance] --> |Session Management| [Agent Session]
    [Agent Session] --> |Tool Execution| [FunctionToolkit]
    [Agent Session] --> |Knowledge Retrieval| [Knowledge Base]
    [Agent Session] --> |Memory Operations| [User Memory]
    [Agent Session] --> |Response Generation| [Structured Output]
```

#### Contrato de Factory: YAML → Agno Objects

**Responsabilidad**: Traducir YAML validado a instancias de Agno Framework sin modificar el framework core.

**@ai-directive**: El siguiente `AgentFactory` es **pseudo-código esquemático**. Muestra el patrón de delegación. El `AgentConfig` **contiene los 80+ parámetros** del constructor `Agent()` de Agno; aquí solo se ilustran los fields core y la delegación a factories de sub-sistemas. La lista completa de parámetros y su mapeo YAML↔Agno vive en este SPEC (sección 1.2) y en los SPECs dedicados (tools/knowledge/memory/model/guardrails). **No cargar todos los imports de Agno al tope del módulo**: usar carga perezosa vía `DependencyManager` (ver sección 1.3).

```python
# yaml-agno/src/factories/agent_factory.py
# SCHEMATIC: illustrates the factory + delegation pattern, not the full 80+ param impl.

from typing import Any
from pydantic import BaseModel, Field
from yaml_agno.di import DependencyManager   # dynamic, lazy, allowlisted loading

class AgentConfig(BaseModel):
    """
    Configuration for an Agno Agent, loaded from YAML.
    @ai-directive: This model holds the 80+ constructor parameters of agno.Agent.
    Only core fields shown here; advanced fields (tools, knowledge, memory, session,
    model, guardrails, hitl, multimodal) are nested configs delegated to their specs.
    """
    # --- core identity ---
    name: str = Field(..., description="Unique agent name")
    model: str = Field(..., description="Model string 'provider:id' (see SPEC_14)")
    instructions: str | None = Field(None, description="System prompt")
    description: str | None = Field(None, description="Agent description")
    role: str | None = Field(None, description="Agent role (used in teams)")

    # --- delegated sub-systems (each is a nested config built by its own factory) ---
    tools: list[dict[str, Any]] = Field(default_factory=list, description="See SPEC_11")
    knowledge: dict[str, Any] | None = Field(None, description="See SPEC_10")
    memory: dict[str, Any] | None = Field(None, description="See SPEC_04")
    learning: dict[str, Any] | None = Field(None, description="LearningMachine config (see SPEC_04)")
    session: dict[str, Any] | None = Field(None, description="See SPEC_03 + SPEC_13")
    guardrails: dict[str, Any] | None = Field(None, description="See SPEC_16")
    hitl: dict[str, Any] | None = Field(None, description="See SPEC_16")
    multimodal: dict[str, Any] | None = Field(None, description="See SPEC_17")
    context: dict[str, Any] | None = Field(None, description="add_*_to_context flags (see SPEC_15)")

    # --- runtime behavior (subset; full list in section 1.2) ---
    markdown: bool = True
    add_history_to_context: bool = False
    num_history_runs: int | None = Field(None, description="Mutually exclusive with num_history_messages")
    num_history_messages: int | None = None
    # ... remaining 80+ params mapped in section 1.2 table ...


class AgentFactory:
    """Factory: validated YAML (AgentConfig) -> agno.Agent instance."""

    def __init__(self, deps: DependencyManager):
        self.deps = deps   # resolves providers/tools/dbs lazily + allowlisted

    async def create(self, config: AgentConfig) -> "Agent":
        """
        Build an agno.Agent from validated config.

        @ai-directive: delegates each sub-system to its factory; only the provider
        referenced in YAML is imported (lazy), not all 30+ providers.
        """
        # lazy model resolution via DependencyManager (registry + importlib + allowlist)
        model = await self.deps.resolve_model(config.model)          # SPEC_14

        # delegated sub-system factories (lazy-resolved, allowlisted)
        tools = await self.deps.build_tools(config.tools)            # SPEC_11
        knowledge = await self.deps.build_knowledge(config.knowledge)# SPEC_10
        memory = await self.deps.build_memory(config.memory)         # SPEC_04
        learning = await self.deps.build_learning(config.learning)   # SPEC_04
        db = await self.deps.build_db(config.session)                # SPEC_03
        guardrails = await self.deps.build_guardrails(config.guardrails)  # SPEC_16

        # The Agent class itself is resolved lazily via DependencyManager too.
        Agent = self.deps.resolve_class("agno.agent", "Agent")

        agent = Agent(
            name=config.name,
            model=model,
            instructions=config.instructions,
            tools=tools,
            knowledge=knowledge,
            memory_manager=memory,
            learning=learning,
            db=db,
            pre_hooks=guardrails,  # guardrails mount as pre_hooks in Agno v2.1.0+
            markdown=config.markdown,
            add_history_to_context=config.add_history_to_context,
            num_history_runs=config.num_history_runs,
            # ... remaining params spread from config ...
        )
        return agent
```

#### 1.2 Mapeo completo de parámetros (80+)

La tabla siguiente mapea los grupos de parámetros del constructor `Agent()` de Agno a su ubicación de especificación. **Cada grupo tiene su SPEC dedicado** que define el YAML schema exacto; este SPEC define únicamente cómo el factory los ensambla.

| Grupo de parámetros | Ejemplos de params Agno | Especificación | Nivel abstracción |
|---------------------|-------------------------|----------------|-------------------|
| Identity | `name`, `model`, `instructions`, `description`, `role`, `agent_id` | SPEC_01 | ABSTRAER (core) |
| Model / resilience | `model` (string/provider), `fallback_models`, `retries`, cache | SPEC_14 | ABSTRAER |
| Tools / MCP | `tools`, `tool_call_limit`, toolkits, MCPTools | SPEC_11 | ABSTRAER |
| Knowledge / RAG | `knowledge`, `knowledge_filters`, `search_knowledge` | SPEC_10 | ABSTRAER |
| Memory | `memory_manager`, `enable_agentic_memory`, `update_memory_on_run`, `add_memories_to_context` | SPEC_04 | ABSTRAER flags / REFERENCIAR manager |
| Learning | `learning` (LearningMachine: 6 stores) | SPEC_04 | REFERENCIAR |
| Session/storage | `db`, `session_id`, `user_id`, `session_state` | SPEC_03 + SPEC_13 | ABSTRAER |
| History | `add_history_to_context`, `num_history_runs`, `num_history_messages`, `max_tool_calls_from_history` | SPEC_01 (§1.4) | ABSTRAER |
| Context engineering | `add_datetime_to_context`, `add_dependencies_to_context`, `dependencies`, `additional_context`, `compress_tool_results` | SPEC_15 | ABSTRAER |
| Guardrails / hooks | `pre_hooks`, `post_hooks`, guardrails | SPEC_16 | ABSTRAER guardrails / REFERENCIAR hooks |
| HITL | `requires_confirmation`, `requires_user_input` (step-level) | SPEC_16 | ABSTRAER flags |
| Multimodal | `images`, `audio`, `videos`, `files`, `send_media_to_model` | SPEC_17 | REFERENCIAR |
| Reasoning | `reasoning`, `reasoning_model`, `reasoning_effort` | SPEC_14 | ABSTRAER |
| Reasoning / debug | `debug_mode`, `debug_level`, `show_tool_calls`, `telemetry`, `markdown` | SPEC_01 (§1.2.1) | ABSTRAER |

##### 1.2.1 Parámetros de runtime/debug (residentes en este SPEC)

| Parámetro YAML | Agno equivalent | Default | Descripción |
|----------------|-----------------|---------|-------------|
| `markdown` | `Agent.markdown` | `true` | Render markdown en la respuesta |
| `debug_mode` | `Agent.debug_mode` / run kwarg | `false` | Logs de ejecución detallados |
| `debug_level` | `Agent.debug_level` | `1` | Nivel de detalle (1-2) |
| `show_tool_calls` | `Agent.show_tool_calls` | `false` | Mostrar tool calls en output |
| `telemetry` | `Agent.telemetry` | `true` | Telemetría anónima (ver SPEC_09) |

#### Loop de Eventos y Sesión

Agno maneja el loop de eventos internamente. yaml-agno expone configuración de parámetros:

```yaml
agent:
  name: "facturacion"
  model: openai/gpt-4o
  instructions: "Process invoices..."
  
  session:
    user_id: "${user_db.id}"
    session_name: "facturacion_${user_db.id}"
    storage_type: postgres  # any Agno DB: sqlite|postgres|memory|redis|mongo|... (see §1.3)
    
  execution:
    max_iterations: 10
    stream: false
    show_tool_calls: true
    debug_mode: false
```

**Parámetros de Session expuestos** (mapeados a Agno `Agent.run()` / `Agent.arun()`):

La tabla lista los parámetros de sesión que efectivamente existen en la API de Agno v2.6.14 (verificados en `agno/agent/agent.py:1336-1361`). **No se inventan parámetros.**

| Parámetro YAML | Agno equivalent | Tipo | Validación |
|----------------|-----------------|------|------------|
| `user_id` | `run(user_id=...)` / Agent attr | `str` | Identifica al usuario (scope de memoria/sesión) |
| `session_id` | `run(session_id=...)` | `str \| None` | Continúa sesión existente (autogenerada si None) |
| `session_state` | `run(session_state=...)` / Agent attr | `dict` | Estado persistente entre turns |
| `storage_type` | `db=` (SqliteDb/PostgresDb/RedisDb/...) | `str` | Resuelto vía DependencyManager (§1.3) |
| `add_history_to_context` | `run(add_history_to_context=...)` | `bool` | Inyecta historial en contexto |
| `add_session_state_to_context` | `run(add_session_state_to_context=...)` | `bool` | Inyecta session_state en contexto |
| `max_iterations` | `run(max_iterations=...)` (límite de loop) | `int` | Integer >= 1 |

> **@ai-directive (punto 7 del usuario - retención/purge de datos)**: ¿qué significa "retención"? Es **cuánto tiempo se guardan los datos antes de borrarlos automáticamente** (ej: "borrar el historial de sesiones de más de 30 días"). Agno **NO** trae un parámetro `retention_days` que haga eso solo. Lo que Agno sí ofrece para limpiar datos viejos:
> - **Curator** (parte de `LearningMachine`): un método `prune(max_age_days=90)` que vos llamás cuando queras borrar memorias con más de N días. No es automático: **vos decidís cuándo llamarlo**.
> - **RedisDb(expire=N)**: si usás Redis como DB, podés setear un TTL en segundos y Redis borra las claves solas al expirar.
>
> Por lo tanto, yaml-agno **no expone un `retention_days` mágico** como si fuera nativo de Agno (porque no lo es). Si queremos retención automática en yaml-agno, la construimos nosotros como **extensión propia**: un **job programado** (cron, en SPEC_13) que corre periódicamente y llama a `Curator.prune(max_age_days=...)`, o configurar `RedisDb(expire=...)` cuando el backend sea Redis. Ese comportamiento se documenta como feature de yaml-agno, no como mapeo directo a un parámetro de Agno que no existe.

### 1.3 DependencyManager (carga dinámica segura de providers/DBs/primitives)

**@ai-directive (puntos 1, 2, 8, 11 del usuario)**: yaml-agno **NO** carga todos los providers de Agno (modelos, DBs, primitivas de workflow) al importar el módulo. Eso gastaría memoria innecesariamente. En su lugar, un **`DependencyManager`** resuelve cada dependencia de forma **perezosa, validada y con cache**.

**División de responsabilidades (decisión P1 del usuario)**: `DependencyManager` se separa en dos partes, siguiendo el principio de que todo lo transversal y reutilizable vive en **Core Infra**:

| Parte | Dónde vive | Qué contiene |
|-------|-----------|--------------|
| **Mecanismo** | **Core Infra** (`core.di.DependencyManager`) | `resolve_class(module, class)` via `importlib`, allowlist, `lru_cache`, `entry_points`. Reutilizable por TODOS los programas CENF, no solo yaml-agno |
| **Registries de Agno** | **yaml-agno** (`yaml_agno.registries`) | `MODEL_REGISTRY`, `STORAGE_REGISTRY`, `WORKFLOW_PRIMITIVE_REGISTRY`: las keys específicas de Agno (qué providers/DBs/primitivas existen) |

yaml-agno **consume** el `DependencyManager` de Core (vía DI) y le **inyecta** sus propios registries de Agno. Si mañana Core mejora el mecanismo, yaml-agno lo hereda sin tocar sus registries.

**Patrón (mecanismo, en Core)**: registry declarativo (dict validado) + `importlib.import_module` perezoso + **allowlist** de módulos (nunca input directo del usuario, mitiga path traversal) + cache de instancias + **entry_points** (`importlib.metadata.entry_points`) para extensión de terceros. Inspirado en el `ReaderFactory` de Agno (que sí usa importlib) y mejorado con allowlist + entry_points.

```python
# --- Core Infra: the reusable MECHANISM (transversal to all CENF programs) ---
# core/di/dependency_manager.py
# SCHEMATIC: the mechanism lives in Core; registries are injected by each program.

import importlib
from functools import lru_cache
from importlib.metadata import entry_points

class DependencyManager:
    """
    Generic dependency resolver: lazy, allowlisted, cached, extensible.
    @ai-directive: mechanism only. Program-specific registries (which providers/DBs
    exist) are injected at construction. Lives in Core Infra so ALL CENF programs
    can reuse it and any agent can audit them uniformly.
    """

    def __init__(self, registries: dict[str, dict], entry_point_groups: list[str]):
        # registries: {"models": {...}, "storage": {...}, ...} injected by the program
        self._registries = registries
        self._ep_groups = entry_point_groups
        self._merge_entry_points()

    def _merge_entry_points(self) -> None:
        """Allow 3rd-party packages to register new providers/DBs safely."""
        for group in self._ep_groups:
            for ep in entry_points(group=group):
                self._registries.setdefault(group, {})[ep.name] = ep.value

    @lru_cache(maxsize=128)
    def resolve_class(self, module_path: str, class_name: str):
        """
        Import module_path and return class_name. Cached.
        @ai-directive: module_path must come from an allowlisted registry;
        NEVER from direct user input (mitigates path traversal).
        """
        module = importlib.import_module(module_path)   # raises ImportError if missing
        return getattr(module, class_name)


# --- yaml-agno: the Agno-specific REGISTRIES (injected into Core DependencyManager) ---
# yaml_agno/registries.py
# SCHEMATIC: these keys map YAML values to Agno classes. Only Agno knowledge here.

MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    "openai":      ("agno.models.openai", "OpenAIChat"),
    "anthropic":   ("agno.models.anthropic", "Claude"),
    "google":      ("agno.models.google", "Gemini"),
    "ollama":      ("agno.models.ollama", "Ollama"),
    "openrouter":  ("agno.models.openrouter", "OpenRouter"),
    # ... remaining Agno providers; extensible via entry_points(group="yaml_agno.models") ...
}

STORAGE_REGISTRY: dict[str, tuple[str, str]] = {
    "sqlite":  ("agno.db.sqlite", "SqliteDb"),
    "postgres":("agno.db.postgres", "PostgresDb"),
    "redis":   ("agno.db.redis", "RedisDb"),
    "memory":  ("agno.db.memory", "InMemoryDb"),
    # ... extensible via entry_points(group="yaml_agno.storage") ...
}

WORKFLOW_PRIMITIVE_REGISTRY: dict[str, tuple[str, str]] = {
    "step":      ("agno.workflow", "Step"),
    "parallel":  ("agno.workflow", "Parallel"),
    "condition": ("agno.workflow", "Condition"),
    "router":    ("agno.workflow", "Router"),
    "loop":      ("agno.workflow", "Loop"),
}


# --- yaml-agno: AgnoProviderResolver uses Core's DependencyManager ---
# yaml_agno/di/resolver.py
# SCHEMATIC: thin wrapper that resolves Agno classes via Core DependencyManager.

class AgnoProviderResolver:
    """Resolves Agno providers/DBs/primitives using Core's DependencyManager."""

    def __init__(self, deps: "DependencyManager"):   # injected Core DependencyManager
        self.deps = deps

    async def resolve_model(self, model_str: str):
        """'openai/gpt-4o' -> OpenAIChat(id='gpt-4o'). Only openai module imported."""
        provider, _, model_id = model_str.partition("/")
        from yaml_agno.registries import MODEL_REGISTRY
        if provider not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model provider: {provider}")
        module_path, class_name = MODEL_REGISTRY[provider]
        ModelCls = self.deps.resolve_class(module_path, class_name)
        return ModelCls(id=model_id)

    async def build_db(self, storage_type: str, connection_string: str | None):
        """storage_type -> Agno DB instance. Only that DB module imported."""
        from yaml_agno.registries import STORAGE_REGISTRY
        if storage_type not in STORAGE_REGISTRY:
            raise ValueError(f"Unknown storage_type: {storage_type}")
        module_path, class_name = STORAGE_REGISTRY[storage_type]
        DbCls = self.deps.resolve_class(module_path, class_name)
        return DbCls(connection_string) if connection_string else DbCls()

    async def resolve_workflow_primitive(self, step_type: str):
        """step_type -> Agno workflow primitive class."""
        from yaml_agno.registries import WORKFLOW_PRIMITIVE_REGISTRY
        if step_type not in WORKFLOW_PRIMITIVE_REGISTRY:
            raise ValueError(f"Unsupported step type: {step_type}")
        module_path, class_name = WORKFLOW_PRIMITIVE_REGISTRY[step_type]
        return self.deps.resolve_class(module_path, class_name)
```

**Do's & Don'ts**:
- ✅ **Mecanismo en Core, registries en yaml-agno**: el `DependencyManager` (mecanismo) vive en Core y lo reutilizan todos los programas CENF; los registries de Agno (keys → clases) viven en yaml-agno
- ✅ Registry declarativo + allowlist: el YAML referencia **keys**, nunca paths de módulo
- ✅ Import perezoso: solo se importa el provider/DB/primitiva referenciado
- ✅ Cache (`lru_cache`): instancias de clase reusadas
- ✅ `entry_points`: extensión segura de terceros (plugins instalados via pip)
- ❌ NUNCA `importlib.import_module` con input directo del usuario (path traversal)
- ❌ NUNCA importar todos los providers al inicio del módulo
- ❌ NUNCA poner lógica de Agno en el `DependencyManager` de Core (Core es agnóstico al framework)

---

## 2. SPECIALIZED TEAMS CONTRACTS

### 2.1 Contrato de Team Configuration

Los Teams en yaml-agno se mapean a `agno.team.Team` con todos sus modos y configuraciones.

#### Modos de Team Soportados

`TeamMode` en Agno v2.6.14 define **4 modos** (verificado en `agno/team/mode.py:6-23`). **No existe `coroutine`** (era un error de versiones previas de este SPEC).

| Modo YAML | Agno `TeamMode` | Descripción |
|-----------|-----------------|-------------|
| `coordinate` | `TeamMode.coordinate` | Supervisor coordina miembros (default) |
| `route` | `TeamMode.route` | Router dirige al miembro adecuado (equivale al flag legacy `respond_directly`) |
| `broadcast` | `TeamMode.broadcast` | Broadcast a todos los miembros (equivale al flag legacy `delegate_to_all_members`) |
| `tasks` | `TeamMode.tasks` | Ejecución autónoma basada en tareas |

#### Team YAML Schema

```yaml
team:
  name: "facturacion_workflow"
  mode: coordinate  # coordinate|route|broadcast|tasks (4 modes, no 'coroutine')
  instructions: |
    You orchestrate invoice processing across specialized agents.
  
  members:
    - member: validator
      agent: validator_agent
      role: "Validate invoice structure and data"
    
    - member: processor
      agent: processor_agent
      role: "Process validated invoices"
    
    - member: notifier
      agent: notification_agent
      role: "Send notifications"
  
  workflows:
    - workflow: invoice_processing
      description: "Main invoice processing pipeline"
      # Ver sección 4 para primitivas de workflow
```

#### TeamFactory Implementation

```python
# yaml-agno/src/factories/team_factory.py
# SCHEMATIC: illustrates the factory + delegation pattern. TeamConfig holds the 25+
# Team() constructor params; only core fields shown. Advanced members (callable
# factories), caching keys, orchestration flags -> delegated to SPEC_05.

from typing import Any
from pydantic import BaseModel, Field
from yaml_agno.di import DependencyManager

class TeamConfig(BaseModel):
    """Configuration for an Agno Team from YAML."""
    name: str
    mode: str = "coordinate"  # coordinate|route|broadcast|tasks (4 modes, no coroutine)
    instructions: str | None = None
    members: list[dict[str, Any]] = Field(default_factory=list, description="Members or callable factory ref")
    workflows: list[dict[str, Any]] = Field(default_factory=list)
    # ... remaining Team() params (callable_members_cache_key, share_member_interactions,
    #     determine_input_for_members, stream_member_events, etc.) -> SPEC_05 ...

class TeamFactory:
    """Factory: validated YAML (TeamConfig) -> agno.Team instance."""

    def __init__(self, deps: DependencyManager):
        self.deps = deps

    async def create(self, config: TeamConfig, agents: dict[str, "Agent"]) -> "Team":
        """
        Build an agno.Team from validated config.
        @ai-directive: validates mode against the 4 real TeamMode values.
        """
        Team, TeamMode = self.deps.resolve_team_symbols()  # lazy import

        if config.mode not in {"coordinate", "route", "broadcast", "tasks"}:
            raise ValueError(
                f"Invalid team mode: {config.mode}. "
                f"Valid: coordinate|route|broadcast|tasks (no 'coroutine')."
            )

        members = []
        for member_config in config.members:
            agent_name = member_config.get("agent")
            if agent_name not in agents:
                raise ValueError(f"Agent not found: {agent_name}")
            members.append(agents[agent_name])

        team = Team(
            name=config.name,
            mode=TeamMode(config.mode),
            members=members,
            instructions=config.instructions,
        )
        return team
```

---

## 3. SESSION AND AGENT STATE GOVERNANCE

### 3.1 Arquitectura de Session Storage

yaml-agno **no hardcodea** un enum cerrado de storage types. Cualquier DB soportada por Agno se declara en YAML y se instancia en runtime vía `DependencyManager` (ver §1.3). La tabla muestra las más comunes; la lista completa la provee el registry.

| Storage Type | YAML key | Agno class | Use Case |
|--------------|----------|------------|----------|
| **SQLite** | `storage_type: sqlite` | `agno.db.sqlite.SqliteDb` | Desarrollo local |
| **PostgreSQL** | `storage_type: postgres` | `agno.db.postgres.PostgresDb` / `AsyncPostgresDb` | Producción multi-tenant |
| **Memory** | `storage_type: memory` | `agno.db.memory.InMemoryDb` | Tests y stateless |
| **Redis** | `storage_type: redis` | `agno.db.redis.RedisDb` (+ `expire` TTL) | Cache / TTL / pub-sub cancellation |
| *(extensible)* | `storage_type: <registry>` | entry_points (3rd-party) | Plugins |

> **@ai-directive (puntos 8, 6 del usuario)**: la abstracción clave es que el `storage_type` en YAML es una **key del registry**, no un enum cerrado. `DependencyManager` resuelve la clase Agno correspondiente, la importa perezosamente (solo esa, no todas) y la instancia con los params del YAML. Esto permite usar **cualquier DB de Agno** sin tocar código yaml-agno.

#### Session Configuration YAML

```yaml
agent:
  name: "my_agent"
  # ...

  session:
    # Identification (Agno first-class isolation keys)
    user_id: "${user_db.id}"
    session_id: "my_session_${user_id}"

    # Storage (resolved via DependencyManager; any Agno DB)
    storage_type: postgres
    connection_string: "${DB_URL}"  # from SecretManager, never env in prod

    # Metadata (tenant_id is NOT a first-class Agno key; modeled as claim/metadata,
    # resolved by Core Infra TenantResolver - see SPEC_00 §7.2)
    metadata:
      tenant_id: "${user_db.tenant_id}"
      environment: "${ENV}"
```

> **@ai-directive (punto 7)**: Agno **no** trae `retention_days` ni `auto_cleanup` nativos (no borra datos viejos solo). La limpieza/retención es **extensión propia** de yaml-agno: un job programado (SPEC_13) que llama a `Curator.prune(max_age_days=...)`, o el TTL de `RedisDb(expire=...)` si el backend es Redis. Ver nota de §1.1 para detalle.

#### Session Manager Contract

```python
# yaml-agno/src/core/session_manager.py
# SCHEMATIC: validates session config and delegates DB resolution to DependencyManager.

from pydantic import BaseModel, Field
from yaml_agno.di import DependencyManager

class SessionConfig(BaseModel):
    """Session config from YAML. No closed storage enum; validated against registry."""
    user_id: str
    session_id: str | None = None          # Agno first-class key
    storage_type: str = "sqlite"           # registry key, not enum
    connection_string: str | None = None   # from SecretManager, never env in prod
    metadata: dict = Field(default_factory=dict)

class SessionManager:
    """Validates session config and builds the Agno db= via DependencyManager."""

    def __init__(self, deps: DependencyManager):
        self.deps = deps

    async def validate(self, config: SessionConfig) -> None:
        """
        @ai-directive: validates storage_type against the DependencyManager registry
        (allowlisted), and that connection_string is present for DBs that require it.
        """
        if not await self.deps.is_known_storage(config.storage_type):
            raise ValueError(
                f"Unknown storage_type: {config.storage_type}. "
                f"Known: {await self.deps.list_storage_types()}"
            )
        if await self.deps.storage_needs_connection(config.storage_type) and not config.connection_string:
            raise ValueError(f"connection_string required for {config.storage_type}")

    async def build_db(self, config: SessionConfig):
        """Resolve the Agno DB instance lazily (only this provider is imported)."""
        return await self.deps.build_db(config.storage_type, config.connection_string)
```

### 3.2 Agent State Governance

El estado de agente se divide en 3 capas, todas mapeadas a **primitivas nativas de Agno** (no se inventan stores):

```mermaid
graph LR
    [Input] --> [Session State]
    [Session State] --> [Working Memory]
    [Working Memory] --> [Long-term Memory]
    [Long-term Memory] --> [Output]

    [Session State] -.-> |Agno db= PostgresDb/SqliteDb/RedisDb| [Persistent Storage]
    [Working Memory] -.-> |Agno run context| [Ephemeral - current run]
    [Long-term Memory] -.-> |Agno LearningMachine / MemoryManager| [Cross-Session Memory]
```

> **@ai-directive (punto 9 del usuario - Redis/learning)**: aclaraciones técnicas verificadas en Agno v2.6.14:
> - **Redis SÍ es de Agno**: `agno.db.redis.RedisDb` (DB de sessions/memory con `expire` TTL), `agno.vectordb.redis.RedisDB` (vector DB) y `RedisRunCancellationManager` (cancelación pub-sub). La etiqueta anterior "Redis/Agno" era imprecisa: Redis es una opción de backend Agno, no un cache genérico nuestro.
> - **`learning` y `culture`**: `learning` = `LearningMachine` (sistema unificado de aprendizaje). `culture` = `CultureManager` (experimental, "shared cultural knowledge"). Ambos son de Agno. Memory (MemoryManager) ≠ Learning (LearningMachine es la evolución más rica). Ver SPEC_04 para detalle.

#### Capas de Estado (mapeadas a Agno nativo)

| Capa | Agno primitive | Storage Agno | Responsabilidad |
|------|----------------|--------------|-----------------|
| **Session State** | `db=` + `session_id`/`user_id` | PostgresDb / SqliteDb / RedisDb | Historial de runs, tool calls |
| **Working Memory** | run context (interno Agno) | (efímero, run actual) | Contexto del run actual |
| **Long-term Memory** | `LearningMachine` (o `MemoryManager`) | db= (misma DB) | Observaciones cross-session |

#### State Persistence YAML

```yaml
agent:
  # ...
  
  state:
    # Session persistence
    session:
      store_history: true
      # @ai-directive (punto 10): num_history_messages is an Agno Agent attribute
      # (agent.py:138), mutually exclusive with num_history_runs. NOT max_history_messages.
      # These params are chatbot-oriented (multi-turn). For agentic single-shot flows
      # set add_history_to_context: false and omit them.
      add_history_to_context: true
      num_history_messages: 100   # OR num_history_runs: 3  (never both)
      max_tool_calls_from_history: 20

    # Working memory (compression is Agno CompressionManager, see SPEC_15)
    working:
      compress_tool_results: true
      compression_ratio_threshold: 0.5

    # Long-term memory (Agno native; Engram is optional external adapter - SPEC_04)
    memory:
      # Agno native options (mutually exclusive strategies):
      enable_agentic_memory: true       # agent decides when to store/recall (efficient)
      # update_memory_on_run: true      # alternative: store after every run (higher latency)
      add_memories_to_context: true

    # Learning (Agno LearningMachine - richer than memory; see SPEC_04)
    learning:
      enabled: false   # opt-in; 6 stores (user_profile, user_memory, ...)
      # type: learning_machine   # native Agno
```

---

## 4. COGNITIVE WORKFLOW TRIGGERS

### 4.1 Workflow Primitives

yaml-agno abstrae las 6 primitivas de workflow de Agno:

```mermaid
graph TD
    [Input] --> |Step| [Agent/Team/Function]
    [Input] --> |Steps| [Sequential Execution]
    [Input] --> |Parallel| [Concurrent Execution]
    [Input] --> |Condition| [Branching]
    [Input] --> |Router| [Dynamic Selection]
    [Input] --> |Loop| [Iterative Execution]
```

#### Primitiva: Step

Unidad básica de ejecución. Puede ser Agent, Team, Function, o Workflow anidado.

```yaml
workflow:
  name: "simple_workflow"
  
  steps:
    - step: extract_data
      type: agent  # agent|team|function|workflow
      agent: data_extractor
      execute: true  # true|false para deshabilitar
    
    - step: validate
      type: agent
      agent: validator
      
    - step: cleanup
      type: function
      function: cleanup_resources
      finally: true  # Ejecutar siempre
```

#### Primitiva: Steps

Ejecución secuencial de steps.

```yaml
workflow:
  name: "linear_pipeline"
  
  steps:
    - step: step1
      type: agent
      agent: agent1
    
    - step: step2
      type: agent
      agent: agent2
      
    - step: step3
      type: team
      team: processor_team
```

#### Primitiva: Parallel

Ejecución concurrente con merge de estado.

```yaml
workflow:
  name: "parallel_processing"
  
  steps:
    - step: parallel_validation
      type: parallel
      steps:
        - step: validate_structure
          type: agent
          agent: structure_validator
        
        - step: validate_content
          type: agent
          agent: content_validator
        
        - step: validate_format
          type: agent
          agent: format_validator
      
      # Merge strategy (opcional)
      merge_strategy: all  # all|first|last|custom
```

#### Primitiva: Condition

Branching condicional con CEL o callable.

```yaml
workflow:
  name: "conditional_flow"
  
  steps:
    - step: check_amount
      type: condition
      
      # CEL expression (Common Expression Language)
      condition: "${input.amount > 1000}"
      
      # O callable (referencia a función Python)
      # condition: "custom_functions.check_amount_threshold"
      
      if_true: senior_approval
      if_false: auto_process
    
    - step: senior_approval
      type: agent
      agent: senior_approver
      
    - step: auto_process
      type: agent
      agent: auto_processor
```

#### Primitiva: Router

Selección dinámica de step basada en input.

```yaml
workflow:
  name: "dynamic_routing"
  
  steps:
    - step: route_by_category
      type: router
      
      # CEL expression para evaluación
      expression: "${input.category}"
      
      cases:
        "billing": billing_agent
        "support": support_agent
        "sales": sales_agent
        "*": default_agent  # Wildcard
    
    - step: billing_agent
      type: agent
      agent: billing_processor
      
    # ... other cases
```

#### Primitiva: Loop

Ejecución iterativa con condición de fin.

```yaml
workflow:
  name: "retry_workflow"
  
  steps:
    - step: retry_operation
      type: loop
      
      # CEL condition para terminar
      end_condition: "${result.success == true || iteration_count >= 5}"
      
      # O callable
      # end_condition: "custom_functions.should_stop_retry"
      
      max_iterations: 10
      step: attempt_operation
    
    - step: attempt_operation
      type: agent
      agent: operation_agent
```

### 4.2 Workflow Factory

> **@ai-directive (punto 11 del usuario - imports perezosos)**: el factory **NO importa todas las primitivas de Agno al tope del módulo**. `DependencyManager` resuelve perezosamente solo la primitiva referenciada en cada step del YAML. Esto evita cargar el árbol completo de imports cuando no se usan.

```python
# yaml-agno/src/factories/workflow_factory.py
# SCHEMATIC: lazy primitive resolution via DependencyManager.

from typing import Any
from pydantic import BaseModel, Field
from yaml_agno.di import DependencyManager

class WorkflowConfig(BaseModel):
    """Configuration for an Agno Workflow from YAML."""
    name: str
    description: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)

class WorkflowFactory:
    """Factory: validated YAML (WorkflowConfig) -> agno.Workflow instance."""

    def __init__(self, deps: DependencyManager):
        self.deps = deps

    async def create(self, config: WorkflowConfig, agents: dict, teams: dict) -> "Workflow":
        Workflow = await self.deps.resolve_class("agno.workflow", "Workflow")  # lazy
        workflow = Workflow(name=config.name, description=config.description)

        for step_config in config.steps:
            step = await self._build_step(step_config, agents, teams)
            workflow.add_step(step)
        return workflow

    async def _build_step(self, step_config: dict, agents: dict, teams: dict):
        """Build a step; primitive class resolved lazily based on step type."""
        step_type = step_config.get("type", "agent")

        # Agent/Team are the most common; their classes resolve lazily too.
        if step_type == "agent":
            agent_name = step_config.get("agent")
            if agent_name not in agents:
                raise ValueError(f"Agent not found: {agent_name}")
            Step = await self.deps.resolve_class("agno.workflow", "Step")
            return Step(agent=agents[agent_name], execute=step_config.get("execute", True))

        if step_type == "team":
            team_name = step_config.get("team")
            if team_name not in teams:
                raise ValueError(f"Team not found: {team_name}")
            Step = await self.deps.resolve_class("agno.workflow", "Step")
            return Step(team=teams[team_name])

        # Parallel / Condition / Router / Loop: only the referenced primitive is imported.
        primitive_cls = await self.deps.resolve_workflow_primitive(step_type)  # lazy + allowlisted
        return primitive_cls(**step_config.get("params", {}))
```

---

## 5. BEHAVIOR DELTA - BDD SCENARIOS

### 5.1 Escenarios de Aceptación (Gherkin)

#### Scenario 1: Golden Path - Agent Creation from YAML

```gherkin
GIVEN a valid YAML agent configuration
  """
  agent:
    name: "test_agent"
    model: "openai/gpt-4o"
    instructions: "You are a test agent"
  """
AND the YAML is validated against AgentConfig schema
WHEN the agent factory creates the instance
THEN an Agno Agent object is returned
AND the agent.name equals "test_agent"
AND the agent.model.id equals "gpt-4o" (only openai module imported)
AND the agent.instructions match the YAML value
```

#### Scenario 2: Golden Path - Team Creation with Members

```gherkin
GIVEN a valid YAML team configuration
  """
  team:
    name: "test_team"
    mode: coordinate
    members:
      - member: member1
        agent: agent1
  """
AND agent1 is already instantiated
WHEN the team factory creates the instance
THEN an Agno Team object is returned
AND the team.mode equals TeamMode.coordinate
AND the team.members list contains agent1
```

#### Scenario 3: Error Case - Invalid Team Mode

```gherkin
GIVEN a YAML team configuration with invalid mode
  """
  team:
    name: "test_team"
    mode: "invalid_mode"
  """
WHEN the team factory attempts to create the instance
THEN a ValueError is raised
AND the error message contains "Invalid team mode"
```

#### Scenario 4: Error Case - Missing Agent Reference

```gherkin
GIVEN a YAML team configuration
  """
  team:
    name: "test_team"
    mode: coordinate
    members:
      - member: missing_member
        agent: "nonexistent_agent"
  """
AND the agents dictionary does NOT contain "nonexistent_agent"
WHEN the team factory attempts to create the instance
THEN a ValueError is raised
AND the error message contains "Agent not found: nonexistent_agent"
```

### 5.2 Matriz de Comportamiento ante Errores

| Error | Tipo | Excepción | Recuperación |
|-------|------|-----------|--------------|
| **Invalid model_id** | Permanente | `ValueError` | Corregir YAML |
| **Invalid team mode** | Permanente | `ValueError` | Corregir YAML |
| **Missing agent reference** | Permanente | `ValueError` | Corregir YAML |
| **Missing connection_string** | Permanente | `ValueError` | Proveer DB_URL |
| **Invalid CEL expression** | Transitorio | `ConditionEvaluationError` | Reintentar (3x) |
| **Agent runtime failure** | Transitorio | `AgentExecutionError` | Reintentar con backoff |

---

## 6. TDD MICRO-TASK EXECUTION PROTOCOL

### 6.1 Protocolo de Ejecución

1. **RED**: Escribir test que falla con implementación vacía
2. **GREEN**: Implementación mínima para pasar el test
3. **REFACTOR**: Limpieza de código sin cambiar comportamiento
4. **COMMIT**: Mensaje descriptivo del cambio

### 6.2 Cascading Task Checklist

#### TASK_001: Define AgentConfig Pydantic Model

- **File**: `yaml-agno/src/models/agent.py`
- **Test**: `tests/unit/test_agent_models.py`
- **RED**:
  ```python
  def test_agent_config_validation():
      config = AgentConfig(name="test", model="openai/gpt-4o")
      assert config.name == "test"
  ```
- **GREEN**: Implementar `AgentConfig` con Pydantic V2
- **Commit**: `feat: add AgentConfig Pydantic model`

#### TASK_002: Implement AgentFactory.create()

- **File**: `yaml-agno/src/factories/agent_factory.py`
- **Test**: `tests/unit/test_agent_factory.py`
- **RED**:
  ```python
  async def test_agent_factory_creates_agent():
      config = AgentConfig(name="test", model="openai/gpt-4o")
      agent = await AgentFactory(deps).create(config)
      assert agent.name == "test"
  ```
- **GREEN**: Implementar `AgentFactory.create()` async básico
- **Commit**: `feat: implement AgentFactory.create()`

#### TASK_003: Add Model Resolution Logic (via DependencyManager)

- **File**: `yaml-agno/src/factories/agent_factory.py`
- **Test**: `tests/unit/test_agent_factory.py`
- **RED**:
  ```python
  async def test_openai_model_resolution():
      config = AgentConfig(name="test", model="openai/gpt-4o")
      agent = await AgentFactory(deps).create(config)
      assert agent.model.id == "gpt-4o"   # only openai module imported
  ```
- **GREEN**: Implementar resolución de modelo vía `DependencyManager.resolve_model()`
- **Commit**: `feat: add model resolution via DependencyManager`

#### TASK_004: Define TeamConfig Pydantic Model

- **File**: `yaml-agno/src/models/team.py`
- **Test**: `tests/unit/test_team_models.py`
- **RED**:
  ```python
  def test_team_config_validation():
      config = TeamConfig(name="test", mode="coordinate")
      assert config.mode == "coordinate"
  ```
- **GREEN**: Implementar `TeamConfig`
- **Commit**: `feat: add TeamConfig Pydantic model`

#### TASK_005: Implement TeamFactory.create() (async)

- **File**: `yaml-agno/src/factories/team_factory.py`
- **Test**: `tests/unit/test_team_factory.py`
- **RED**:
  ```python
  async def test_team_factory_creates_team():
      config = TeamConfig(name="test", mode="coordinate", members=[])
      team = await TeamFactory(deps).create(config, agents={})
      assert team.name == "test"
  ```
- **GREEN**: Implementar `TeamFactory.create()` async básico
- **Commit**: `feat: implement TeamFactory.create()`

#### TASK_006: Add Team Mode Mapping (4 modes, no coroutine)

- **File**: `yaml-agno/src/factories/team_factory.py`
- **Test**: `tests/unit/test_team_factory.py`
- **RED**:
  ```python
  async def test_team_mode_mapping():
      config = TeamConfig(name="test", mode="coordinate", members=[])
      team = await TeamFactory(deps).create(config, agents={})
      assert team.mode == TeamMode.coordinate

  async def test_coroutine_mode_rejected():
      config = TeamConfig(name="test", mode="coroutine", members=[])
      with pytest.raises(ValueError, match="no 'coroutine'"):
          await TeamFactory(deps).create(config, agents={})
  ```
- **GREEN**: Implementar validación contra los 4 modos reales (`coordinate|route|broadcast|tasks`)
- **Commit**: `feat: add team mode mapping (4 modes)`

#### TASK_007: Define SessionConfig Pydantic Model

- **File**: `yaml-agno/src/models/session.py`
- **Test**: `tests/unit/test_session_models.py`
- **RED**:
  ```python
  def test_session_config_validation():
      config = SessionConfig(user_id="test-user", session_id="test")
      assert config.storage_type == "sqlite"  # registry key, not enum
  ```
- **GREEN**: Implementar `SessionConfig` (storage_type como string/registry key)
- **Commit**: `feat: add SessionConfig Pydantic model`

#### TASK_008: Implement SessionManager (async validate via DependencyManager)

- **File**: `yaml-agno/src/core/session_manager.py`
- **Test**: `tests/unit/test_session_manager.py`
- **RED**:
  ```python
  async def test_session_manager_validates_unknown_storage():
      config = SessionConfig(user_id="test", session_id="test", storage_type="unknown_db")
      with pytest.raises(ValueError, match="Unknown storage_type"):
          await SessionManager(deps).validate(config)
  ```
- **GREEN**: Implementar `SessionManager.validate()` (delega validación a DependencyManager registry)
- **Commit**: `feat: implement SessionManager validation`

---

## 7. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] Uso de Pydantic V2 para Validación

**Justificación**: Pydantic V2 ofrece validación de runtime 5-10x más rápida que V1, integración nativa con Python 3.12+ type hints, y soporte para `model_serializer`/`model_validator` que simplifican la validación compleja de YAML.

### [Decisión 2] Mapeo Directo a Agno Framework sin Wrapper

**Justificación**: Construir SOBRE Agno en lugar de re-implementar sus internals reduce deuda técnica, garantiza compatibilidad con updates de Agno, y permite acceso a 80+ parámetros de Agent/Team sin reimplementación.

### [Decisión 3] CEL (Common Expression Language) para Workflows

**Justificación**: CEL es estándar de industria para expresiones configurables, tipo-seguro, y permite sandboxing de condiciones evaluadas en runtime sin `eval()` de Python.

---

## 8. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Escalabilidad de Session Storage — DECIDIDO

**Decisión del usuario**: empezar por **< 100 sesiones activas simultáneas** (PostgreSQL single instance, MVP actual) y escalar a **10,000+ sesiones** cuando haya suficientes clientes/usuarios.

Umbral de diseño (para no re-arquitecturar tarde):
- **Etapa 1 (ahora): < 100 sesiones activas simultáneas** → PostgreSQL single instance es suficiente
- **Etapa 2 (cuando tengamos clientes/usuarios suficientes): 10,000+ sesiones** → connection pooling (PgBouncer) + revisar índices
- **Etapa 3 (futuro): 100,000+ sesiones** → particionamiento/sharding (por `user_id`/tenant)

Implica: SPEC_03 define partitioning opcional desde el inicio (para no re-arquitecturar tarde); el salto a Etapa 2 se documenta como criterio operativo, no como bloqueador del MVP.

### [Pregunta 2] Consistencia de Workflow State (¿qué es ACID?) — PENDIENTE

**Aclaración del concepto (preguntado por el usuario)**: **ACID** son las 4 garantías transaccionales de una base de datos relacional:
- **A**tomicidad: una operación de varios pasos se completa entera o se revierte entera (no queda a medias). Si un workflow de 5 steps falla en el paso 3, los pasos 1-2 se deshacen.
- **C**onsistencia: la DB pasa de un estado válido a otro estado válido (respeta constraints/claves).
- **I**solación: transacciones concurrentes no interfieren entre sí (una no ve cambios a medias de otra).
- **D**urabilidad: una vez confirmada (commit), el cambio sobrevive a crashes/cortes de luz.

**La decisión pendiente**: ¿un workflow multi-step debe garantizar ACID (estado guardado transaccionalmente en PostgreSQL, "todo o nada") o basta consistencia eventual (estado en Redis + replicación asíncrona a PostgreSQL, más rápido pero puede haber breves inconsistencias)?

Implica:
- **ACID (PostgreSQL transaccional)**: máxima garantía de estado; workflows financieros/legales lo exigen. Trade-off: algo más de latencia.
- **Eventual (Redis + write-behind)**: menor latencia; aceptable para workflows donde una breve inconsistencia no es crítica.
- **Recomendación tentativa**: ACID por defecto (somos productos escalables que pueden tocar datos sensibles), con opción de eventual para casos de baja criticidad.

### [Pregunta 3] Cacheo de Agent/Team Instances — DECIDIDO (feature planeada)

**Aclaración del concepto**: cada vez que llega un request HTTP, el `AgentFactory` puede **reconstruir** el objeto `Agent` desde el YAML (leer YAML, validar Pydantic, resolver modelo, construir tools, etc.). Eso cuesta ~5ms por agente.

**Decisión del usuario**: **sí, vale la pena cachear** instancias de Agent/Team construidas y reusarlas en requests siguientes del mismo tenant/config, en vez de reconstruir cada vez. Se deja **planteado como feature planeada** (no bloqueante para el MVP core).

Diseño de la feature:
- **Cache LRU por `tenant_id + config_hash`**: la clave combina el tenant y un hash del YAML de config.
- **Invalidación automática en hot-reload**: si el YAML cambia, su hash cambia → cache miss → se reconstruye con la config nueva.
- **Capas de cache complementarias**: el `DependencyManager` (Core) ya provee `lru_cache` a nivel de **clase**; esta feature extiende el cache a nivel de **instancia de Agent/Team**.
- **Cuándo construir**: post-MVP core, como optimización de rendimiento (ver roadmap SPEC_00).

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
