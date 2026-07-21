# Spec: resolver-bootstrap-fix

> 6 requirements covering the 4 fixes. RFC 2119 keywords (MUST, SHALL, SHOULD,
> MAY). Each requirement maps to one or more scenarios with Given/When/Then.

## Requirements

### Requirement 1 — Default allowlist seed

The `build_agno_resolver()` factory MUST seed `dependency.allowlist_paths`
from `AGNO_ALLOWLIST_PREFIXES` (registries.py) when the config section is
empty, instead of raising `ValidationError`. This MUST happen before the
`ImportlibDependencyAdapter` is constructed so strict-mode resolution works
out of the box.

The caller MAY still opt into the old behavior by passing
`strict_allowlist=True` (new keyword arg, default `False`); in that case the
factory MUST raise `ValidationError` when the section is empty, exactly as it
does today.

**Scenario 1.1 — empty allowlist seeds defaults**
- Given a `ConfigManager` whose `dependency.allowlist_paths` is empty or
  missing
- When `build_agno_resolver(config=cfg)` is called
- Then the returned `AgnoResolver` MUST resolve a canonical Agno class
  (e.g. `resolver.resolve_model("openai:gpt-4o")`) without raising

**Scenario 1.2 — strict mode preserves the crash**
- Given an empty allowlist and `strict_allowlist=True`
- When `build_agno_resolver(config=cfg, strict_allowlist=True)` is called
- Then the call MUST raise `ValidationError` (backward-compat invariant)

**Scenario 1.3 — explicit allowlist is honored unchanged**
- Given a config that already declares `dependency.allowlist_paths`
- When `build_agno_resolver(config=cfg)` is called
- Then the factory MUST NOT overwrite the caller's allowlist

### Requirement 2 — ProviderFactory routing in AgentFactory.build

`AgentFactory.build()` MUST accept an optional keyword argument
`provider_factory: ProviderFactory | None = None`. When provided, the factory
MUST parse `cfg.model` via `parse_model_spec()`, call
`provider_factory.build(spec)` to obtain an Agno `Model` instance, and forward
that instance (not the raw string) to `agno.Agent(model=instance)`.

When `provider_factory is None`, the factory MUST continue to pass
`model=cfg.model` as a raw string (current behavior; zero broken tests).

**Scenario 2.1 — provider_factory produces a Model instance**
- Given an `AgentConfig` with `model="openrouter:auto@meta-llama/..."`
- And a `ProviderFactory` wired to a seeded `AgnoResolver`
- When `AgentFactory.build(cfg, resolver=r, provider_factory=pf)` is called
- Then the returned `Agent.model` MUST be the instance returned by
  `provider_factory.build(spec)` (identity equality)

**Scenario 2.2 — no provider_factory keeps string passthru**
- Given an `AgentConfig` with `model="openai:gpt-4o"`
- When `AgentFactory.build(cfg)` is called (no `provider_factory`)
- Then `Agent.model` MUST be whatever Agno resolves the string to
  (current behavior; existing tests unchanged)

### Requirement 3 — Fail-fast on missing api_key

`ProviderFactory.build()` MUST raise `ModelConstructionError` when, after
consulting the `SecretResolver`, `api_key is None` AND the provider's
`ProviderRegistryEntry.api_key_env is not None`. The error message MUST
include the env-var name so the user knows which variable to set.

Local providers (whose `api_key_env is None`) MUST continue to construct
without raising (they never need an api_key).

**Scenario 3.1 — cloud provider missing key raises**
- Given a spec with `provider="openrouter"` (which declares
  `api_key_env="OPENROUTER_API_KEY"`)
- And a `SecretResolver` that returns `None` for that env name
- When `provider_factory.build(spec)` is called
- Then it MUST raise `ModelConstructionError` whose `str()` contains
  `"OPENROUTER_API_KEY"`

**Scenario 3.2 — local provider skips the check**
- Given a spec with `provider="ollama"` (whose `api_key_env is None`)
- And a `SecretResolver` that returns `None`
- When `provider_factory.build(spec)` is called
- Then it MUST return a constructed instance without raising

### Requirement 4 — SecretResolver os.environ fallback

`ConfigSecretResolver.__call__` MUST, after `ConfigManager.get_string` returns
None or raises `ValidationError`, fall back to `os.environ.get(env_name)`
before returning None. ConfigManager remains authoritative; the env is only
consulted on a config miss.

The fallback MUST be the last step (config wins). It MUST NOT be skipped when
the env var is unset (`os.environ.get` returning None is a valid final
result).

**Scenario 4.1 — config miss + env present returns env value**
- Given a `ConfigManager` without `secrets.openrouter_api_key`
- And `OPENROUTER_API_KEY="sk-env"` in `os.environ`
- When the resolver is called with `"OPENROUTER_API_KEY"`
- Then it MUST return `"sk-env"`

**Scenario 4.2 — config wins over env**
- Given a `ConfigManager` with `secrets.openai_api_key="sk-cfg"`
- And `OPENAI_API_KEY="sk-env"` in `os.environ`
- When the resolver is called with `"OPENAI_API_KEY"`
- Then it MUST return `"sk-cfg"` (config authoritative)

**Scenario 4.3 — both missing returns None**
- Given a config miss AND `os.environ` without the var
- When the resolver is called
- Then it MUST return `None`

### Requirement 5 — Backward-compat invariants

All four fixes MUST preserve the existing public surface. Specifically:

- `AgentFactory.build(cfg)` (no `resolver`, no `provider_factory`) MUST behave
  exactly as today — string model passthru, `tools=[]`, `skills=None`.
- `build_agno_resolver()` (no args) MUST NOT raise (was raising; now seeds).
- `ProviderFactory.build(spec)` for local providers MUST still work with a
  resolver that always returns None.
- `ConfigSecretResolver(cfg)` for a config that has the secret MUST still
  return it without touching `os.environ`.

**Scenario 5.1 — existing 400-test suite stays green**
- Given the current test suite
- When `python -m pytest -m "unit and not integration" -q` runs
- Then all previously-passing tests MUST still pass (no regression)

### Requirement 6 — Lint and type cleanliness

All new and modified source MUST pass `ruff check .` and `mypy src/yaml_agno`
with zero new warnings or errors.

**Scenario 6.1 — clean lint**
- Given the modified source
- When `ruff check .` is run
- Then it MUST exit 0

**Scenario 6.2 — clean types**
- Given the modified source
- When `mypy src/yaml_agno` is run
- Then it MUST report no new errors vs. baseline
