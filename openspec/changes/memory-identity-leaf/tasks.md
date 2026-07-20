# Tasks: memory-identity-leaf

> SPEC_04 LEAF slice. Two additive self-contained modules + one re-export.
> Strict TDD (RED → GREEN). ~200 LOC forecast. Low risk, single PR.
> Literal source is baked into `design.md` — apply verbatim, do NOT reshape.

## Forecast

- **LOC**: ~200 (3 source files + 2 test files)
- **Risk**: Low (additive, zero callers wired, Option B opaque)
- **PRs**: 1
- **Spec coverage**: 9 requirements, 14 scenarios

## Phase 0 — Baseline

- [ ] 0.1 Confirm clean working tree and `AgentConfig.memory` still
  `dict[str, Any] | None` (Option B precondition).
  `grep -n "memory:" src/yaml_agno/models/config/agent_config.py`.
  **Spec**: AgentConfig.memory permanece opaco.

## Phase 1 — RED (tests first, modules do not exist yet)

These four tasks are independent and MAY run in parallel.

- [ ] 1.1 Write `tests/yaml_agno/memory/test_user_identity.py` with 7 cases:
  golden-human, golden-system-literal, golden-template-expanded,
  RED-missing-tenant, RED-missing-principal, RED-template-without-context,
  RED-template-missing-key (asserts `__cause__` is `KeyError`).
  Run `pytest tests/yaml_agno/memory/test_user_identity.py` → must fail on
  `ImportError`. **Spec**: Reqs 1-4 (resolver + fail-fast + template).
- [ ] 1.2 Write `tests/yaml_agno/models/config/test_memory_config.py` with:
  golden-canonical-parse (6 scalars, 4 nested None), RED-extra-forbid,
  RED-missing-required-scalar, RED-system_user_id-empty,
  RED-num_history-negative, RED-storage_type-out-of-Literal,
  optional-nested-blocks-None.
  Run `pytest tests/yaml_agno/models/config/test_memory_config.py` → must
  fail on `ImportError`. **Spec**: Reqs 5-6 (MemoryConfig + sub-schemas).
- [ ] 1.3 Confirm `tests/yaml_agno/memory/__init__.py` and
  `tests/yaml_agno/models/config/__init__.py` exist (or create empty).
- [ ] 1.4 No-op: leave `src/yaml_agno/memory/__init__.py` empty until Phase 2.3.

## Phase 2 — GREEN (literal source from design.md, verbatim)

- [ ] 2.1 Write `src/yaml_agno/memory/user_identity.py` verbatim from
  `design.md` §Literal Code (UserIdentityResolutionError + resolve_user_id).
  Run `pytest tests/yaml_agno/memory/test_user_identity.py` → all green.
  **Spec**: Reqs 1-4. **Sequential**: after 1.1.
- [ ] 2.2 Write `src/yaml_agno/models/config/memory_config.py` verbatim from
  `design.md` §Literal Code (MemoryConfig + 7 nested sub-schemas, all
  `extra="forbid"`). Run
  `pytest tests/yaml_agno/models/config/test_memory_config.py` → all green.
  **Spec**: Reqs 5-6. **Parallelizable** with 2.1 (independent). After 1.2.
- [ ] 2.3 Edit `src/yaml_agno/memory/__init__.py` to add the two re-exports
  (`resolve_user_id`, `UserIdentityResolutionError`) + `__all__`.
  **Spec**: Req 7 (re-export). **Sequential**: after 2.1.

## Phase 3 — Verification

- [ ] 3.1 `python -m pytest tests/yaml_agno/memory/test_user_identity.py
  tests/yaml_agno/models/config/test_memory_config.py -v` → all green.
  **Spec**: Req 9.
- [ ] 3.2 `ruff check src/yaml_agno/memory/ src/yaml_agno/models/config/memory_config.py`
  → zero findings.
- [ ] 3.3 `mypy src/yaml_agno/memory/ src/yaml_agno/models/config/memory_config.py`
  → zero errors.
- [ ] 3.4 Import smoke test:
  `python -c "from yaml_agno.memory import resolve_user_id, UserIdentityResolutionError; from yaml_agno.models.config.memory_config import MemoryConfig; print('ok')"`.
  **Spec**: Req 7.
- [ ] 3.5 Confirm no `agno` import in the two new modules:
  `grep -nE "^(import|from) agno" src/yaml_agno/memory/user_identity.py src/yaml_agno/models/config/memory_config.py`
  → no output. **Spec**: Req 8.
- [ ] 3.6 Confirm `AgentConfig.memory` untouched:
  `git diff --name-only src/yaml_agno/models/config/agent_config.py` → empty.
  **Spec**: Req 7 (Option B).

## Phase 4 — Gate VQ + Commit

- [ ] 4.1 Run repo GATE VQ (quality verification gate) per project workflow.
- [ ] 4.2 Stage all 5 files (3 src + 2 tests) and commit with conventional
  message: `feat(memory): add resolve_user_id leaf + MemoryConfig schema (SPEC_04 leaf)`.
  Single PR.

## Dependency Graph

```
Phase 1 (RED, parallel):  1.1 ─┐
                           1.2 ─┤
                           1.3 ─┤
                           1.4 ─┘
                                │
Phase 2 (GREEN):            2.1 (after 1.1) ──┬── 2.3 (after 2.1)
                            2.2 (after 1.2) ──┘
                                │
Phase 3 (Verify, sequential): 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6
                                │
Phase 4 (Gate + Commit):    4.1 → 4.2
```

## Parallel vs Sequential Summary

- **Parallelizable**: 1.1, 1.2, 1.3, 1.4 (RED authoring); 2.1 ∥ 2.2 (GREEN,
  independent modules).
- **Strictly sequential**: 2.1 → 2.3 (init re-export depends on user_identity
  module existing); all of Phase 3 and Phase 4.
