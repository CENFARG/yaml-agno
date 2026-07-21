# Design: resolver-bootstrap-fix

> Literal code changes for the 4 fixes. The apply phase MUST implement these
> verbatim (modulo naming tweaks that do not change behavior).

## Architecture Decisions

### AD1 — Seed defaults in the factory, not in the registries

The defaults live in `registries.py::AGNO_ALLOWLIST_PREFIXES` (already a
`Final[list[str]]`). The factory (`build_agno_resolver`) imports the constant
and seeds the config in place when the section is empty. This keeps the
registries as pure data and puts the "if empty, seed" policy in the only place
that has a config to mutate.

### AD2 — `provider_factory` as a new optional keyword on `build()`

Adding the param to `AgentFactory.build()` (not to the `AgentConfig` schema,
not to the constructor) keeps the factory stateless and the schema untouched.
This matches the existing `resolver` optional param pattern (slice C / SPEC_11).

### AD3 — Fail-fast at construction time, not at run time

Agno Model constructors accept `api_key=None` silently and only fail on the
first network call. The factory is the last synchronous gate before the model
disappears into `agno.Agent`; raising here gives the user the env-var name
instead of an opaque 401 an hour later.

### AD4 — SecretResolver owns env access

SPEC_00 §9.3 bans `os.environ` in **app code**. `ConfigSecretResolver` is
**infrastructure** (the port adapter whose entire job is to abstract secret
sources). Adding the env fallback there centralizes env access in ONE place;
the production wiring (SPEC_23) will swap this resolver for the async
SecretManager adapter and the env fallback goes away with it.

## Data Flow

```
build_agno_resolver()                     AgentFactory.build(cfg, r, pf)
  │                                        │
  ├─ read dependency.allowlist_paths       ├─ if provider_factory:
  │                                        │     spec = parse_model_spec(cfg.model)
  ├─ if empty AND not strict_allowlist:    │     model = provider_factory.build(spec)
  │     seed AGNO_ALLOWLIST_PREFIXES       │     Agent(model=model, ...)
  │                                        │ else:
  ├─ build ImportlibDependencyAdapter      │     Agent(model=cfg.model, ...)
  │                                        │
  └─ AgnoResolver(adapter)                 └─ ...

provider_factory.build(spec):
  ├─ entry = PROVIDER_REGISTRY[spec.provider]
  ├─ cls = resolver.resolve_class(...)
  ├─ kwargs = _compose_kwargs(spec, cls)
  ├─ if entry.api_key_env is not None:
  │     api_key = secret_resolver(entry.api_key_env)
  │     if api_key is None:
  │        raise ModelConstructionError(env_name=entry.api_key_env)
  │     kwargs["api_key"] = api_key
  └─ return cls(id=spec.id, **kwargs)

ConfigSecretResolver.__call__(env_name):
  ├─ try config.get_string("secrets.<env_lower>")
  ├─ on hit: return value
  ├─ on miss/ValidationError:
  │     env_value = os.environ.get(env_name)
  │     return env_value  # may be None
  └─ (config always wins; env is last-resort fallback)
```

## Literal Code Changes

### Fix 1 — `src/yaml_agno/di/agno_resolver.py`

Add `strict_allowlist` keyword to `build_agno_resolver()` and seed when empty.

Replace the guard block (currently lines 245-253):

```python
# Imports: add AGNO_ALLOWLIST_PREFIXES
from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    PROVIDER_ALIASES,
    STORAGE_REGISTRY,
    WORKFLOW_REGISTRY,
)
```

Signature change:

```python
def build_agno_resolver(
    config: ConfigManager | None = None,
    *,
    logger: LoggerManager | None = None,
    errors: ErrorHandlingManager | None = None,
    observability: ObservabilityManager | None = None,
    adapter: DependencyManager | None = None,
    strict_allowlist: bool = False,
) -> AgnoResolver:
```

Replace the guard block:

```python
    # Guard de siembra: si la sección no tiene allowlist_paths, sembrar los
    # prefijos canónicos declarativos desde registries.py (FIX 1). Solo crashea
    # si el caller opta explícitamente por strict_allowlist=True (back-compat).
    dep_section = resolved_config.get_section("dependency")
    if not dep_section.get("allowlist_paths"):
        if strict_allowlist:
            raise ValidationError(
                "dependency.allowlist_paths is empty — seed AGNO_ALLOWLIST_PREFIXES "
                "in the config before calling build_agno_resolver()",
                details={"section": "dependency"},
            )
        # Seed in place: mutate the config section so ImportlibDependencyAdapter
        # reads the canonical Agno prefixes. set_value is the ConfigManager port
        # method both PydanticConfigAdapter and InMemoryConfigAdapter expose.
        resolved_config.set_value(
            "dependency.allowlist_paths",
            list(AGNO_ALLOWLIST_PREFIXES),
        )
```

### Fix 2 — `src/yaml_agno/factories/agent_factory.py`

Add `provider_factory` param and route the model when provided.

Add imports:

```python
from yaml_agno.di.provider_factory import ProviderFactory
from yaml_agno.models.model_spec import ModelExpandedSpec, parse_model_spec
```

Replace the `build()` signature and body:

```python
    @staticmethod
    def build(
        cfg: AgentConfig,
        resolver: AgnoResolver | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> Agent:
        # ... (docstring updated to describe provider_factory)

        tools: list[Any] = []
        if cfg.tools and resolver is not None:
            factory = ToolFactory(resolver)
            tools = factory.build(cfg.tools)
        skills = SkillsFactory.build(cfg.skills) if cfg.skills else None

        # FIX 2: when a provider_factory is wired, parse cfg.model and build a
        # real Agno Model instance (with api_key injected) instead of passing
        # the raw string. Backward-compat: provider_factory=None keeps the
        # slice-#1 string passthru.
        model: Any = cfg.model
        if provider_factory is not None:
            spec = parse_model_spec(cfg.model)
            # ModelExpandedSpec carries the generation params; ModelStringSpec
            # only carries provider+id. ProviderFactory.build handles both via
            # attribute access — if the spec is a ModelStringSpec, it lacks the
            # optional generation params and _compose_kwargs filters cleanly.
            if not isinstance(spec, ModelExpandedSpec):
                spec = ModelExpandedSpec(provider=spec.provider, id=spec.id)
            model = provider_factory.build(spec)

        return Agent(
            name=cfg.name,
            instructions=cfg.instructions,
            description=cfg.description,
            model=model,
            tools=tools or None,
            tool_call_limit=cfg.tool_call_limit,
            skills=skills,
        )
```

### Fix 3 — `src/yaml_agno/di/provider_factory.py`

Add `env_name` to `ModelConstructionError` and raise on missing api_key.

Extend the exception:

```python
class ModelConstructionError(Exception):
    """Raised when a provider class cannot be instantiated from a spec.

    Wraps the underlying TypeError/ValueError from the Agno constructor OR
    surfaces a missing-api_key failure (FIX 3) with the env-var name.
    """

    def __init__(
        self,
        provider: str,
        model_id: str,
        cause: Exception | None = None,
        *,
        env_name: str | None = None,
    ) -> None:
        self.provider = provider
        self.model_id = model_id
        self.cause = cause
        self.env_name = env_name
        if env_name is not None:
            message = (
                f"Missing api_key for provider={provider!r} id={model_id!r}: "
                f"set the {env_name!r} environment variable (or add it to the "
                f"secrets config namespace)."
            )
        else:
            assert cause is not None  # narrowing for mypy
            message = (
                f"Failed to construct Agno Model for provider={provider!r} "
                f"id={model_id!r}: {type(cause).__name__}: {cause}"
            )
        super().__init__(message)
```

In `build()`, replace the api_key block:

```python
        if entry.api_key_env is not None:
            api_key = self._secret_resolver(entry.api_key_env)
            if api_key is None:
                # FIX 3: fail fast with the env-var name. The provider entry
                # declares it needs a key; constructing silently with None
                # pushes the failure to agent.run() (opaque 401). Surface it
                # here at the last sync gate before the model is wrapped.
                raise ModelConstructionError(
                    spec.provider,
                    spec.id,
                    env_name=entry.api_key_env,
                )
            kwargs["api_key"] = api_key
```

### Fix 4 — `src/yaml_agno/di/secret_resolver.py`

Add `os.environ` fallback after the config miss.

```python
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.ports import ConfigManager
```

Replace `__call__`:

```python
    def __call__(self, env_name: str) -> str | None:
        """Resolve ``env_name`` to its secret, config first, env fallback.

        Order:
          1. ``config.get_string("secrets.<env_lower>")`` (authoritative).
          2. On miss / ValidationError: ``os.environ.get(env_name)`` (FIX 4).
          3. If both miss: None.

        FIX 4 rationale: SPEC_00 §9.3 bans os.environ in app code. This
        resolver IS the infrastructure layer that abstracts secret sources
        (the production wiring in SPEC_23 replaces this resolver with the
        async SecretManager adapter). Centralizing the env fallback here keeps
        os.environ access in ONE place.
        """
        key = f"secrets.{env_name.lower()}"
        try:
            value = self._config.get_string(key, default_value=None)
        except ValidationError:
            value = None
        if value is not None:
            return str(value)
        # FIX 4: env fallback (infrastructure-layer escape hatch).
        return os.environ.get(env_name)
```

## Sequence Diagram (Fix 1+2+3+4 happy path)

```
caller                build_agno_resolver()        AgentFactory.build()
  │                          │                            │
  │── build_agno_resolver() ─>                            │
  │                          │── seed allowlist (FIX 1)   │
  │                          │── build ImportlibAdapter   │
  │<── AgnoResolver ──────────│                            │
  │                                                       │
  │── AgentFactory.build(cfg, r, pf) ─────────────────────>│
  │                                                       │── parse_model_spec(cfg.model)
  │                                                       │── provider_factory.build(spec)
  │                                                       │       │── entry.api_key_env = OPENROUTER_API_KEY
  │                                                       │       │── secret_resolver(env)
  │                                                       │       │       │── config miss
  │                                                       │       │       │── os.environ.get (FIX 4)
  │                                                       │       │       │<── "sk-..."
  │                                                       │       │<── kwargs["api_key"] = "sk-..."
  │                                                       │       │── cls(id=spec.id, api_key="sk-...")
  │                                                       │<── Model instance
  │                                                       │── Agent(model=instance, ...)
  │<── Agent ──────────────────────────────────────────────│
```

## Threat Matrix

| Case | Handler |
|------|---------|
| Empty allowlist + strict=False | Seed defaults (FIX 1) |
| Empty allowlist + strict=True | Raise ValidationError (back-compat) |
| provider_factory=None | String passthru (FIX 2 back-compat) |
| Cloud provider missing api_key | Raise ModelConstructionError (FIX 3) |
| Local provider (api_key_env=None) | Construct without key (FIX 3) |
| Config has secret | Return it (FIX 4) |
| Config miss + env present | Return env value (FIX 4) |
| Config miss + env absent | Return None (FIX 4) |
