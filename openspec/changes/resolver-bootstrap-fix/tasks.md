# Tasks: resolver-bootstrap-fix

> 4 fixes, strict TDD (RED → GREEN → REFACTOR). ~120 LOC source + ~150 LOC
> tests across 4 files. Single PR, low risk. All fixes are additive with
> backward-compat invariants.

## Forecast

- **LOC**: ~270 (4 source + 4 test edits)
- **Risk**: Low (all fixes behind optional params / guarded branches)
- **PRs**: 1
- **Spec coverage**: 6 requirements, 11 scenarios
- **Decision needed before apply**: No
- **Chained PRs recommended**: No
- **400-line budget risk**: Low

## Phase 0 — Baseline

- [ ] 0.1 Confirm clean baseline: `python -m pytest -m "unit and not integration"
  -q` → 400 passed. `git status` clean except `.codegraph/`.
  **Spec**: Req 5 (no regression invariant).

## Phase 1 — Fix 1: default allowlist seed (agno_resolver.py)

### RED

- [ ] 1.1 Add `test_build_agno_resolver_seeds_defaults_when_empty` to
  `tests/unit/di/test_agno_resolver.py`: construct `InMemoryConfigAdapter()`
  (no `dependency.allowlist_paths`), call `build_agno_resolver(config=cfg)`,
  assert `resolver.resolve_model("openai:gpt-4o")` returns a real Model
  instance. Run → must FAIL with `ValidationError`.
  **Spec**: Req 1 Scenario 1.1.
- [ ] 1.2 Add `test_build_agno_resolver_strict_preserves_crash`: same setup,
  call with `strict_allowlist=True`, assert `ValidationError` raised.
  **Spec**: Req 1 Scenario 1.2.
- [ ] 1.3 Add `test_build_agno_resolver_honors_explicit_allowlist`: seed
  `["agno.models."]` only, call without `strict_allowlist`, assert the
  caller's list is preserved (resolver still resolves `openai:gpt-4o`).
  **Spec**: Req 1 Scenario 1.3.

### GREEN

- [ ] 1.4 Add `AGNO_ALLOWLIST_PREFIXES` to the existing import block in
  `agno_resolver.py`. Add `strict_allowlist: bool = False` keyword to
  `build_agno_resolver()`. Replace the guard: when empty and not strict,
  call `resolved_config.set_value("dependency.allowlist_paths",
  list(AGNO_ALLOWLIST_PREFIXES))`. Run tests 1.1-1.3 → all GREEN.
  **Spec**: Req 1. **Commit**: `fix(di): seed default allowlist in
  build_agno_resolver when empty`.

## Phase 2 — Fix 4: SecretResolver env fallback (secret_resolver.py)

> Done before Fix 3 because Fix 3's tests need a resolver that can return a
> real value from env, and Fix 2's integration check depends on Fix 3.

### RED

- [ ] 2.1 Add `test_config_secret_resolver_falls_back_to_environ` to
  `tests/unit/di/test_secret_resolver.py`: empty config +
  `monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")`, assert resolver
  returns `"sk-env"`. Run → must FAIL (returns None).
  **Spec**: Req 4 Scenario 4.1.
- [ ] 2.2 Add `test_config_secret_resolver_config_wins_over_environ`: config
  has `secrets.openai_api_key="sk-cfg"`, env has `OPENAI_API_KEY="sk-env"`,
  assert returns `"sk-cfg"`. Run → must FAIL or pass depending on order;
  document the result.
  **Spec**: Req 4 Scenario 4.2.
- [ ] 2.3 Add `test_config_secret_resolver_both_missing_returns_none`:
  `monkeypatch.delenv(..., raising=False)`, empty config, assert None.
  **Spec**: Req 4 Scenario 4.3.

### GREEN

- [ ] 2.4 Add `import os` to `secret_resolver.py`. Rewrite
  `ConfigSecretResolver.__call__`: try config, on miss set value=None, if
  value is None return `os.environ.get(env_name)`. Run tests 2.1-2.3 → all
  GREEN. **Spec**: Req 4. **Commit**: `feat(di): add os.environ fallback to
  SecretResolver`.

## Phase 3 — Fix 3: fail-fast on missing api_key (provider_factory.py)

### RED

- [ ] 3.1 Add `test_provider_factory_raises_on_missing_api_key_cloud` to
  `tests/unit/di/test_provider_factory.py`: build factory with
  `secret_resolver=lambda env: None`, build spec for `openrouter` (which
  declares `api_key_env="OPENROUTER_API_KEY"`), assert `ModelConstructionError`
  raised and `str(exc)` contains `"OPENROUTER_API_KEY"`. Run → must FAIL
  (currently constructs silently with api_key=None).
  **Spec**: Req 3 Scenario 3.1.
- [ ] 3.2 Add `test_provider_factory_local_provider_no_raise_on_missing_key`:
  build spec for `ollama` (api_key_env=None), secret_resolver returns None,
  assert construction succeeds. Run → must PASS already (regression guard).
  **Spec**: Req 3 Scenario 3.2.

### GREEN

- [ ] 3.3 Extend `ModelConstructionError.__init__` with `env_name:
  str | None = None` keyword and the two-branch message (see design). In
  `ProviderFactory.build`, after `api_key = self._secret_resolver(...)`,
  add `if api_key is None: raise ModelConstructionError(spec.provider,
  spec.id, env_name=entry.api_key_env)`. Run tests 3.1-3.2 → GREEN.
  **Spec**: Req 3. **Commit**: `fix(di): fail-fast on missing api_key in
  ProviderFactory`.

## Phase 4 — Fix 2: route model through ProviderFactory (agent_factory.py)

### RED

- [ ] 4.1 Add `test_build_with_provider_factory_uses_model_instance` to
  `tests/unit/factories/test_agent_factory.py`: construct a real
  `ProviderFactory` over a seeded `AgnoResolver` (use the existing
  integration-style helper from `test_agno_resolver.py`), set
  `monkeypatch.setenv("OPENAI_API_KEY", "sk-test")`, build
  `AgentConfig(name="x", model="openai:gpt-4o")`, call
  `AgentFactory.build(cfg, resolver=r, provider_factory=pf)`, assert
  `agent.model` is the instance returned by `pf.build(spec)` (identity).
  Run → must FAIL with TypeError (provider_factory unknown kwarg).
  **Spec**: Req 2 Scenario 2.1.
- [ ] 4.2 Add `test_build_without_provider_factory_keeps_string_passthru`:
  call `AgentFactory.build(cfg)` (no provider_factory), assert
  `agent.model.id == "gpt-4o"` and that it's whatever Agno resolves
  (regression guard). Run → must PASS already.
  **Spec**: Req 2 Scenario 2.2.

### GREEN

- [ ] 4.3 Add imports (`ProviderFactory`, `ModelExpandedSpec`,
  `parse_model_spec`) to `agent_factory.py`. Add `provider_factory:
  ProviderFactory | None = None` to `build()`. When provided, parse
  `cfg.model`, promote `ModelStringSpec` to `ModelExpandedSpec` if needed,
  call `provider_factory.build(spec)`, forward the instance to `Agent`. Run
  tests 4.1-4.2 → GREEN. **Spec**: Req 2. **Commit**: `feat(factories):
  route model through ProviderFactory in AgentFactory.build`.

## Phase 5 — Verify

- [ ] 5.1 `python -m pytest -m "unit and not integration" -q` → all green
  (400 baseline + new tests).
- [ ] 5.2 `ruff check .` → clean.
- [ ] 5.3 `mypy src/yaml_agno` → no new errors vs. baseline.
- [ ] 5.4 Integration smoke (manual or new `@pytest.mark.integration` test):
  `build_agno_resolver()` with zero args succeeds; `AgentFactory.build(cfg,
  resolver=r, provider_factory=pf)` with `OPENROUTER_API_KEY` set returns an
  Agent whose `.model` is an `OpenRouter` instance with `api_key` populated.
  **Spec**: Req 5 (back-compat) + happy-path integration.

## Rollback

Each fix is a single commit; `git revert <sha>` per fix restores prior
behavior independently. No migrations, no schema changes.
