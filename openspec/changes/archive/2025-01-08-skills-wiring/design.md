---
change: skills-wiring
spec: SPEC_30
status: proposed
artifact_store: hybrid
depends_on: [skills-foundation]
---

# Design: Skills Wiring — AgentFactory Forwarding (SPEC_30, Slice B)

> Closes SPEC_30. Slice A (`skills-foundation`) shipped `SkillsConfig` +
> `SkillsFactory.build`. This slice is the single wiring point that turns the
> opaque `AgentConfig.skills` slot into a live `agno.skills.Skills` on the
> constructed `agno.Agent`.

## Technical Approach

Extend `AgentFactory.build` with one conditional branch that mirrors the
existing `tools` branch: when `cfg.skills` is non-`None`, call
`SkillsFactory.build(cfg.skills)` and forward the result to
`Agent(skills=...)`. When `cfg.skills is None`, behavior is UNCHANGED from
slice #1 — `skills=None` is forwarded and existing callers/tests stay green
(zero breaking tests, same backward-compat invariant SPEC_11 slice C
established for `tools`).

The factory is NOT a new abstraction. It is a one-line delegation that reuses
the slice A adapter. yaml-agno owns no skill logic — validation, loading,
system-prompt injection, and access-tool exposure all live in Agno 2.6.22
(verified obs-2137). This slice only connects the slice A output to the
`Agent` constructor's `skills` kwarg.

Contract tests use `tmp_path` `SKILL.md` fixtures (no Agno mocks) so the
end-to-end wiring is exercised against the real `Skills.get_system_prompt_snippet()`
and `Skills.get_tools()` surfaces.

## Architecture Decisions

### Decision: SkillsFactory dispatch INSIDE `build()`, same pattern as tools

**Choice**: Add `skills = SkillsFactory.build(cfg.skills) if cfg.skills else None`
inside `AgentFactory.build`, then pass `skills=skills` to `Agent(...)`.
**Alternatives considered**:
- Move dispatch to a higher layer (caller passes pre-built `Skills`). REJECTED:
  breaks the self-contained `build(cfg, resolver) -> Agent` contract; callers
  would need to know about `SkillsFactory` and `ToolFactory` independently.
- Add a `skills_resolver` param alongside `resolver`. REJECTED: skills need no
  dotted-path resolution (unlike custom tools); `cfg.skills` carries the full
  dict the factory needs. Extra param is dead weight.
**Rationale**: Symmetry with the existing `tools` branch (lines 99-102 of
agent_factory.py) keeps the cognitive load flat — one factory-per-opaque-slot
pattern, applied identically. The `resolver` param stays tools-only because
skills have no allowlist resolution path.

### Decision: Forward `cfg.skills` (raw dict), NOT a pre-parsed SkillsConfig

**Choice**: Pass the opaque `cfg.skills: dict[str, Any] | None` straight to
`SkillsFactory.build`, which already accepts `dict | SkillsConfig | None` and
runs `TypeAdapter(SkillsConfig)` internally (factory.py:84-88).
**Alternatives considered**:
- Validate in `AgentConfig` and pass a `SkillsConfig` instance. REJECTED:
  violates Option B invariant (SPEC_30 skills-foundation spec, "AgentConfig.skills
  permanece opaco"). The validation boundary lives in the factory, not the aggregate.
- Validate in `AgentFactory` before calling `SkillsFactory`. REJECTED: duplicates
  the `TypeAdapter` work the factory already does.
**Rationale**: Slice A designed `SkillsFactory.build` to accept the raw dict
precisely so slice B's wiring stays a one-liner. Honoring that contract keeps
`AgentConfig` opaque and centralizes validation in one place.

### Decision: Contract tests against real Agno, not mocks

**Choice**: `tmp_path` fixtures write a structurally valid `SKILL.md`, then
assert `agent.skills.get_system_prompt_snippet()` returns a non-empty XML
block and `agent.skills.get_tools()` returns 3 `Function` objects
(`get_skill_instructions`, `get_skill_reference`, `get_skill_script`).
**Alternatives considered**:
- Mock `SkillsFactory.build` to return a fake `Skills`. REJECTED: the slice B
  risk is precisely that Agno's `Agent(skills=...)` wiring actually invokes the
  snippet injector and tool exposer; mocks would assert nothing about that.
- Assert only `isinstance(agent.skills, Skills)`. REJECTED: too weak — passes
  even if Agno silently drops the snippet. Contract tests must prove behavior.
**Rationale**: SPEC_30 slice A spec "Out of Scope" explicitly defers the
system-prompt contract (TASK_006) and access-tools presence (TASK_007) to slice
B. These contract assertions ARE slice B.

### Decision: DEFER multi-loader to a later change

**Choice**: This slice forwards a single `Skills` instance (one
`SkillsFactory.build` call). Multi-directory aggregation (multiple `paths`) is
out of scope.
**Alternatives considered**: Extend `SkillsConfig` to a list now. REJECTED:
slice A shipped single-loader; expanding the schema here would inflate the
diff and re-open a settled decision.
**Rationale**: Keep the slice focused on wiring. Schema expansion is a separate
change with its own proposal/spec cycle.

## Data Flow

```
AgentConfig.skills (dict | None)
        │
        ▼
AgentFactory.build(cfg, resolver)
        │
        ├── if cfg.skills:
        │       SkillsFactory.build(cfg.skills)   ← slice A adapter
        │           │
        │           ├── TypeAdapter(SkillsConfig).validate_python(dict)
        │           ├── LocalSkills(path, validate)
        │           └── Skills(loaders=[local_skills])
        │       │
        │       ▼
        │   skills: Skills | None
        │
        ▼
Agent(name=..., model=..., tools=..., skills=skills, tool_call_limit=...)
        │
        ├── Agent.__init__ stores skills; no loading happens here
        │
        ▼  (at agent.run() / agent.arun() time, Agno auto-invokes)
agent.skills.get_system_prompt_snippet()  → XML <skills_system> block
agent.skills.get_tools()                  → 3 Function objects
```

Construction stays pure assignment + factory dispatch. No network, no LLM
instantiation, no skill loading beyond what `Skills.__init__` already does in
slice A (`_load_skills` runs synchronously inside `SkillsFactory.build`).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/agent_factory.py` | Modify | Add `skills` forwarding branch in `build()`; update docstring table + scope; import `SkillsFactory`. |
| `tests/unit/factories/test_agent_factory.py` | Modify | Add `TestAgentFactorySkillsWiring` class with contract tests (golden path, None path, system-prompt snippet, 3 access tools, invalid skill propagates). |

**File count**: 1 modified production file, 1 modified test file. 0 new files.
2 files total touched.

## Interfaces / Contracts

### Modified: `AgentFactory.build` — skills forwarding snippet (LITERAL)

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agno.agent import Agent

from yaml_agno.models.config.agent_config import AgentConfig
from yaml_agno.skills import SkillsFactory
from yaml_agno.tools.tool_factory import ToolFactory

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["AgentFactory"]


class AgentFactory:
    """Builds ``agno.Agent`` instances from validated ``AgentConfig`` objects.

    Scope (identity + model + optional tools + optional skills):

        +--------------------------+--------------------------+-----------+
        | AgentConfig field        | agno.Agent kwarg         | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | instructions: str | None | instructions             | direct    |
        | description: str | None  | description              | direct    |
        | model: str               | model                    | passthru  |
        | tools: list[dict]        | tools                    | factory*  |
        | tool_call_limit: int|None| tool_call_limit          | direct    |
        | skills: dict | None      | skills                   | factory** |
        +--------------------------+--------------------------+-----------+
        | knowledge, memory, ...   | (not forwarded)          | deferred  |
        | tags, metadata           | (not forwarded)          | deferred  |
        +--------------------------+--------------------------+-----------+

        * tools is resolved ONLY when ``resolver`` is passed to ``build()``.
        ** skills is resolved via ``SkillsFactory.build`` whenever
           ``cfg.skills`` is non-None; no resolver needed (Option B).

    Deferred slots are accepted silently and resolved by their owner SPECs +
    the DependencyManager. This class exposes a static ``build()`` method; it
    holds no state and is not instantiated.
    """

    @staticmethod
    def build(
        cfg: AgentConfig,
        resolver: AgnoResolver | None = None,
    ) -> Agent:
        """Build a native ``agno.Agent`` from an ``AgentConfig``.

        Maps the identity/behavior fields directly. When ``resolver`` is
        provided AND ``cfg.tools`` is non-empty, resolves the opaque tools
        dicts into the mixed list ``agno.Agent(tools=...)`` accepts via
        ``ToolFactory`` (Option B). When ``cfg.skills`` is non-None, resolves
        the opaque skills dict into a ``Skills`` instance via
        ``SkillsFactory.build`` and forwards it to ``Agent(skills=...)``.

        Args:
            cfg: A validated ``AgentConfig`` (SPEC_02). Its ``model`` field is
                a ``provider:id`` string forwarded verbatim to Agno. Its
                ``tools`` field is an opaque ``list[dict]`` resolved here when
                a resolver is supplied. Its ``skills`` field is an opaque
                ``dict[str, Any] | None`` resolved here whenever non-None.
            resolver: Optional ``AgnoResolver`` for allowlisted dotted-path
                resolution of custom tools / toolkit classes / MCP
                ``header_provider``. When ``None`` (default), tools are
                skipped — callers that do not need tools pass nothing. Skills
                do not use the resolver.

        Returns:
            A constructed ``agno.Agent``. Per ``agno/agent/agent.py:504``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked. MCP tools are UNCONNECTED at this point;
            Agent auto-connects them during ``aget_tools`` (A2). Skills loaders
            run synchronously inside ``SkillsFactory.build`` (slice A).

        Raises:
            (none directly) Any exception raised by ``agno.Agent.__init__``,
                ``ToolFactory.build()`` (``UnknownBuiltinError``,
                ``SecurityError``, ``ValidationError``), or
                ``SkillsFactory.build()`` (``ValidationError``,
                ``FileNotFoundError``, ``SkillValidationError``) propagates
                unchanged.
        """
        tools: list[Any] = []
        if cfg.tools and resolver is not None:
            factory = ToolFactory(resolver)
            tools = factory.build(cfg.tools)
        skills = SkillsFactory.build(cfg.skills) if cfg.skills else None
        return Agent(
            name=cfg.name,
            instructions=cfg.instructions,
            description=cfg.description,
            model=cfg.model,
            tools=tools or None,
            tool_call_limit=cfg.tool_call_limit,
            skills=skills,
        )
```

### New test class: `TestAgentFactorySkillsWiring` (LITERAL)

```python
class TestAgentFactorySkillsWiring:
    """RED->GREEN tests for SPEC_30 slice B: ``build(cfg)`` skills forwarding.

    When ``cfg.skills`` is non-None, the factory builds a ``Skills`` instance
    via ``SkillsFactory.build`` and forwards it to ``Agent(skills=...)``. When
    ``cfg.skills is None``, behavior is unchanged (``agent.skills is None``).

    Contract tests (R-sysprompt, R-tools): real ``SKILL.md`` fixtures in
    ``tmp_path`` exercise Agno's system-prompt snippet injector and access-tool
    exposer end-to-end. No Agno mocks.
    """

    @staticmethod
    def _write_valid_skill(skill_dir, name="my-skill"):
        """Write a structurally valid ``SKILL.md`` (lowercase, hyphenated name).

        Mirrors the helper in ``tests/unit/skills/test_skills_factory.py`` so
        Agno's ``validate_skill_directory`` passes when ``validate=True``.
        """
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

    def test_build_forwards_skills_when_present(self, tmp_path) -> None:
        """Slice B golden: build(cfg with skills) -> agent.skills is a Skills instance."""
        from agno.skills import Skills

        self._write_valid_skill(tmp_path / "my-skill")
        cfg = AgentConfig(
            name="agent-skills",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert isinstance(result.skills, Skills)

    def test_build_without_skills_keeps_agent_skills_none(self) -> None:
        """Slice B backward-compat: build(cfg without skills) -> agent.skills is None."""
        cfg = AgentConfig(name="agent-no-skills", model="openai:gpt-4o")
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert result.skills is None

    def test_build_skills_injects_system_prompt_snippet(self, tmp_path) -> None:
        """Slice B contract (R-sysprompt): agent.skills.get_system_prompt_snippet()
        returns a non-empty XML block (the ``<skills_system>`` injection)."""
        self._write_valid_skill(tmp_path / "my-skill")
        cfg = AgentConfig(
            name="agent-snippet",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        result = AgentFactory.build(cfg)
        assert result.skills is not None
        snippet = result.skills.get_system_prompt_snippet()
        assert isinstance(snippet, str)
        assert snippet.strip() != ""

    def test_build_skills_exposes_three_access_tools(self, tmp_path) -> None:
        """Slice B contract (R-tools): agent.skills.get_tools() returns the
        three Agno access tools (instructions, reference, script) as Function
        objects."""
        from agno.tools.function import Function

        self._write_valid_skill(tmp_path / "my-skill")
        cfg = AgentConfig(
            name="agent-tools",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        result = AgentFactory.build(cfg)
        assert result.skills is not None
        tools = result.skills.get_tools()
        assert len(tools) == 3
        assert all(isinstance(t, Function) for t in tools)
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "get_skill_instructions",
            "get_skill_reference",
            "get_skill_script",
        }

    def test_build_skills_propagates_invalid_skill_error(self, tmp_path) -> None:
        """Slice B error propagation: an invalid skill dir (BadName uppercase)
        with validate=True propagates SkillValidationError from the factory."""
        from agno.skills import SkillValidationError

        self._write_valid_skill(tmp_path / "BadName", name="BadName")
        cfg = AgentConfig(
            name="agent-bad",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        with pytest.raises(SkillValidationError):
            AgentFactory.build(cfg)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (contract) | `build(cfg with skills)` -> `agent.skills` is a `Skills` instance | `tmp_path` fixture + real `SKILL.md`; no Agno mocks. |
| Unit (contract) | `build(cfg without skills)` -> `agent.skills is None` (backward-compat) | Plain `AgentConfig`, assert default. |
| Unit (contract) | `agent.skills.get_system_prompt_snippet()` returns non-empty XML block | Real Agno snippet injector; proves TASK_006 contract. |
| Unit (contract) | `agent.skills.get_tools()` returns 3 `Function` objects with expected names | Real Agno tool exposer; proves TASK_007 contract. |
| Unit (error) | Invalid skill (`BadName` uppercase) + `validate=True` propagates `SkillValidationError` | `tmp_path` fixture with deliberately invalid bundle. |
| Regression | All existing `test_agent_factory.py` tests stay green (the `test_build_all_opaque_slots_tags_metadata_populated` test currently asserts `result.skills is None` for an opaque dict that is NOT a valid `SkillsConfig` shape — see Open Questions). | Re-run full suite; no modifications to existing tests unless the regression below forces it. |

## TDD

Strict TDD mode is active (sdd-init detected pytest). The phase will be
implemented RED -> GREEN:

1. Add the 5 tests in `TestAgentFactorySkillsWiring` first. They FAIL because
   `AgentFactory.build` does not yet forward `skills`.
2. Add the `skills = SkillsFactory.build(cfg.skills) if cfg.skills else None`
   line + the `skills=skills` kwarg + the `SkillsFactory` import.
3. Tests go GREEN.
4. `ruff check . && ruff format --check . && mypy && pytest -q` must pass.

No production code is written before the RED tests exist.

## Verification

- `pytest tests/unit/factories/test_agent_factory.py -v` — new class green,
  existing 13 scenarios still green.
- `pytest tests/unit/skills/test_skills_factory.py -v` — slice A tests still
  green (no regression in the adapter).
- `pytest -q` — full suite green.
- `ruff check . && ruff format --check .` — lint/format clean.
- `mypy` — strict type-check clean (the `skills: Skills | None` annotation
  matches `Agent.__init__`'s `skills: Optional[Skills]`).

## Migration / Rollback

No migration required. `AgentConfig.skills` is already an opaque slot
populated from YAML; this slice only changes how the factory consumes it.

**Rollback**: revert the single production-file diff
(`src/yaml_agno/factories/agent_factory.py`) to remove the `skills` branch and
the `SkillsFactory` import, and revert the test-file diff to drop
`TestAgentFactorySkillsWiring`. `AgentConfig.skills` returns to being
opaque-unconsumed — identical to the slice A state. `git revert` of the slice B
commit is a clean rollback; no data, no state, no migration to undo.

## Open Questions

- [ ] **Regression on `test_build_all_opaque_slots_tags_metadata_populated`
  (line 147)**: that existing test populates `skills={"list": ["s1"]}` and
  asserts `result.skills is None`. After slice B, `SkillsFactory.build` will
  try to validate `{"list": ["s1"]}` against `SkillsConfig` and raise
  `ValidationError` (missing `path`). The existing test will break. DECISION
  NEEDED at tasks/apply time: (a) update that test's opaque `skills` value to
  a structurally-invalid-for-SkillsConfig dict that we still expect to raise
  (changing the assertion from "silently ignored" to "raises ValidationError"),
  OR (b) change the opaque value to `None` / remove `skills` from that
  fixture. Recommended: (b) — the test's intent is "opaque slots I do not own
  are ignored", and `skills` is now owned by slice B. Recommended fix (LITERAL):

  ```python
  # In test_build_all_opaque_slots_tags_metadata_populated, remove or null the
  # skills= line (currently line 133):
  #   skills={"list": ["s1"]},   # REMOVE — skills is now owned by slice B
  # and remove the assertion on line 147:
  #   assert result.skills is None  # REMOVE — covered by TestAgentFactorySkillsWiring
  ```
- [ ] Confirm `Function.name` is the canonical attribute for access-tool names
  in Agno 2.6.22 (used in the `tool_names` set assertion). If the attribute
  differs, adjust the assertion at apply time — this is a one-line fix, not a
  design change.
