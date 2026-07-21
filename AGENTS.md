# AGENTS.md — yaml-agno

> Concise guide for coding agents working on this repo.

## What is yaml-agno

A **pip-installable Python library** that abstracts the Agno Framework via YAML configuration. Pattern: `YAML → Pydantic *Config → Factory → Agno Objects`. It builds **ON TOP** of Agno — never reimplements Agno's runtime, session, memory, A2A, or retry internals.

## Stack

- **Python 3.12+** (strict)
- **Agno 2.6.22** (pinned, the runtime we build on top of)
- **core-cenf-py** (`core_infrastructure` — DatabaseManager, ConfigManager, SecretManager, ErrorHandlingManager, ObservabilityManager, DependencyManager)
- **Pydantic V2** (schemas, validation, discriminated unions)
- **SQLAlchemy 2.0** (`yamlagno_*` ORM models, DeclarativeBase)

## Quick commands

```bash
pip install -e ".[dev]"              # Install editable with dev deps
python -m pytest -m unit -q          # Run unit tests (410+)
ruff check .                         # Lint
mypy src/yaml_agno                   # Type check
python scripts/spec_gate.py all      # SPEC gate (34 SPECs, 0 violations)
```

## Inviolable rules

1. **Build ON TOP**: never reimplement Agno runtime/session/memory/A2A/retry/CEL. If Agno provides it, use it.
2. **user_id ALWAYS composite** `{tenant_id}:{principal_id}` — never None, never bare, never in YAML. `resolve_user_id()` (SPEC_04) is the single resolver.
3. **asyncio.TaskGroup** (never `asyncio.gather`).
4. **NO `os.environ` in app code** — use `ConfigManager`/`SecretManager` from core-cenf. (SecretResolver IS the abstraction layer that may read env.)
5. **Enums imported from Agno** (TeamMode, StepType) — never redefined.
6. **Code in English** (identifiers, docstrings, comments). Narrative in Spanish.
7. **Strict TDD**: every behavioral task follows RED → GREEN → REFACTOR.
8. **SDD workflow**: explore → propose → spec → design → tasks → apply → verify → archive.
9. **Commits granular** (conventional, no AI attribution, no squash).

## Canonical src/ tree

```
src/yaml_agno/
├── factories/         # SPEC_01: AgentFactory, TeamFactory, WorkflowFactory
├── models/            # SPEC_02 (SSOT): *Config Pydantic schemas + model_spec
├── di/                # AgnoResolver, ProviderFactory, SecretResolver, registries
├── tools/             # SPEC_11: ToolFactory, BUILTIN_REGISTRY (134), MCPResolver
├── skills/            # SPEC_30: SkillsFactory, SkillsConfig
├── memory/            # SPEC_04: resolve_user_id, UserIdentityResolutionError
├── resilience/        # SPEC_09: CircuitBreaker (CLOSED/OPEN/HALF_OPEN)
├── db/                # SPEC_03: ORM models (yamlagno_* tables)
└── models/config/     # AgentConfig, TeamConfig, WorkflowConfig, MemoryConfig
```

Full tree: `DECISIONES.md §4bis`.

## Key API surface

```python
from yaml_agno.factories import AgentFactory, TeamFactory, WorkflowFactory
from yaml_agno.tools import ToolFactory
from yaml_agno.skills import SkillsFactory
from yaml_agno.di import build_agno_resolver, ProviderFactory
from yaml_agno.di.secret_resolver import ConfigSecretResolver
from yaml_agno.memory import resolve_user_id
from yaml_agno.resilience import CircuitBreaker

# Build a fully-configured Agent (model + api_key from env):
resolver = build_agno_resolver()              # seeds defaults, no .env needed
secret = ConfigSecretResolver()               # reads OPENROUTER_API_KEY etc
pf = ProviderFactory(resolver, secret)
agent = AgentFactory.build(cfg, resolver=resolver, provider_factory=pf)

# Model format: "openrouter:openai/gpt-4o" or "openai:gpt-4o"
# Tools: [{"kind": "builtin", "name": "calculator"}, {"kind": "function", "path": "my.fn"}]
# Skills: {"path": "/skills/dir", "validate": true}
```

## Verification gate (MANDATORY before PASS)

Load `.chats/decisions.yaml` → `verification_queries` (VQ001-VQ009). Execute each against code. Any FAIL = CRITICAL. See `DECISIONES.md §7` for the full protocol.

## Dependencies

- `agno==2.6.22` (pip)
- `core-cenf-py` (git+https, private — needs `GIT_AUTH_TOKEN` for CI)
- `pydantic>=2.0`, `pyyaml>=6.0`, `sqlalchemy[asyncio]>=2.0`

## Where things are

- **DECISIONES.md** — 12 inviolable decisions + src/ tree + gate protocol
- **VISION.md** — project vision/mission/philosophy
- **specs/INDEX.md** — 34 SPECs in 10 groups, Read_Order
- **.chats/decisions.yaml** — SSOT snapshot with VQ001-VQ009 verification queries
- **openspec/specs/** — published capability specs
- **openspec/changes/archive/** — completed change records
