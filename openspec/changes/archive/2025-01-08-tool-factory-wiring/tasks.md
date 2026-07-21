---
change: tool-factory-wiring
spec: SPEC_11
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - openspec/changes/tool-factory-wiring/proposal.md
  - openspec/changes/tool-factory-wiring/specs/tool-factory-wiring/spec.md
  - openspec/changes/tool-factory-wiring/design.md
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: ToolFactory Wiring (SPEC_11 Slice C)

> Closes the loop opened by slices A+B: wires `AgentConfig.tools` (opaque) into
> `agno.Agent(tools=...)` via a SYNC `ToolFactory` orchestrator, widens
> `CustomToolConfig` with `@tool` flags + HITL validator, and threads an optional
> `resolver` through `AgentFactory.build()`. **STRICT TDD** — RED before GREEN
> on every behavioral task.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~280-340 (tool_factory.py ~120 new, schema.py ~90 widen, agent_factory.py ~40 modify, __init__.py ~3, 3 test files ~90-120) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (1 NEW file + 3 MODIFY + 3 test files; under budget) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | CustomToolConfig widen + HITL validator (schema.py + test_schema.py) | PR único | base = feature branch; standalone, ships first |
| 2 | ToolFactory + _wrap_tool (tool_factory.py + __init__.py + test_tool_factory.py) | PR único | depends on Unit 1 (CustomToolConfig flags) |
| 3 | AgentFactory.build resolver wiring (agent_factory.py + test_agent_factory.py) | PR único | depends on Unit 2 (ToolFactory import) |

## Open Items (CRÍTICO — read before apply)

- **`external_execution_silent`**: the design literal code (schema.py MODIFY +
  `_wrap_tool` flags dict) includes `external_execution_silent: bool | None =
  None`, but the spec's MODIFIED requirement field list does NOT name it.
  **Resolution**: follow the design literal (SSOT for HOW); include the field.
  The spec's field list is illustrative ("the following fields MUST be added"),
  not exhaustive — the design code is the exact contract.
- **`_loader._resolver` private access**: `ToolFactory.build` accesses
  `self._loader._resolver` to pass to `BUILTIN_REGISTRY[name].build()`. This
  reads a private attr of `CustomToolLoader`. Acceptable (same package, same
  slice author) but documented as a coupling point. Alternative: expose a
  `resolver` property on `CustomToolLoader`. Follow design literal for slice C.
- **`tools=tools or None`**: AgentFactory passes `None` when `tools == []` so
  Agno uses its default. This means `agent.tools` may be Agno's default list,
  not literally `[]`. Existing test `test_build_all_opaque_slots...` asserts
  `result.tools == []` — Agno default IS `[]`, so this holds. Verify in Phase 5.

## Phase 1: Baseline verification

- [x] 1.1 Confirm clean baseline: `git status` clean, HEAD on the feature
  branch. Note current `python -m pytest` is green (slices A+B shipped).
  **Req: Rollback Plan (baseline obligatorio).**
- [x] 1.2 Confirm `AgentConfig.tools` is opaque `list[dict[str, Any]]` today
  (`agent_config.py`) — NOT widened. **Req: `AgentConfig.tools` permanece opaco.**

## Phase 2: RED — failing tests first (STRICT TDD)

> Each test below MUST fail for the RIGHT reason (missing module / missing
> field / missing param) before its GREEN counterpart runs.

- [x] 2.1 **test_schema.py** — ADD `test_custom_tool_config_accepts_tool_flags`:
  `CustomToolConfig(path="x.y", requires_confirmation=True, cache_results=True,
  cache_ttl=3600)` parses; assert fields populated. FAILS today: `extra="forbid"`
  rejects unknown fields. **Req: `CustomToolConfig` ensanchado acepta flags.**
- [x] 2.2 **test_schema.py** — ADD `test_custom_tool_config_minimal_still_valid`:
  `CustomToolConfig(path="x.y")` still valid; all flags at defaults
  (`requires_confirmation == False`, `cache_ttl is None`). **Req: CustomToolConfig minimal sigue válido.**
- [x] 2.3 **test_schema.py** — ADD `test_hitl_validator_rejects_two_flags_true`:
  `CustomToolConfig(path="x.y", requires_confirmation=True,
  requires_user_input=True)` raises `ValidationError`. FAILS today: no
  validator. **Req: Validador HITL — RED con 2 flags True.**
- [x] 2.4 **test_schema.py** — ADD `test_hitl_validator_rejects_three_flags_true`:
  all 3 HITL flags `True` raises `ValidationError`. **Req: RED — HITL con los 3 flags True.**
- [x] 2.5 **test_schema.py** — ADD `test_hitl_single_flag_true_is_valid`:
  `external_execution=True` alone is valid (no raise). **Req: Un solo flag HITL True es válido.**
- [x] 2.6 **test_tool_factory.py** (NEW file) — ADD `test_build_empty_list_returns_empty`:
  `ToolFactory(resolver).build([])` returns `[]`. FAILS: `ToolFactory` does not
  exist (ImportError). **Req: Lista vacía retorna lista vacía.**
- [x] 2.7 **test_tool_factory.py** — ADD `test_build_unknown_kind_raises_validation_error`:
  `build([{"kind": "bogus"}])` raises `ValidationError`. **Req: RED — kind desconocido produce ValidationError.**
- [x] 2.8 **test_tool_factory.py** — ADD `test_build_dispatches_builtin`:
  `build([{"kind": "builtin", "name": "calculator"}])` returns a `CalculatorTools`
  instance (mock the registry adapter or use real resolver). **Req: Dispatch builtin.**
- [x] 2.9 **test_tool_factory.py** — ADD `test_build_wraps_function_with_tool_flags`:
  `build([{"kind": "function", "path": "...", "requires_confirmation": True}])`
  returns a `Function` object with `requires_confirmation == True`. FAILS:
  `ToolFactory` missing. **Req: @tool wrapping aplica flags del config.**
- [x] 2.10 **test_tool_factory.py** — ADD `test_build_mcp_returns_unconnected`:
  `build([{"kind": "mcp", "transport": "stdio", "command": "uvx x"}])` returns
  `MCPTools` with `initialized == False`. **Req: SYNC ToolFactory — MCP retorna UNCONNECTED.**
- [x] 2.11 **test_agent_factory.py** — ADD `test_build_forwards_tools_when_resolver`:
  `AgentFactory.build(cfg_with_tools, resolver=resolver)` → `agent.tools` is
  non-empty (contains resolved instance). FAILS today: `build()` takes no
  `resolver` param (TypeError). **Req: AgentFactory wiring — resolver + tools.**
- [x] 2.12 **test_agent_factory.py** — ADD `test_build_without_resolver_keeps_tools_empty`:
  `AgentFactory.build(cfg_with_tools)` (no resolver) → `agent.tools == []`.
  Existing tests already cover this implicitly — this makes it explicit.
  **Req: AgentFactory sin resolver — tools=[] (backward compat).**

## Phase 3: GREEN — make tests pass (smallest correct change)

> Follow the design literal code exactly (SSOT for HOW). One file at a time,
  re-running the corresponding RED tests after each.

- [x] 3.1 **MODIFY `src/yaml_agno/tools/schema.py`** — Widen `CustomToolConfig`
  per design §schema.py MODIFY: add `name`, `description`, `strict` (if in
  design — verify), `requires_confirmation`, `requires_user_input`,
  `user_input_fields`, `external_execution`, `external_execution_silent`,
  `show_result`, `stop_after_tool_call`, `cache_results`, `cache_dir`,
  `cache_ttl`. Keep `extra="forbid"`. Add `model_validator(mode="after")`
  `_validate_hitl_mutual_exclusivity` (at most 1 of 3 HITL True). **Req: CustomToolConfig ensanchado + Validador HITL.**
- [x] 3.2 Run `python -m pytest tests/unit/tools/test_schema.py` → GREEN
  (tasks 2.1-2.5 pass). Existing schema tests still pass (2.6-2.12 of the
  shipped file).
- [x] 3.3 **CREATE `src/yaml_agno/tools/tool_factory.py`** per design §NEW
  tool_factory.py: `ToolFactory(resolver)` with `build(tool_entries)` +
  `_wrap_tool(raw_callable, config)`. Import `agno_tool` from
  `agno.tools.decorator`, `TypeAdapter` from pydantic, dispatch by `isinstance`
  over `ToolEntry` subtypes. `_wrap_tool` drops `None` flags, keeps `False`.
  **Req: ToolFactory.build orquestador SYNC + Dispatch por kind + @tool wrapping.**
- [x] 3.4 **MODIFY `src/yaml_agno/tools/__init__.py`** — Add
  `from yaml_agno.tools.tool_factory import ToolFactory` and `"ToolFactory"` to
  `__all__` (alphabetical, after `"ToolEntry"`). **Req implícita (re-export público).**
- [x] 3.5 Run `python -m pytest tests/unit/tools/test_tool_factory.py` → GREEN
  (tasks 2.6-2.10 pass).
- [x] 3.6 **MODIFY `src/yaml_agno/factories/agent_factory.py`** per design §
  MODIFY: change `build(cfg)` to `build(cfg, resolver: AgnoResolver | None =
  None)`. When `cfg.tools and resolver is not None`: build `ToolFactory(resolver)`,
  call `build(cfg.tools)`, forward result to `Agent(tools=...)`. Otherwise
  `tools=[]`. Pass `tools=tools or None` to Agent. **Req: AgentFactory.build gana resolver + El signature gana resolver opcional.**
- [x] 3.7 Run `python -m pytest tests/unit/factories/test_agent_factory.py` →
  GREEN (tasks 2.11-2.12 pass AND all existing 13 scenarios still pass).

## Phase 4: Verification gates

- [x] 4.1 `python -m pytest` → FULL suite green (zero regressions). **Req: todos los scenarios.**
- [x] 4.2 `ruff check .` → zero findings. **Scenario: Ruff sin findings.**
- [x] 4.3 `mypy src/yaml_agno` → zero errors (watch `list[Any]` return, `Any`
  flags dict, `TYPE_CHECKING` import for `AgnoResolver`). **Scenario: Mypy sin errores.**
- [x] 4.4 Cold import verification (pytest masks circular imports — TECH010
  lesson): `python -c "from yaml_agno.tools import ToolFactory"` AND
  `python -c "from yaml_agno.factories import AgentFactory"` AND
  `python -c "from yaml_agno.tools.tool_factory import ToolFactory"`. All must
  succeed without error. **Req implícita (no circular import).**
- [x] 4.5 **AgentConfig unchanged** — `git diff src/yaml_agno/models/config/
  agent_config.py` is EMPTY (Option B: `tools` stays opaque, no widening).
  **Req: `AgentConfig.tools` permanece opaco.**
- [x] 4.6 **GATE — decisions.yaml VQ**: verify implementation matches
  `.chats/decisions.yaml`:
  - TECH001: `AgentConfig.tools` is `list[dict]` NOT `list[ToolEntry]` — VQ.
  - CONT001: `ToolEntry` canonical union lives in `tools/schema.py`; `ToolConfig`
    deprecated alias intact — VQ.
  - TECH011: `@tool` returns `Function` (not callable); HITL mutual-exclusivity
    enforced at schema boundary — VQ.
  - PHIL004 (anti-Frankenstein): `ToolFactory` dispatches to Agno objects, does
    NOT reimplement tool execution — VQ.
  If any mismatch: STOP and reconcile. **Req implícita (code matches decisions SSOT).**
- [x] 4.7 DEFER boundary check: confirm NO hooks (`tool_hooks`, `pre_hook`,
  `post_hook`), NO cross-run caching, NO `asyncio.TaskGroup`, NO
  `tool_call_limit` forwarding leaked into slice C code. **Req: A5 DEFER.**

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 `feat(tools): widen CustomToolConfig with @tool flags and HITL validator`
  (Phase 3.1 — schema.py).
- [x] 5.2 `test(tools): add CustomToolConfig flag and HITL validator tests`
  (Phase 2.1-2.5 — test_schema.py additions).
- [x] 5.3 `feat(tools): add ToolFactory orchestrator with @tool wrapping`
  (Phase 3.3 + 3.4 — tool_factory.py + __init__.py).
- [x] 5.4 `test(tools): add ToolFactory dispatch and wrapping tests`
  (Phase 2.6-2.10 — test_tool_factory.py).
- [x] 5.5 `feat(factories): wire AgentFactory.build with optional resolver`
  (Phase 3.6 — agent_factory.py).
- [x] 5.6 `test(factories): add tools-forwarding scenario`
  (Phase 2.11-2.12 — test_agent_factory.py additions).

## TDD Compliance Matrix

| # | Requirement | RED task | GREEN task | Scenario |
|---|-------------|----------|------------|----------|
| 1 | ToolFactory.build SYNC orquestador | 2.6, 2.7 | 3.3 | Golden path mixto + empty + unknown kind |
| 2 | Dispatch por kind | 2.8, 2.9, 2.10 | 3.3 | builtin / function / mcp |
| 3 | @tool wrapping function kind | 2.9 | 3.3 | flags aplicados + None dropped |
| 4 | CustomToolConfig ensanchado | 2.1, 2.2 | 3.1 | flags aceptados + minimal válido |
| 5 | Validador HITL exclusividad | 2.3, 2.4, 2.5 | 3.1 | 2 True reject / 3 True reject / 1 True ok |
| 6 | AgentConfig.tools opaco (Option B) | 1.2 | 4.5 | AgentConfig sin cambios |
| 7 | AgentFactory.build gana resolver | 2.11, 2.12 | 3.6 | resolver forwards / None keeps [] |
| 8 | SYNC ToolFactory MCP UNCONNECTED | 2.10 | 3.3 | initialized == False |
| 9 | CustomToolConfig MODIFIED (prev minimal) | 2.1 | 3.1 | inspect fields present |
| 10 | AgentFactory.build MODIFIED (prev identity-only) | 2.11 | 3.6 | signature has resolver |
| 11 | extra="forbid" conservado | 2.1 (implicit) | 3.1 | rogue field still rejected |
| 12 | DEFER hooks/caching/concurrency | 4.7 | — | none leaked into slice C |

## Implementation Order

```
Phase 1 (baseline) → Phase 2.1-2.5 (RED schema) → Phase 3.1-3.2 (GREEN schema)
→ Phase 2.6-2.10 (RED factory) → Phase 3.3-3.5 (GREEN factory)
→ Phase 2.11-2.12 (RED agent_factory) → Phase 3.6-3.7 (GREEN agent_factory)
→ Phase 4 (gates) → Phase 5 (commits)
```

Schema first (it is the dependency for both the factory's `_wrap_tool` and the
ToolEntry union it reads), then the factory (consumes schema + existing
loaders/registry), then the agent_factory wiring (consumes ToolFactory). Each
GREEN step is gated by its matching RED step. Commits are granular per file.
