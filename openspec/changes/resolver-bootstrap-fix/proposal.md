---
change: resolver-bootstrap-fix
spec: SPEC_14, SPEC_01
status: proposed
artifact_store: hybrid
depends_on: []
---

# Proposal: resolver-bootstrap-fix

> Fix the 3 gaps that prevent `build_agno_resolver()` + `AgentFactory.build()`
> from producing a fully-configured Agent with OpenRouter + `api_key` from env.

## Intent / Why

Three independently-verifiable gaps block the OpenRouter bootstrap path:

1. **`build_agno_resolver()` crashes on default config.** When the caller does
   not pre-seed `dependency.allowlist_paths`, the factory raises
   `ValidationError` instead of seeding the canonical Agno prefixes that
   already exist as data in `registries.py::AGNO_ALLOWLIST_PREFIXES`. The data
   exists; the factory just refuses to use it.

2. **`AgentFactory.build()` passes `model` as a raw string.** When a caller
   wants a fully-configured Model with `api_key`, there is no path through
   `AgentFactory.build()` to route the model spec through `ProviderFactory`.
   The factory hardcodes `model=cfg.model` (string) and never builds a Model
   instance with an injected key.

3. **`ProviderFactory` silently constructs a Model with `api_key=None`.** When
   the secret is missing the factory proceeds and Agno fails much later (often
   only on `agent.run()`) with an opaque 401. The provider entry already
   declares `api_key_env`; the factory should fail fast with the env name.

4. **`ConfigSecretResolver` never reads `os.environ`.** Typical users set
   `OPENROUTER_API_KEY` in their shell, not in a YAML `secrets:` block. The
   resolver is the infrastructure layer (per SPEC_00 §9.3 the os.environ ban
   applies to app code, not the abstraction that owns env access); it should
   fall back to `os.environ.get(env_name)` when ConfigManager returns None.

**Success**: `build_agno_resolver()` succeeds with zero args;
`AgentFactory.build(cfg, resolver=r, provider_factory=pf)` returns an
`agno.Agent` whose `.model` is a real `OpenRouter` instance with a populated
`api_key`; missing api_key raises `ModelConstructionError` naming the env var;
all 400 existing tests stay green.

## Scope

### In Scope

- `src/yaml_agno/di/agno_resolver.py` — seed defaults when allowlist is empty
  (Fix 1).
- `src/yaml_agno/factories/agent_factory.py` — optional `provider_factory`
  param on `AgentFactory.build()` (Fix 2).
- `src/yaml_agno/di/provider_factory.py` — fail-fast on missing api_key
  (Fix 3).
- `src/yaml_agno/di/secret_resolver.py` — `os.environ` fallback in
  `ConfigSecretResolver` (Fix 4).

### Out of Scope

- Wiring `AgentConfig.model` to the `ModelSpec` union (deferred to a future
  coordinated SPEC_02 evolution slice).
- Async `SecretManager` integration (SPEC_23, not yet delivered).
- Any change to `parse_model_spec`, `ProviderResolver`, or the registries.

## Approach

Each fix is a strict-additive change with a backward-compat invariant:

| Fix | File | Change | Backward-compat |
|-----|------|--------|-----------------|
| 1 | `agno_resolver.py` | Seed `AGNO_ALLOWLIST_PREFIXES` when empty | `strict_allowlist=True` preserves the old crash |
| 2 | `agent_factory.py` | New optional `provider_factory` param | `provider_factory=None` keeps string passthru |
| 3 | `provider_factory.py` | Raise on `api_key is None` when env declared | Local providers (env=None) unaffected |
| 4 | `secret_resolver.py` | `os.environ.get` fallback after Config | Config still wins; env only consulted on miss |

Strict TDD: each fix starts with a RED test that demonstrates the gap, then a
GREEN implementation that matches existing patterns.

## Rollback Plan

Each fix is a single-file change behind an additive branch. Rollback is `git
revert <commit>` per fix; the 4 commits are independent and can be reverted
individually. No data migrations, no schema changes, no breaking imports.

## Risks

- **Low**: all 4 fixes are behind optional params or guarded branches. Existing
  call sites are untouched.
- **Medium (Fix 4)**: the `os.environ` fallback loosens SPEC_00 §9.3. Mitigated
  by documenting that `SecretResolver` IS the infrastructure layer that owns
  env access, and that the production wiring (SPEC_23) replaces this resolver
  with the async SecretManager adapter.

## Decision Needed Before Apply

No. Estimated work is ~120 LOC across 4 source files + ~150 LOC across 4 test
files. `400-line budget risk: Low`. `Chained PRs recommended: No`. Single PR.
