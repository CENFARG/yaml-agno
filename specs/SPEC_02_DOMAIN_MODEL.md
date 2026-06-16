---
Spec_ID: "SPEC_02"
Title: "Domain Model - DDD Aggregates and Value Objects"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#DDD", "#PydanticV2", "#DomainModel", "#ValueObjects"]
Dependency_Hashes: ["SPEC_00", "SPEC_01"]
Last_Updated: "2026-06-13"
---

# SPEC_02_DOMAIN_MODEL

> **Propósito**: Declarar los tipos de datos abstractos, agregados DDD, entidades con ciclo de vida, objetos de valor inmutables y eventos de dominio que constituyen el modelo core de yaml-agno.

---

## 1. DDD BOUNDED CONTEXTS AGGREGATES

### 1.1 Mapa de Contextos Delimitados

```mermaid
graph TB
    subgraph["Config Context"]
        [AgentConfig]
        [TeamConfig]
        [WorkflowConfig]
        [DIConfig]
    end
    
    subgraph["Runtime Context"]
        [AgentInstance]
        [TeamInstance]
        [WorkflowInstance]
        [SessionContext]
    end
    
    subgraph["Memory Context"]
        [SessionState]
        [WorkingMemory]
        [LongTermMemory]
    end
    
    [Config Context] -->|Factory Pattern| [Runtime Context]
    [Runtime Context] -->|State Transitions| [Memory Context]
    [Memory Context] -.->|Rehydration| [Runtime Context]
```

### 1.2 Agregado: AgentConfig (Config Context)

**Raíz de Agregado**: `AgentConfig`
**Responsabilidad**: Validar y mantener la integridad de configuración de agente desde YAML.

```python
# yaml-agno/src/models/config/agent_config.py

from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Literal
from enum import Enum

# Type aliases PEP 695
type Instructions = str
type ModelReference = str
type ToolConfiguration = Dict[str, Any]
type ToolkitName = str
type Tag = str

class ModelProvider(str, Enum):
    """Proveedores de modelos soportados"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    GOOGLE_GEMINI = "google_gemini"
    COHERE = "cohere"
    # ... 25+ providers mapeados desde Agno

class StorageType(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MEMORY = "memory"

class AgentConfig(BaseModel):
    """
    Agregado raíz de configuración de Agente.
    
    Invariante: Un AgentConfig válido siempre tiene:
    - name no vacío y único dentro del tenant
    - model_id válido con formato provider/model
    - Opcionalmente tools, knowledge, memory, session configurados
    """
    
    # Identidad
    name: str = Field(..., min_length=1, max_length=100, description="Nombre único del agente")
    model: str = Field(..., pattern=r"^[a-z_]+/[a-z0-9_-]+$", description="Model ID (ej: openai/gpt-4o)")
    
    # Comportamiento
    instructions: str | None = Field(None, max_length=50000, description="System prompt del agente")
    response_model: Dict[str, Any] | None = Field(None, description="Schema de salida estructurada")
    
    # Herramientas
    tools: list[Dict[str, Any]] = Field(default_factory=list, max_length=50, description="Configuración de tools")
    toolkits: list[str] = Field(default_factory=list, max_length=20, description="Nombres de toolkits predefinidos")
    
    # Conocimiento
    knowledge: list[Dict[str, Any]] | None = Field(None, description="Fuentes de conocimiento")
    
    # Memoria
    memory: Dict[str, Any] | None = Field(None, description="Configuración de memoria")
    
    # Sesión
    session: Dict[str, Any] | None = Field(None, description="Configuración de sesión")
    
    # Metadata
    description: str | None = Field(None, description="Descripción del agente")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Tags para organización")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata adicional")
    
    @field_validator("model")
    @classmethod
    def validate_model_format(cls, v: str) -> str:
        """Valida formato provider/model"""
        parts = v.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid model format: {v}. Expected: provider/model")
        
        provider, model_name = parts
        
        # Validar provider conocido
        try:
            ModelProvider(provider)
        except ValueError:
            raise ValueError(f"Unknown model provider: {provider}")
        
        return v
    
    @field_validator("name")
    @classmethod
    def validate_name_characters(cls, v: str) -> str:
        """Valida que nombre solo contenga caracteres seguros"""
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Invalid agent name: {v}. Only alphanumeric, underscore, and hyphen allowed")
        return v
    
    def get_provider(self) -> ModelProvider:
        """Extrae provider del model_id"""
        return ModelProvider(self.model.split("/")[0])
    
    def get_model_name(self) -> str:
        """Extrae model name del model_id"""
        return self.model.split("/")[1]

class AgentConfigWithDI(AgentConfig):
    """Extensión de AgentConfig con Dependency Injection resuelta"""
    
    di_variables: Dict[str, Any] = Field(default_factory=dict, description="Variables DI resueltas")
    di_resolved: bool = Field(default=False, description="Indica si DI fue aplicado")
    
    def apply_di(self, variables: Dict[str, Any]) -> "AgentConfigWithDI":
        """Aplica variables DI a templates en instructions y otros campos"""
        # TODO: Implementar resolución de ${provider.key}
        return self.model_copy(di_variables=variables, di_resolved=True)
```

### 1.3 Agregado: TeamConfig (Config Context)

**Raíz de Agregado**: `TeamConfig`
**Responsabilidad**: Validar configuración de equipo con miembros, modo y workflows.

```python
# yaml-agno/src/models/config/team_config.py

from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Literal, List
from enum import Enum

class TeamMode(str, Enum):
    """Modos de Team soportados"""
    COORDINATE = "coordinate"
    ROUTE = "route"
    BROADCAST = "broadcast"
    TASKS = "tasks"
    COROUTINE = "coroutine"

class TeamMemberConfig(BaseModel):
    """Configuración de miembro de team"""
    member: str = Field(..., description="ID único del miembro")
    agent: str = Field(..., description="Nombre del agente referenciado")
    role: str | None = Field(None, description="Rol del miembro en el team")
    
class TeamConfig(BaseModel):
    """
    Agregado raíz de configuración de Team.
    
    Invariante: Un TeamConfig válido siempre tiene:
    - name no vacío y único
    - mode válido
    - miembros referenciando agentes existentes (validación externa)
    """
    
    # Identidad
    name: str = Field(..., min_length=1, max_length=100)
    mode: TeamMode = Field(..., description="Modo de ejecución del team")
    
    # Comportamiento
    instructions: str | None = Field(None, description="Instructions del team")
    
    # Composición
    members: List[TeamMemberConfig] = Field(default_factory=list, description="Miembros del team")
    
    # Workflows
    workflows: List[Dict[str, Any]] = Field(default_factory=list, description="Workflows del team")
    
    # Metadata
    description: str | None = Field(None)
    tags: list[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator("members")
    @classmethod
    def validate_members_unique(cls, v: List[TeamMemberConfig]) -> List[TeamMemberConfig]:
        """Valida que no haya miembros duplicados"""
        member_ids = [m.member for m in v]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Duplicate member IDs detected")
        return v
    
    @field_validator("mode")
    @classmethod
    def validate_mode_requirements(cls, v: TeamMode, info) -> TeamMode:
        """Valida requisitos específicos por modo"""
        members = info.data.get("members", [])
        
        if v == TeamMode.ROUTE and len(members) < 2:
            raise ValueError("ROUTE mode requires at least 2 members")
        
        if v == TeamMode.BROADCAST and len(members) < 2:
            raise ValueError("BROADCAST mode requires at least 2 members")
        
        return v
```

### 1.4 Agregado: WorkflowConfig (Config Context)

**Raíz de Agregado**: `WorkflowConfig`
**Responsabilidad**: Validar primitivas de workflow (steps, parallel, condition, router, loop).

```python
# yaml-agno/src/models/config/workflow_config.py

from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Literal, List, Union
from enum import Enum

class StepType(str, Enum):
    """Tipos de step soportados"""
    AGENT = "agent"
    TEAM = "team"
    FUNCTION = "function"
    WORKFLOW = "workflow"
    PARALLEL = "parallel"
    CONDITION = "condition"
    ROUTER = "router"
    LOOP = "loop"

class StepConfig(BaseModel):
    """Configuración base de step"""
    step: str = Field(..., description="ID único del step")
    type: StepType = Field(default=StepType.AGENT, description="Tipo de step")
    description: str | None = Field(None, description="Descripción del step")
    
    # Referencias (mutuamente exclusivas según type)
    agent: str | None = Field(None, description="Nombre del agent (type=agent)")
    team: str | None = Field(None, description="Nombre del team (type=team)")
    function: str | None = Field(None, description="Nombre de función (type=function)")
    workflow: str | None = Field(None, description="Nombre de workflow anidado (type=workflow)")
    
    # Ejecución
    execute: bool = Field(default=True, description="Habilitar/deshabilitar step")
    finally: bool = Field(default=False, description="Ejecutar siempre (cleanup)")
    
    # Nested steps (para parallel)
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="Steps anidados (type=parallel)")
    
    # Condition (para condition)
    condition: str | None = Field(None, description="Expresión CEL o callable (type=condition)")
    if_true: str | None = Field(None, description="Step ID si condition=true")
    if_false: str | None = Field(None, description="Step ID si condition=false")
    
    # Router (para router)
    expression: str | None = Field(None, description="Expresión CEL (type=router)")
    cases: Dict[str, str] = Field(default_factory=dict, description="Map valor→step_id (type=router)")
    
    # Loop (para loop)
    end_condition: str | None = Field(None, description="Condición de fin (type=loop)")
    max_iterations: int | None = Field(None, ge=1, description="Máximo de iteraciones (type=loop)")
    
    @field_validator("steps")
    @classmethod
    def validate_nested_steps(cls, v: List[Dict[str, Any]], info) -> List[Dict[str, Any]]:
        """Valida que steps solo existan en type=parallel"""
        step_type = info.data.get("type")
        if v and step_type != StepType.PARALLEL:
            raise ValueError("Nested steps only allowed for type=parallel")
        return v

class WorkflowConfig(BaseModel):
    """
    Agregado raíz de configuración de Workflow.
    
    Invariante: Un WorkflowConfig válido siempre tiene:
    - name no vacío
    - steps con IDs únicos
    - Referencias a agents/teams/workflows existentes (validación externa)
    """
    
    # Identidad
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None)
    
    # Primitivas
    steps: List[StepConfig] = Field(..., min_length=1, description="Pasos del workflow")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator("steps")
    @classmethod
    def validate_step_ids_unique(cls, v: List[StepConfig]) -> List[StepConfig]:
        """Valida que no haya step IDs duplicados"""
        step_ids = [s.step for s in v]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Duplicate step IDs detected in workflow")
        return v
    
    @field_validator("steps")
    @classmethod
    def validate_branch_references(cls, v: List[StepConfig]) -> List[StepConfig]:
        """Valida que if_true/if_false y cases referencien steps existentes"""
        step_ids = {s.step for s in v}
        
        for step in v:
            if step.if_true and step.if_true not in step_ids:
                raise ValueError(f"if_true references non-existent step: {step.if_true}")
            if step.if_false and step.if_false not in step_ids:
                raise ValueError(f"if_false references non-existent step: {step.if_false}")
            
            for case_value in step.cases.values():
                if case_value not in step_ids:
                    raise ValueError(f"Router case references non-existent step: {case_value}")
        
        return v
```

---

## 2. ENTITIES AND LIFECYCLE

### 2.1 Entidad: AgentInstance

**Estado Inicial**: Created (desde YAML)
**Transiciones**: Created → Initialized → Running → Completed/Failed

```python
# yaml-agno/src/models/runtime/agent_instance.py

from enum import Enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

class AgentState(str, Enum):
    """Estados del ciclo de vida de AgentInstance"""
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class AgentInstance(BaseModel):
    """
    Entidad que representa una instancia de Agent en runtime.
    
    Lifecycle:
    1. CREATED: Factory crea instancia desde config
    2. INITIALIZED: Agno Agent construido
    3. RUNNING: Agent.run() ejecutándose
    4. COMPLETED/FAILED: Ejecución terminada
    """
    
    # Identidad
    id: UUID = Field(default_factory=uuid4, description="ID único de instancia")
    config_name: str = Field(..., description="Nombre del AgentConfig origen")
    
    # Estado
    state: AgentState = Field(default=AgentState.CREATED, description="Estado actual")
    current_iteration: int = Field(default=0, ge=0, description="Iteración actual")
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp de creación")
    started_at: Optional[datetime] = Field(None, description="Timestamp de inicio")
    completed_at: Optional[datetime] = Field(None, description="Timestamp de completion")
    
    # Resultados
    result: Optional[str] = Field(None, description="Resultado final")
    error: Optional[str] = Field(None, description="Error si falló")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def transition_to(self, new_state: AgentState) -> None:
        """
        Transiciona estado con validación.
        
        Args:
            new_state: Nuevo estado
            
        Raises:
            ValueError: Si transición no es válida
        """
        valid_transitions = {
            AgentState.CREATED: [AgentState.INITIALIZED, AgentState.FAILED],
            AgentState.INITIALIZED: [AgentState.RUNNING, AgentState.FAILED],
            AgentState.RUNNING: [AgentState.COMPLETED, AgentState.FAILED],
            AgentState.COMPLETED: [],  # Terminal
            AgentState.FAILED: [],  # Terminal
        }
        
        if new_state not in valid_transitions[self.state]:
            raise ValueError(f"Invalid transition: {self.state} → {new_state}")
        
        self.state = new_state
        
        # Update timestamps
        if new_state == AgentState.RUNNING and not self.started_at:
            self.started_at = datetime.utcnow()
        if new_state in [AgentState.COMPLETED, AgentState.FAILED]:
            self.completed_at = datetime.utcnow()
    
    def is_terminal(self) -> bool:
        """Verifica si estado es terminal"""
        return self.state in [AgentState.COMPLETED, AgentState.FAILED]
    
    def duration_seconds(self) -> Optional[float]:
        """Calcula duración de ejecución en segundos"""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()
```

### 2.2 Entidad: SessionContext

**Estado Inicial**: Active
**Transiciones**: Active → Paused → Active | Closed

```python
# yaml-agno/src/models/runtime/session_context.py

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any

class SessionState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"

class SessionContext(BaseModel):
    """
    Entidad que representa contexto de sesión de usuario.
    
    Gestiona:
    - Historial de mensajes
    - Estado de agentes/teams en sesión
    - Metadata cross-session
    """
    
    # Identidad
    session_id: str = Field(..., description="ID único de sesión (user-defined)")
    user_id: str = Field(..., description="ID de usuario")
    tenant_id: str = Field(..., description="ID de tenant (multi-tenant)")
    
    # Estado
    state: SessionState = Field(default=SessionState.ACTIVE)
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    
    # Historial
    message_history: list[Dict[str, Any]] = Field(default_factory=list, description="Mensajes intercambiados")
    max_history_size: int = Field(default=100, ge=1, description="Máximo de mensajes en historial")
    
    # Estado de agentes
    agent_states: Dict[str, str] = Field(default_factory=dict, description="agent_name → state JSON")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_message(self, role: str, content: str, metadata: Dict[str, Any] | None = None) -> None:
        """
        Agrega mensaje al historial.
        
        Args:
            role: Rol (user|assistant|system|tool)
            content: Contenido del mensaje
            metadata: Metadata adicional
        """
        if len(self.message_history) >= self.max_history_size:
            # Remove oldest message (FIFO)
            self.message_history.pop(0)
        
        self.message_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        })
        
        self.last_activity = datetime.utcnow()
    
    def pause(self) -> None:
        """Pausa la sesión"""
        if self.state != SessionState.ACTIVE:
            raise ValueError(f"Cannot pause session in state: {self.state}")
        self.state = SessionState.PAUSED
    
    def resume(self) -> None:
        """Reanuda la sesión"""
        if self.state != SessionState.PAUSED:
            raise ValueError(f"Cannot resume session in state: {self.state}")
        self.state = SessionState.ACTIVE
    
    def close(self) -> None:
        """Cierra la sesión"""
        if self.state == SessionState.CLOSED:
            return  # Already closed
        self.state = SessionState.CLOSED
        self.closed_at = datetime.utcnow()
    
    def is_active(self) -> bool:
        """Verifica si sesión está activa"""
        return self.state == SessionState.ACTIVE
```

---

## 3. VALUE OBJECTS

### 3.1 Value Object: ModelId

**Invariante**: Siempre formato `provider/model_name`

```python
# yaml-agno/src/models/value_objects/model_id.py

from pydantic import BaseModel, Field, field_validator

class ModelId(BaseModel):
    """
    Value Object para identificadores de modelo.
    
    Invariante: Formato siempre válido provider/model
    """
    
    value: str = Field(..., pattern=r"^[a-z_]+/[a-z0-9_-]+$")
    
    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str) -> str:
        """Valida y normaliza"""
        parts = v.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid ModelId: {v}")
        return v.lower()  # Normalize to lowercase
    
    @property
    def provider(self) -> str:
        """Extrae provider"""
        return self.value.split("/")[0]
    
    @property
    def model_name(self) -> str:
        """Extrae model name"""
        return self.value.split("/")[1]
    
    def __str__(self) -> str:
        return self.value
```

### 3.2 Value Object: SessionKey

**Invariante**: Key única compuesta por `user_id:session_name`

```python
# yaml-agno/src/models/value_objects/session_key.py

from pydantic import BaseModel, Field

class SessionKey(BaseModel):
    """
    Value Object para clave de sesión.
    
    Invariante: Formato user_id:session_name (ú único)
    """
    
    user_id: str = Field(..., min_length=1)
    session_name: str = Field(..., min_length=1)
    
    @property
    def key(self) -> str:
        """Genera clave única"""
        return f"{self.user_id}:{self.session_name}"
    
    def __str__(self) -> str:
        return self.key
```

### 3.3 Value Object: DIReference

**Invariante**: Referencia a variable DI formato `${provider.key}`

```python
# yaml-agno/src/models/value_objects/di_reference.py

from pydantic import BaseModel, Field, field_validator

class DIReference(BaseModel):
    """
    Value Object para referencia de DI.
    
    Invariante: Formato ${provider.key} o ${provider.key.subkey}
    """
    
    template: str = Field(..., description="String con template ${provider.key}")
    
    @field_validator("template")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Valida que tenga formato ${...}"""
        import re
        if not re.match(r"^.*\$\{[a-z_]+(\.[a-z0-9_]+)*\}.*$", v):
            raise ValueError(f"Invalid DI reference format: {v}")
        return v
    
    @property
    def provider(self) -> str:
        """Extrae nombre del provider"""
        import re
        match = re.search(r"\$\{([a-z_]+)", self.template)
        return match.group(1) if match else ""
    
    @property
    def key(self) -> str:
        """Extrae key del provider"""
        import re
        match = re.search(r"\$\{[a-z_]+\.([a-z0-9_.]+)\}", self.template)
        return match.group(1) if match else ""
    
    def resolve(self, value: Any) -> str:
        """Resuelve template con valor"""
        return self.template.replace(f"${{{self.provider}.{self.key}}}", str(value))
```

---

## 4. DOMAIN EVENTS

### 4.1 Evento: AgentConfigCreated

**Cuándo se emite**: Después de validar y crear AgentConfig desde YAML

```python
# yaml-agno/src/domain/events/config_events.py

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Any

class AgentConfigCreated(BaseModel):
    """Evento de dominio: AgentConfig creada"""
    
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "AgentConfigCreated"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Payload
    config_name: str
    model_id: str
    tenant_id: str
    source_file: str  # Path del archivo YAML origen
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 4.2 Evento: AgentStateChanged

**Cuándo se emite**: Cuando AgentInstance cambia estado

```python
class AgentStateChanged(BaseModel):
    """Evento de dominio: Agent cambió estado"""
    
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "AgentStateChanged"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Payload
    agent_instance_id: UUID
    config_name: str
    old_state: AgentState
    new_state: AgentState
    iteration: int
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 4.3 Evento: SessionMessageAdded

**Cuándo se emite**: Cuando se agrega mensaje a SessionContext

```python
class SessionMessageAdded(BaseModel):
    """Evento de dominio: Mensaje agregado a sesión"""
    
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "SessionMessageAdded"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Payload
    session_id: str
    user_id: str
    role: str  # user|assistant|system|tool
    message_length: int
    has_tool_calls: bool
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 4.4 Evento: WorkflowStepCompleted

**Cuándo se emite**: Cuando un step de workflow se completa

```python
class WorkflowStepCompleted(BaseModel):
    """Evento de dominio: Step de workflow completado"""
    
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "WorkflowStepCompleted"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Payload
    workflow_name: str
    step_id: str
    step_type: StepType
    success: bool
    duration_seconds: float
    
    # Resultados
    result: str | None
    error: str | None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

---

## 5. BDD SCENARIOS - DOMAIN MODEL

### 5.1 Escenarios de Aceptación

#### Scenario 1: Golden Path - AgentConfig Validation

```gherkin
GIVEN a YAML string with valid agent configuration
  """
  agent:
    name: "test_agent"
    model: "openai/gpt-4o"
    instructions: "You are helpful"
  """
WHEN the YAML is parsed and validated
THEN AgentConfig instance is created
AND config.name equals "test_agent"
AND config.model equals "openai/gpt-4o"
AND config.get_provider() returns ModelProvider.OPENAI
AND config.get_model_name() returns "gpt-4o"
```

#### Scenario 2: Golden Path - TeamConfig with Members

```gherkin
GIVEN a YAML string with valid team configuration
  """
  team:
    name: "test_team"
    mode: coordinate
    members:
      - member: m1
        agent: agent1
      - member: m2
        agent: agent2
  """
WHEN the YAML is parsed and validated
THEN TeamConfig instance is created
AND config.mode equals TeamMode.COORDINATE
AND config.members has exactly 2 items
AND all member.member IDs are unique
```

#### Scenario 3: Error Case - Invalid Model Format

```gherkin
GIVEN a YAML string with invalid model format
  """
  agent:
    name: "test"
    model: "invalid-format"
  """
WHEN the YAML is parsed and validated
THEN ValidationError is raised
AND the error message mentions "Invalid model format"
```

#### Scenario 4: Error Case - Duplicate Step IDs

```gherkin
GIVEN a YAML string with duplicate step IDs
  """
  workflow:
    name: "test"
    steps:
      - step: step1
        type: agent
        agent: a1
      - step: step1
        type: agent
        agent: a2
  """
WHEN the YAML is parsed and validated
THEN ValidationError is raised
AND the error message mentions "Duplicate step IDs"
```

---

## 6. TDD MICRO-TASK EXECUTION PROTOCOL

### 6.1 Cascading Task Checklist

#### TASK_001: Define AgentConfig Pydantic Model

- **File**: `yaml-agno/src/models/config/agent_config.py`
- **Test**: `tests/unit/models/test_agent_config.py`
- **RED**:
  ```python
  def test_agent_config_creation():
      config = AgentConfig(name="test", model="openai/gpt-4o")
      assert config.name == "test"
      assert config.get_provider() == ModelProvider.OPENAI
  ```
- **GREEN**: Implementar `AgentConfig` con validadores
- **Commit**: `feat: add AgentConfig with Pydantic V2`

#### TASK_002: Add Model Format Validation

- **File**: `yaml-agno/src/models/config/agent_config.py`
- **Test**: `tests/unit/models/test_agent_config.py`
- **RED**:
  ```python
  def test_invalid_model_format_raises_error():
      with pytest.raises(ValidationError):
          AgentConfig(name="test", model="invalid")
  ```
- **GREEN**: Implementar `@field_validator("model")`
- **Commit**: `feat: add model format validation`

#### TASK_003: Define TeamConfig Pydantic Model

- **File**: `yaml-agno/src/models/config/team_config.py`
- **Test**: `tests/unit/models/test_team_config.py`
- **RED**:
  ```python
  def test_team_config_creation():
      config = TeamConfig(name="test", mode="coordinate")
      assert config.mode == TeamMode.COORDINATE
  ```
- **GREEN**: Implementar `TeamConfig` con `TeamMemberConfig`
- **Commit**: `feat: add TeamConfig Pydantic model`

#### TASK_004: Add Member Uniqueness Validation

- **File**: `yaml-agno/src/models/config/team_config.py`
- **Test**: `tests/unit/models/test_team_config.py`
- **RED**:
  ```python
  def test_duplicate_members_raise_error():
      with pytest.raises(ValidationError):
          TeamConfig(
              name="test",
              mode="coordinate",
              members=[
                  TeamMemberConfig(member="m1", agent="a1"),
                  TeamMemberConfig(member="m1", agent="a2")
              ]
          )
  ```
- **GREEN**: Implementar `@field_validator("members")`
- **Commit**: `feat: add member uniqueness validation`

#### TASK_005: Define WorkflowConfig Pydantic Model

- **File**: `yaml-agno/src/models/config/workflow_config.py`
- **Test**: `tests/unit/models/test_workflow_config.py`
- **RED**:
  ```python
  def test_workflow_config_creation():
      step = StepConfig(step="s1", type=StepType.AGENT, agent="a1")
      config = WorkflowConfig(name="test", steps=[step])
      assert len(config.steps) == 1
  ```
- **GREEN**: Implementar `WorkflowConfig` y `StepConfig`
- **Commit**: `feat: add WorkflowConfig Pydantic model`

#### TASK_006: Add Step ID Uniqueness Validation

- **File**: `yaml-agno/src/models/config/workflow_config.py`
- **Test**: `tests/unit/models/test_workflow_config.py`
- **RED**:
  ```python
  def test_duplicate_step_ids_raise_error():
      steps = [
          StepConfig(step="s1", type=StepType.AGENT, agent="a1"),
          StepConfig(step="s1", type=StepType.AGENT, agent="a2")
      ]
      with pytest.raises(ValidationError):
          WorkflowConfig(name="test", steps=steps)
  ```
- **GREEN**: Implementar `@field_validator("steps")`
- **Commit**: `feat: add step ID uniqueness validation`

#### TASK_007: Define AgentInstance Entity

- **File**: `yaml-agno/src/models/runtime/agent_instance.py`
- **Test**: `tests/unit/models/test_agent_instance.py`
- **RED**:
  ```python
  def test_agent_instance_creation():
      instance = AgentInstance(config_name="test")
      assert instance.state == AgentState.CREATED
  ```
- **GREEN**: Implementar `AgentInstance` con lifecycle
- **Commit**: `feat: add AgentInstance entity`

#### TASK_008: Add State Transition Validation

- **File**: `yaml-agno/src/models/runtime/agent_instance.py`
- **Test**: `tests/unit/models/test_agent_instance.py`
- **RED**:
  ```python
  def test_invalid_transition_raises_error():
      instance = AgentInstance(config_name="test")
      with pytest.raises(ValueError):
          instance.transition_to(AgentState.COMPLETED)
  ```
- **GREEN**: Implementar `transition_to()` con validación
- **Commit**: `feat: add state transition validation`

#### TASK_009: Define SessionContext Entity

- **File**: `yaml-agno/src/models/runtime/session_context.py`
- **Test**: `tests/unit/models/test_session_context.py`
- **RED**:
  ```python
  def test_session_context_creation():
      ctx = SessionContext(session_id="s1", user_id="u1", tenant_id="t1")
      assert ctx.state == SessionState.ACTIVE
  ```
- **GREEN**: Implementar `SessionContext`
- **Commit**: `feat: add SessionContext entity`

#### TASK_010: Add Message History Management

- **File**: `yaml-agno/src/models/runtime/session_context.py`
- **Test**: `tests/unit/models/test_session_context.py`
- **RED**:
  ```python
  def test_add_message_increases_history():
      ctx = SessionContext(session_id="s1", user_id="u1", tenant_id="t1", max_history_size=3)
      ctx.add_message("user", "Hello")
      assert len(ctx.message_history) == 1
  ```
- **GREEN**: Implementar `add_message()` con FIFO
- **Commit**: `feat: add message history with FIFO`

#### TASK_011: Define ModelId Value Object

- **File**: `yaml-agno/src/models/value_objects/model_id.py`
- **Test**: `tests/unit/value_objects/test_model_id.py`
- **RED**:
  ```python
  def test_model_id_creation():
      model_id = ModelId(value="openai/gpt-4o")
      assert model_id.provider == "openai"
      assert model_id.model_name == "gpt-4o"
  ```
- **GREEN**: Implementar `ModelId` VO
- **Commit**: `feat: add ModelId value object`

#### TASK_012: Define DIReference Value Object

- **File**: `yaml-agno/src/models/value_objects/di_reference.py`
- **Test**: `tests/unit/value_objects/test_di_reference.py`
- **RED**:
  ```python
  def test_di_reference_creation():
      ref = DIReference(template="${user_db.name}")
      assert ref.provider == "user_db"
      assert ref.key == "name"
  ```
- **GREEN**: Implementar `DIReference` VO
- **Commit**: `feat: add DIReference value object`

---

## 7. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] Pydantic V2 para Todos los Modelos de Dominio

**Justificación**: Pydantic V2 ofrece:
- 5-10x más rápido que V1
- Type hints nativos de Python 3.12
- `model_serializer`/`model_validator` para validación compleja
- Integración con FastAPI/SQLAlchemy para MVPs futuros

### [Decisión 2] Value Objects como Pydantic Models (frozen=True)

**Justificación**: Pydantic con `frozen=True` garantiza inmutabilidad:
- `model_config = ConfigDict(frozen=True)`
- Previne mutación accidental
- `__hash__` automático para usar en sets/dicts

### [Decisión 3] Domain Events como Pydantic Models (No Dataclasses)

**Justificación**: Pydantic permite:
- Serialización JSON automática para mensajería
- Validación de estructura en runtime
- Integración futura con event bus (Kafka/RabbitMQ)

---

## 8. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Cardinalidad de AgentConfig a AgentInstance

**¿Cuántas instancias de AgentInstance pueden existir por AgentConfig?**

Implica:
- **1:N** (Un config → muchas instancias) → Stateless, config es template
- **1:1** (Un config → una instancia) → Singleton por tenant
- **Trade-off**: Flexibilidad vs complejidad de lifecycle

### [Pregunta 2] Consistencia de SessionContext Across Threads

**¿SessionContext debe ser thread-safe para access concurrente?**

Implica:
- **Sí**: Requiere locks/asyncio.Lock overhead
- **No**: Asumir single-thread por session, documentar restricción
- **Trade-off**: Performance vs garantías de consistencia

### [Pregunta 3] Retención de Domain Events

**¿Por cuánto tiempo retener domain events y dónde?**

Implica:
- **En memoria**: 24h máximo, Redis cache
- **Persistido**: PostgreSQL con partición por fecha
- **Trade-off**: Storage cost vs capacidad de debugging/historial

---