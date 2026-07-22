---
change: yaml-agentos-foundation
spec: SPEC_06
status: proposed
artifact_store: hybrid
depends_on: [SPEC_01, SPEC_02]
slice: "A"
---

# Proposal: yaml-agentos-foundation (SPEC_06 Slice A)

> Land the minimal HTTP foundation of yaml-agno: a `YamlAgentOS(AgentOS)`
> subclass that inherits the full native router set from Agno 2.6.22 and a thin
> runtime entry point that boots it under uvicorn. Slice A corrects the four
> SPEC_06 defects the exploration surfaced and ships a runnable server, deferring
> multi-tenant middleware, rate limiting, MCP, and the DB session layer to later
> slices.

## Intent / Why

SPEC_06 (v0.5.0-iter5) is a long-horizon spec covering the full HTTP + AX layer:
`YamlAgentOS(AgentOS)` inheritance, composite `user_id` multi-tenancy,
`TenantContextMiddleware`, `RateLimitMiddleware`, readiness/liveness routers,
and native MCP discovery. Landing the whole spec in one PR would cross the
400-line review budget and depend on SPEC_03 B-E (DB session), SPEC_04
(`resolve_user_id`), and SPEC_19 (rate limiting) — none of which exist yet.

Slice A carves out the **only** deliverable that is valuable today and has zero
unmet dependencies:

1. The `YamlAgentOS(AgentOS)` subclass itself — the inheritance shell.
2. YAML-driven agent registration feeding `super().__init__(agents=...)`.
3. A `get_app()` override that calls `super().get_app()` and **optionally**
   mounts `/health/readiness` and `/health/liveness`.
4. A `runtime/server.py` entry point that wires YAML → agents → `YamlAgentOS`
   and starts uvicorn.

This is the smallest autonomous slice: it boots a server, exposes the full
native Agno API surface (`POST /agents/{agent_id}/runs`, `GET /health`, ...),
and gives downstream slices a real `YamlAgentOS` class to extend with the
deferred middleware.

### The four SPEC_06 defects corrected in this slice

Exploration against the installed `agno==2.6.22` distribution found that the
sketches in SPEC_06 §2.2–§2.3 reference modules that do not exist yet or were
renamed. Slice A ships the corrected imports and **trusts the installed code**
over the spec sketches:

| # | SPEC_06 sketch (WRONG) | Reality (Agno 2.6.22 / yaml-agno HEAD) | Slice A fix |
|---|---|---|---|
| 1 | `from agno.app import AgentOS` | `from agno.os import AgentOS` (`agno.os`, not `agno.app`) | Use `from agno.os import AgentOS` |
| 2 | `from yaml_agno.factory.agent_factory import build_agents` | `yaml_agno.factories.agent_factory.AgentFactory` (class, static `.build(cfg, ...)`) — `factory/` is a typo and `build_agents` does not exist | Use `yaml_agno.factories.agent_factory.AgentFactory.build(...)` per agent config |
| 3 | `from yaml_agno.db.session import resolve_agentos_db` | `db/session.py` does not exist (SPEC_03 B-E unstarted) | Pass `db=None`; rely on `auto_provision_dbs=True` (Agno default) for in-memory runs in slice A |
| 4 | `authorization=True` always-on + test JWT | Integration tests cannot easily mint a valid JWT, and SPEC_04's `resolve_user_id` (the tenant-composite source of truth) is not implemented yet | Default `authorization=False` for slice A (local dev); document that production MUST set `authorization=True` + `AuthorizationConfig(user_isolation=True)` once SPEC_04 ships |

## Scope

### In Scope

- NEW `src/yaml_agno/api/app.py` — `class YamlAgentOS(AgentOS)`:
  - `__init__(self, *, config_path=None, agents=None, authorization=False, mount_health=True, **agentos_kwargs)` — accepts EITHER a list of pre-built `agno.Agent` instances OR a YAML config path it loads, validates via `AgentConfig`, and builds via `AgentFactory.build(...)`.
  - `get_app(self)` — calls `super().get_app()` (inherits every native router) and **optionally** mounts `/health/readiness` and `/health/liveness` as factory routers when `mount_health=True`.
- NEW `src/yaml_agno/api/health.py` — `get_liveness_router()` and `get_readiness_router()` factories mirroring `agno/os/routers/health.py:get_health_router`. Readiness gate is a no-op in slice A (returns `ready=True` with empty checks; the real Postgres ping lands with SPEC_03).
- NEW `src/yaml_agno/runtime/server.py` — `create_app(config_path=None, agents=None, **kwargs) -> FastAPI` and `run_server(config_path=None, agents=None, host=..., port=..., **kwargs)`; loads config, builds agents, instantiates `YamlAgentOS`, and returns/runs the FastAPI app.
- MODIFY `src/yaml_agno/api/__init__.py` — re-export `YamlAgentOS`.
- MODIFY `src/yaml_agno/runtime/__init__.py` — re-export `create_app`, `run_server`.
- Tests under `tests/unit/api/` and `tests/integration/api/` (contract tests that `get_app()` returns a FastAPI app exposing the native run + health routes).

### Out of Scope (DEFERRED)

- `TenantContextMiddleware` (SPEC_04 `resolve_user_id` not implemented yet).
- `RateLimitMiddleware` (SPEC_19).
- MCP server / AX discovery (SPEC_26).
- `resolve_agentos_db` / real DB session layer (SPEC_03 B-E).
- Composite `user_id`, `AuthorizationConfig(user_isolation=True)`, and the NULL-bucket guard contract tests (need SPEC_04).
- `core-cenf-py ConfigManager` integration for config loading (slice A reads YAML files directly; ConfigManager wiring lands when SPEC_02's loader is added).

## Approach

### Class shape

```python
class YamlAgentOS(AgentOS):
    def __init__(self, *, config_path=None, agents=None,
                 authorization=False, mount_health=True, **agentos_kwargs):
        # 1. Resolve agents: explicit list wins; else load+build from YAML.
        # 2. super().__init__(agents=..., authorization=..., **agentos_kwargs)
    def get_app(self):
        app = super().get_app()
        if self.mount_health:
            app.include_router(get_liveness_router())
            app.include_router(get_readiness_router())
        return app
```

### Why `authorization=False` as the slice-A default (not a violation of SPEC_06 §3.1)

SPEC_06 §3.1 mandates `authorization=True` + `user_isolation=True` ALWAYS ON
to prevent the NULL-bucket footgun. That mandate is **correct for production**
and will be enforced once SPEC_04's `resolve_user_id` exists — without a
composite `user_id` source, `user_isolation=True` has nothing to thread. Slice A
defaults `authorization=False` for **local dev and integration tests** so the
contract tests can exercise `get_app()` without minting a real JWT, and the
default is documented as "NOT for production." Production callers (and later
slices) pass `authorization=True` explicitly.

### Config loading (slice A)

Slice A reads YAML files directly with `yaml.safe_load`. Each entry is validated
via `AgentConfig.model_validate(entry)` (SPEC_02) and built via
`AgentFactory.build(cfg)` (SPEC_01). The `core-cenf-py ConfigManager` integration
defers to the slice that adds SPEC_02's loader.

## Rollback Plan

- All changes are additive (NEW files + two `__init__.py` re-exports). No
  existing module is mutated, so reverting slice A is `git revert <commit>` with
  no migration, no schema change, no dependency shift.
- The new `YamlAgentOS` class is not imported by any production path yet; even
  if it shipped broken, existing tests and the factory pipeline are unaffected.
- The runtime entry point is invoked only by explicit opt-in (`python -m
  yaml_agno.runtime.server`); no auto-registration, no side effects on import.

## Success Criteria

- `YamlAgentOS(agents=[<real agno.Agent>]).get_app()` returns a `FastAPI` app.
- That app exposes the native `POST /agents/{agent_id}/runs`, `GET /agents`,
  `GET /health` routes inherited from `super().get_app()`.
- That app ALSO exposes `/health/readiness` and `/health/liveness` when
  `mount_health=True` (default).
- `YamlAgentOS(config_path="agents.yaml")` loads YAML, validates each entry
  through `AgentConfig`, and builds agents through `AgentFactory.build(...)`.
- `runtime/server.py::create_app(...)` returns the same FastAPI app, and
  `run_server(...)` starts uvicorn bound to `host:port`.
- Unit + integration tests pass; `ruff check .` and `mypy src/yaml_agno` are
  clean.
