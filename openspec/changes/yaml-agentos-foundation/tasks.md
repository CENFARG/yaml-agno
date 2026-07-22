---
tasks:
  change: yaml-agentos-foundation
  parent_spec: SPEC_06
  slice: "A"
  mode: strict-tdd
---

# Tasks: yaml-agentos-foundation (SPEC_06 Slice A)

> Strict TDD mode. Every behavior task starts with a RED test that fails for the
> right reason, then implements the minimum to turn it GREEN. Commits are split
> RED / GREEN per the task contract.

## Review Workload Forecast

- Estimated authored changed lines: ~250 (2 new modules ~80 lines each, 2 small
  `__init__.py` re-exports ~10 lines each, ~140 lines of tests).
- 400-line budget risk: **Low**.
- Chained PRs recommended: **No**.
- Decision needed before apply: **No**.
- Chain strategy: pending (single PR).

## Phase 1: Health factory routers (foundation for get_app extensions)

- [x] 1.1 RED — `tests/unit/api/test_health_routers.py::test_liveness_router_returns_alive_response` asserts `get_liveness_router()` returns an `APIRouter` whose `GET /health/liveness` handler returns `{"status": "alive"}` with HTTP 200.
- [x] 1.2 RED — `tests/unit/api/test_health_routers.py::test_readiness_router_returns_ready_with_empty_checks` asserts `get_readiness_router()` returns an `APIRouter` whose `GET /health/readiness` handler returns `{"status": "ready", "checks": {}}` with HTTP 200.
- [x] 1.3 GREEN — implement `src/yaml_agno/api/health.py` with `get_liveness_router()` and `get_readiness_router()` factories, Pydantic `LivenessResponse` / `ReadinessResponse` models, Google docstrings mirroring `agno/os/routers/health.py:get_health_router`.

## Phase 2: YamlAgentOS subclass — __init__ resolution rules

- [x] 2.1 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_accepts_prebuilt_agents` asserts `YamlAgentOS(agents=[agent])` is an `AgentOS` instance and forwards the list unchanged.
- [x] 2.2 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_builds_agents_from_config_path` (uses `tmp_path` to write `agents.yaml`) asserts the agents are built via `AgentFactory` from the YAML entries.
- [x] 2.3 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_rejects_both_agents_and_config_path` asserts `ValueError` when both kwargs are passed.
- [x] 2.4 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_default_authorization_false` asserts `.authorization is False` by default (call passes a minimal agent list because `AgentOS` requires at least one of agents/teams/workflows/knowledge/db).
- [x] 2.5 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_forwards_authorization_true` asserts `.authorization is True` when explicitly passed.
- [x] 2.6 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_forwards_extra_agentos_kwargs` asserts `enable_mcp_server=True` / `telemetry=False` reach the parent.
- [x] 2.7 RED — `tests/unit/api/test_yaml_agent_os_init.py::test_init_invalid_yaml_entry_raises_validation_error` asserts an invalid YAML entry surfaces `pydantic.ValidationError` rather than being silently skipped.
- [x] 2.8 GREEN — implement `src/yaml_agno/api/app.py::YamlAgentOS.__init__` with dual-source resolution, `**agentos_kwargs` pass-through, and the slice-A `authorization=False` default + docstring WARNING.

## Phase 3: get_app() override — native routes + optional health extensions

- [x] 3.1 RED — `tests/integration/api/test_yaml_agent_os_app.py::test_get_app_returns_fastapi_with_native_routes` asserts the returned app exposes `POST /agents/{agent_id}/runs`, `GET /health`, and `GET /agents`.
- [x] 3.2 RED — `tests/integration/api/test_yaml_agent_os_app.py::test_get_app_mounts_health_extensions_by_default` asserts `/health/readiness` and `/health/liveness` are present with `mount_health=True`.
- [x] 3.3 RED — `tests/integration/api/test_yaml_agent_os_app.py::test_get_app_skips_health_when_mount_health_false` asserts the two extension routes are ABSENT with `mount_health=False`.
- [x] 3.4 RED — `tests/integration/api/test_yaml_agent_os_app.py::test_get_app_does_not_shadow_native_run_route` asserts there is exactly one route whose path is `POST /agents/{agent_id}/runs` (no yaml-agno duplicate).
- [x] 3.5 GREEN — implement `YamlAgentOS.get_app()` calling `super().get_app()` and conditionally `app.include_router(get_liveness_router())` + `app.include_router(get_readiness_router())`.

## Phase 4: runtime entry point

- [x] 4.1 RED — `tests/integration/api/test_runtime_server.py::test_create_app_returns_fastapi_app` asserts `create_app(agents=[...])` returns `fastapi.FastAPI` exposing native routes.
- [x] 4.2 RED — `tests/integration/api/test_runtime_server.py::test_create_app_with_config_path_builds_agents` asserts `create_app(config_path=...)` produces an app whose registered agent names match the YAML.
- [x] 4.3 RED — `tests/integration/api/test_runtime_server.py::test_run_server_uses_injected_server_factory` asserts `run_server(..., server_factory=fake)` constructs the server with the YamlAgentOS app and the provided host/port, and that `.run()` is invoked exactly once.
- [x] 4.4 GREEN — implement `src/yaml_agno/runtime/server.py::create_app` and `run_server` with an injectable `server_factory` defaulting to a `uvicorn.Server(uvicorn.Config(...))` builder.

## Phase 5: Package re-exports + cleanup

- [x] 5.1 GREEN — update `src/yaml_agno/api/__init__.py` to re-export `YamlAgentOS`.
- [x] 5.2 GREEN — update `src/yaml_agno/runtime/__init__.py` to re-export `create_app`, `run_server`.
- [x] 5.3 VERIFY — `python -m pytest -m "unit and not integration" -q` is green.
- [x] 5.4 VERIFY — `ruff check .` is clean.
- [x] 5.5 VERIFY — `mypy src/yaml_agno` is clean.

## Commit Plan

- RED commit: `test: add RED tests for YamlAgentOS foundation` (after Phases 1–4 RED tasks).
- GREEN commit: `feat(api): add YamlAgentOS(AgentOS) subclass + server entry point (SPEC_06 slice A)` (after all GREEN + VERIFY).
