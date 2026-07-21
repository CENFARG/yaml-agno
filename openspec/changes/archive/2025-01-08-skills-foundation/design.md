# Design: skills-foundation (SPEC_30 Slice A)

## Technical Approach

Thin adapter that mirrors the shipped `ToolFactory` Option B pattern: the
`AgentConfig.skills` opaque `dict[str, Any] | None` slot is validated at
factory-build time (NOT at config-parse time) and mapped to a native
`agno.skills.Skills` instance. yaml-agno owns NO skills logic — no SKILL.md
parsing, no tool generation, no system-prompt snippet construction. All of
that lives in Agno 2.6.22 (`agent_skills.py`, `loaders/local.py`,
`validator.py`), which we verified against the installed source.

The adapter exposes two new modules under `src/yaml_agno/skills/`:

- `schema.py` — `SkillsConfig` Pydantic V2 BaseModel (2 fields: `path`,
  `validate`).
- `factory.py` — `SkillsFactory.build(config)` constructs
  `LocalSkills(path, validate)` and wraps it in `Skills(loaders=[...])`.

Wiring into `AgentFactory` is DEFERRED to slice B (A4). This slice is
independently testable with temp-dir `SKILL.md` fixtures.

## Architecture Decisions

### Decision A1: Thin adapter — delegate everything to Agno

**Choice**: yaml-agno only translates config shape (`SkillsConfig` → native
`Skills`). No re-implementation of validation, loading, or prompt injection.

**Alternatives considered**:
- Re-implement validation in yaml-agno (rejected: duplicates Agno logic,
  drifts on version upgrades; SPEC_30 §6.1 explicitly delegates to Agno).
- Wrap Agno with extra behavior (rejected: no requirements justify it in
  slice A; YAGNI).

**Rationale**: Verified exploration (obs-2137) confirms Agno 2.6.22 owns
`validate_skill_directory`, `LocalSkills.load()`, `Skills.reload()`, and the
system-prompt injection (`_messages.py:282-285`). Mirrors `ToolFactory`,
which also delegates execution to Agno.

### Decision A2: Option B opaque — validate at factory boundary

**Choice**: `AgentConfig.skills` stays `dict[str, Any] | None`. Raw dict is
validated into `SkillsConfig` inside `SkillsFactory.build`, not in
`AgentConfig` model validators.

**Alternatives considered**:
- Option A (validate at config-parse via a nested `SkillsConfig` field on
  `AgentConfig`) — rejected: inconsistent with `ToolFactory`, which uses
  Option B (`tool_factory.py:54` module-level `TypeAdapter`).
- Option C (no validation, pass raw dict to Agno) — rejected: Agno's
  `LocalSkills` expects typed kwargs, not an arbitrary dict.

**Rationale**: Consistency with the shipped `tools` layer. The validation
boundary moves from config-parse to factory-build; it does NOT disappear.

### Decision A3: Factory class named `SkillsFactory` (bare-noun convention)

**Choice**: `SkillsFactory` class with a `build()` classmethod.

**Alternatives considered**:
- `SkillsConfigFactory` (SPEC_30 §4.4 names it this) — rejected: codebase
  convention is bare-noun factories (`ToolFactory`, `AgentFactory`,
  `TeamFactory`, `WorkflowFactory`). Explore obs-2137 flagged this
  discrepancy explicitly.
- `build_skills()` free function — rejected: breaks the class-based factory
  pattern every other layer uses.

**Rationale**: Naming alignment across the codebase. A bare-noun factory
matches `ToolFactory` exactly, making the skills layer instantly familiar.

### Decision A4: DEFER AgentFactory wiring to slice B

**Choice**: Slice A ships `schema.py` + `factory.py` + `__init__.py`
re-exports only. `AgentFactory` does NOT receive or forward `skills=` yet.

**Alternatives considered**:
- Wire `AgentFactory` in the same slice — rejected: SPEC_30 split is 2
  slices precisely to keep the foundational schema+factory independently
  testable. Slice B adds the `agent_factory.py` change + contract tests.

**Rationale**: Slice independence. Slice A's tests use temp-dir `SKILL.md`
fixtures and assert against `SkillsFactory.build()` output directly, with
zero dependency on the agent-construction path.

### Decision A5: `SkillsFactory.build` accepts `SkillsConfig | dict | None`

**Choice**: Single entry point with three input shapes:
- `None` → returns `None` (no skills configured).
- `dict` → validated into `SkillsConfig` via `TypeAdapter`.
- `SkillsConfig` → used as-is.

**Alternatives considered**:
- Two methods (`build_from_dict`, `build_from_config`) — rejected: forces
  callers to branch; `ToolFactory.build` accepts both shapes in one method.

**Rationale**: Mirrors `ToolFactory.build` which accepts
`Sequence[dict[str, Any] | ToolEntry]` (tool_factory.py:84).

## Data Flow

```
AgentConfig.skills (dict | None)
        │
        ▼
SkillsFactory.build(config)
        │
        ├─ None ──────────────────────────► None
        │
        ├─ dict ──► TypeAdapter(SkillsConfig).validate_python(dict)
        │                                   │
        └─ SkillsConfig ◄───────────────────┘
                │
                ▼
        LocalSkills(path=cfg.path, validate=cfg.validate)
                │
                ▼
        Skills(loaders=[local_skills])
                │
                ▼
        (slice B: AgentFactory → Agent(skills=...))
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/skills/schema.py` | Create | `SkillsConfig` Pydantic V2 BaseModel (path + validate). |
| `src/yaml_agno/skills/factory.py` | Create | `SkillsFactory.build(config)` → `Skills \| None`. |
| `src/yaml_agno/skills/__init__.py` | Modify | Re-export `SkillsConfig`, `SkillsFactory`. |

**File count: 2 new + 1 modified = 3 files.**

## Interfaces / Contracts

### NEW `src/yaml_agno/skills/schema.py`

```python
"""Skills config schema (SPEC_30 slice A) — Pydantic V2 BaseModel for the
opaque ``AgentConfig.skills`` slot.

De-opacifies ``AgentConfig.skills`` from a raw dict to a validated config
carried into ``SkillsFactory.build``. Mirrors how ``tools/schema.py``
de-opacifies ``AgentConfig.tools``.

NOTE: this schema ships standalone. ``AgentConfig.skills`` stays the opaque
``dict[str, Any] | None``; the validation boundary lives in
``SkillsFactory.build`` (Option B), consistent with ``ToolFactory``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SkillsConfig"]


class SkillsConfig(BaseModel):
    """Local-skills source declaration for one agent.

    Maps to ``agno.skills.LocalSkills(path, validate)``. yaml-agno owns NO
    skill logic — validation, loading, and prompt injection all live in Agno
    2.6.22 (verified obs-2137: ``loaders/local.py:25``, ``validator.py``).

    Attributes:
        path: Filesystem path to a skill folder (contains ``SKILL.md``) or
            a directory of skill folders. Resolved via
            ``Path(path).resolve()`` inside ``LocalSkills``; a missing path
            raises ``FileNotFoundError`` at load time.
        validate: If ``True`` (default), invalid skills raise
            ``SkillValidationError`` at load time. If ``False``, Agno logs
            and skips invalid skills. Forwarded directly to
            ``LocalSkills(validate=...)``.
    """

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        min_length=1,
        description="Path to a skill folder or a directory of skill folders.",
    )
    validate: bool = Field(
        default=True,
        description="If True, invalid skills raise SkillValidationError (Agno default).",
    )
```

### NEW `src/yaml_agno/skills/factory.py`

```python
"""SkillsFactory — maps ``SkillsConfig`` to a native ``agno.skills.Skills``
instance (SPEC_30 slice A).

The factory is the SINGLE wiring point between the opaque
``AgentConfig.skills`` dict (Option B) and ``agno.Agent(skills=...)``. It
accepts either a raw dict (opaque ``AgentConfig.skills``), a pre-parsed
``SkillsConfig``, or ``None``, validates raw dicts via
``TypeAdapter(SkillsConfig)``, constructs ``LocalSkills(path, validate)``,
wraps it in ``Skills(loaders=[...])``, and returns the orchestrator Agent
accepts.

Thin adapter by design (A1): all skill logic — validation, loading, system
prompt injection, tool exposure — lives in Agno 2.6.22 (verified
obs-2137). yaml-agno does NOT reimplement any of it.

Synchronous by design: ``LocalSkills.__init__`` calls ``Path.resolve()`` but
does NOT load skills; ``Skills.__init__`` calls ``_load_skills()`` which
runs ``LocalSkills.load()`` synchronously (verified
``agent_skills.py:29-52``). No ``await`` is needed on the construction path.

@ai-directive: SSOT is specs/SPEC_30_SKILLS_MANAGEMENT.md §4 (factory
contract), §6 (Agno delegation). Slice B adds AgentFactory wiring; this
slice ships schema + factory + re-exports only (A4).
"""

from __future__ import annotations

from typing import Any

from agno.skills import LocalSkills, Skills
from pydantic import TypeAdapter

from yaml_agno.skills.schema import SkillsConfig

__all__ = ["SkillsFactory"]


# Reusable validator: raw dict -> SkillsConfig instance. Built ONCE at
# import (TypeAdapter is the documented Pydantic V2 pattern for validating
# outside a model field). Option B: validation boundary lives here, NOT in
# AgentConfig.
_CONFIG_ADAPTER: TypeAdapter[SkillsConfig] = TypeAdapter(SkillsConfig)


class SkillsFactory:
    """Map ``SkillsConfig`` (or raw dict) to a native ``Skills`` instance.

    Stateless: every ``build()`` call is independent. No instance state is
    held — the class is used for namespace + convention alignment with
    ``ToolFactory`` (A3).

    Scope: schema validation + ``LocalSkills``/``Skills`` construction
    (slice A). AgentFactory wiring is DEFERRED to slice B (A4). Agno owns
    all skill execution logic (A1).
    """

    @classmethod
    def build(cls, config: SkillsConfig | dict[str, Any] | None) -> Skills | None:
        """Build a native ``Skills`` instance from config.

        Accepts EITHER a raw dict (opaque ``AgentConfig.skills``, Option B),
        a pre-parsed ``SkillsConfig``, or ``None``. Raw dicts are validated
        against ``SkillsConfig`` via ``TypeAdapter`` (the validation boundary
        moves from config-parse to factory-build; it does NOT disappear).

        Args:
            config: The raw ``AgentConfig.skills`` dict, a parsed
                ``SkillsConfig``, or ``None`` when no skills are configured.
                ``None`` short-circuits to ``None`` (no Agno object built).

        Returns:
            A native ``agno.skills.Skills`` instance wrapping one
            ``LocalSkills`` loader, or ``None`` if ``config`` is ``None``.

        Raises:
            ValidationError: If a raw dict fails ``SkillsConfig`` validation
                (re-raised from ``TypeAdapter.validate_python``).
            FileNotFoundError: If ``path`` does not exist (propagated from
                ``LocalSkills.load()`` via ``Skills.__init__`` when the
                path is absent).
            SkillValidationError: If ``validate=True`` and a skill fails
                Agno's ``validate_skill_directory`` (propagated from
                ``Skills.__init__``).
        """
        if config is None:
            return None

        cfg = (
            _CONFIG_ADAPTER.validate_python(config)
            if isinstance(config, dict)
            else config
        )

        local_skills = LocalSkills(path=cfg.path, validate=cfg.validate)
        return Skills(loaders=[local_skills])
```

### MODIFY `src/yaml_agno/skills/__init__.py`

```python
"""yaml-agno skills layer — SPEC_30 (slice A).

Public API:
    from yaml_agno.skills import SkillsConfig, SkillsFactory
"""

from yaml_agno.skills.factory import SkillsFactory
from yaml_agno.skills.schema import SkillsConfig

__all__ = ["SkillsConfig", "SkillsFactory"]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `SkillsFactory.build(None)` returns `None`. | Direct call, assert `is None`. |
| Unit | `SkillsFactory.build(dict)` validates via `TypeAdapter`; rejects missing `path`, extra keys (`extra="forbid"`). | `pytest.raises(ValidationError)`. |
| Unit | `SkillsFactory.build(SkillsConfig)` returns a `Skills` with one `LocalSkills` loader whose `path` and `validate` match config. | `tmp_path` fixture writes a valid `SKILL.md`; assert `isinstance(result, Skills)`, `len(result.loaders) == 1`, `loader.path == resolved`, `loader.validate == cfg.validate`. |
| Unit | Invalid skill with `validate=True` raises `SkillValidationError`. | `tmp_path` with malformed `SKILL.md` (bad name / missing frontmatter); `pytest.raises(SkillValidationError)`. |
| Unit | Invalid skill with `validate=False` does NOT raise (Agno logs + skips). | `tmp_path` with malformed `SKILL.md`, `validate=False`; assert `isinstance(result, Skills)`. |

### TDD (Strict TDD Mode is active — project verified via sdd-init)

RED → GREEN → REFACTOR per test. Tests live at
`tests/unit/skills/test_skills_factory.py`.

Temp-dir SKILL.md fixture (literal):

```python
import pytest
from agno.skills import Skills, SkillValidationError
from pydantic import ValidationError

from yaml_agno.skills import SkillsConfig, SkillsFactory


def _write_valid_skill(skill_dir, name="my-skill"):
    """Write a structurally valid SKILL.md (lowercase, hyphenated name)."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: A test skill.\n"
        "---\n"
        "# My Skill\n"
        "Instructions here.\n",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_build_none_returns_none() -> None:
    assert SkillsFactory.build(None) is None


@pytest.mark.unit
def test_build_missing_path_rejected(tmp_path) -> None:
    with pytest.raises(ValidationError):
        SkillsFactory.build({"validate": True})


@pytest.mark.unit
def test_build_extra_keys_rejected(tmp_path) -> None:
    with pytest.raises(ValidationError):
        SkillsFactory.build({"path": str(tmp_path), "bogus": 1})


@pytest.mark.unit
def test_build_dict_returns_skills_with_localskills(tmp_path) -> None:
    _write_valid_skill(tmp_path / "my-skill")
    result = SkillsFactory.build({"path": str(tmp_path), "validate": True})
    assert isinstance(result, Skills)
    assert len(result.loaders) == 1
    assert result.loaders[0].validate is True


@pytest.mark.unit
def test_build_invalid_skill_raises_when_validate_true(tmp_path) -> None:
    # Bad name: uppercase violates Agno name rules.
    _write_valid_skill(tmp_path / "BadName", name="BadName")
    with pytest.raises(SkillValidationError):
        SkillsFactory.build({"path": str(tmp_path), "validate": True})


@pytest.mark.unit
def test_build_invalid_skill_skipped_when_validate_false(tmp_path) -> None:
    _write_valid_skill(tmp_path / "BadName", name="BadName")
    result = SkillsFactory.build({"path": str(tmp_path), "validate": False})
    assert isinstance(result, Skills)
```

## Verification

1. `pytest tests/unit/skills/ -v` — all 6 tests GREEN.
2. `ruff check src/yaml_agno/skills/` — clean.
3. `mypy src/yaml_agno/skills/` — clean (Python 3.12 strict).
4. Import smoke test: `python -c "from yaml_agno.skills import SkillsConfig, SkillsFactory; print('ok')"`.

## Migration / Rollback

No migration required. Slice A adds two new modules and re-exports; nothing
existing imports from `yaml_agno.skills` (the `__init__.py` was an empty
stub).

**Rollback**: delete `schema.py`, `factory.py`, and revert `__init__.py`
to empty. No downstream impact since `AgentFactory` is not yet wired (A4).

## Open Questions

- None for slice A. Slice B will address `AgentFactory` integration
  (forwarding `SkillsFactory.build(config.skills)` to `Agent(skills=...)`).
