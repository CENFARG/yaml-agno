# Tasks: auth-r1-fail-fast

> S5a.0 — kill the R1 declarative fail-open in `AuthorizationConfig` build.
> Strict TDD (RED → GREEN) per task; each task is one potential conventional commit.
> Whitelist = agno 2.8.7 7 fields; `_SUPPORTED_FIELDS` documents verified version.

## Forecast

- **LOC**: ~300 (2 src adapters + 1 schema doc + 2 test rewrites)
- **Risk**: Medium (breaking by design: configs with `basic_auth`/bad keys now raise)
- **PRs**: 1
- **Spec coverage**: 7 requirements, 27 scenarios
- **Gates**: VQ011 (`.chats/decisions.yaml`), D-F1-10

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 0 — Baseline

- [ ] 0.1 Confirm clean working tree; verify installed agno 2.8.7
  `AuthorizationConfig` accepts exactly the 7 documented fields
  (`python -c "from agno.os.config import AuthorizationConfig; print(AuthorizationConfig.model_fields.keys())"`).
- [ ] 0.2 Confirm both blind-forward sites exist:
  `authorization_adapter.py:77-81` (`kwargs.update` + `kwargs["basic_auth"]`) and
  `agentos_factory.py:515-524` (`auth_kwargs["basic_auth"]` + `["config"]`).

## Phase 1 — Schema + error docs (no behavior change)

- [x] 1.1 `src/yaml_agno/models/config/agentos_config.py`: extend
  `AuthorizationSettings.basic_auth` (line 53) Field `description` + class docstring
  to mark it UNSUPPORTED in agno 2.8.7 with pointer to
  `BasicAuthMiddleware` (SPEC_19 §1.2, S5a.2). NO `DeprecationWarning`, NO removal.
  **Spec**: Req 7. Commit: `docs(agentos): mark basic_auth UNSUPPORTED (S5a.2)`.
- [x] 1.2 `src/yaml_agno/agentos/errors.py`: extend `AuthorizationBuildError` docstring
  to cover whitelist rejections (unknown key, `basic_auth`, `user_isolation` override,
  unresolved secret) — no new class. **Spec**: Reqs 1-5. Same commit as 1.1.

## Phase 2 — RED: adapter contract tests (content assertions)

- [x] 2.1 Rewrite `tests/unit/agentos/test_authorization_adapter.py` T007b (secret
  resolution) using a REAL whitelisted key
  (`config={"verification_keys": ["${SECRET:JWT_SIGNING_KEY}"]}`), asserting
  `cfg.verification_keys == ["hush-hush"]` and `cfg.algorithm == "HS256"`.
  Must fail on unknown-key handling. **Spec**: Req 4.
- [x] 2.2 Rewrite T007d (`basic_auth`) into rejection tests: non-empty AND empty dict
  with `enabled=True` → `AuthorizationBuildError` mentioning `basic_auth`,
  `agno 2.8.7`, `BasicAuthMiddleware`; `enabled=False` → `(False, None)`.
  **Spec**: Req 2.
- [x] 2.3 Rewrite T007e (non-secret passthrough) to assert CONTENT
  (`cfg.user_isolation is True`, `cfg.algorithm == "HS256"`, `cfg.verify_audience is True`).
  **Spec**: Req 6.
- [x] 2.4 Add whitelist tests: unknown key `{"foo": 1}` → error listing the 7 fields;
  whitelist error wins over secret resolution (secret_manager never invoked);
  `config={}` and `config=None` valid with `user_isolation is True`;
  disabled guard wins over unknown key. **Spec**: Req 1.
- [x] 2.5 Add `user_isolation` override tests (`True` and `False` both raise with the
  invariant message; absent key → `cfg.user_isolation is True`). **Spec**: Req 3.
- [x] 2.6 Run `python -m pytest tests/unit/agentos/test_authorization_adapter.py -m unit`
  → RED (expect failures). Commit: `test(agentos): RED contract tests for fail-fast auth build (T007b/d/e rewrite)`.

## Phase 3 — GREEN: adapter whitelist + shared helper

- [x] 3.1 `src/yaml_agno/agentos/authorization_adapter.py`: add module-level
  `_SUPPORTED_FIELDS` (the 6 settable fields + documented 7-field list) and a
  `_`-prefixed private helper `_map_authorization_config(...)` (pure mapping +
  rejections) shared by adapter and legacy path; NOT in `__all__`. **Spec**: Reqs 1, 5.
- [x] 3.2 Rewrite `AuthorizationAdapter.build()`: whitelist check BEFORE secret
  resolution; reject unknown keys, `basic_auth`, and `user_isolation` override;
  construct with `user_isolation=True`; remove `kwargs.update` and `kwargs["basic_auth"]`.
  **Spec**: Reqs 1-4.
- [x] 3.3 Run adapter tests → all green. Commit:
  `feat(agentos): fail-fast AuthorizationConfig build via field whitelist (VQ011)`.

## Phase 4 — RED: legacy-path factory tests

- [x] 4.1 Update `tests/unit/factories/test_agentos_factory.py` tests at :799 and :841:
  legacy path (no adapter injected) rejects unknown key / `basic_auth` / unresolved
  `${SECRET:...}` literal (naming the key), and builds valid config with
  `user_isolation is True`. Run → RED. **Spec**: Req 5.
  Commit: `test(factories): RED legacy auth-path rejection tests`.

## Phase 5 — GREEN: legacy path parity

- [ ] 5.1 Rewrite `AgentOSFactory._build_authorization_config_legacy`
  (`agentos_factory.py:515-524`) to build through the SAME shared
  `_map_authorization_config` helper; raise `AuthorizationBuildError` on any
  residual `${SECRET:...}` literal (never forward the raw string). **Spec**: Req 5.
- [ ] 5.2 Run factory tests → all green. Commit:
  `feat(factories): legacy auth path delegates to shared whitelist helper`.

## Phase 6 — Verification

- [ ] 6.1 VQ011 greps (zero matches expected):
  `grep -n "kwargs.update" src/yaml_agno/agentos/authorization_adapter.py`;
  `grep -nE "basic_auth\]" src/yaml_agno/agentos/authorization_adapter.py src/yaml_agno/factories/agentos_factory.py`.
- [ ] 6.2 `python -m pytest tests/unit/agentos/ tests/unit/factories/test_agentos_factory.py -m unit`
  → 0 failed. **Spec**: Req 6.
- [ ] 6.3 `ruff check src/yaml_agno/agentos/ src/yaml_agno/factories/agentos_factory.py src/yaml_agno/models/config/agentos_config.py` → zero findings.
- [ ] 6.4 `mypy src/yaml_agno/agentos src/yaml_agno/factories/agentos_factory.py` → zero errors.
- [ ] 6.5 Confirm no existence-only assertions remain:
  `grep -n "cfg is not None" tests/unit/agentos/test_authorization_adapter.py tests/unit/factories/test_agentos_factory.py` → no output. **Spec**: Req 6.
- [ ] 6.6 Confirm `__all__` unchanged (helper stays private):
  `grep -n "__all__" src/yaml_agno/agentos/authorization_adapter.py`. **Spec**: Req 5.

## Change Verification Command

```bash
python -m pytest tests/unit/agentos/test_authorization_adapter.py tests/unit/factories/test_agentos_factory.py -m unit
grep -n "kwargs.update" src/yaml_agno/agentos/authorization_adapter.py          # expect: zero
grep -nE "basic_auth\]" src/yaml_agno/agentos/authorization_adapter.py src/yaml_agno/factories/agentos_factory.py  # expect: zero
grep -n "cfg is not None" tests/unit/agentos/test_authorization_adapter.py tests/unit/factories/test_agentos_factory.py  # expect: zero
```

## Traceability

| Requirement | Task(s) | Test (pytest -k) |
|---|---|---|
| Req 1 — Whitelist mapping | 3.1, 3.2 | `test_unknown_key_rejected` / `test_valid_config_maps_every_field` / `test_disabled_guard_wins` / `test_whitelist_error_wins_over_secret` |
| Req 2 — basic_auth rejection | 2.2, 3.2 | `test_basic_auth_rejected` / `test_empty_basic_auth_rejected` / `test_disabled_guard_wins_over_basic_auth` |
| Req 3 — user_isolation invariant | 2.5, 3.2 | `test_user_isolation_override_rejected` / `test_user_isolation_invariant_applied` |
| Req 4 — Secret resolution restricted | 2.1, 3.2 | `test_secret_resolved_on_whitelisted_key` / `test_unresolvable_secret_raises` / `test_resolver_none_raises` |
| Req 5 — Legacy path parity | 4.1, 5.1 | `test_legacy_rejects_unknown_key` / `test_legacy_rejects_basic_auth` / `test_legacy_unresolved_secret_raises` / `test_helper_stays_private` |
| Req 6 — Contract tests assert content | 2.3, 6.5 | `test_nonsecret_values_passthrough` (content asserts) |
| Req 7 — Schema UNSUPPORTED docs | 1.1 | `test_basic_auth_still_parses` / no DeprecationWarning |

## Dependency Graph

```
Phase 0: 0.1 → 0.2
Phase 1: 1.1, 1.2 (sequential, one commit)
Phase 2: 2.1→2.6 (RED, all in one file, must be committed together)
Phase 3: 3.1 → 3.2 → 3.3 (GREEN, after Phase 2)
Phase 4: 4.1 (RED, independent of Phase 2-3)
Phase 5: 5.1 → 5.2 (GREEN, after 4.1)
Phase 6: 6.1 → 6.2 → 6.3 → 6.4 → 6.5 → 6.6 (sequential verification)
```
