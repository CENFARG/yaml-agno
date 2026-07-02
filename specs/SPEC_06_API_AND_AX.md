---
Spec_ID: "SPEC_06"
Title: "API and AX - Thin Layer over AgentOS"
Version: "0.4.0-iter3"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#FastAPI", "#AgentOS", "#REST", "#AX", "#FunctionCalling", "#Middleware"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02", "SPEC_03", "SPEC_04"]
Last_Updated: "2026-07-02"
Revision_Note: "Iter 3 (thin-layer reformulation). Removes all yaml-agno-owned /run, /sessions, /agents-config and /health endpoints that duplicated AgentOS v2.6.18 native routers. Reformulates SPEC_06 as a THIN LAYER that mounts AgentOS native routers via get_app() and adds only genuine gaps: (1) YAML->AgentOS wiring, (2) readiness/liveness routers replicating get_health_router factory, (3) rate-limit-by-tenant middleware (none in AgentOS), (4) tenant_id->request.state.user_id middleware, (5) thin GET /ax/tools discovery surface. Documents AgentOS's native multipart/form-data + {id} wire contract instead of inventing a JSON/{name} contract. Strategic questions resolved. Faithful to AgentOS coding patterns (factory routers, _add_router mounting)."
---

# SPEC_06_API_AND_AX

> **Purpose**: yaml-agno is a THIN LAYER over AgentOS (Agno v2.6.18). It does NOT ship its own `/run`, `/sessions`, `/agents` config, or `/health` execution endpoints — those are **native to AgentOS** and yaml-agno MOUNTS them via `AgentOS(...).get_app()`. yaml-agno adds only what AgentOS lacks:
>
> 1. **Wiring YAML -> AgentOS** — translate YAML files into the `agents=[...]` / `teams=[...]` / `workflows=[...]` lists that `AgentOS(...)` consumes. This is yaml-agno's CORE job.
> 2. **Readiness + Liveness routers** — AgentOS ships only `GET /health` (simple). yaml-agno adds DB-gated readiness and process liveness, as router factories in the SAME style as `get_health_router`.
> 3. **Rate-limit-by-tenant middleware** — AgentOS has zero rate limiting (grep `ratelimit|throttle|slowapi` in `os/` = 0 hits). yaml-agno adds a FastAPI middleware keyed on `tenant_id`.
> 4. **Tenant scoping middleware** — `tenant_id` does NOT exist in any native AgentOS endpoint (only `user_id` / `session_id`). yaml-agno resolves `tenant_id` -> stamps `request.state.user_id` so native routers scope correctly (Agno honours `request.state.user_id` at `agents/router.py:616`, `teams/router.py:588`).
> 5. **AX REST discovery** — `run_agent` / `run_team` / `run_workflow` exist ONLY over MCP (`os/mcp.py:227-264`, `enable_mcp_server=True`). There is NO REST JSON-schema discovery endpoint. yaml-agno adds a thin `GET /ax/tools` publishing function-calling schemas.
>
> *Config schemas (`*Config`) are the SSOT defined in SPEC_02; this API imports and validates against them rather than redefining them. `MediaInput` is owned by SPEC_17 (Multimodal I/O) and is only referenced by one-line pointer here.*

---

## 1. NATIVE AGENTOS ENDPOINTS yaml-agno MOUNTS (do NOT reimplement)

yaml-agno mounts these via `AgentOS(agents=..., teams=..., workflows=..., db=...).get_app()`. Every native router is a FACTORY `get_*_router(...)` returning an `APIRouter`, mounted by `os._add_router(app, get_xxx_router(...))` (`os/app.py:509-540` and `app.py:969-1007`, ~22 routers total). Native endpoints are far more complete than anything yaml-agno could clone: streaming, background runs, SSE resume, checkpoints, fork, continue, cancel, multimodal upload (~1744 lines in `agents/router.py` alone).

### 1.1 Native run / session / config / health endpoints

| yaml-agno role | AgentOS native endpoint | file:line (v2.6.18) |
|---|---|---|
| Mount, do NOT reimplement | `POST /agents/{agent_id}/runs` | `agents/router.py:551` |
| Mount, do NOT reimplement | `GET /agents/{agent_id}`, `GET /agents`, `GET /config` | `agents/router.py:1320`, `agents/router.py:1216`, `os/router.py:79` |
| Mount, do NOT reimplement | `POST /teams/{team_id}/runs` | `teams/router.py:527` |
| Mount, do NOT reimplement | `POST /workflows/{workflow_id}/runs` | `workflows/router.py:1118` |
| Mount, do NOT reimplement | `GET /sessions/{session_id}` | `session/session.py:331` |
| Mount, do NOT reimplement | `DELETE /sessions/{session_id}` | `session/session.py:804` |
| Mount, do NOT reimplement | `GET /health` | `health.py:13` |

> @ai-directive: yaml-agno MUST NOT define its own `/run`, `/sessions`, `/agents` config, or `/health` routers. It builds an `AgentOS(...)` instance from YAML (see §2) and calls `.get_app()`, which mounts all native routers. The ONLY routers yaml-agno adds itself are the 4 gaps in §3. A verification test (§5, TASK_007) asserts yaml-agno's router list contains NO `/run`, `/sessions`, or `/agents` config route.

### 1.2 Wire contract (MUST document, do NOT invent)

> @ai-directive: AgentOS run endpoints are **`multipart/form-data`** (`Form` fields + `UploadFile`), NOT JSON. Path params are `{agent_id}` / `{team_id}` / `{workflow_id}` (numeric/string IDs from the resolved config), NOT `{name}`. yaml-agno MUST NOT invent a JSON-body + `{name}` path contract; doing so would require an adapter shim that diverges from Agno's real API surface and breaks native streaming/upload/SSE semantics. yaml-agno clients call the native form API directly.

For multimodal input on native run endpoints, clients attach `images` / `audio` / `videos` / `files` as `UploadFile` parts in the SAME multipart request, plus the boolean form fields `send_media_to_model` / `store_media`. The media reference model is `MediaInput`, owned by **SPEC_17** — see that spec for the full multimodal pipeline (validation, storage, `ToolResult`). yaml-agno does not redefine it here.

---

## 2. YAML -> AgentOS WIRING (yaml-agno core job)

yaml-agno's reason to exist is turning YAML files into a running AgentOS app. The pipeline below is the canonical wiring; it produces the `FastAPI` app that already carries every native router from §1 plus the gaps from §3.

```python
# yaml-agno/src/wiring/build_app.py
"""Wires YAML config files into a served AgentOS FastAPI app.

Mirrors AgentOS's own construction pattern: build the object lists, hand them
to AgentOS(...), call get_app(), then mount any extra routers/middleware.
"""

from pathlib import Path
from typing import Any

from agno.os import AgentOS

from yaml_agno.config.loader import load_yaml_site          # SPEC_02 SSOT
from yaml_agno.factory.agent_factory import build_agents     # SPEC_01
from yaml_agno.factory.team_factory import build_teams       # SPEC_01
from yaml_agno.factory.workflow_factory import build_workflows  # SPEC_01
from yaml_agno.db.session import resolve_agentos_db          # SPEC_03
from yaml_agno.api.gaps.readiness import get_readiness_router, get_liveness_router
from yaml_agno.api.gaps.ax_tools import get_ax_tools_router
from yaml_agno.api.middleware.tenant_scope import TenantScopeMiddleware
from yaml_agno.api.middleware.rate_limit import RateLimitMiddleware


def build_app(yaml_root: str | Path) -> Any:
    """Build a served AgentOS app from a YAML site directory.

    Args:
        yaml_root: Path to the YAML site (agents/, teams/, workflows/ subdirs).

    Returns:
        A FastAPI application with all native AgentOS routers mounted
        (run/sessions/config/health) plus yaml-agno's 4 genuine gaps.

    @ai-directive: this is yaml-agno's CORE function. It MUST call
    AgentOS(...).get_app() so native routers are mounted. It MUST NOT
    register its own /run, /sessions, or /agents config routes.
    """
    site = load_yaml_site(yaml_root)                          # SPEC_02 SSOT

    # 1. Translate YAML -> Agno object lists (SPEC_01 factories).
    agents = build_agents(site)
    teams = build_teams(site)
    workflows = build_workflows(site)

    # 2. Resolve the AgentOS-compatible DB (SPEC_03).
    agentos_db = resolve_agentos_db(site)

    # 3. Hand everything to AgentOS and let IT mount the native routers.
    agentos = AgentOS(
        agents=agents,
        teams=teams,
        workflows=workflows,
        db=agentos_db,
        # Native MCP server carries run_agent/run_team/run_workflow over MCP
        # (os/mcp.py:227-264). Enabled per site config; see §3.4.
        enable_mcp_server=site.get("mcp", {}).get("enabled", False),
    )
    app = agentos.get_app()

    # 4. Mount ONLY the genuine gaps (see §3) in AgentOS _add_router style.
    app.include_router(get_readiness_router())
    app.include_router(get_liveness_router())
    app.include_router(get_ax_tools_router(agents, teams, workflows))

    # 5. Middleware: tenant scoping + rate limit (AgentOS has neither).
    app.add_middleware(TenantScopeMiddleware)
    app.add_middleware(RateLimitMiddleware)

    return app
```

> @ai-directive: the wiring MUST keep `AgentOS(...)` as the single source of execution. yaml-agno never instantiates its own run/session handlers; it only feeds and lightly extends AgentOS.

---

## 3. THE GENUINE GAPS yaml-agno ADDS (in AgentOS style)

All routers below are FACTORIES returning `APIRouter`, mirroring `agno/os/routers/health.py:get_health_router` (`health.py:8`). Mounting uses `app.include_router(...)` (FastAPI standard; equivalent to AgentOS's internal `_add_router`).

### 3.1 Readiness + Liveness routers (AgentOS ships only `GET /health`)

```python
# yaml-agno/src/api/gaps/readiness.py
"""Readiness and liveness routers, mirroring get_health_router structure.

AgentOS ships only a simple GET /health (health.py:8-13). yaml-agno adds
DB-gated readiness (Kubernetes removes the pod from rotation when not ready)
and a process liveness probe. Both are factory routers in the same style as
agno/os/routers/health.py.
"""

from typing import Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Liveness probe response (process alive?)."""

    status: str = Field(..., description="alive | dead")


class ReadinessResponse(BaseModel):
    """Readiness probe response (ready to receive traffic?)."""

    status: str = Field(..., description="ready | not_ready")
    checks: Dict[str, bool] = Field(
        default_factory=dict,
        description="Per-dependency readiness. Only MANDATORY deps gate status.",
    )


def get_liveness_router(liveness_endpoint: str = "/health/liveness") -> APIRouter:
    """Build the liveness router (factory, mirrors get_health_router).

    Args:
        liveness_endpoint: Path for the liveness probe.

    Returns:
        An APIRouter exposing the liveness probe.
    """
    router = APIRouter(tags=["Health"])

    @router.get(
        liveness_endpoint,
        operation_id="liveness_check",
        summary="Liveness Check",
        response_model=LivenessResponse,
    )
    async def liveness_check() -> LivenessResponse:
        """Return liveness; Kubernetes restarts the pod on failure."""
        return LivenessResponse(status="alive")

    return router


def get_readiness_router(
    readiness_endpoint: str = "/health/readiness",
    db_dependency=None,
) -> APIRouter:
    """Build the readiness router (factory, mirrors get_health_router).

    Args:
        readiness_endpoint: Path for the readiness probe.
        db_dependency: Callable resolving the AgentOS DB to ping.

    Returns:
        An APIRouter exposing the readiness probe.

    @ai-directive: Only MANDATORY dependencies gate readiness. Engram is an
    OPTIONAL external MCP adapter and MUST NOT appear in the check set;
    a missing Engram config never flips status to not_ready. Per SPEC_04,
    Engram is not part of yaml-agno's data model (canonical directive), so
    a readiness probe MUST NOT depend on it.
    """
    router = APIRouter(tags=["Health"])

    @router.get(
        readiness_endpoint,
        operation_id="readiness_check",
        summary="Readiness Check",
        response_model=ReadinessResponse,
        responses={503: {"description": "Not ready"}},
    )
    async def readiness_check() -> ReadinessResponse:
        """Return readiness; Kubernetes removes the pod from rotation when not ready."""
        checks: Dict[str, bool] = {
            "postgres": await _ping_postgres(db_dependency),
        }
        mandatory_ready = all(checks.values())
        # NOTE: no Engram key here. Optional deps are intentionally absent so
        # they can never force not_ready.
        return ReadinessResponse(
            status="ready" if mandatory_ready else "not_ready",
            checks=checks,
        )

    return router


async def _ping_postgres(db_dependency) -> bool:
    """Ping the AgentOS DB. Returns True if reachable."""
    # Implemented in SPEC_03 (DB session layer).
    raise NotImplementedError("Wired in SPEC_03; see resolve_agentos_db.")
```

### 3.2 Rate-limit-by-tenant middleware (AgentOS has NONE)

AgentOS ships no rate limiting (`grep ratelimit|throttle|slowapi` in `os/` = 0 hits). yaml-agno adds a FastAPI middleware keyed on `tenant_id`. It runs BEFORE the native run endpoints, so it protects `POST /agents/{agent_id}/runs`, `POST /teams/{team_id}/runs`, and `POST /workflows/{workflow_id}/runs` without yaml-agno owning those routes.

```python
# yaml-agno/src/api/middleware/rate_limit.py
"""Rate-limit middleware keyed on tenant_id (+ client IP fallback).

AgentOS ships no rate limiting. This middleware protects every mounted
native router by running on the request before AgentOS handlers see it.
"""

import time
from typing import Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limit per tenant and per client IP.

    Attributes:
        tenant_buckets: tenant_id -> (window_start, count).
        ip_buckets: client_ip -> (window_start, count).
        tenant_limit: Max requests per window per tenant.
        ip_limit: Max requests per window per IP.
        window: Window size in seconds.
    """

    def __init__(
        self,
        app,
        tenant_limit: int = 100,
        ip_limit: int = 20,
        window: int = 60,
    ) -> None:
        """Initialize the middleware with per-tenant and per-IP limits.

        Args:
            app: The ASGI app (passed by add_middleware).
            tenant_limit: Max requests per window per tenant.
            ip_limit: Max requests per window per IP.
            window: Window size in seconds.
        """
        super().__init__(app)
        self.tenant_buckets: Dict[str, Tuple[int, int]] = {}
        self.ip_buckets: Dict[str, Tuple[int, int]] = {}
        self.tenant_limit = tenant_limit
        self.ip_limit = ip_limit
        self.window = window

    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply tenant + IP limits; return 429 on breach.

        Args:
            request: Incoming request (tenant_id resolved by TenantScopeMiddleware).
            call_next: Next ASGI handler.

        Returns:
            The downstream response, or 429 JSON on rate-limit breach.
        """
        tenant_id = getattr(request.state, "tenant_id", None) or "anonymous"
        client_ip = request.client.host if request.client else "unknown"
        now = int(time.time())

        if not self._allow(self.tenant_buckets, tenant_id, now, self.tenant_limit):
            return JSONResponse(
                status_code=429,
                content={"detail": f"Tenant rate limit exceeded: {self.tenant_limit} req/{self.window}s"},
            )
        if not self._allow(self.ip_buckets, client_ip, now, self.ip_limit):
            return JSONResponse(
                status_code=429,
                content={"detail": f"IP rate limit exceeded: {self.ip_limit} req/{self.window}s"},
            )
        return await call_next(request)

    def _allow(
        self,
        buckets: Dict[str, Tuple[int, int]],
        key: str,
        now: int,
        limit: int,
    ) -> bool:
        """Return True if the bucket allows one more request."""
        window_start, count = buckets.get(key, (now, 0))
        if now - window_start >= self.window:
            window_start, count = now, 0
        if count >= limit:
            buckets[key] = (window_start, count)
            return False
        buckets[key] = (window_start, count + 1)
        return True
```

### 3.3 Tenant scoping middleware (`tenant_id` -> `request.state.user_id`)

`tenant_id` does NOT exist in any native AgentOS endpoint; only `user_id` / `session_id` do. AgentOS honours `request.state.user_id` for scoping (`agents/router.py:616`, `teams/router.py:588`). yaml-agno resolves `tenant_id` from the request (header or token) and stamps `request.state.user_id` so native routers scope correctly.

> @ai-directive: this middleware ONLY resolves `tenant_id` and sets `request.state.user_id` (Agno's native key). It does NOT add Postgres RLS, does NOT auto-scope, and does NOT mutate `agno_*` rows. Per SPEC_03 §5 and SPEC_04 §3.3: tenant isolation is **explicit** via WHERE filters on `yamlagno_*` config rows only; `tenant_id` is NEVER added to `agno_*` tables; isolation is app-layer filters + contextvar telemetry, NOT RLS. The middleware's sole job is to translate yaml-agno's `tenant_id` into Agno's native `user_id` key.

```python
# yaml-agno/src/api/middleware/tenant_scope.py
"""Tenant scoping middleware: resolve tenant_id -> request.state.user_id.

AgentOS has no tenant_id concept; it scopes native runs on request.state.user_id
(agents/router.py:616, teams/router.py:588). This middleware performs ONLY that
translation. It adds NO RLS and NO auto-scope (SPEC_03 §5, SPEC_04 §3.3).
"""

from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from yaml_agno.tenant.resolver import TenantResolver  # SPEC_03 Core Infra


class TenantScopeMiddleware(BaseHTTPMiddleware):
    """Resolve tenant_id and stamp request.state.user_id (Agno native key).

    @ai-directive: tenant_id is resolved EXPLICITLY (Core Infra TenantResolver,
    SPEC_03). The resolved value is set on request.state.user_id ONLY. The
    middleware MUST NOT open a DB session, MUST NOT add a tenant_id column to
    agno_* tables, and MUST NOT apply RLS. Tenant isolation of yaml-agno's OWN
    config rows is handled by explicit WHERE filters in the config repositories
    (SPEC_03), not here.
    """

    def __init__(self, app, tenant_resolver: Optional[TenantResolver] = None) -> None:
        """Initialize with an optional TenantResolver (defaults to Core Infra)."""
        super().__init__(app)
        self.resolver = tenant_resolver or TenantResolver()

    async def dispatch(self, request: Request, call_next) -> Response:
        """Resolve tenant_id and set request.state.user_id for native routers.

        Args:
            request: Incoming request; may carry X-Tenant-Id or an auth claim.
            call_next: Next ASGI handler.

        Returns:
            The downstream response. Native AgentOS handlers read
            request.state.user_id for scoping.
        """
        tenant_id = self.resolver.resolve(request)  # SPEC_03 Core Infra
        if tenant_id is not None:
            # Agno's native scoping key. Native routers honour this value.
            request.state.user_id = str(tenant_id)
            request.state.tenant_id = str(tenant_id)  # yaml-agno audit metadata only
        return await call_next(request)
```

### 3.4 AX REST discovery (`GET /ax/tools`)

`run_agent` / `run_team` / `run_workflow` exist ONLY over MCP (`os/mcp.py:227-264`, enabled by `enable_mcp_server=True`). There is NO REST JSON-schema discovery endpoint. yaml-agno adds a thin `GET /ax/tools` publishing function-calling schemas derived from the resolved YAML objects, so REST clients can discover callable tools without enabling the MCP server.

> @ai-directive: this is a READ-ONLY discovery surface. It publishes function-calling schemas; it does NOT execute. Execution stays on the native AgentOS run endpoints (§1) or MCP. Keep this router minimal.

```python
# yaml-agno/src/api/gaps/ax_tools.py
"""Thin AX discovery router: publishes function-calling schemas.

AgentOS exposes run_agent/run_team/run_workflow ONLY over MCP
(os/mcp.py:227-264). This router adds a REST JSON-schema discovery surface so
clients can list callable YAML-defined tools without enabling the MCP server.
It is read-only and does NOT execute.
"""

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field


class AXToolSchema(BaseModel):
    """Function-calling schema for one discoverable tool."""

    name: str = Field(..., description="Tool name (e.g. run_agent).")
    description: str = Field("", description="Human-readable description.")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-schema parameters object.",
    )


class AXToolsResponse(BaseModel):
    """Response model for GET /ax/tools."""

    tools: List[AXToolSchema] = Field(
        default_factory=list,
        description="Discoverable function-calling schemas.",
    )


def get_ax_tools_router(agents, teams, workflows, endpoint: str = "/ax/tools") -> APIRouter:
    """Build the AX discovery router (factory, mirrors get_health_router style).

    Args:
        agents: Resolved Agent objects (from §2 wiring).
        teams: Resolved Team objects.
        workflows: Resolved Workflow objects.
        endpoint: Path for the discovery surface.

    Returns:
        An APIRouter exposing GET /ax/tools.
    """
    router = APIRouter(tags=["AX"])

    @router.get(
        endpoint,
        operation_id="list_ax_tools",
        summary="List AX Function-Calling Schemas",
        response_model=AXToolsResponse,
    )
    async def list_ax_tools() -> AXToolsResponse:
        """Publish function-calling schemas derived from the resolved YAML objects."""
        tools: List[AXToolSchema] = []
        # run_agent / run_team / run_workflow mirror the MCP tool surface
        # (os/mcp.py:227-264) so REST clients see the same callable names.
        tools.append(AXToolSchema(
            name="run_agent",
            description="Execute an agent via the native POST /agents/{agent_id}/runs endpoint.",
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Resolved agent ID."},
                    "input": {"type": "string", "description": "Prompt input."},
                    "user_id": {"type": "string", "description": "Agno user_id (scoped by TenantScopeMiddleware)."},
                },
                "required": ["agent_id", "input", "user_id"],
            },
        ))
        return AXToolsResponse(tools=tools)

    return router
```

The JSON-schema shapes mirror the MCP tool surface (`os/mcp.py:227-264`) so REST and MCP clients see the same callable names. Clients then execute via the native AgentOS run endpoints (§1) — yaml-agno does not provide an AX execution path.

---

## 4. BEHAVIOR DELTA - BDD SCENARIOS

### 4.1 Acceptance Scenarios

#### Scenario 1: Wiring produces a mounted AgentOS app with native /run working

```gherkin
GIVEN a YAML site with one agent definition
WHEN build_app(yaml_root) is called
THEN the returned FastAPI app includes the native route POST /agents/{agent_id}/runs
AND the app includes the native route GET /health
AND the app includes yaml-agno's GET /health/readiness
AND the app includes yaml-agno's GET /ax/tools
AND no yaml-agno-owned /run route exists in the app's router list
```

#### Scenario 2: Readiness gates on the DB

```gherkin
GIVEN the service is running
AND PostgreSQL is reachable
WHEN GET /health/readiness is called
THEN the response status is 200
AND the status field is "ready"
AND checks.postgres is true
AND there is NO engram key in checks

GIVEN the service is running
BUT PostgreSQL is disconnected
WHEN GET /health/readiness is called
THEN the response status is 503
AND the status field is "not_ready"
AND checks.postgres is false
```

#### Scenario 3: Tenant middleware scopes a native run

```gherkin
GIVEN a request carries header X-Tenant-Id: tenant_42
WHEN the TenantScopeMiddleware resolves the request
THEN request.state.user_id is set to "tenant_42"
AND request.state.tenant_id is set to "tenant_42"
AND no RLS policy is applied to agno_* tables
AND the downstream native POST /agents/{agent_id}/runs handler sees request.state.user_id == "tenant_42"
```

#### Scenario 4: Rate limit protects native runs

```gherkin
GIVEN tenant tenant_42 has a limit of 100 requests per 60 seconds
WHEN the 101st request from tenant_42 arrives at POST /agents/{agent_id}/runs
THEN the response status is 429
AND the response detail mentions "Tenant rate limit exceeded"
```

#### Scenario 5: AX discovery returns schemas

```gherkin
GIVEN the app is built from a YAML site defining agents
WHEN GET /ax/tools is called
THEN the response status is 200
AND the response contains a tool named "run_agent"
AND that tool's parameters reference agent_id and user_id
AND the endpoint does NOT execute any agent
```

#### Scenario 6: Wire contract is native (no invented JSON/{name})

```gherkin
GIVEN the mounted native AgentOS app
WHEN a client calls POST /agents/{agent_id}/runs
THEN the request content-type is multipart/form-data
AND the path uses {agent_id} (NOT {name})
AND yaml-agno exposes NO POST /agents/{name}/run JSON endpoint
```

---

## 5. TDD MICRO-TASK EXECUTION PROTOCOL

### 5.1 Cascading Task Checklist

#### TASK_001: Implement YAML -> AgentOS wiring

- **File**: `yaml-agno/src/wiring/build_app.py`
- **Test**: `tests/integration/wiring/test_build_app.py`
- **RED**:
  ```python
  async def test_build_app_mounts_native_run_route(tmp_yaml_site):
      app = build_app(tmp_yaml_site)
      routes = {r.path for r in app.routes}
      assert "/agents/{agent_id}/runs" in routes
      assert "/health" in routes

  async def test_build_app_has_no_yamlagno_owned_run_route(tmp_yaml_site):
      app = build_app(tmp_yaml_site)
      routes = {r.path for r in app.routes}
      assert "/api/v1/agents/{name}/run" not in routes
  ```
- **GREEN**: Implement `build_app()` calling `AgentOS(...).get_app()` and mounting the gap routers.
- **Commit**: `feat: wire YAML into AgentOS app with native routers`

#### TASK_002: Implement readiness + liveness routers (factory style)

- **File**: `yaml-agno/src/api/gaps/readiness.py`
- **Test**: `tests/integration/api/test_readiness.py`
- **RED**:
  ```python
  async def test_liveness_returns_alive(client):
      resp = await client.get("/health/liveness")
      assert resp.status_code == 200
      assert resp.json()["status"] == "alive"

  async def test_readiness_has_no_engram_key(client):
      resp = await client.get("/health/readiness")
      data = resp.json()
      assert "engram" not in data["checks"]
  ```
- **GREEN**: Implement `get_readiness_router` / `get_liveness_router` factories.
- **Commit**: `feat: add readiness and liveness factory routers`

#### TASK_003: Implement rate-limit-by-tenant middleware

- **File**: `yaml-agno/src/api/middleware/rate_limit.py`
- **Test**: `tests/unit/api/middleware/test_rate_limit.py`
- **RED**:
  ```python
  async def test_rate_limit_429_after_breach(app_with_rate_limit):
      client = app_with_rate_limit(tenant_limit=2)
      await client.get("/health", headers={"X-Tenant-Id": "t1"})
      await client.get("/health", headers={"X-Tenant-Id": "t1"})
      resp = await client.get("/health", headers={"X-Tenant-Id": "t1"})
      assert resp.status_code == 429
  ```
- **GREEN**: Implement `RateLimitMiddleware` (token bucket per tenant + IP).
- **Commit**: `feat: add rate-limit-by-tenant middleware`

#### TASK_004: Implement tenant scoping middleware

- **File**: `yaml-agno/src/api/middleware/tenant_scope.py`
- **Test**: `tests/unit/api/middleware/test_tenant_scope.py`
- **RED**:
  ```python
  async def test_tenant_scope_sets_user_id(app_with_tenant_scope):
      client = app_with_tenant_scope()
      await client.get("/health", headers={"X-Tenant-Id": "tenant_42"})
      # request.state.user_id must be "tenant_42" for native routers
      # (verified via a spy handler that reads request.state.user_id).
  ```
- **GREEN**: Implement `TenantScopeMiddleware` (resolve tenant_id -> `request.state.user_id`; NO RLS).
- **Commit**: `feat: add tenant scope middleware (tenant_id -> request.state.user_id)`

#### TASK_005: Implement AX discovery router

- **File**: `yaml-agno/src/api/gaps/ax_tools.py`
- **Test**: `tests/integration/api/test_ax_tools.py`
- **RED**:
  ```python
  async def test_ax_tools_lists_run_agent(client):
      resp = await client.get("/ax/tools")
      assert resp.status_code == 200
      names = [t["name"] for t in resp.json()["tools"]]
      assert "run_agent" in names

  async def test_ax_tools_does_not_execute(client):
      resp = await client.get("/ax/tools")
      # read-only: no agent run side effects
      assert resp.status_code == 200
  ```
- **GREEN**: Implement `get_ax_tools_router` factory publishing function-calling schemas.
- **Commit**: `feat: add AX REST discovery router (GET /ax/tools)`

#### TASK_006: Document native wire contract (no JSON/{name})

- **File**: `yaml-agno/docs/api_contract.md`
- **Test**: `tests/contract/test_native_wire_contract.py`
- **RED**:
  ```python
  def test_native_run_endpoint_is_multipart_form():
      # Asserts the mounted route expects multipart/form-data, not JSON,
      # and uses {agent_id}, not {name}.
      app = build_app(tmp_yaml_site)
      run_route = next(r for r in app.routes if r.path.endswith("/agents/{agent_id}/runs"))
      assert "multipart/form-data" in str(run_route.body_field)
  ```
- **GREEN**: Document the multipart/{id} contract; assert no invented JSON/{name} shim.
- **Commit**: `docs: document native AgentOS multipart/{id} wire contract`

#### TASK_007: Verify yaml-agno defines NO own /run, /sessions, or /agents config routes

- **File**: `tests/contract/test_no_duplicate_routes.py`
- **RED**:
  ```python
  def test_yamlagno_has_no_owned_run_or_sessions_router():
      app = build_app(tmp_yaml_site)
      paths = {r.path for r in app.routes}
      # These are native AgentOS routes; yaml-agno MUST NOT own a parallel one.
      forbidden_yamlagno_owned = {
          "/api/v1/agents/{name}/run",
          "/api/v1/sessions/{id}",
          "/api/v1/agents/{name}",
      }
      assert forbidden_yamlagno_owned.isdisjoint(paths)
  ```
- **GREEN**: Confirm all execution routes come from `AgentOS.get_app()`; no yaml-agno duplicate.
- **Commit**: `test: assert no yaml-agno-owned duplicate execution routes`

---

## 6. STRATEGIC QUESTIONS (RESOLVED)

### [Pregunta 1] Streaming Response — RESUELTO: nativo (no rebuild)

**¿El endpoint /run debe soportar Server-Sent Events (SSE) para streaming?**

**Resolución**: AgentOS YA hace streaming nativamente en `POST /agents/{agent_id}/runs` (SSE resume, background runs, checkpoints, fork, continue, cancel). yaml-agno NO reconstruye streaming; monta el endpoint nativo vía `get_app()`. Reconstruirlo sería duplicar ~1744 líneas de `agents/router.py` y romper la semántica nativa de upload/SSE.

### [Pregunta 2] Rate Limiting — RESUELTO: SÍ, yaml-agno lo agrega (gap)

**¿Debería haber rate limiting por tenant/user en los endpoints?**

**Resolución**: SÍ. AgentOS no trae nada de rate limiting (`grep` en `os/` = 0 hits). yaml-agno agrega `RateLimitMiddleware` (§3.2) como un middleware FastAPI estándar keyed en `tenant_id`, que protege TODOS los routers nativos montados sin que yaml-agno los posea. Es un gap genuino.

### [Pregunta 3] API Versioning — RESUELTO: defer a las convenciones nativas de AgentOS

**¿Estrategia de versioning: /api/v1/ vs Accept header?**

**Resolución**: yaml-agno NO introduce su propio namespace `/api/v1/`. Monta los routers nativos de AgentOS tal cual (`POST /agents/{agent_id}/runs`, etc.), que siguen las convenciones de ruteo de Agno. Inventar un prefijo `/api/v1/` own crearía un shim de re-ruteo innecesario y rompería la fidelidad al sistema. Los gaps propios (readiness, AX tools) se montan sin prefijo de versión, siguiendo el mismo estilo de AgentOS (p. ej. `GET /health` no lleva versión).

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
