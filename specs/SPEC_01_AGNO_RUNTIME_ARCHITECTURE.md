---
Spec_ID: "SPEC_01"
Title: "Agno Runtime Architecture"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#Agno", "#Runtime", "#SessionManagement", "#WorkflowPrimitives"]
Dependency_Hashes: ["SPEC_00"]
Last_Updated: "2026-06-13"
---

# SPEC_01_AGNO_RUNTIME_ARCHITECTURE

> **Propósito**: Definir la infraestructura de agentes y orquestación asíncrona en runtime para yaml-agno, incluyendo configuración del ciclo de vida, contratos de equipos especializados, gobernanza de estado y disparadores de workflows cognitivos.

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

```python
# yaml-agno/src/factories/agent_factory.py

from typing import Dict, Any
from agno.agent import Agent
from agno.models import OpenAIChat
from agno.tools import FunctionToolkit
from agno.knowledge import Knowledge
from agno.memory import Memory
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    """Configuración completa de Agente desde YAML"""
    name: str = Field(..., description="Nombre único del agente")
    model: str = Field(..., description="Modelo ID (ej: openai/gpt-4o)")
    instructions: str | None = Field(None, description="System prompt del agente")
    tools: list[Dict[str, Any]] = Field(default_factory=list, description="Lista de tools configuradas")
    knowledge: list[Dict[str, Any]] | None = Field(None, description="Fuentes de conocimiento")
    memory: Dict[str, Any] | None = Field(None, description="Configuración de memoria")
    session: Dict[str, Any] | None = Field(None, description="Configuración de sesión")

class AgentFactory:
    """Factory para crear instancias de Agent desde YAML"""
    
    @staticmethod
    def create(config: AgentConfig) -> Agent:
        """
        Crea una instancia de Agent desde configuración validada.
        
        Args:
            config: Configuración validada de YAML
            
        Returns:
            Agent: Instancia configurada de Agno Agent
            
        Raises:
            ValueError: Si model_id no es válido
            TypeError: Si tools no es lista
        """
        # Validación de modelo
        model = AgentFactory._resolve_model(config.model)
        
        # Construcción del agente
        agent = Agent(
            name=config.name,
            model=model,
            instructions=config.instructions,
            tools=AgentFactory._build_tools(config.tools),
            knowledge=AgentFactory._build_knowledge(config.knowledge),
            memory=AgentFactory._build_memory(config.memory),
        )
        
        return agent
    
    @staticmethod
    def _resolve_model(model_id: str) -> OpenAIChat:
        """Resuelve model_id string a instancia de modelo Agno"""
        # Agno soporta 30+ providers, mapeamos ID → instancia
        if model_id.startswith("openai/"):
            model_name = model_id.split("/")[-1]
            return OpenAIChat(id=model_name)
        # TODO: agregar soporte para anthropic, azure, etc.
        raise ValueError(f"Unsupported model: {model_id}")
    
    @staticmethod
    def _build_tools(tools_config: list[Dict[str, Any]]) -> list[FunctionToolkit]:
        """Construye toolkit desde configuración YAML"""
        # TODO: implementar ToolFactory para tools complejas
        return []
    
    @staticmethod
    def _build_knowledge(knowledge_config: list[Dict[str, Any]]) | None:
        """Construye instancias de Knowledge desde YAML"""
        if not knowledge_config:
            return None
        # TODO: implementar KnowledgeFactory
        return None
    
    @staticmethod
    def _build_memory(memory_config: Dict[str, Any]) | None:
        """Construye instancia de Memory desde YAML"""
        if not memory_config:
            return None
        # TODO: implementar MemoryFactory
        return None
```

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
    storage_type: postgres  # sqlite | postgres | memory
    retention_days: 30
    
  execution:
    max_iterations: 10
    stream: false
    show_tool_calls: true
    debug_mode: false
```

**Parámetros de Session expuestos** (mapeados a Agno):

| Parámetro YAML | Agno Equivalent | Validación |
|----------------|-----------------|-------------|
| `user_id` | `session.user_id` | UUIDv4 o string único |
| `session_name` | `session.session_name` | String no vacío |
| `storage_type` | `session.storage` | sqlite|postgres|memory |
| `retention_days` | `session.retention` | Integer >= 1 |
| `max_iterations` | `run(max_iterations=...)` | Integer >= 1 |

---

## 2. SPECIALIZED TEAMS CONTRACTS

### 2.1 Contrato de Team Configuration

Los Teams en yaml-agno se mapean a `agno.team.Team` con todos sus modos y configuraciones.

#### Modos de Team Soportados

| Modo YAML | Agno Team Mode | Descripción |
|-----------|----------------|-------------|
| `coordinate` | `TeamMode.COORDINATE` | Coordinación simple |
| `route` | `TeamMode.ROUTE` | Routing dinámico |
| `broadcast` | `TeamMode.BROADCAST` | Broadcast a todos |
| `tasks` | `TeamMode.TASKS` | DAG de dependencias |
| `coroutine` | `TeamMode.COROUTINE` | Corrutinas paralelas |

#### Team YAML Schema

```yaml
team:
  name: "facturacion_workflow"
  mode: coordinate  # coordinate|route|broadcast|tasks|coroutine
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

from agno.team import Team, TeamMode
from agno.agent import Agent
from typing import Dict, Any, List

class TeamConfig(BaseModel):
    """Configuración de Team desde YAML"""
    name: str
    mode: str  # coordinate|route|broadcast|tasks|coroutine
    instructions: str | None = None
    members: List[Dict[str, Any]] = Field(default_factory=list)
    workflows: List[Dict[str, Any]] = Field(default_factory=list)

class TeamFactory:
    """Factory para crear instancias de Team desde YAML"""
    
    MODE_MAP = {
        "coordinate": TeamMode.COORDINATE,
        "route": TeamMode.ROUTE,
        "broadcast": TeamMode.BROADCAST,
        "tasks": TeamMode.TASKS,
        "coroutine": TeamMode.COROUTINE,
    }
    
    @staticmethod
    def create(config: TeamConfig, agents: Dict[str, Agent]) -> Team:
        """
        Crea una instancia de Team desde configuración validada.
        
        Args:
            config: Configuración validada de YAML
            agents: Diccionario de agent_name → Agent instance
            
        Returns:
            Team: Instancia configurada de Agno Team
            
        Raises:
            ValueError: Si mode no es válido o member no existe en agents
        """
        # Validar modo
        if config.mode not in TeamFactory.MODE_MAP:
            raise ValueError(f"Invalid team mode: {config.mode}")
        
        team_mode = TeamFactory.MODE_MAP[config.mode]
        
        # Construir miembros
        members = []
        for member_config in config.members:
            agent_name = member_config.get("agent")
            if agent_name not in agents:
                raise ValueError(f"Agent not found: {agent_name}")
            
            members.append({
                "agent": agents[agent_name],
                "role": member_config.get("role", ""),
            })
        
        # Construir team
        team = Team(
            name=config.name,
            mode=team_mode,
            instructions=config.instructions,
            members=[m["agent"] for m in members],  # Agno espera lista de Agents
        )
        
        return team
```

---

## 3. SESSION AND AGENT STATE GOVERNANCE

### 3.1 Arquitectura de Session Storage

yaml-agno soporta 3 tipos de almacenamiento de sesión mapeados a Agno:

| Storage Type | YAML Key | Agno Implementation | Use Case |
|--------------|----------|---------------------|----------|
| **SQLite** | `storage_type: sqlite` | `session_type=sqlite` | Desarrollo local |
| **PostgreSQL** | `storage_type: postgres` | `session_type=postgres` + connection string | Producción multi-tenant |
| **Memory** | `storage_type: memory` | `session_type=None` | Tests y stateless |

#### Session Configuration YAML

```yaml
agent:
  name: "my_agent"
  # ...
  
  session:
    # Identificación
    user_id: "${user_db.id}"  # Required: UUIDv4 o unique string
    session_name: "my_session_${user_id}"
    
    # Storage
    storage_type: postgres  # sqlite|postgres|memory
    connection_string: "${DB_URL}"  # Required for postgres
    
    # Retención
    retention_days: 30
    auto_cleanup: true
    
    # Metadata
    metadata:
      tenant_id: "${user_db.tenant_id}"
      environment: "${ENV}"
```

#### Session Manager Contract

```python
# yaml-agno/src/core/session_manager.py

from enum import Enum
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

class StorageType(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MEMORY = "memory"

class SessionConfig(BaseModel):
    """Configuración de sesión desde YAML"""
    user_id: str
    session_name: str
    storage_type: StorageType = StorageType.SQLITE
    connection_string: str | None = None
    retention_days: int = 30
    auto_cleanup: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SessionManager:
    """Gestiona configuración y ciclo de vida de sesiones"""
    
    @staticmethod
    def validate_config(config: SessionConfig) -> None:
        """
        Valida configuración de sesión antes de pasar a Agno.
        
        Args:
            config: Configuración validada
            
        Raises:
            ValueError: Si storage_type=postgres y connection_string está vacío
        """
        if config.storage_type == StorageType.POSTGRES and not config.connection_string:
            raise ValueError("connection_string required for postgres storage")
        
        if config.storage_type == StorageType.MEMORY and config.retention_days > 0:
            # Memory storage no soporta retención persistente
            raise ValueError("Memory storage does not support retention_days")
    
    @staticmethod
    def build_session_params(config: SessionConfig) -> Dict[str, Any]:
        """
        Construye parámetros para Agno Agent session.
        
        Returns:
            Dict con parámetros para Agent.run(session=...)
        """
        params = {
            "user_id": config.user_id,
            "session_name": config.session_name,
        }
        
        if config.storage_type != StorageType.MEMORY:
            params["storage_type"] = config.storage_type.value
            if config.connection_string:
                params["connection_string"] = config.connection_string
        
        return params
```

### 3.2 Agent State Governance

El estado de agente se divide en 3 capas:

```mermaid
graph LR
    [Input] --> [Session State]
    [Session State] --> [Working Memory]
    [Working Memory] --> [Long-term Memory]
    [Long-term Memory] --> [Output]
    
    [Session State] -.-> |PostgreSQL| [Persistent Storage]
    [Working Memory] -.-> |Redis/Agno| [Ephemeral Cache]
    [Long-term Memory] -.-> |Engram| [Cross-Session Memory]
```

#### Capas de Estado

| Capa | Storage | TTL | Responsabilidad |
|------|---------|-----|-----------------|
| **Session State** | PostgreSQL | 30 días | Historial de conversación, tool calls |
| **Working Memory** | Agno internal | Sesión actual | Contexto del run actual |
| **Long-term Memory** | Engram | Permanente | Aprendizaje跨 sesiones |

#### State Persistence YAML

```yaml
agent:
  # ...
  
  state:
    # Session persistence
    session:
      store_history: true
      max_history_messages: 100
      include_tool_calls: true
    
    # Working memory
    working:
      max_context_tokens: 8000
      compression_threshold: 6000
    
    # Long-term memory
    memory:
      enabled: true
      type: engram  # engram|custom|none
      project: "yaml-agno"
      scope: project  # project|personal
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

```python
# yaml-agno/src/factories/workflow_factory.py

from agno.workflow import Workflow, Step, Parallel, Condition, Router, Loop
from typing import Dict, Any, List

class WorkflowConfig(BaseModel):
    """Configuración de Workflow desde YAML"""
    name: str
    description: str | None = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)

class WorkflowFactory:
    """Factory para crear instancias de Workflow desde YAML"""
    
    @staticmethod
    def create(config: WorkflowConfig, agents: Dict[str, Agent], teams: Dict[str, Team]) -> Workflow:
        """
        Crea una instancia de Workflow desde configuración validada.
        
        Args:
            config: Configuración validada de YAML
            agents: Diccionario de agent_name → Agent instance
            teams: Diccionario de team_name → Team instance
            
        Returns:
            Workflow: Instancia configurada de Agno Workflow
            
        Raises:
            ValueError: Si step type no es válido o reference no existe
        """
        workflow = Workflow(name=config.name, description=config.description)
        
        for step_config in config.steps:
            step = WorkflowFactory._build_step(step_config, agents, teams)
            workflow.add_step(step)
        
        return workflow
    
    @staticmethod
    def _build_step(step_config: Dict[str, Any], agents: Dict[str, Agent], teams: Dict[str, Team]) -> Step:
        """Construye una instancia de Step desde config YAML"""
        step_type = step_config.get("type", "agent")
        
        if step_type == "agent":
            agent_name = step_config.get("agent")
            if agent_name not in agents:
                raise ValueError(f"Agent not found: {agent_name}")
            return Step(agent=agents[agent_name], execute=step_config.get("execute", True))
        
        elif step_type == "team":
            team_name = step_config.get("team")
            if team_name not in teams:
                raise ValueError(f"Team not found: {team_name}")
            return Step(team=teams[team_name])
        
        # TODO: implementar function, workflow, parallel, condition, router, loop
        else:
            raise ValueError(f"Unsupported step type: {step_type}")
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
AND the agent.model is an instance of OpenAIChat
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
AND the team.mode equals TeamMode.COORDINATE
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
  def test_agent_factory_creates_agent():
      config = AgentConfig(name="test", model="openai/gpt-4o")
      agent = AgentFactory.create(config)
      assert isinstance(agent, Agent)
  ```
- **GREEN**: Implementar `AgentFactory.create()` básico
- **Commit**: `feat: implement AgentFactory.create()`

#### TASK_003: Add Model Resolution Logic

- **File**: `yaml-agno/src/factories/agent_factory.py`
- **Test**: `tests/unit/test_agent_factory.py`
- **RED**:
  ```python
  def test_openai_model_resolution():
      config = AgentConfig(name="test", model="openai/gpt-4o")
      agent = AgentFactory.create(config)
      assert isinstance(agent.model, OpenAIChat)
  ```
- **GREEN**: Implementar `_resolve_model()`
- **Commit**: `feat: add model resolution for OpenAI`

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

#### TASK_005: Implement TeamFactory.create()

- **File**: `yaml-agno/src/factories/team_factory.py`
- **Test**: `tests/unit/test_team_factory.py`
- **RED**:
  ```python
  def test_team_factory_creates_team():
      config = TeamConfig(name="test", mode="coordinate", members=[])
      team = TeamFactory.create(config, agents={})
      assert isinstance(team, Team)
  ```
- **GREEN**: Implementar `TeamFactory.create()` básico
- **Commit**: `feat: implement TeamFactory.create()`

#### TASK_006: Add Team Mode Mapping

- **File**: `yaml-agno/src/factories/team_factory.py`
- **Test**: `tests/unit/test_team_factory.py`
- **RED**:
  ```python
  def test_team_mode_mapping():
      config = TeamConfig(name="test", mode="coordinate", members=[])
      team = TeamFactory.create(config, agents={})
      assert team.mode == TeamMode.COORDINATE
  ```
- **GREEN**: Implementar `MODE_MAP` y validación
- **Commit**: `feat: add team mode mapping`

#### TASK_007: Define SessionConfig Pydantic Model

- **File**: `yaml-agno/src/models/session.py`
- **Test**: `tests/unit/test_session_models.py`
- **RED**:
  ```python
  def test_session_config_validation():
      config = SessionConfig(user_id="test-user", session_name="test")
      assert config.storage_type == StorageType.SQLITE
  ```
- **GREEN**: Implementar `SessionConfig`
- **Commit**: `feat: add SessionConfig Pydantic model`

#### TASK_008: Implement SessionManager

- **File**: `yaml-agno/src/core/session_manager.py`
- **Test**: `tests/unit/test_session_manager.py`
- **RED**:
  ```python
  def test_session_manager_validates_postgres_connection():
      config = SessionConfig(
          user_id="test",
          session_name="test",
          storage_type=StorageType.POSTGRES,
          connection_string=None
      )
      with pytest.raises(ValueError):
          SessionManager.validate_config(config)
  ```
- **GREEN**: Implementar `SessionManager.validate_config()`
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

### [Pregunta 1] Escalabilidad de Session Storage

**¿Qué volumen esperado de sesiones concurrentes se debe soportar antes de considerar sharding de PostgreSQL para session storage?**

Considerando:
- 100 sesiones activas simultáneas → PostgreSQL single instance es suficiente
- 10,000+ sesiones → Requiere connection pooling + PgBouncer
- 100,000+ sesiones → Considerar sharding por tenant_id

### [Pregunta 2] Consistencia de Workflow State

**¿Debe haber ACID strict consistency en workflows multi-step o eventual consistency es aceptable?**

Implica:
- **ACID**: Workflow state guardado en PostgreSQL transaccional
- **Eventual**: Workflow state en Redis + write-behind a PostgreSQL
- **Trade-off**: Latencia vs garantías de estado

### [Pregunta 3] Cacheo de Agent/Team Instances

**¿Debería cachearse instancias de Agent/Team en memoria por tenant para evitar reconstrucción por request?**

Implica:
- **Cache LRU**: Reducción de overhead de factory (~5ms por agent)
- **Trade-off**: Memoria vs CPU
- **Invalidation**: Requires cache-busting on config hot-reload

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
