# Proposal: auth-jwt-native-isolation (S5a.1)

## Intent

Activate Agno 2.8.7 native JWT + `user_isolation` in `YamlAgentOS` and prove gate L-03 E2E (2+ tenants, same instance, 0 cross-tenant leaks — D-F1-11, blocking client data). Today `authorization=False` (slice-A default) and `TenantContextMiddleware` targets claim names that do not exist in agno 2.8.7: it reads `request.state.user_sub`/`tenant_claim`, but Agno stamps `user_id` (bare `sub`), `claims`, `scopes` (`agno/os/middleware/jwt.py:1059-1072`). Being outermost it runs BEFORE Agno's JWT middleware, so with JWT active it sees no claims (falls back to the spoofable header) and is then overwritten by `jwt.py:1060` — the composite dies and L-03 is impossible as designed.

## Scope

### In Scope
- `YamlAgentOS` path: `authorization=True` + `AuthorizationConfig` (HS256 dev key, `user_isolation=True` invariant) via the S5a.0 `AuthorizationAdapter`.
- Test-only dev JWT issuer (HS256) minting composite `sub="{tenant_id}:{principal_id}"` + scopes; `sub` built via `resolve_user_id()` (VQ012 — no inline composites anywhere).
- Middleware mode contract: JWT mode vs dev-header mode, mutually exclusive (Approach).
- L-03 E2E suite: SAME `principal_id` under 2 tenants; cross-tenant reads 404/masked; `admin_scope` sees all; dev header path still works.
- SPEC_06 §3.1-3.2 + SPEC_19 reference updates for the new middleware contract.

### Out of Scope
- Keycloak (S5b), Casbin/PolicyEnforcer (S5a.2), RLS (prohibited, D-F1-05), any edit to agno `src/`.

## Capabilities

### New Capabilities
- `agentos-jwt-isolation`: native JWT activation path, composite-sub issuer contract, middleware mode contract, L-03 gate.

### Modified Capabilities
- None. `agentos-authorization-build` (S5a.0) is consumed unchanged.

## Approach

Recommended: **Option C (hybrid)** — dev issuer mints composite `sub`; Agno's native pipeline does ALL scoping (`jwt.py:1039` reads `sub` → `user_id`; `user_scope.py:105` threads it on every read/write). Zero yaml-agno code on the JWT path.

| Option | Verdict | Why |
|---|---|---|
| A — composite `sub`, decide Keycloak mapper NOW | Deferred | Max alignment, but forces non-standard Keycloak `sub` override prematurely |
| B — inner middleware post-JWT | Rejected | No clean insertion point after Agno's JWT middleware without wrapping/monkeypatching = Frankenstein (PHIL001/PHIL004) |
| **C — hybrid** | **Recommended** | A's mechanics for the dev issuer; S5b decides Keycloak (custom claim + `user_id_claim` `jwt.py:547`, or mapper) in its own design |

Middleware contract: with `authorization=True`, `TenantContextMiddleware` is NOT mounted — Agno owns identity, the header is never read (JD-01 becomes structural exclusion, not claim precedence). With `authorization=False` (dev/test), current header→`resolve_user_id` behavior is unchanged. Edge: composite `sub` must not collide with reserved principals (`sa:`, `__scheduler__` — `jwt.py:1048`) → fail-fast `tenant_id` validation at issuance.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/yaml_agno/api/app.py` | Modified | Authorization activation; conditional middleware mounting |
| `src/yaml_agno/api/middleware/tenant_context.py` | Modified | Contract reduced to the dev/no-JWT path |
| `tests/` (issuer helper + L-03 suite) | New | Dev HS256 issuer; E2E isolation suite |
| `specs/SPEC_06_API_AND_AX.md`, `specs/SPEC_19_*` | Modified | Middleware contract rewrite |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Keycloak `sub`=UUID vs composite (S5b tension) | High (deferred by design) | Documented contract; S5b design owns the decision |
| Reserved-principal collision in composite `sub` | Low | Fail-fast `tenant_id` validation at issuance |
| JWT mode accidentally mounts header middleware | Low | Contract test: JWT mode must NOT mount TenantContextMiddleware |

## Rollback Plan

Pure code revert to slice-A state (`authorization=False`, middleware always mounted). No schema, migration, or data implications.

## Dependencies

- agno==2.8.7 (pinned); S5a.0 `AuthorizationAdapter` (archived `auth-r1-fail-fast`); SPEC_04 `resolve_user_id` (closed).

## Success Criteria

- [ ] L-03 suite green: 2+ tenants same instance, same principal in both, 0 leaks; admin sees all; dev path works
- [ ] VQ010 (always-on production auth) and VQ012 (single composite builder) hold
- [ ] Unit suite green; ruff + mypy clean
