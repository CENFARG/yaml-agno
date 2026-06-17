---
Spec_ID: "SPEC_06"
Title: "API and AX - REST Endpoints and Function Calling"
Version: "0.2.0-iter1"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#FastAPI", "#REST", "#AX", "#FunctionCalling"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02"]
Last_Updated: "2026-06-17"
Revision_Note: "Iter 1 cleanup. Engram removed from mandatory readiness/health (optional adapter). SPEC_02 added to Dependency_Hashes (API validates against *Config schemas). Readiness path and postgres key unified across BDD and code. Spanish docstrings/comments translated to English (Google style). Clarified this is an additional management/AX layer over AgentOS, not a duplication of Agno native /run endpoints."
---

# SPEC_06_API_AND_AX

> **Purpose**: Define the additional REST management layer and AX (function-calling) profiles for yaml-agno, plus health checks. This API is an ADDITIONAL management/AX layer mounted ON TOP of the Agno app served by AgentOS (`get_app()`). It does NOT duplicate Agno's native `/run` execution endpoints; it complements them with management, discovery, and observability surfaces. *Config schemas are the SSOT defined in SPEC_02; this API imports and validates against them rather than redefining them.

---

## 1. REST/RPC ENDPOINTS CONTRACTS

### 1.1 Endpoints Principales

| Método | Endpoint | Payload | Response | Descripción |
|--------|----------|---------|----------|-------------|
| POST | `/api/v1/agents/{name}/run` | AgentRunRequest | AgentRunResponse | Ejecutar agente |
| GET | `/api/v1/agents/{name}` | - | AgentConfigResponse | Obtener config |
| POST | `/api/v1/teams/{name}/run` | TeamRunRequest | TeamRunResponse | Ejecutar team |
| POST | `/api/v1/workflows/{name}/run` | WorkflowRunRequest | WorkflowRunResponse | Ejecutar workflow |
| GET | `/api/v1/sessions/{id}` | - | SessionContextResponse | Obtener sesión |
| DELETE | `/api/v1/sessions/{id}` | - | DeleteResponse | Eliminar sesión |

### 1.2 Agent Run Endpoint

```python
# yaml-agno/src/api/endpoints/agents.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

class MediaInput(BaseModel):
    """Multimodal media reference.

    @ai-directive: maps to Agno's native media classes (agno.media.Image /
    Audio / Video / File), which accept exactly one content source among
    `url` (remote), `filepath` (local) or `content` (raw bytes). Verified
    in agno/media.py v2.6.14. See SPEC_17 (Multimodal I/O) for full detail.
    """
    url: str | None = Field(None, description="Remote media location.")
    filepath: str | None = Field(None, description="Local media file path.")
    content: str | None = Field(None, description="Base64-encoded media bytes (transport only).")

class AgentRunRequest(BaseModel):
    """HTTP transport DTO for an agent run request.

    @ai-directive: this is an API-level DTO (request body), NOT the
    AgentConfig SSOT from SPEC_02. When the request references an agent by
    name, the resolved AgentConfig is loaded and validated against the
    SPEC_02 schema. SPEC_17 imports these DTOs from this module.

    Multimodal fields (images/audio/videos/files, send_media_to_model,
    store_media) are OWNED by this DTO; they map to the Agno Agent.run()
    kwargs of the same name (verified in agno/agent/agent.py v2.6.14).
    See SPEC_17 for the multimodal pipeline (validation, storage, ToolResult).
    """
    input: str | Dict[str, Any] = Field(..., max_length=10000, description="Input for the agent")
    session_id: str | None = Field(None, description="Existing session ID")
    user_id: str = Field(..., description="User ID")
    tenant_id: str = Field(..., description="Tenant ID")
    stream: bool = Field(default=False, description="Streaming response")
    max_iterations: int | None = Field(None, ge=1, le=100, description="Maximum iterations")
    # Multimodal input (Agno native kwargs)
    images: list[MediaInput] = Field(default_factory=list, description="Input images (Agno Image).")
    audio: list[MediaInput] = Field(default_factory=list, description="Input audio (Agno Audio).")
    videos: list[MediaInput] = Field(default_factory=list, description="Input videos (Agno Video).")
    files: list[MediaInput] = Field(default_factory=list, description="Input files (Agno File).")
    send_media_to_model: bool = Field(default=True, description="Send media to the model (Agno native kwarg).")
    store_media: bool = Field(default=False, description="Persist media artifacts (Agno native kwarg).")

class AgentRunResponse(BaseModel):
    """HTTP transport DTO for an agent run response.

    @ai-directive: API-level DTO (response body). SPEC_17 imports this DTO.
    Multimodal output (images/videos/audio) maps to Agno's RunOutput media
    fields (verified in agno/run/agent.py v2.6.14).
    """
    agent_name: str
    session_id: str
    result: Dict[str, Any]
    iterations: int
    duration_ms: float
    tool_calls: list[Dict[str, Any]] = Field(default_factory=list)
    # Multimodal output (Agno native RunOutput fields)
    images: list[MediaInput] = Field(default_factory=list, description="Generated/returned images.")
    audio: list[MediaInput] = Field(default_factory=list, description="Generated/returned audio.")
    videos: list[MediaInput] = Field(default_factory=list, description="Generated/returned videos.")

@router.post("/{name}/run", response_model=AgentRunResponse)
async def run_agent(
    name: str,
    request: AgentRunRequest,
    agent_service: AgentService = Depends()
) -> AgentRunResponse:
    """
    Executes an agent resolved from its YAML config.

    Raises:
        404: Agent not found
        400: Invalid input
        500: Execution error
    """
    try:
        result = await agent_service.run_agent(
            agent_name=name,
            user_input=request.input,
            session_id=request.session_id,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            stream=request.stream,
            max_iterations=request.max_iterations
        )
        return result
    
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AgentExecutionError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 1.3 Health Check Endpoints

```python
# yaml-agno/src/api/endpoints/health.py

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict

router = APIRouter(prefix="/health", tags=["health"])

class HealthResponse(BaseModel):
    """Health check response."""
    status: str  # healthy|degraded|unhealthy
    version: str
    dependencies: Dict[str, str]

class LivenessResponse(BaseModel):
    """Liveness probe response."""
    status: str  # alive|dead

class ReadinessResponse(BaseModel):
    """Readiness probe response."""
    status: str  # ready|not_ready
    checks: Dict[str, bool]

@router.get("/", response_model=HealthResponse)
async def health() -> HealthResponse:
    """General health check.

    Lists only MANDATORY dependencies. Engram is an OPTIONAL external MCP
    adapter and MUST NOT appear here; a missing Engram config does not make
    the service unhealthy.
    """
    return HealthResponse(
        status="healthy",
        version="0.1.0-MVP",
        dependencies={
            "postgres": "connected",
        }
    )

@router.get("/liveness", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """
    Liveness probe - is the process alive?

    Kubernetes uses this endpoint to restart the pod on failure.
    """
    return LivenessResponse(status="alive")

@router.get("/readiness", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """
    Readiness probe - is the service ready to receive traffic?

    Kubernetes uses this endpoint to remove the pod from rotation when
    not ready. Only MANDATORY dependencies gate readiness.

    @ai-directive: Engram is an OPTIONAL external MCP adapter. Its check
    MUST be skippable: if Engram is not configured, the probe skips it
    (returns "skipped") and MUST NOT mark the service not_ready. Only
    mandatory dependencies (e.g., postgres) can flip status to not_ready.
    """
    checks: Dict[str, bool] = {
        "postgres": await check_postgres(),
    }

    # Optional, non-gating Engram check. Reported for observability only.
    # @ai-directive: skipped/False here never forces not_ready.
    if is_engram_configured():
        checks["engram"] = await check_engram()
    else:
        checks["engram"] = False  # skipped, optional

    mandatory_ready = checks["postgres"]
    return ReadinessResponse(
        status="ready" if mandatory_ready else "not_ready",
        checks=checks
    )
```

### 1.4 Rate Limiting

```python
# yaml-agno/src/api/middleware/rate_limit.py

from fastapi import Request, HTTPException
from typing import Dict
import time

class RateLimiter:
    """
    Rate limiter by tenant and IP.

    Limits:
    - Per tenant: 100 requests/minute
    - Per IP: 20 requests/minute
    """

    def __init__(self):
        # tenant_id -> {timestamp, count}
        self.tenant_buckets: Dict[str, Dict[str, int]] = {}
        # ip -> {timestamp, count}
        self.ip_buckets: Dict[str, Dict[str, int]] = {}

        self.tenant_limit = 100  # requests per minute
        self.ip_limit = 20  # requests per minute
        self.window = 60  # seconds

    async def check_rate_limit(
        self,
        tenant_id: str,
        client_ip: str
    ) -> None:
        """
        Checks rate limits.

        Raises:
            HTTPException: 429 Too Many Requests
        """
        now = int(time.time())

        # Check tenant limit
        if not self._check_bucket(self.tenant_buckets, tenant_id, now, self.tenant_limit):
            raise HTTPException(
                status_code=429,
                detail=f"Tenant rate limit exceeded: {self.tenant_limit} req/min"
            )

        # Check IP limit
        if not self._check_bucket(self.ip_buckets, client_ip, now, self.ip_limit):
            raise HTTPException(
                status_code=429,
                detail=f"IP rate limit exceeded: {self.ip_limit} req/min"
            )

    def _check_bucket(
        self,
        buckets: Dict[str, Dict[str, int]],
        key: str,
        now: int,
        limit: int
    ) -> bool:
        """Checks whether the bucket allows the request."""
        if key not in buckets:
            buckets[key] = {"timestamp": now, "count": 0}

        bucket = buckets[key]

        # Reset if the window has expired
        if now - bucket["timestamp"] >= self.window:
            bucket = {"timestamp": now, "count": 0}
            buckets[key] = bucket

        # Check limit
        if bucket["count"] >= limit:
            return False

        bucket["count"] += 1
        return True
```

---

## 2. AX FUNCTION CALLING (JSON SCHEMAS)

### 2.1 AX Profile para Agent Creation

```json
{
  "name": "create_agent",
  "description": "Creates a new agent configuration from YAML",
  "parameters": {
    "type": "object",
    "properties": {
      "tenant_id": {
        "type": "string",
        "description": "UUID of the tenant"
      },
      "name": {
        "type": "string",
        "description": "Agent name (unique per tenant)"
      },
      "model": {
        "type": "string",
        "description": "Model ID (e.g., openai/gpt-4o)"
      },
      "instructions": {
        "type": "string",
        "description": "System prompt for the agent"
      },
      "tools": {
        "type": "array",
        "items": {"type": "object"},
        "description": "List of tool configurations"
      }
    },
    "required": ["tenant_id", "name", "model"]
  }
}
```

### 2.2 AX Profile para Agent Execution

```json
{
  "name": "run_agent",
  "description": "Executes an agent and returns the result",
  "parameters": {
    "type": "object",
    "properties": {
      "agent_name": {
        "type": "string",
        "description": "Name of the agent to execute"
      },
      "input": {
        "oneOf": [
          {"type": "string"},
          {"type": "object"}
        ],
        "description": "Input for the agent (text or structured)"
      },
      "session_id": {
        "type": "string",
        "description": "Optional session ID for continuity"
      },
      "user_id": {
        "type": "string",
        "description": "User ID executing the agent"
      }
    },
    "required": ["agent_name", "input", "user_id"]
  }
}
```

### 2.3 AX Profile para Team Execution

```json
{
  "name": "run_team",
  "description": "Executes a team of agents and returns the result",
  "parameters": {
    "type": "object",
    "properties": {
      "team_name": {
        "type": "string",
        "description": "Name of the team to execute"
      },
      "input": {
        "type": "object",
        "description": "Input for the team"
      },
      "user_id": {
        "type": "string",
        "description": "User ID executing the team"
      }
    },
    "required": ["team_name", "input", "user_id"]
  }
}
```

---

## 3. BEHAVIOR DELTA - BDD SCENARIOS

### 3.1 Acceptance Scenarios

#### Scenario 1: Golden Path - Agent Execution via API

```gherkin
GIVEN an agent configuration exists
AND the agent is active
WHEN POST /api/v1/agents/my_agent/run is called
AND the request body contains valid input
THEN the response status is 200
AND the response contains result from the agent
AND the session_id is returned
AND the duration_ms is populated
```

#### Scenario 2: Error Case - Agent Not Found

```gherkin
GIVEN an agent configuration does NOT exist
WHEN POST /api/v1/agents/nonexistent/run is called
THEN the response status is 404
AND the error message mentions "Agent not found"
```

#### Scenario 3: Golden Path - Health Check

```gherkin
GIVEN the service is running
AND all dependencies are connected
WHEN GET /health is called
THEN the response status is 200
AND the status field is "healthy"
AND all dependencies show "connected"
```

#### Scenario 4: Error Case - Readiness Fails

```gherkin
GIVEN the service is running
BUT PostgreSQL is disconnected
WHEN GET /health/readiness is called
THEN the response status is 503
AND the status field is "not_ready"
AND the checks.postgres is false
```

---

## 4. TDD MICRO-TASK EXECUTION PROTOCOL

### 4.1 Cascading Task Checklist

#### TASK_001: Define AgentRunRequest Model

- **File**: `yaml-agno/src/api/models/agents.py`
- **Test**: `tests/unit/api/test_agent_models.py`
- **RED**:
  ```python
  def test_agent_run_request_validation():
      req = AgentRunRequest(
          input="test input",
          user_id="user1",
          tenant_id="tenant1"
      )
      assert req.input == "test input"
  ```
- **GREEN**: Implement `AgentRunRequest` with Pydantic
- **Commit**: `feat: add AgentRunRequest model`

#### TASK_002: Define AgentRunResponse Model

- **File**: `yaml-agno/src/api/models/agents.py`
- **Test**: `tests/unit/api/test_agent_models.py`
- **RED**:
  ```python
  def test_agent_run_response_validation():
      resp = AgentRunResponse(
          agent_name="test",
          session_id="s1",
          result={"output": "test"},
          iterations=1,
          duration_ms=100.5
      )
      assert resp.agent_name == "test"
  ```
- **GREEN**: Implement `AgentRunResponse` with Pydantic
- **Commit**: `feat: add AgentRunResponse model`

#### TASK_003: Implement Run Agent Endpoint

- **File**: `yaml-agno/src/api/endpoints/agents.py`
- **Test**: `tests/integration/api/test_agent_endpoints.py`
- **RED**:
  ```python
  async def test_run_agent_endpoint(client, agent_service):
      response = await client.post(
          "/api/v1/agents/test/run",
          json={
              "input": "test",
              "user_id": "user1",
              "tenant_id": "tenant1"
          }
      )
      assert response.status_code == 200
  ```
- **GREEN**: Implement `run_agent()` endpoint
- **Commit**: `feat: add run agent endpoint`

#### TASK_004: Implement Health Check Endpoint

- **File**: `yaml-agno/src/api/endpoints/health.py`
- **Test**: `tests/integration/api/test_health_endpoints.py`
- **RED**:
  ```python
  async def test_health_endpoint(client):
      response = await client.get("/health")
      assert response.status_code == 200
      data = response.json()
      assert data["status"] == "healthy"
  ```
- **GREEN**: Implement `health()` endpoint
- **Commit**: `feat: add health check endpoint`

#### TASK_005: Implement Readiness Probe

- **File**: `yaml-agno/src/api/endpoints/health.py`
- **Test**: `tests/integration/api/test_health_endpoints.py`
- **RED**:
  ```python
  async def test_readiness_endpoint(client):
      response = await client.get("/health/readiness")
      assert response.status_code == 200
      data = response.json()
      assert "status" in data
      assert "checks" in data
  ```
- **GREEN**: Implement `readiness()` endpoint
- **Commit**: `feat: add readiness probe`

#### TASK_006: Define AX Schemas

- **File**: `yaml-agno/src/api/ax/schemas.py`
- **Test**: `tests/unit/api/test_ax_schemas.py`
- **RED**:
  ```python
  def test_create_agent_ax_schema():
      schema = get_ax_schema("create_agent")
      assert schema["name"] == "create_agent"
      assert "parameters" in schema
  ```
- **GREEN**: Implement `get_ax_schema()` function
- **Commit**: `feat: add AX schema definitions`

---

## 5. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decision 1] FastAPI for REST API

**Justificación**:
- Soporte nativo para async/await
- Validación automática con Pydantic
- OpenAPI schema generation
- WebSocket support para streaming

### [Decision 2] Liveness vs Readiness Separation

**Justificación**:
- **Liveness**: Proceso vivo (siempre true si running)
- **Readiness**: Listo para tráfico (depende de dependencies)
- Kubernetes necesita ambos para rolling updates

### [Decision 3] AX Schemas for Function Calling

**Justificación**:
- Estándar de facto para AI function calling
- Compatible con OpenAI, Anthropic, Google
- Permite discovery de tools vía API

---

## 6. STRATEGIC CALIBRATION QUESTIONS

### [Pregunta 1] Streaming Response

**¿El endpoint /run debe soportar Server-Sent Events (SSE) para streaming?**

Implica:
- **Sí**: Mejor UX para respuestas largas, más complejidad
- **No**: Más simple, polling alternativo
- **Trade-off**: UX vs complejidad de implementación

### [Pregunta 2] Rate Limiting

**¿Debería haber rate limiting por tenant/user en los endpoints?**

Implica:
- **Sí**: Previene abuso, requiere infra adicional
- **No**: Más simple, deja rate limiting a gateway
- **Trade-off**: Security vs simplicidad

### [Pregunta 3] API Versioning

**¿Estrategia de versioning: /api/v1/ vs Accept header?**

Implica:
- **URL versioning**: Más explícito, breaking changes obvios
- **Header versioning**: URLs más limpias, menos visible
- **Trade-off**: Claridad vs limpieza

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
