# Proposal: auth-vq010-isolation-guard

## Intent

Judgment Day CRITICAL #3120: VQ010 (`runtime/server.py:120-126`) checks only `authorization=True`; Agno defaults `user_isolation=False`, so `run_server`/direct `YamlAgentOS` boot authenticated-but-unisolated apps. Factory adapter already enforces.

## Scope

### In Scope

| File | Exact contract |
|---|---|
| `src/yaml_agno/agentos/authorization_adapter.py` | Private predicate beside `_map_authorization_config` (name in design), `(authorization, authorization_config)` → VQ010 message or None. Fires iff `authorization is True` and (`authorization_config is None` or `.user_isolation is not True`). Strict `is True` identity: rejects `None`/`False`/`0`/`1`/`"true"`. |
| `src/yaml_agno/api/app.py` | After JD-01 (`:183-189`): violation → `ValueError` before `super().__init__`. Authoritative: closes direct-`YamlAgentOS`/`create_app` bypass; dev path and JD-01 unchanged. |
| `src/yaml_agno/runtime/server.py` | Keep guard (`:120-126`); add predicate check → `RuntimeError` (VQ010 message) before `create_app`; keep `**yaml_agentos_kwargs`. |
| `src/yaml_agno/factories/agentos_factory.py` | No code change; reference, test-asserted only. |
| `tests/unit/{runtime/test_run_server_auth,api/test_app_jwt_mode,factories/test_agentos_factory,agentos/test_authorization_adapter}.py` | Expand per matrix. |
| `.chats/decisions.yaml` VQ010, `DECISIONES.md` D-F1-10 | Yes: presence-only grep passes on fail-open; tighten to refusal wording. |

### Out of Scope

S5a.1 rewrite; Keycloak (S5b); Casbin (VQ013); RLS (VQ014); `os.environ` (VQ015); external `agno.os.AgentOS` ownership; `AgentOSFactory` code change; post-construction mutation.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `agentos-authorization-build`: ADDED requirement — isolation refusal contract.

## Approach

Approach 3 (exploration): shared predicate; `YamlAgentOS` authoritative (`ValueError`), `run_server` defense-in-depth (`RuntimeError`). Public Agno API only; no internals, monkeypatch, duplicate auth runtime. Strict TDD (RED→GREEN→REFACTOR), feature branch, granular commits, work units ≤400 LOC, validate before merge/push.

### Test Matrix

| Group | Cases |
|---|---|
| `run_server` negative | `authorization=True` with `None`/explicit-`False`/implicit-default config; `authorization="true"` → `RuntimeError` VQ010 |
| `run_server` positive | valid isolated config (`mount_tenant_context=False`) + fake server → `run()` once |
| `YamlAgentOS` negative | `authorization=True` + None/explicit-False/implicit-default config → `ValueError`; JD-01 preserved |
| `YamlAgentOS` positive | valid config constructs; `get_app()` mounts no `TenantContextMiddleware` |
| Dev regression | no-auth `create_app` → `FastAPI`; `X-Tenant-Id` integration 200 |
| Factory invariant | adapter build yields `user_isolation=True` (content); no-adapter override → `AuthorizationBuildError` |
| Gates | `pytest` 840+ green; `ruff`; `mypy`; `spec_gate.py` 34/34 |

## Affected Areas

| Area | Impact |
|---|---|
| `authorization_adapter.py`, `api/app.py`, `runtime/server.py`, 4 test files, VQ010 text | Modified |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Truthy bypass | Low | `is True` checks; negatives tested |
| Break S5a.1 fakes | Low | Conftest already isolated |
| Predicate/factory drift | Low | Same module |

## Rollback Plan

Revert corrective commits; S5a.1 source/spec bytes untouched; restores verified `826f9d2` state.

## Dependencies

- `auth-jwt-native-isolation` @ `826f9d2` (840 green; JD ESCALATED pending this fix).

## Success Criteria

- [ ] Unisolated authenticated startup impossible via `run_server`, `create_app`, `YamlAgentOS`.
- [ ] Dev `authorization=False` path and JD-01 unchanged.
- [ ] 840+ green; ruff/mypy/spec_gate clean; VQ010 query tightened.
