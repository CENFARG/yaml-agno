---
design:
  change: yaml-agentos-foundation
  parent_spec: SPEC_06
  slice: "A"
---

# Design: yaml-agentos-foundation (SPEC_06 Slice A)

> HOW slice A is structured. The spec (sibling `spec.md`) defines WHAT; this
> document fixes the architecture decisions, the sequence of construction, and
> the deviations from the SPEC_06 §2.3 sketch that the Agno 2.6.22 reality
> forced.

## 1. Verified Agno 2.6.22 surface (source of truth)

Probed against the installed `agno==2.6.22` wheel before writing any code:

```python
from agno.os import AgentOS          # NOT agno.app (SPEC_06 sketch #1 wrong)
import inspect
inspect.signature(AgentOS.__init__)
# (self, id=None, name=None, description=None, version=None, db=None,
#  checkpoint=None, agents=None, teams=None, workflows=None, knowledge=None,
#  interfaces=None, a2a_interface=False, authorization=False,
#  authorization_config=None, cors_allowed_origins=None, config=None,
#  settings=None, lifespan=None, enable_mcp_server=False, mcp_config=None,
#  base_app=None, on_route_conflict='preserve_agentos', tracing=False,
#  auto_provision_dbs=True, run_hooks_in_background=False, telemetry=True,
#  registry=None, scheduler=False, scheduler_poll_interval=15,
#  scheduler_base_url=None, internal_service_token=None)

inspect.signature(AgentOS.get_app)   # (self) -> fastapi.applications.FastAPI
```

A direct instantiation test against the installed wheel returned a `FastAPI` app
with **77 routes**, including `POST /agents/{agent_id}/runs`, `GET /agents`,
`GET /agents/{agent_id}`, and `GET /health`. Inheriting those via `super()
.get_app()` is therefore the correct extension mechanism; no reimplementation.

The sketch's `from yaml_agno.factory.agent_factory import build_agents` is wrong
in two ways: the directory is `factories/` (plural), and `AgentFactory` is a
class with a static `.build(cfg, resolver=None, provider_factory=None)` method,
not a module-level `build_agents(...)` function. Slice A imports the real class.

The sketch's `from yaml_agno.db.session import resolve_agentos_db` points at a
module that does not exist (SPEC_03 B-E not started). Slice A passes `db=None`
and relies on `auto_provision_dbs=True` (the Agno default) to provision an
in-memory DB for local runs. The real session resolver lands with SPEC_03.

## 2. Architecture decisions

### 2.1 AD-1: Subclass, not composition (matches SPEC_06 §2.1)

`class YamlAgentOS(AgentOS)` — inheritance is the design AgentOS itself prescribes
(open class, no `@final`, overridable `get_app`). Slice A implements exactly
this. Any temptation to wrap AgentOS in a composition layer is rejected: it
would re-mask the native router surface and break the contract tests that walk
`app.routes` for native paths.

### 2.2 AD-2: Dual agent sources, explicit list wins

`__init__` accepts BOTH `agents=[...]` (pre-built `agno.Agent` instances — the
primary integration-test path) AND `config_path="agents.yaml"` (the production
YAML path). Rules:

- If both are passed → raise `ValueError` (ambiguous; spec Scenario 3).
- If `agents` is passed → forward unchanged. No rebuild, no validation.
- If only `config_path` is passed → load YAML, validate each entry via
  `AgentConfig.model_validate(entry)`, build each via
  `AgentFactory.build(cfg)`.
- If neither is passed → forward `agents=None` (Agno accepts an empty agent set
  and still mounts `/config`, `/health`, etc.; this is the "foundation only"
  boot path).

Rationale: integration tests want to feed a real `agno.Agent` without writing a
YAML file; production wants YAML. Two explicit paths avoid a synthetic
"build-from-YAML-then-accept-also-list" hybrid that obscures intent.

### 2.3 AD-3: `authorization=False` slice-A default (documented deviation)

SPEC_06 §3.1 mandates `authorization=True` + `user_isolation=True` ALWAYS ON.
That mandate is **correct for production** but requires SPEC_04's
`resolve_user_id` to compose the `user_id` string. SPEC_04 is not implemented
yet, so enabling `user_isolation=True` today would have nothing to thread —
effectively a no-op with a misleading flag.

Slice A therefore defaults `authorization=False` so:
- Integration tests can exercise `get_app()` without minting a real JWT.
- Local dev can boot `uvicorn` and hit `/docs` immediately.
- The docstring carries a `WARNING` block stating production MUST set
  `authorization=True` + `AuthorizationConfig(user_isolation=True)` once
  SPEC_04 lands.

This is a **documented slice deviation**, not a silent violation: the spec
explicitly carves it out (spec.md Scenario 8) and the design records it here.

### 2.4 AD-4: Health routers as factories (mirror Agno's `get_health_router`)

`get_liveness_router()` and `get_readiness_router()` each return an
`APIRouter`, mirroring `agno/os/routers/health.py:get_health_router`. Slice A's
readiness returns `{"status": "ready", "checks": {}}` unconditionally — no fake
`postgres: true`. The Postgres ping lands with SPEC_03 B-E; until then the
route is honest about what it can check (nothing).

`YamlAgentOS(mount_health=True)` calls `app.include_router(...)` for both inside
`get_app()`, AFTER `super().get_app()`. `mount_health=False` skips both —
useful for unit tests that only want the native surface.

### 2.5 AD-5: Runtime entry point with injectable server factory

`runtime/server.py` exposes two functions:

- `create_app(config_path=None, agents=None, **kwargs) -> FastAPI` — pure;
  builds the `YamlAgentOS` and returns `.get_app()`. Integration tests call
  this.
- `run_server(config_path=None, agents=None, host="127.0.0.1", port=8000,
  server_factory=None, **kwargs) -> None` — constructs a `uvicorn.Server` via
  the injectable `server_factory` (default: a function that builds
  `uvicorn.Server(uvicorn.Config(...))`) and calls `.run()`. Tests inject a
  fake factory to assert the server is constructed correctly without binding
  a TCP port.

The injection seam avoids the anti-pattern of `if os.environ.get("TESTING")`
inside production code and keeps `run_server` unit-testable.

## 3. Sequence: YAML → YamlAgentOS → FastAPI

```
            ┌────────────────────────┐
 caller ──▶ │ YamlAgentOS.__init__   │
            │  (config_path=...,     │
            │   agents=...,          │
            │   authorization=False, │
            │   mount_health=True,   │
            │   **agentos_kwargs)    │
            └─────────┬──────────────┘
                      │ resolve agent source
            ┌─────────▼──────────────┐
            │ agents is not None?    │──yes──▶ forward agents as-is
            └─────────┬──────────────┘
                      │ no
            ┌─────────▼──────────────┐
            │ config_path is not None│──yes──▶ yaml.safe_load(path)
            │ AND agents is None?    │        ▶ [AgentConfig.model_validate(e) for e in data]
            └─────────┬──────────────┘        ▶ [AgentFactory.build(cfg) for cfg in configs]
                      │
            ┌─────────▼──────────────┐
            │ super().__init__(      │
            │   agents=resolved,     │  ◀── inherits ALL native routers
            │   authorization=...,   │
            │   **agentos_kwargs)    │
            └─────────┬──────────────┘
                      │
            ┌─────────▼──────────────┐
            │ self.mount_health flag │
            └─────────┬──────────────┘
                      │
 caller ──▶ .get_app()
                      │
            ┌─────────▼──────────────┐
            │ app = super().get_app()│  ◀── 77 native routes (POST /agents/{id}/runs, /health, ...)
            └─────────┬──────────────┘
                      │ if self.mount_health
            ┌─────────▼──────────────┐
            │ app.include_router(    │
            │   get_liveness_router())│
            │ app.include_router(    │
            │   get_readiness_router())│
            └─────────┬──────────────┘
                      │
                      ▼ return app (fastapi.FastAPI)
```

## 4. YAML → Pydantic → Factory → Agno mapping (slice A)

| YAML field | Pydantic (AgentConfig) | Factory call | Agno kwarg |
|---|---|---|---|
| `name` | `AgentConfig.name` | — | `Agent(name=...)` |
| `model` | `AgentConfig.model` | — | `Agent(model=...)` |
| `instructions` | `AgentConfig.instructions` | — | `Agent(instructions=...)` |
| `description` | `AgentConfig.description` | — | `Agent(description=...)` |
| `tools` | `AgentConfig.tools` | resolved by `AgentFactory.build` when a resolver is wired (not in slice A) | `Agent(tools=...)` |
| (others) | opaque slots per SPEC_02 | deferred to owner SPECs | deferred |

Slice A wires `AgentFactory.build(cfg)` with no `resolver` and no
`provider_factory` — slice A's job is to instantiate agents, not to resolve
tools or provider secrets. That keeps the slice autonomous.

## 5. File layout

```
src/yaml_agno/
├── api/
│   ├── __init__.py          ← MODIFY: re-export YamlAgentOS
│   ├── app.py               ← NEW: YamlAgentOS(AgentOS)
│   └── health.py            ← NEW: get_liveness_router, get_readiness_router
└── runtime/
    ├── __init__.py          ← MODIFY: re-export create_app, run_server
    └── server.py            ← NEW: create_app, run_server

tests/
├── unit/
│   └── api/
│       ├── __init__.py
│       ├── test_health_routers.py     ← unit tests for the factory routers
│       └── test_yaml_agent_os_init.py ← unit tests for __init__ resolution
└── integration/
    └── api/
        ├── __init__.py
        ├── test_yaml_agent_os_app.py  ← contract tests on get_app() route set
        └── test_runtime_server.py     ← tests for create_app + run_server injection
```

## 6. Deviations from SPEC_06

Recorded explicitly; none are silent:

| SPEC_06 says | Slice A does | Why |
|---|---|---|
| `from agno.app import AgentOS` | `from agno.os import AgentOS` | Installed wheel; `agno.app` does not export `AgentOS` |
| `build_agents(site)` module function | `AgentFactory.build(cfg)` static method per config | Real API in `yaml_agno.factories.agent_factory` |
| `resolve_agentos_db(site)` | `db=None` (Agno `auto_provision_dbs=True`) | SPEC_03 B-E unstarted |
| `authorization=True` ALWAYS ON | `authorization=False` slice-A default | SPEC_04 `resolve_user_id` not implemented; tests cannot mint JWTs |
| `TenantContextMiddleware`, `RateLimitMiddleware`, MCP, ConfigManager | DEFERRED | SPEC_04, SPEC_19, SPEC_26, SPEC_02 respectively |

## 7. TDD plan (strict mode)

Strict TDD is enabled (`openspec/config.yaml` `apply.tdd: true`). Every behavior
task follows RED → GREEN → REFACTOR:

1. **RED** for `YamlAgentOS.__init__` resolution rules (Scenarios 1, 2, 3, 8, 9).
2. **GREEN** with the subclass body.
3. **RED** for `get_app()` route surface (Scenarios 4, 5).
4. **GREEN** by calling `super().get_app()` + conditional health mounts.
5. **RED** for health router responses (Scenarios 6, 7).
6. **GREEN** with the factory router implementations.
7. **RED** for `runtime.create_app` / `run_server` (Scenarios 10, 11).
8. **GREEN** with the server module + injectable factory.

Each RED step writes the test first, runs it, confirms failure, then implements
the minimum to pass. Commits are split: one RED commit, one GREEN commit, per
the task contract.
