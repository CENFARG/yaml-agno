# Exploration: auth-vq010-isolation-guard

## Current State

**HEAD**: `826f9d2` (merge S5a.1 final fix, 840 passed / 1 skipped). Worktree clean. Change `auth-jwt-native-isolation` is verified (840 green, L-03 T1-T7 green, ruff/mypy/spec_gate clean) but Judgment Day is `ESCALATED` pending the VQ010 isolation hole and is not archived or pushed. S5a.0 (`agentos-authorization-build`) is already archived.

**What VQ010 promises** (`.chats/decisions.yaml` VQ010, `DECISIONES.md` D-F1-02, `DECISIONES.md` D-F1-10):
> `rg -n 'authorization=True|user_isolation' src/yaml_agno/api/ src/yaml_agno/agentos/` must show always-on `authorization=True` + `AuthorizationConfig(user_isolation=True)` in production. Agno 2.8.7 `AuthorizationConfig` (`agno/os/config.py:121-139`, verified `help(AuthorizationConfig)` in this exploration) defaults `user_isolation=False` and accepts exactly 7 fields with `extra=ignore` — a silent fail-open if `basic_auth` or unknown keys are forwarded.

**How the code works today**:

1. `src/yaml_agno/runtime/server.py:120-126` — `run_server` is the documented production entry point. Guard is:
   ```python
   if yaml_agentos_kwargs.get("authorization") is not True: raise RuntimeError(VQ010)
   ```
   It does **not** inspect `authorization_config` or `user_isolation`. A caller can pass `authorization=True, authorization_config=AuthorizationConfig(user_isolation=False, verification_keys=[...])` or `authorization=True` with no config and pass the guard, then produce an authenticated-but-not-isolated deployment.

2. `src/yaml_agno/api/app.py:92-206` (`YamlAgentOS(AgentOS)`) — constructor accepts `authorization: bool=False` and `authorization_config: AuthorizationConfig | None`. Forwards both to `super().__init__` (`agno.os.AgentOS`). Has exactly one auth-related guard: JD-01 mutual exclusion `if authorization and mount_tenant_context: raise ValueError` (`app.py:183-189`). Has **no** `user_isolation` guard. `get_app():275-276` mounts `TenantContextMiddleware` only when `self._mount_tenant_context and not self.authorization` — structurally correct, but does not refuse `authorization=True` with `user_isolation=False`.

3. `src/yaml_agno/agentos/authorization_adapter.py:56-126` (`_map_authorization_config`) and `src/yaml_agno/factories/agentos_factory.py:278-534` — the YAML factory path is **already safe**: `AuthorizationAdapter.build()` and the legacy `_map_authorization_config` whitelist the 6 settable fields, reject `basic_auth`/`unknown`/`user_isolation` override, and always build `AuthorizationConfig(**kwargs, user_isolation=True)`. Any `AgentOSConfig(authorization.enabled=True, config={...})` built via `AgentOSFactory` is therefore isolated by construction.

4. `src/yaml_agno/runtime/server.py:54-83` (`create_app`) — pure dev seam, no guard, documented as `For dev/test workflows without JWT, use create_app() instead`. `AgentOSFactory.build()` returns plain `agno.os.AgentOS` (not `YamlAgentOS`) and is also a production-equivalent path with no `run_server` interlock.

**Result**: the invariant holds **only** when the operator goes through the YAML factory. Direct `YamlAgentOS(authorization=True, authorization_config=AuthorizationConfig(..., user_isolation=False))` or direct `AgentOS(authorization=True, authorization_config=...)` bypasses it. Judgment Day Judge B correctly flagged this as CRITICAL; Judge A missed it (hence ESCALATED, not auto-fixed).

### Entrypoint inventory (Q1 answered)

| Entrypoint | File:Line | Production? | Can bypass current VQ010? | Why |
|---|---|---|---|---|
| `run_server(**kwargs)` | `runtime/server.py:86` | **Yes** — documented production entry point | **Yes, partially** | Guard checks only `authorization is True`, not `user_isolation` |
| `create_app(**kwargs)` | `runtime/server.py:54` | Dev/test seam (explicit) | **Yes** | No guard by design; delegates to `YamlAgentOS` |
| `YamlAgentOS(...).get_app()` + external ASGI (uvicorn/gunicorn) | `api/app.py:92,246` | **Yes** — any runner can call `app = YamlAgentOS(...).get_app()` directly | **Yes — primary bypass** | No `user_isolation` guard; JD-01 only |
| `AgentOSFactory.build(AgentOSConfig)` → `AgentOS(...).get_app()` | `factories/agentos_factory.py:172,326-339` | Yes — YAML aggregate root path | **No** (today) | Adapter enforces `user_isolation=True`; safe **iff** adapter is injected. Legacy path also enforces via same helper, but direct `YamlAgentOS` bypass skips the factory entirely |
| `agno.os.AgentOS` directly | external dep `agno==2.8.7` | Out of yaml-agno ownership | N/A | Not yaml-agno's to guard, but yaml-agno must not encourage it |

No `pyproject.toml` `[project.scripts]` CLI entry or `src/yaml_agno/cli.py` producing an additional production entry point was found. `runtime/__init__.py:1-7` re-exports `create_app`/`run_server` only.

## Affected Areas

- `src/yaml_agno/api/app.py:92-206` — **primary enforcement site**. Add isolation invariant to `YamlAgentOS.__init__`; authoritative boundary that covers `create_app` and direct `YamlAgentOS` usage. JD-01 guard stays.
- `src/yaml_agno/runtime/server.py:86-136` — **defense-in-depth site**. Extend VQ010 guard (lines 120-126) to also require `authorization_config.user_isolation is True`. Keep `RuntimeError` type and VQ010 message; preserve strict `is True` identity check.
- `src/yaml_agno/agentos/authorization_adapter.py:34-126` — **shared invariant owner** (optional but preferred). Extract a tiny public/private helper `validate_authorization_isolation(authorization, authorization_config)` or reuse `_map_authorization_config` knowledge so both `app.py` and `server.py` share one predicate. No Agno internals, no RLS, no Casbin, no `kwargs.update` — just read `AuthorizationConfig.user_isolation` (public field, `help(AuthorizationConfig)` confirmed).
- `src/yaml_agno/factories/agentos_factory.py:486-534` — **no code change needed**; verify-tested. Document that this path already satisfies the invariant and is the reference implementation.
- `tests/unit/runtime/test_run_server_auth.py:43-113` — expand VQ010 contract tests with isolation negatives (see § Tests).
- `tests/unit/api/test_app_jwt_mode.py` (S5a.1 WU2, `tests/unit/api/test_app_jwt_mode.py` in S5a.1) — add YamlAgentOS isolation negatives; keep JD-01 tests green.
- `tests/unit/factories/test_agentos_factory.py` + `tests/unit/agentos/test_authorization_adapter.py` — add explicit factory-path content assertions (already content-asserting per `agentos-authorization-build` spec, but add disabled/missing cases).
- `openspec/specs/agentos-authorization-build/spec.md` + `openspec/specs/memory-identity-leaf` — **no in-place edit**; S5a.1 specs stay immutable until archive. The fix ships a delta spec under `openspec/changes/auth-vq010-isolation-guard/specs/` (see § Scope).
- `.chats/decisions.yaml` VQ010 + `DECISIONES.md` D-F1-10/D-F1-11 — read-only for this exploration; the next phase may propose a VQ010 query clarification (see § Scope).

## Approaches

### 1. Extend `run_server` guard only (Judge B's minimal patch)

- What: `runtime/server.py:120` becomes `if kwargs.get("authorization") is not True or not getattr(kwargs.get("authorization_config"), "user_isolation", False) is True: raise RuntimeError(...)`.
- Pros: single-file diff, smallest blast radius, no constructor signature change, preserves dev `YamlAgentOS`/`create_app` path untouched.
- Cons: **does not close the direct `YamlAgentOS` bypass** — `app = YamlAgentOS(authorization=True, authorization_config=AuthorizationConfig(user_isolation=False)).get_app()` + `uvicorn.run(app)` still boots authenticated-but-not-isolated. Fails the "safest minimal boundary" criterion. Requires duplicating the predicate if YamlAgentOS is later patched anyway.
- Effort: Low (1 file, 5-10 lines + tests).

### 2. Guard in `YamlAgentOS.__init__` only

- What: at `api/app.py:183` after JD-01, add `if authorization: if authorization_config is None or getattr(authorization_config, "user_isolation", False) is not True: raise ValueError("VQ010: authorization=True requires AuthorizationConfig(user_isolation=True) ...")`. `create_app` inherits the guard transitively. `run_server` keeps its existing `is True` check (or delegates).
- Pros: **authoritative** — closes every YamlAgentOS-derived path, including `create_app` and external ASGI runners. Single public invariant owner (subclass that all yaml-agno callers touch). Strict `is True` prevents `1`/`"true"` truthy bypass.
- Cons: `run_server` still benefits from an earlier, more descriptive `RuntimeError` before building agents/YAML; relying solely on constructor defers the failure to `YamlAgentOS` construction (still before network binding but after YAML parsing potential). Needs careful `None`/`False` default semantics.
- Effort: Low (1 file + tests).

### 3. Shared validator — YamlAgentOS authoritative, `run_server` defense-in-depth (RECOMMENDED)

- What: define one predicate, e.g. `def _require_isolated_auth(authorization: bool, authorization_config: AuthorizationConfig | None) -> None:` that raises `ValueError` (constructor) / `RuntimeError` (server) with a VQ010-referencing message if `authorization is True` and `authorization_config is None or authorization_config.user_isolation is not True`. Place it in `agentos/authorization_adapter.py` (SSOT for the invariant, already owns `_SUPPORTED_FIELDS`/`_map_authorization_config`) or as a private helper in `api/app.py` imported by `runtime/server.py`. Both call sites call the same predicate (DRY, no drift). Keep exception types distinct: `ValueError` in `YamlAgentOS` (construction contract, matches JD-01), `RuntimeError` in `run_server` (production refusal contract, matches existing tests `test_run_server_auth.py:49,56,70,79`).
- Pros: **minimal + safest** — single source of truth for "isolated auth", no duplication, closes both bypasses, preserves `is True` strictness, keeps Agno public API only (`AuthorizationConfig.user_isolation`). No new dependencies, no RLS/Casbin. Aligns with anti-Frankenstein: adapter owns `user_isolation=True`, app/server just validate the built value.
- Cons: two files touched instead of one (still <30 lines src), shared import creates a tiny coupling `runtime → agentos` (acceptable — `runtime/server.py` already imports `YamlAgentOS` from `api`, which already depends on `agentos`). Alternative placement `api ↔ runtime` would invert the dependency less cleanly.
- Effort: Low (2 files, ~15 lines src + ~80 lines tests).

### 4. Factory-only hardening

- What: add validation inside `AgentOSFactory.build()` that `kwargs["authorization_config"].user_isolation is True`.
- Pros: protects YAML path doubly.
- Cons: **irrelevant to the bypass** — the YAML path already enforces the invariant via the adapter; the bypass is the non-factory `YamlAgentOS` path. Adds a check where it is already guaranteed, misses where it is not.
- Effort: Low, but wrong layer.

| Approach | Closes `run_server` bypass | Closes `YamlAgentOS` direct bypass | Preserves `create_app` dev path | DRY | Risk of drift |
|---|---|---|---|---|---|
| 1 run_server only | Yes | No | Yes | N/A | High — YamlAgentOS stays open |
| 2 YamlAgentOS only | Partial (via delegation) | Yes | Yes | Single site | Low |
| **3 Shared (recommended)** | **Yes (explicit)** | **Yes (authoritative)** | **Yes** | **Yes** | **Lowest** |
| 4 Factory only | No | No | Yes | N/A | N/A |

## Recommendation

**Adopt Approach 3 — shared validator, YamlAgentOS authoritative + `run_server` defense-in-depth.**

**Rationale**:
- The Judgment Day CRITICAL is precisely that `authorization=True` without `user_isolation=True` is bootable. The authoritative construction boundary is `YamlAgentOS.__init__` (`api/app.py:92`) — every yaml-agno production app goes through it, including `create_app`. `run_server` (`runtime/server.py:86`) is the documented production *entry point* and must refuse **before** agent/YAML building (current lines 120-126 run as first statement, message already references VQ010 and dev seam).
- Enforcing in both places with a single predicate gives defense-in-depth without duplication or Agno internals coupling. The YAML factory path (`factories/agentos_factory.py:486-514`) is already correct and serves as the reference implementation; no change there.
- This keeps the anti-Frankenstein constraint: the predicate reads the **public** `AuthorizationConfig.user_isolation` field (`agno==2.8.7`, verified `False` default), never touches `agno/os/middleware/jwt.py` or `user_scope.py` internals, never adds RLS/Casbin/duplicate auth logic, and never touches `os.environ`.
- Dev/test preservation: guard is `if authorization is not True: pass` — `authorization=False` (S5a.1 default) remains allowed with `mount_tenant_context=True`. The strict `is True` identity check already in `runtime/server.py:120` (and `test_run_server_auth.py:76-84` asserts it rejects `"true"`) is preserved; the new check adds `authorization_config` inspection only when `authorization is True`.

**Minimal enforcement boundary**: `YamlAgentOS.__init__` is the safest minimal boundary; `run_server` mirrors it via the shared helper for early refusal and clearer `RuntimeError` UX. No need to guard `AgentOSFactory` or `AgnoResolver` — they already enforce via `_map_authorization_config`.

**Dev/test preservation (Q3 answered)**:
- `YamlAgentOS()` / `YamlAgentOS(authorization=False)` / `create_app(agents=[...])` continue to work (header middleware mounted, dev semantics).
- `YamlAgentOS(authorization=True, authorization_config=AuthorizationConfig(verification_keys=[k], algorithm="HS256", user_isolation=True), mount_tenant_context=False)` is the only accepted production form.
- Tests that inject `FakeServer` (`test_run_server_auth.py:31-41`, `test_runtime_server.py:97-109`) keep working by passing a valid `authorization_config` with `user_isolation=True` (the S5a.1 conftest already does: `tests/integration/helpers/conftest.py:19-23`).

## Risks

- **If only `run_server` is patched, direct `YamlAgentOS` bypass survives** — an operator or future CLI/helper that builds `YamlAgentOS` and runs it under `uvicorn.Server`/`gunicorn` can still ship `user_isolation=False`. Mitigated by YamlAgentOS-authoritative recommendation.
- **Strict `is True` vs truthy**: `authorization=True` must be checked with `is True`, not `if authorization:`. Current code already does this correctly in `runtime/server.py:120`; YamlAgentOS uses `if authorization and mount_tenant_context` (`app.py:183`) which is truthy — new guard must use `is True` for the isolation branch to avoid `"true"`/`1` bypass.
- **`authorization_config=None`**: `YamlAgentOS` forwards `None` to `super().__init__`; Agno then fails later on missing `verification_keys` (`os/app.py:1387-1393`) but not on isolation. The new guard must catch `None` explicitly before delegating to Agno, with a message naming `VQ010` and `user_isolation`.
- **`AuthorizationConfig` is mutable after construction**: guard reads `config.user_isolation` at `__init__` time only; post-construction mutation is out of scope (same as JD-01). Document as out-of-scope; Agno itself does not re-validate after `super().__init__`.
- **Factory path divergence**: if the shared helper lives outside `authorization_adapter.py`, the set of valid fields (`_SUPPORTED_FIELDS`) and `user_isolation=True` invariant must not diverge from `_map_authorization_config`. Placing the helper alongside that module or importing its constant prevents drift.
- **Spec drift**: S5a.1 specs (`openspec/specs/agentos-authorization-build`, `openspec/changes/auth-jwt-native-isolation`) describe `user_isolation` as invariant but do not state the `YamlAgentOS`/`run_server` *refusal* contract. Without a delta spec, VQ010 query text remains under-specified. Mitigated by shipping a delta spec in the new change.

## Ready for Proposal

**Yes — ready for `sdd-propose` to create `auth-vq010-isolation-guard`.**

**What the proposal must contain**:

1. **Entrypoint clarification** (Q1): enumerate the 4 entrypoints above; state that the fix closes the two production-bypassable ones (`run_server` + direct `YamlAgentOS`/`create_app`), leaves the YAML factory as reference, and leaves plain `agno.os.AgentOS` out of scope.

2. **Boundary decision** (Q2): ratify shared validator approach; `YamlAgentOS` authoritative (`ValueError`), `run_server` defense-in-depth (`RuntimeError`), one predicate, one message referencing VQ010 + S5a.1 + dev seam.

3. **Dev preservation** (Q3): explicit invariant — `authorization=False` default stays bootable; guard fires only when `authorization is True`; `mount_tenant_context` contract unchanged; existing unit/integration suites stay green.

4. **Test matrix (Q4 — exact tests required)**:
   - Negative `run_server`: `authorization=True, authorization_config=None` → `RuntimeError` VQ010; `authorization=True, AuthorizationConfig(user_isolation=False, ...)` → `RuntimeError`; `authorization=True, AuthorizationConfig(..., verification_keys=[k])` with default `user_isolation=False` → `RuntimeError`; `authorization="true"` → `RuntimeError` (already existing, keep).
   - Negative `YamlAgentOS`: `YamlAgentOS(agents=[...], authorization=True, authorization_config=None)` → `ValueError`; `..., authorization_config=AuthorizationConfig(user_isolation=False, ...)` → `ValueError`; `..., authorization_config=AuthorizationConfig(verification_keys=[k])` (implicit False) → `ValueError`; `YamlAgentOS(authorization=True, authorization_config=valid, mount_tenant_context=True)` → `ValueError` JD-01 already, keep.
   - Positive: `YamlAgentOS(agents=[...], authorization=True, authorization_config=AuthorizationConfig(verification_keys=[k], algorithm="HS256", user_isolation=True), mount_tenant_context=False)` → succeeds; `.get_app()` mounts no `TenantContextMiddleware` (assert `app.user_middleware`); `run_server(..., authorization=True, authorization_config=valid, mount_tenant_context=False, server_factory=fake)` → `fake.run()` called once.
   - Factory path: `AgentOSFactory(build with adapter).build(AgentOSConfig(authorization.enabled=True, config={algorithm:"HS256"}))` → `auth_config.user_isolation is True` (content assertion, not `is not None`); `AgentOSFactory` without adapter + `config={user_isolation:False}` still raises `AuthorizationBuildError` (existing).
   - No regression: `create_app(agents=[...])` (no auth) → `FastAPI`; `create_app(config_path=..., memory_cfg=...)` with `X-Tenant-Id` header still 200 (existing `test_runtime_server.py:74-85`); full `python -m pytest -q` 840 green; `ruff` + `mypy` clean; `python scripts/spec_gate.py all` 34/34.

5. **Scope & rollback (Q5)**:
   - **Scope**: new change `auth-vq010-isolation-guard` — delta spec `specs/api-isolation-guard` or patch to `agentos-authorization-build` with `ADDED Requirement: isolation refusal contract` (guard in `YamlAgentOS` + `run_server`); 2 src files + shared helper; ~4 test files expanded; no migration.
   - **Modify S5a.1 or separate?** Separate. S5a.1 target `826f9d2` is immutable (verified, Judgment Day evidence quoted). Do not rewrite `auth-jwt-native-isolation/proposal.md`/`design.md`/`specs` in place; reference them as `DependsOn: auth-jwt-native-isolation (826f9d2)`. If the maintainer prefers to amend S5a.1 before archive, the delta can be folded as `MODIFIED Requirement` — but default is separate corrective change.
   - **Rollback**: revert 2 guards + helper (1 commit). Restores S5a.1 verified state (authenticated-but-not-isolated bootable, L-03 still green). No DB, no env, no archived spec mutation.

6. **Anti-Frankenstein (Q6)**: checklist — uses `agno.os.config.AuthorizationConfig` public field; reuses `AuthorizationAdapter`/`_map_authorization_config` knowledge; no `import agno.os.middleware.jwt` beyond already-used `is_reserved_principal` in test helpers; no RLS (`ROW LEVEL SECURITY` grep must stay ZERO per VQ014); no `import casbin` (VQ013); no `os.environ` in `api/`/`agentos/`/`memory/` (VQ015); no inline `f"{tenant_id}:{principal_id}"` (VQ012 via `resolve_user_id` only).

**Open questions for proposal to resolve**:
- Exact helper location: `agentos/authorization_adapter.py:validate_isolated_auth` vs private `api/app.py:_require_isolated_auth` — decision to include in proposal's File Changes table.
- VQ010 query text update: current `.chats/decisions.yaml` VQ010 says `rg -n 'authorization=True|user_isolation' ...` (presence check). Should be tightened to `authorization=True` + `user_isolation is True` refusal contract — propose edited query or keep code-level enforcement only.
- Whether `run_server` should also expose `authorization_config` explicitly in its signature (mirroring `YamlAgentOS`) or keep `**yaml_agentos_kwargs` — keep `**kwargs` to avoid API churn; guard reads from kwargs.

**Traceability for proposal**: `DECISIONES.md` D-F1-02 (JWT always-on) + D-F1-10 (R1 whitelist, 7 fields) + `specs/SPEC_06` §2-3 + `specs/SPEC_19` + `agentos-authorization-build` whitelist + Judgment Day report `#3120` (Judge B CRITICAL).
