# Tasks: auth-jwt-native-isolation (S5a.1)

> Option C ratified in `design.md`. Strict TDD. Dev issuer is test-only (never in `src/`).
> Agno 2.8.7 native scoping; zero yaml-agno code on the JWT path. Workdir = repo root.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,700–2,100 total (mostly tests + fixtures) |
| 400-line budget risk | Resolved by re-slicing (8 work units, each ≤400) |
| Chained PRs recommended | Yes (stacked-to-main) |
| Delivery strategy | ask-on-risk → resolved |
| Chain strategy | stacked-to-main (feature branch → validations per unit → merge --no-ff to main → push) |

Decision needed before apply: No (re-sliced 2026-08-19 per maintainer rule: PRs ALWAYS ≤400 lines — re-slice, never expand budget)
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low (per-unit)

### Work Units (gitflow: feature branch `feature/s5a1-auth-jwt-native-isolation` → per-unit validations → merge --no-ff to main → push)

| Unit | Tasks | Goal | Est. LOC | Focused test command | Validations before merge |
|------|-------|------|----------|----------------------|--------------------------|
| WU1 | 1.1–1.3 | Dev JWT issuer + signing-key/authorization fixtures (test-only) | ~350 | `python -m pytest tests/unit/api/test_dev_jwt_issuer.py -q` | pytest unit green + ruff |
| WU2 | 2.1–2.2 | `authorization_config` kwarg + JD-01 guard (app.py) | ~300 | `python -m pytest tests/unit/api/test_app_jwt_mode.py -q` | pytest unit green + ruff + mypy |
| WU3 | 2.3–2.6 | VQ010 refuse-to-start + middleware dev-only cleanup (net-negative in src) | ~400 | `python -m pytest tests/unit -q` | full unit green + ruff + mypy |
| WU4 | 1.4, 3.1–3.2 | StaticReplyModel + L-03 conftest + T1 disjoint buckets + T2 cross-tenant 404 | ~350 | `python -m pytest tests/integration/api/test_jwt_isolation_l03.py -q` | unit + integration green |
| WU5 | 3.3–3.5 | T3 memory isolation + T4 run masking + T5 admin sees all | ~350 | `python -m pytest tests/integration/api/test_jwt_isolation_l03.py -q` | unit + integration green |
| WU6 | 3.6–3.7 | T6 dev-header regression + T7 auth negatives 401 | ~250 | `python -m pytest tests/integration/api/test_jwt_isolation_l03.py -q` | unit + integration green |
| WU7 | 4.1 | SPEC_06 §3.1–3.2 rewrite | ~200 | `python scripts/spec_gate.py all` | spec_gate 0 violations + stale-grep |
| WU8 | 4.2–4.3, 5.1–5.4 | SPEC_19 rewrite + final full verification (pytest, ruff, mypy, spec_gate, VQ010/VQ012/CI greps) | ~250 | full suite | ALL gates green → close S5a.1 |

Unit boundary rule: if a unit's actual diff exceeds 400 lines at merge time, SPLIT the unit before merging — never expand.

---

## Phase 0 — Baseline

- [ ] 0.1 On `main`, clean tree. Verify `agno==2.8.7` and `from agno.os.middleware.jwt import is_reserved_principal` imports. Run `python -m pytest -m unit -q` → green baseline. No commit.

## Phase 1 — Dev issuer helper (test-only, with own unit tests)

- [x] 1.1 **RED** Write `tests/unit/api/test_dev_jwt_issuer.py`: composite built via `resolve_user_id` (no inline `f"{}:{}"`); fail-fast on `:` in tenant and in principal; fail-fast on reserved principals (`sa:x`, `__scheduler__`, `__oauth__:x`); claims `sub`/`scopes`/`iat`/`exp`; `auth_header()` shape. `python -m pytest tests/unit/api/test_dev_jwt_issuer.py -q` → ImportError. Commit: `test(auth): RED DevJwtIssuer contract tests (S5a.1)`
- [x] 1.2 **GREEN** Create `tests/integration/helpers/__init__.py` + `dev_jwt_issuer.py` — `DevJwtIssuer.mint()` + `auth_header()`, delegates to `resolve_user_id()`, guards via `is_reserved_principal`, HS256 via PyJWT. Tests green. Commit: `feat(tests): DevJwtIssuer HS256 helper (S5a.1)`
- [x] 1.3 Create `tests/integration/helpers/conftest.py` fixtures: `dev_jwt_signing_key` (session, `secrets.token_urlsafe(48)`), `authorization_config` (`AuthorizationConfig(verification_keys=[key], algorithm="HS256", user_isolation=True)`), `dev_token` factory. Commit: `test(auth): signing-key + authorization fixtures for L-03 (S5a.1)`
- [x] 1.4 Create `tests/integration/helpers/static_reply_model.py` — no-network `Model` subclass (public `agno.models.base.Model` extension point) returning a canned reply. Commit: `test(auth): StaticReplyModel no-network model (S5a.1)`
- [ ] 1.5 Verify: `python -m pytest tests/unit/api/test_dev_jwt_issuer.py tests/integration -q` green; `ruff check tests/` clean. No commit.

## Phase 2 — Wiring YamlAgentOS (RED → GREEN)

- [x] 2.1 **RED** Write `tests/unit/api/test_app_jwt_mode.py`: (a) JD-01 — `YamlAgentOS(authorization=True, mount_tenant_context=True)` raises `ValueError`; (b) `authorization_config` forwarded to `super().__init__`; (c) JWT-mode app does NOT mount `TenantContextMiddleware` (absent from `app.user_middleware`). → fails. Commit: `test(api): RED JD-01 + conditional-mount contract (S5a.1)`
- [x] 2.2 **GREEN** `src/yaml_agno/api/app.py`: add `authorization_config: AuthorizationConfig | None = None`; JD-01 guard (`ValueError`); forward to `super().__init__`; mount `TenantContextMiddleware` only when not JWT mode; rewrite class/`get_app` docstrings. Tests green. Commit: `feat(api): authorization_config kwarg + JD-01 guard (S5a.1)`
- [x] 2.3 **RED** Write `tests/unit/runtime/test_run_server_auth.py`: `run_server(agents=[...])` (no auth) raises `RuntimeError` before building; `authorization=True` passes the guard and reaches the injected factory. → fails. Commit: `test(runtime): RED VQ010 refuse-to-start contract (S5a.1)`
- [x] 2.4 **GREEN** `src/yaml_agno/runtime/server.py`: first statement in `run_server` refuses unless `yaml_agentos_kwargs.get("authorization") is True` → `RuntimeError`. Tests green. Commit: `feat(runtime): VQ010 run_server refuse without authorization (S5a.1)`
- [x] 2.5 **RED** `tests/unit/api/middleware/test_tenant_context.py`: remove JD-01 JWT-precedence class + `_stamp_jwt_claims_middleware` + `_build_jwt_test_app` (claims no longer read); keep golden-path/fail-fast/delegation suites. Suite green. Commit: `test(middleware): drop dead JWT-claim extraction tests (S5a.1)`
- [x] 2.6 **GREEN** `src/yaml_agno/api/middleware/tenant_context.py`: dev-only contract — remove `_extract_tenant_id` claim logic + `_extract_raw_user_id`; header → `resolve_user_id` only; update module/class docstrings. Suite green. Commit: `refactor(middleware): dev-only header contract, drop tenant_claim/user_sub (S5a.1)`
- [ ] 2.7 Verify: `python -m pytest tests/unit -q` green; `ruff check .` + `mypy src/yaml_agno` clean. No commit.

## Phase 3 — L-03 E2E suite (core; one task per matrix case)

Conftest: `tests/integration/api/conftest.py` — `l03_app` fixture (`YamlAgentOS(agents=[StaticReplyAgent], authorization=True, authorization_config=..., mount_tenant_context=False, db=None)`), `l03_client`, token fixtures `alice_a`/`alice_b`/`admin_token`.

- [x] 3.1 Scaffold `tests/integration/api/test_jwt_isolation_l03.py` + conftest; **T1** same `alice` under tenants A/B → disjoint session buckets. Commit: `test(auth): L-03 T1 disjoint session buckets (S5a.1)`
- [x] 3.2 **T2** alice/B reads alice/A's session id → **404** (native masking). Commit: `test(auth): L-03 T2 cross-tenant session 404 (S5a.1)`
- [ ] 3.3 **T3** memories isolated: B list/read of A's memory → empty/404. Commit: `test(auth): L-03 T3 memory isolation (S5a.1)`
- [ ] 3.4 **T4** alice/B fetches alice/A's run in session → **404** (runs masked). Commit: `test(auth): L-03 T4 cross-tenant run 404 (S5a.1)`
- [ ] 3.5 **T5** admin (`scopes=["agent_os:admin"]`) lists BOTH tenants' sessions. Commit: `test(auth): L-03 T5 admin sees all (S5a.1)`
- [ ] 3.6 **T6** dev-header app (`authorization=False`, `mount_tenant_context=True`, separate instance) still green — `X-Tenant-Id` path regression. Commit: `test(auth): L-03 T6 dev-header path regression (S5a.1)`
- [ ] 3.7 **T7** negatives: no token / invalid signature / expired token → **401**. Commit: `test(auth): L-03 T7 auth negatives 401 (S5a.1)`

Each: `python -m pytest tests/integration/api/test_jwt_isolation_l03.py -q` (green).

## Phase 4 — Docs SPEC_06 / SPEC_19

- [ ] 4.1 `specs/SPEC_06_API_AND_AX.md` §3.1 approach rewrite (composite minted into `sub` at issuance; Agno threads natively; delete "middleware extracts `tnt`" narrative); §3.2 middleware = dev/no-JWT only + JD-01 mutual exclusion; §2 `get_app` snippet. Commit: `docs(spec): SPEC_06 §3 JWT-native isolation contract (S5a.1)`
- [ ] 4.2 `specs/SPEC_19_SECURITY_AUTH_API_SURFACE.md`: supersede `build_jwt_middleware` narrative with AuthorizationAdapter (S5a.0) + agno `build_jwt_middleware_kwargs`; delete "TenantContextMiddleware resolves sub→composite"; admin = native `agent_os:admin`; reference `user_id_claim` escape hatch (`jwt.py:547`). Commit: `docs(spec): SPEC_19 native auth + admin contract (S5a.1)`
- [ ] 4.3 Grep `specs/` + `src/` for stale `tenant_claim` / `user_sub` / `tnt` middleware refs → none. No commit.

## Phase 5 — Final verification

- [ ] 5.1 `python -m pytest -q` → full suite green.
- [ ] 5.2 `ruff check .` and `mypy src/yaml_agno` → clean.
- [ ] 5.3 `python scripts/spec_gate.py all` → 0 violations.
- [ ] 5.4 Greps: **VQ010** `rg -n 'authorization=True|user_isolation' src/yaml_agno/api/ src/yaml_agno/agentos/`; **VQ012** `rg -n 'f"\{tenant_id\}"|resolve_user_id' src/yaml_agno/api/` (no inline composite); CI gate `rg -n "DevJwtIssuer" src/` → exit ≠ 0 (dev helper never in `src/`).

## Dependency Graph

```
P0: 0.1
P1: 1.1 → 1.2 → 1.3 ┐
                1.2 → 1.4 ─→ 1.5
P2: 2.1 → 2.2 ─┐
    2.3 → 2.4 ─┼→ 2.7      (2.5 → 2.6 parallel)
    2.5 → 2.6 ─┘
P3: 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → 3.7   (sequential, matrix order)
P4: 4.1 ∥ 4.2 → 4.3
P5: 5.1 → 5.2 → 5.3 → 5.4
```

## Traceability

| Task(s) | Design ref | Files |
|---------|-----------|-------|
| 0.1 | — | repo |
| 1.1–1.5 | Dev Issuer Contract | `tests/integration/helpers/{__init__,dev_jwt_issuer,static_reply_model}.py`, `tests/integration/helpers/conftest.py`, `tests/unit/api/test_dev_jwt_issuer.py` |
| 2.1–2.2 | JD-01, Wiring | `src/yaml_agno/api/app.py`, `tests/unit/api/test_app_jwt_mode.py` |
| 2.3–2.4 | VQ010 | `src/yaml_agno/runtime/server.py`, `tests/unit/runtime/test_run_server_auth.py` |
| 2.5–2.6 | Middleware dev-only | `src/yaml_agno/api/middleware/tenant_context.py`, `tests/unit/api/middleware/test_tenant_context.py` |
| 3.1–3.7 | L-03 matrix T1–T7 | `tests/integration/api/test_jwt_isolation_l03.py`, `tests/integration/api/conftest.py` |
| 4.1–4.3 | SPEC_06 §3.1–3.2, SPEC_19 | `specs/SPEC_06_API_AND_AX.md`, `specs/SPEC_19_SECURITY_AUTH_API_SURFACE.md` |
| 5.1–5.4 | Success criteria, risks | — |

**Forecast**: ~27 tasks · ~23 commits · ~1,700–2,100 LOC total (≈85% tests/docs) · 8 work units ≤400 LOC each · stacked-to-main · per-unit validations (pytest/ruff/mypy/spec_gate) before every merge.
