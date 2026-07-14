---
change: skills-wiring
spec: SPEC_30
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on: [proposal, spec, design]
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: Skills Wiring — AgentFactory Forwarding (SPEC_30, Slice B)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150 (10 prod + 70 tests + 15 fixture fix + 65 contract tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | RED tests + fixture fix + GREEN wiring + verify | PR 1 (single) | base: main; ~150 LOC total |

## TDD Compliance Matrix

| Req ID | Requirement | RED test | GREEN code | Scenario |
|--------|-------------|----------|------------|----------|
| R-fwd | AgentFactory.build cablea cfg.skills | test_build_forwards_skills_when_present | skills branch + Agent(skills=...) | Golden: agent.skills is Skills |
| R-none | None forwarding → Agent(skills=None) | test_build_without_skills_keeps_agent_skills_none | skills=None short-circuit | Backward compat: agent.skills is None |
| R-sysprompt | System prompt contiene bloque skills_system | test_build_skills_injects_system_prompt_snippet | forwarding enables Agno injection | snippet non-empty XML |
| R-tools | Agente con skills expone 3 access tools | test_build_skills_exposes_three_access_tools | forwarding enables Agno tools | 3 Function objects, exact names |
| R-nosysprompt | Agente sin skills SIN bloque (MODIFIED) | covered by test_build_without_skills_keeps_agent_skills_none | same GREEN | agent.skills is None |
| R-notools | Agente sin skills SIN access tools | covered by negative path in test_build_without_skills | same GREEN | no skill tools present |
| R-err | ValidationError se propaga | test_build_skills_propagates_invalid_skill_error | no try/except in build | SkillValidationError raised |

## Phase 1: Baseline (verify clean starting point)

- [x] 1.1 Run `python -m pytest tests/unit/factories/test_agent_factory.py -v` — confirm all existing tests GREEN before any change.
- [x] 1.2 Run `python -m pytest tests/unit/skills/test_skills_factory.py -v` — confirm slice A adapter still GREEN (no regression source).
- [x] 1.3 Run `ruff check . && ruff format --check . && mypy` — confirm lint/format/types clean at baseline.

## Phase 2: RED — Contract tests + fixture fix (tests FIRST, no prod code)

- [x] 2.1 Fix `tests/unit/factories/test_agent_factory.py:133` — remove `skills={"list": ["s1"]},` line from `test_build_all_opaque_slots_tags_metadata_populated` (skills now owned by slice B, not opaque-ignored).
- [x] 2.2 Fix `tests/unit/factories/test_agent_factory.py:147` — remove `assert result.skills is None` (covered by new TestAgentFactorySkillsWiring class).
- [x] 2.3 Add `TestAgentFactorySkillsWiring` class to `tests/unit/factories/test_agent_factory.py` with `_write_valid_skill` helper (tmp_path + lowercase SKILL.md frontmatter).
- [x] 2.4 RED test: `test_build_forwards_skills_when_present` — assert `isinstance(result.skills, Skills)` when cfg.skills is valid dict. Fails: build ignores skills.
- [x] 2.5 RED test: `test_build_without_skills_keeps_agent_skills_none` — assert `result.skills is None` when cfg.skills omitted. PASSES already (baseline).
- [x] 2.6 RED test: `test_build_skills_injects_system_prompt_snippet` — assert `result.skills.get_system_prompt_snippet()` returns non-empty str. Fails: skills is None.
- [x] 2.7 RED test: `test_build_skills_exposes_three_access_tools` — assert `result.skills.get_tools()` returns 3 Function with names {get_skill_instructions, get_skill_reference, get_skill_script}. Fails: skills is None.
- [x] 2.8 RED test: `test_build_skills_propagates_invalid_skill_error` — assert `SkillValidationError` raised on BadName uppercase + validate=True. Fails: build ignores skills (no validation triggered).
- [x] 2.9 Run `python -m pytest tests/unit/factories/test_agent_factory.py -v` — confirm 4 new tests RED (2.4, 2.6, 2.7, 2.8 fail), 2.5 GREEN, existing fixture-fixed test GREEN.

## Phase 3: GREEN — AgentFactory skills forwarding (minimal code to pass)

- [x] 3.1 Add `from yaml_agno.skills import SkillsFactory` import to `src/yaml_agno/factories/agent_factory.py`.
- [x] 3.2 Add skills branch in `build()`: `skills = SkillsFactory.build(cfg.skills) if cfg.skills else None` (after tools branch, before Agent constructor).
- [x] 3.3 Add `skills=skills` kwarg to `Agent(...)` constructor call.
- [x] 3.4 Update `build()` docstring: add skills row to mapping table, note SkillsFactory dispatch, update Raises section.
- [x] 3.5 Run `python -m pytest tests/unit/factories/test_agent_factory.py -v` — confirm all 5 new tests GREEN + 13 existing scenarios GREEN.

## Phase 4: Verification (full quality gate — GATE VQ)

- [x] 4.1 Run `python -m pytest tests/unit/factories/test_agent_factory.py -v` — new class + existing scenarios GREEN.
- [x] 4.2 Run `python -m pytest tests/unit/skills/test_skills_factory.py -v` — slice A no regression.
- [x] 4.3 Run `python -m pytest -q` — full suite GREEN.
- [x] 4.4 Run `ruff check .` — lint clean.
- [x] 4.5 Run `ruff format --check .` — format clean.
- [x] 4.6 Run `mypy` — types clean (skills: Skills | None matches Agent.__init__ Optional[Skills]).
- [x] 4.7 Cold import check: `python -c "from yaml_agno.factories.agent_factory import AgentFactory"` — no circular import, no runtime error.

## Phase 5: Commit (granular, conventional)

- [x] 5.1 Commit 1: `test: fix opaque-skills fixture + add RED contract tests for skills-wiring (SPEC_30 slice B)` — Phase 2 changes.
- [x] 5.2 Commit 2: `feat(factories): wire AgentFactory.build to forward cfg.skills via SkillsFactory (SPEC_30 slice B)` — Phase 3 changes.
- [x] 5.3 Confirm `git status` clean after both commits.

## Open Items

- [x] Confirm `Function.name` is the canonical attribute for access-tool names in Agno 2.6.22 (one-line assertion fix at apply time if it differs). — RESOLVED: `Function.name` confirmed canonical in Agno 2.6.22.
- [x] If system-prompt snippet assertion via `get_system_prompt_snippet()` is empty, fall back to inspecting assembled system message (design open question, default is public method). — RESOLVED: `get_system_prompt_snippet()` returns non-empty `<skills_system>` block; public method works, no fallback needed.
