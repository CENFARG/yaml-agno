# Tasks: auth-vq010-isolation-guard

## Review Workload Forecast

Estimated changed lines: ~200-260 (~20 src, ~180 tests, 2 docs). Delivery strategy: single-pr.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Work Units

| Unit | Goal | PR | Focused | Harness | Rollback |
|---|---|---|---|---|---|
| WU1 | Predicate `_require_isolated_auth` + truth table | PR1 | `python -m pytest tests/unit/agentos/test_authorization_adapter.py -k RequireIsolatedAuth` | `python -m pytest tests/unit/agentos/test_authorization_adapter.py` | Revert predicate+tests (inert alone) |
| WU2 | `YamlAgentOS` guard (`ValueError` pre-`super().__init__`) | PR1 | `python -m pytest tests/unit/api/test_app_jwt_mode.py -k isolation` | `python -m pytest tests/unit/api/test_app_jwt_mode.py` | Revert guard+tests; JD-01/dev intact |
| WU3 | `run_server` guard (`RuntimeError` pre-`create_app`) | PR1 | `python -m pytest tests/unit/runtime/test_run_server_auth.py -k isolation` | `python -m pytest tests/unit/runtime/test_run_server_auth.py` | Revert call+tests; old guard verbatim |
| WU4 | Factory invariant content asserts (test-only) | PR1 | `python -m pytest tests/unit/factories/test_agentos_factory.py -k isolation` | `python -m pytest tests/unit/factories/test_agentos_factory.py` | Revert test file; factory untouched |
| WU5 | VQ010 refusal wording (2 docs) | PR1 | `python -m pytest -m unit -q` | `python scripts/spec_gate.py all` | Docs-only revert |

Gitflow (mirrors S5a.1): per WU, branch `feature/vq010-wu{n}` off `main` → focused pytest + ruff → merge `--no-ff`. Order WU1→WU5. Per-commit gates: unit suite + ruff + mypy.

## Phase 1: WU1 — Shared Predicate

- [x] 1.1 RED: add `TestRequireIsolatedAuth` in `tests/unit/agentos/test_authorization_adapter.py`: `(True,None)`, `(True,isolation=False)`, `(True,implicit)` → message naming VQ010 + `user_isolation`; `(True,isolation=True)` → None; auth None/False/0/1/"true" → None.
- [x] 1.2 GREEN: add `_require_isolated_auth(authorization, authorization_config)` in `src/yaml_agno/agentos/authorization_adapter.py` beside `_map_authorization_config`; `is True` both flags; canonical message; `__all__` unchanged.
- [x] 1.3 REFACTOR: docstring; Req 5 privacy test; ruff+mypy.

## Phase 2: WU2 — YamlAgentOS Guard

- [x] 2.1 RED: in `tests/unit/api/test_app_jwt_mode.py` add "YamlAgentOS refuses unisolated construction" (None/explicit-False/implicit-default → `ValueError` VQ010, pre-superclass), "YamlAgentOS preserves JD-01", "Dev path unchanged" (no-auth → 200 (`X-Tenant-Id`)).
- [x] 2.2 GREEN: in `src/yaml_agno/api/app.py` call predicate after JD-01 (`:189`); `ValueError` before `super().__init__`.
- [x] 2.3 RED+GREEN+REFACTOR: "YamlAgentOS accepts isolated config": constructs with `mount_tenant_context=False`; `get_app()` mounts no `TenantContextMiddleware`; shared fixtures.

## Phase 3: WU3 — run_server Guard

- [ ] 3.1 RED: in `tests/unit/runtime/test_run_server_auth.py` add "run_server refuses missing config" + "refuses non-isolated config" (explicit-False/implicit) → `RuntimeError` VQ010 pre-`create_app`, never `FileNotFoundError`; "rejects truthy authorization" (`"true"`).
- [ ] 3.2 GREEN: in `src/yaml_agno/runtime/server.py` keep guard `:120-126` verbatim; predicate → `RuntimeError` before `create_app` (`:128`); keep `**yaml_agentos_kwargs`.
- [ ] 3.3 RED+GREEN+REFACTOR: "run_server boots valid isolated config": FakeServer `run()` once; shared VQ010 assertion helper.

## Phase 4: WU4 — Factory Invariant (test-only)

- [ ] 4.1 RED: in `tests/unit/factories/test_agentos_factory.py` assert "Factory invariant unchanged": adapter build → `user_isolation is True` (content); no-adapter override → `AuthorizationBuildError`.
- [ ] 4.2 GREEN/REFACTOR: no factory code (`git diff --exit-code src/yaml_agno/factories/agentos_factory.py`); gates green.

## Phase 5: WU5 — VQ010 Text + Gates

- [ ] 5.1 "VQ010 query tightened": tighten `.chats/decisions.yaml` VQ010 from presence-only grep to refusal wording (guard + `user_isolation is not True` + refusal exceptions).
- [ ] 5.2 Mirror in `DECISIONES.md` D-F1-10 (Spanish narrative).
- [ ] 5.3 Gates + `--no-ff` merge: `python -m pytest -m unit -q` (840+), `ruff check .`, `mypy src/yaml_agno`, `python scripts/spec_gate.py all` (34/34).
