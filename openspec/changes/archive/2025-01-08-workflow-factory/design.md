---
change: workflow-factory
spec: SPEC_01
artifact: design
status: designed
artifact_store: hybrid
depends_on:
  - explore: engram project `doc.reca`, topic_key `sdd/workflow-factory/explore` (obs #1962 — verified 7-primitive matrix + CEL API)
  - source_spec: specs/SPEC_01_AGENT_FACTORY.md (read-only SSOT, slice #4 of 4)
  - shipped_pattern: src/yaml_agno/factories/agent_factory.py (AgentFactory.build @staticmethod — style template)
  - shipped_pattern: src/yaml_agno/factories/team_factory.py (TeamFactory.build + resolve-by-name — style template)
  - consumed_contract: src/yaml_agno/models/config/workflow_config.py (WorkflowConfig + StepConfig, 16 fields)
  - agno_source_cel: agno/workflow/cel.py:87-96 (is_cel_expression regex `^[a-zA-Z_][a-zA-Z0-9_]*$` + _CEL_INDICATORS)
  - agno_source_primitives: agno/workflow/{step,parallel,condition,router,loop,workflow}.py constructors (verified accept `str` for evaluator/selector/end_condition — compiled internally)
---

# Design: WorkflowFactory — SPEC_01 slice #4 (WorkflowConfig + agents/teams/callables dicts → agno.Workflow)

> **@ai-directive**: This document is the **technical HOW**. The behavioral SSOT
> is `sdd/workflow-factory/explore` (engram obs #1962 — verified against Agno
> source); the architectural SSOT is `specs/SPEC_01_AGENT_FACTORY.md` (read-only).
> This change delivers **slice #4 of 4** (the hardest). All discrepancies
> resolve in favor of the explore artifact's source-verified findings. The code
> shown here is **living documentation** — the `sdd-apply` change creates the
> `.py` files literally as specified here. Any divergence between this design
> and the shipped Agno source is a bug in this design, not a license to
> improvise.

## Technical Approach

**A recursive YAML→Agno translator that delegates CEL compilation to Agno.**
`WorkflowFactory.build(cfg: WorkflowConfig, agents, teams, callables=None)`
walks `cfg.steps` and, for each `StepConfig`, dispatches on `cfg.type` to one of
the 7 Agno workflow primitives (`Step`, `Parallel`, `Condition`, `Router`,
`Loop`, `Steps`, nested `Workflow`). The assembled list is passed to
`agno.Workflow(name=cfg.name, description=cfg.description, steps=[...])`.

The strategy rests on **four facts verified by reading Agno source** (not
assumed from docs):

1. **`Condition.evaluator`, `Router.selector`, and `Loop.end_condition` all
   accept a bare `str` and compile it internally.**
   - `condition.py:100-105` types `evaluator: Union[Callable, bool, str]`; the
     CEL branch lives in `_evaluate_condition` (`condition.py:395-404`) which
     calls `evaluate_cel_condition_evaluator(self.evaluator, step_input, ...)`.
   - `router.py:88-94` types `selector: Optional[Union[Callable, str]] = None`;
     the CEL branch lives in `_route_steps` (`router.py:569-581`).
   - `loop.py:76` types `end_condition: Optional[Union[Callable, str]] = None`;
     the CEL branch lives in `_evaluate_end_condition` (`loop.py:306-316`).
   **Implication**: the factory passes the YAML string through unchanged — it
   does NOT pre-compile, does NOT wrap, does NOT call `celpy` itself.
2. **`agno.workflow.cel.is_cel_expression(value: str) -> bool`** is the
   authoritative dotted-ref vs CEL discriminator (`cel.py:87-96`). It returns
   `False` for a simple identifier matching `^[a-zA-Z_][a-zA-Z0-9_]*$` (no dots,
   no operators) and `True` otherwise. The factory reuses this exact function
   rather than re-implementing the heuristic, aligning with Agno's own
   `Condition.from_dict` / `Router.from_dict` / `Loop.from_dict` deserialization
   paths (`condition.py:274`, `router.py:335`, `loop.py:268`).
3. **Router choices are looked up by `.name`.** `Router._prepare_steps`
   (`router.py:420-423`) builds `_step_name_map` from each choice's `.name`
   attribute, and `_resolve_selector_result` (`router.py:520-522`) resolves the
   CEL-returned string against that map. The CEL selector returns a **case key**
   (the value the user routes on). **Implication**: each `cases` entry must
   produce a Step whose `.name` equals the **case key**, NOT the referenced
   step-id.
4. **`Workflow.__init__(name, description, steps, ...)` takes `steps` as a list
   at construction** (`workflow.py:457-490`). No `add_step` method exists
   (confirmed by exploration). Session/db/model are all optional and deferred
   to `.run()` time.

The factory is **pure translation**: it reads validated config, looks up
references, and constructs Agno objects. No network, no LLM, no session.

## Architecture Decisions

### Decision A1: Pass CEL/expression strings through raw; do NOT pre-compile

**Choice**: The factory passes `cfg.condition`, `cfg.expression`, and
`cfg.end_condition` to `Condition(evaluator=...)`, `Router(selector=...)`, and
`Loop(end_condition=...)` as bare strings. Agno compiles them at evaluation time.

**Alternatives considered**:
- Pre-compile via `evaluate_cel_condition_evaluator` into a closure at build
  time. Rejected: Agno already does this lazily, and pre-compiling would
  duplicate Agno's context-building (`_build_step_input_context`,
  `_build_loop_step_output_context`) — leaking Agno internals into yaml-agno and
  creating a maintenance surface that breaks on Agno upgrades.
- Import `celpy` directly and compile. Rejected: violates the "reuse Agno's CEL
  integration" decision (see explore Q1). Agno already gates on
  `CEL_AVAILABLE` and raises clear errors; bypassing it loses those guards.

**Rationale**: Source-verified — all three primitives type-accept `str` and have
explicit `if isinstance(self.evaluator, str):` / `isinstance(self.selector, str):`
branches that call Agno's own `evaluate_cel_*` helpers. Passing the raw string
is the path Agno's own `from_dict` deserializers take.

### Decision A2: Reuse `is_cel_expression` to dispatch callable-ref vs CEL string

**Choice**: For the `function` field (executor references) and any string that
could be either a callable name or a CEL expression, the factory calls
`from agno.workflow.cel import is_cel_expression`. If it returns `False` (simple
identifier, no dots), the string is treated as a key into the `callables`
registry. If it returns `True`, the string is passed through to Agno as a CEL
expression.

**Alternatives considered**:
- The SPEC's originally-proposed regex `^[a-zA-Z_][a-zA-Z0-9_.]*$` (allows dots
  for dotted callable refs like `mymod.myfunc`). Rejected per explore Q1b: it
  would misclassify CEL dotted-access expressions like
  `session_state.retry_count` or
  `previous_step_outputs.research.contains("error")` as callable refs. Agno's
  own `is_cel_expression` is the authoritative inverse detector.

**Rationale**: Dotted callable refs are NOT supported in slice #4. Callables are
registered by simple name in the `callables` dict (mirroring Agno's
`registry.get_function(name)` pattern at `condition.py:280`, `router.py:341`,
`loop.py:272`). This keeps the dispatch identical to Agno's own deserialization
logic and avoids the dotted-ref misclassification risk.

### Decision A3: Router case Steps are named with the case KEY, not the step-id

**Choice**: For `cfg.cases: dict[str, str]` (mapping `{case_key: step_id}`),
the factory builds the referenced StepConfig and then **overrides its name** to
`case_key` when wrapping it for the Router's `choices` list.

**Alternatives considered**:
- Name the choice Step with its referenced step-id. Rejected: the CEL selector
  returns the case key (e.g. `"billing"` from
  `previous_step_outputs.classifier.contains("billing") ? "billing" : "support"`).
  `Router._step_name_map` is keyed by `.name`, so naming the Step with the
  step-id would make `_resolve_selector_result` fail to find the choice.

**Rationale**: Source-verified at `router.py:420-423` (`_step_name_map`) and
`router.py:520-522` (string lookup). The choice's `.name` IS the lookup key.
This is non-obvious and load-bearing — see `_build_router` in the literal code.

### Decision A4: Build a step-id→StepConfig index for if_true/if_false resolution

**Choice**: At the top of `build()`, the factory constructs
`_step_index: dict[str, StepConfig] = {s.step: s for s in cfg.steps}`. When
`_build_step` encounters a `Condition`, it looks up `cfg.if_true` and
`cfg.if_false` (step-id strings) in `_step_index`, recurses via `_build_step`
on the referenced StepConfig, and wraps the result into `steps=[...]` /
`else_steps=[...]`.

**Alternatives considered**:
- Defer resolution to the caller. Rejected: the caller passes only config + the
  three registries; it has no knowledge of intra-workflow step references. The
  factory is the natural owner of this translation.
- Require `if_true`/`if_false` to be inline step dicts instead of refs.
  Rejected: the `StepConfig` schema (SPEC_02) defines them as `str` step-id
  references, and `WorkflowConfig.validate_steps_integrity` already enforces
  they point to existing step ids (`workflow_config.py:128-131`). The factory
  trusts that validation.

**Rationale**: `WorkflowConfig` already guarantees referential integrity at the
schema boundary. The factory performs no re-validation — it just resolves.

### Decision A5: `execute` and `finally_` are validate-and-warn, not enforced

**Choice**: When `cfg.execute is False` or `cfg.finally_ is True` on a StepConfig
reached via `_build_step`, the factory emits a `logger.warning(...)` identifying
the step-id and the unsupported field, then builds the primitive normally
(included in the workflow). The step is NOT dropped, NOT reordered.

**Alternatives considered**:
- Drop steps with `execute=False`. Rejected: Agno has no "finally" semantics,
  and dropping a step silently would change workflow semantics without the
  user's consent. A loud warning + inclusion is the least-surprising behavior;
  the user can act on the log.
- Raise on `finally_=True`. Rejected: that would block workflows that use
  `finally_` purely as documentation. Warn-and-include matches the "deferred
  feature" pattern used by `AgentFactory` (silently accepts deferred slots).

**Rationale**: `execute` and `finally_` are yaml-agno's own syntax
(`workflow_config.py:44-49`) with no Agno equivalent. Slice #4 translates the
core primitive matrix; execution-control semantics are a future slice.

### Decision A6: Use stdlib `logging`, not a framework logger

**Choice**: `import logging; _logger = logging.getLogger("yaml_agno.factories.workflow_factory")`.
Warnings go through `_logger.warning(...)`.

**Alternatives considered**:
- Accept an optional `logger` parameter. Rejected: the shipped `AgentFactory`
  and `TeamFactory` take no logger and emit no warnings — introducing a logger
  param would break the static-`build()` signature symmetry across the 4
  factories. If a caller wants to capture warnings, stdlib `logging` is already
  globally configurable.
- Use Agno's `agno.utils.log.logger`. Rejected: yaml-agno is a separate package
  and should not depend on Agno's logging internals for its own diagnostics.

**Rationale**: Matches shipped factory style (no deps beyond Agno types) and
keeps the module self-contained.

## Data Flow

```
                    WorkflowFactory.build(cfg, agents, teams, callables)
                                          |
                                          v
                    +-----------------------------------------+
                    | _step_index = {s.step: s for s in cfg.steps}
                    +-----------------------------------------+
                                          |
                                          v
                    +-----------------------------------------+
                    | for each cfg.steps[i]:                  |
                    |   primitive = _build_step(cfg.steps[i], |
                    |                              agents,    |
                    |                              teams,    |
                    |                              callables,|
                    |                              _step_index)
                    +-----------------------------------------+
                                          |
                          dispatch on cfg.type:
                                          |
          +---------+---------+-----------+-----------+----------+
          |         |         |           |           |          |
          v         v         v           v           v          v
        Step    Parallel  Condition    Router       Loop      nested
       (agent/   (*built   (evaluator  (selector    (end_     Workflow
        team/    steps,    = cfg.cond  = cfg.expr   cond      (recursive
        fn/      name=)    str,        str,         str,      build)
        wf)                steps/      choices      max_iter,
                           else_steps  named by     steps)
                           from idx)  case KEY)
          |         |         |           |           |          |
          +---------+---------+-----------+-----------+----------+
                                          |
                                          v
                    agno.Workflow(name=cfg.name,
                                  description=cfg.description,
                                  steps=[primitive, ...])
```

**Lookup registries** (all supplied by caller, all optional except as executor
sources require):

```
agents:     dict[str, agno.Agent]     -- keyed by AgentConfig.name
teams:      dict[str, agno.Team]      -- keyed by TeamConfig.name
callables:  dict[str, Callable]       -- keyed by simple name (no dots)
_step_index: dict[str, StepConfig]    -- built internally, keyed by cfg.step
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/workflow_factory.py` | Create | `WorkflowFactory.build()` + private `_build_step()` dispatcher + `_resolve_callable_or_cel()` helper. Translates the 7-primitive matrix; reuses `is_cel_expression`; warns on execute/finally_. |
| `src/yaml_agno/factories/__init__.py` | Modify | Add `WorkflowFactory` to imports + `__all__`. |

No other files change. `WorkflowConfig` / `StepConfig` are consumed read-only
(verified 16-field schema in
`src/yaml_agno/models/config/workflow_config.py`).

## Interfaces / Contracts

### `WorkflowFactory.build` (public, static)

```python
@staticmethod
def build(
    cfg: WorkflowConfig,
    agents: dict[str, Agent],
    teams: dict[str, Team],
    callables: dict[str, Callable[..., Any]] | None = None,
) -> Workflow: ...
```

- `cfg`: validated `WorkflowConfig` (step-ids unique, branch refs valid —
  guaranteed by `WorkflowConfig.validate_steps_integrity`).
- `agents`, `teams`: pre-built registries (produced by `AgentFactory.build` /
  `TeamFactory.build`). Factory does NOT instantiate agents/teams.
- `callables`: optional registry of executor functions, keyed by simple name.
  `None` is equivalent to `{}` — any `function` ref will then raise `KeyError`.
- Returns: a constructed `agno.Workflow`. Per `workflow.py:457-490`, construction
  is pure assignment — no network, no session, no db.

### `_build_step` (private, recursive)

```python
@staticmethod
def _build_step(
    step_cfg: StepConfig,
    agents: dict[str, Agent],
    teams: dict[str, Team],
    callables: dict[str, Callable[..., Any]],
    step_index: dict[str, StepConfig],
) -> Step | Parallel | Condition | Router | Loop | Workflow: ...
```

Dispatches on `step_cfg.type` (`agno.workflow.types.StepType`). Recurses for
nested `steps` (Parallel), `if_true`/`if_false` (Condition), `cases` (Router),
and nested `steps` (Loop).

### `_resolve_callable_or_cel` (private)

```python
@staticmethod
def _resolve_callable_or_cel(
    value: str,
    callables: dict[str, Callable[..., Any]],
) -> Callable[..., Any] | str: ...
```

Returns the callable from `callables[value]` if `is_cel_expression(value)` is
`False`; otherwise returns the string unchanged (Agno compiles it).

## Literal Code

### `src/yaml_agno/factories/workflow_factory.py`

```python
"""WorkflowFactory — builds a native ``agno.Workflow`` from a
``WorkflowConfig`` plus dicts of pre-built agents, teams, and callables.

This is slice #4 of SPEC_01 (4-slice factory chain) and the hardest slice: it
translates the 7-primitive YAML matrix (Step/Steps/Parallel/Condition/Router/
Loop/nested-Workflow, discriminated by ``StepConfig.type``) into the
corresponding native ``agno.workflow`` constructs.

Translation strategy (source-verified against Agno 2.6.22 — see
``sdd/workflow-factory/explore`` engram obs #1962):

    +--------------+-------------------------------------------+----------+
    | cfg.type     | Agno primitive                            | Notes    |
    +--------------+-------------------------------------------+----------+
    | Step         | Step(name, agent | team | executor |      | exactly  |
    |              |            workflow, description)         | 1 source |
    | Steps        | Steps(name, steps=[build...])             | pipeline |
    | Parallel     | Parallel(*[build...], name)               | variadic |
    | Condition    | Condition(evaluator=cfg.condition str,    | CEL/cbbl |
    |              |   steps=[build(if_true ref)],             |          |
    |              |   else_steps=[build(if_false ref)], name) |          |
    | Router       | Router(selector=cfg.expression str,       | choices  |
    |              |   choices=[Step(name=case_key, ...)],     | named by |
    |              |   name)                                   | case key |
    | Loop         | Loop(steps=[build...],                    |          |
    |              |   max_iterations=cfg.max_iterations or 3,  |          |
    |              |   end_condition=cfg.end_condition str)    |          |
    +--------------+-------------------------------------------+----------+

Assembly: ``Workflow(name=cfg.name, description=cfg.description, steps=[...])``.

CEL handling (HYBRID via Agno native): ``cfg.condition``, ``cfg.expression``,
and ``cfg.end_condition`` are passed to the Agno constructors as bare strings.
Agno compiles them internally — see ``condition.py:395-404``,
``router.py:569-581``, ``loop.py:306-316``. The factory does NOT import
``celpy`` and does NOT pre-compile. ``agno.workflow.cel.is_cel_expression`` is
reused to distinguish simple callable refs (registry lookup) from CEL
expressions (pass-through), matching Agno's own ``from_dict`` deserializers.

Deferred (validate-and-warn) features:
    - ``StepConfig.execute`` (yaml-agno own; no Agno equivalent) — if ``False``,
      a warning is logged and the step is still built.
    - ``StepConfig.finally_`` (yaml-agno own; no Agno equivalent) — if ``True``,
      a warning is logged and the step is still built.
    Slice #4 does NOT drop or reorder steps based on these flags.

Contract:
    - ``WorkflowConfig`` is already Pydantic-validated (step-id uniqueness,
      branch-ref integrity). This factory performs NO re-validation.
    - ``agents`` / ``teams`` / ``callables`` are supplied pre-built by the
      caller (runtime loader). The factory does NOT instantiate them.
    - Construction is pure assignment; no network, no LLM, no session occurs
      until ``Workflow.run()`` / ``arun()`` is invoked.

@ai-directive: SSOT is ``sdd/workflow-factory/explore`` (engram obs #1962) and
``specs/SPEC_01_AGENT_FACTORY.md`` (slice #4 of 4). Discrepancies resolve in
their favor. This module consumes SPEC_02 (WorkflowConfig + StepConfig)
read-only.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Union

from agno.agent import Agent
from agno.team.team import Team
from agno.workflow.condition import Condition
from agno.workflow.loop import Loop
from agno.workflow.parallel import Parallel
from agno.workflow.router import Router
from agno.workflow.step import Step
from agno.workflow.steps import Steps
from agno.workflow.types import StepType
from agno.workflow.workflow import Workflow
from agno.workflow.cel import is_cel_expression

from yaml_agno.models.config.workflow_config import StepConfig, WorkflowConfig

__all__ = ["WorkflowFactory"]

_logger = logging.getLogger("yaml_agno.factories.workflow_factory")

# Union of all workflow constructs the factory can return from _build_step.
# Kept as a type alias for readability; mypy sees it as the broad union.
_BuiltStep = Union[Step, Steps, Parallel, Condition, Router, Loop, Workflow]


class WorkflowFactory:
    """Builds ``agno.Workflow`` instances from a validated ``WorkflowConfig``
    and dicts of pre-built agents, teams, and callables.

    Slice #4 scope (the 7-primitive matrix):

        +--------------------------+------------------------------------+
        | StepConfig field         | agno primitive mapping             |
        +--------------------------+------------------------------------+
        | type=Step + agent        | Step(agent=agents[cfg.agent])      |
        | type=Step + team         | Step(team=teams[cfg.team])         |
        | type=Step + function     | Step(executor=callables[fn])       |
        | type=Step + workflow     | Step(workflow=<nested build>)      |
        | type=Parallel + steps    | Parallel(*[build...], name=step)   |
        | type=Condition +         | Condition(evaluator=condition,     |
        |   condition/if_true/...  |   steps=[build(if_true)],          |
        |                          |   else_steps=[build(if_false)])    |
        | type=Router +            | Router(selector=expression,        |
        |   expression/cases       |   choices=[Step(name=key, ...)],   |
        |                          |   name=step)                       |
        | type=Loop + steps/       | Loop(steps=[build...],             |
        |   end_condition/         |   max_iterations=max_iter or 3,    |
        |   max_iterations         |   end_condition=end_cond)          |
        +--------------------------+------------------------------------+

    CEL handling: ``cfg.condition`` / ``cfg.expression`` / ``cfg.end_condition``
    are passed as bare strings — Agno compiles them internally. The factory
    reuses ``agno.workflow.cel.is_cel_expression`` only to decide whether a
    ``function`` ref is a simple callable name (registry lookup) or a CEL
    expression (pass-through).

    Branch resolution: ``cfg.if_true`` / ``cfg.if_false`` / ``cfg.cases``
    values are step-id strings. The factory builds a ``step-id -> StepConfig``
    index at the top of ``build()`` and recurses via ``_build_step`` to resolve
    them. Integrity is already guaranteed by
    ``WorkflowConfig.validate_steps_integrity``.

    Deferred (validate-and-warn): ``execute=False`` and ``finally_=True`` log a
    warning and the step is still built — slice #4 does not enforce them.

    This class exposes a static ``build()`` method; it holds no state and is
    not instantiated.
    """

    @staticmethod
    def build(
        cfg: WorkflowConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]] | None = None,
    ) -> Workflow:
        """Build a native ``agno.Workflow`` from a validated ``WorkflowConfig``.

        Walks ``cfg.steps`` and dispatches each ``StepConfig`` to
        ``_build_step`` based on ``cfg.type``. Assembles the resulting
        primitives into ``agno.Workflow(name=cfg.name, description=cfg.description,
        steps=[...])``.

        Args:
            cfg: A validated ``WorkflowConfig`` (SPEC_02). Step-id uniqueness
                and branch-ref integrity are already enforced by
                ``WorkflowConfig.validate_steps_integrity``; this factory
                performs no re-validation.
            agents: A mapping from ``AgentConfig.name`` to a pre-built
                ``agno.Agent`` (produced by ``AgentFactory.build()``, slice #1).
                The factory does NOT instantiate agents.
            teams: A mapping from ``TeamConfig.name`` to a pre-built
                ``agno.Team`` (produced by ``TeamFactory.build()``, slice #3).
                The factory does NOT instantiate teams.
            callables: An optional mapping from simple name (no dots) to a
                callable executor. ``None`` is treated as an empty dict — any
                ``function`` ref on a Step-type config will then raise
                ``KeyError``.

        Returns:
            A constructed ``agno.Workflow``. Per ``agno/workflow/workflow.py:
            457-490``, construction is pure assignment — no network call, no
            session, no db is created until ``.run()`` / ``.arun()``.

        Raises:
            KeyError: If a ``StepConfig`` references an ``agent``, ``team``, or
                ``function`` name absent from the corresponding registry. Raised
                before ``agno.Workflow`` is constructed, so no partial Workflow
                is ever produced.
            ValueError: If a ``StepConfig`` has no executor source for a
                Step-type step (i.e. none of ``agent``/``team``/``function``/
                ``workflow`` is set). Agno's ``Step._validate_executor_config``
                would reject this too, but the factory surfaces a clearer
                message naming the offending step-id.
        """
        resolved_callables: dict[str, Callable[..., Any]] = callables or {}

        # step-id -> StepConfig index for if_true/if_false/cases resolution.
        # Integrity is already guaranteed by WorkflowConfig.validate_steps_integrity.
        step_index: dict[str, StepConfig] = {s.step: s for s in cfg.steps}

        built_steps: list[Any] = []
        for step_cfg in cfg.steps:
            built_steps.append(
                WorkflowFactory._build_step(
                    step_cfg=step_cfg,
                    agents=agents,
                    teams=teams,
                    callables=resolved_callables,
                    step_index=step_index,
                )
            )

        return Workflow(
            name=cfg.name,
            description=cfg.description,
            steps=built_steps,
        )

    @staticmethod
    def _build_step(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_index: dict[str, StepConfig],
    ) -> _BuiltStep:
        """Dispatch a single ``StepConfig`` to its Agno primitive.

        Dispatches on ``step_cfg.type`` (``agno.workflow.types.StepType``):

            - ``Step``    -> ``Step(name, <one executor>, description)``
            - ``Steps``   -> ``Steps(name, steps=[build...])``
            - ``Parallel``-> ``Parallel(*[build...], name)``
            - ``Condition``-> ``Condition(evaluator=cfg.condition,
                                steps=[build(cfg.if_true)],
                                else_steps=[build(cfg.if_false)], name)``
            - ``Router``  -> ``Router(selector=cfg.expression,
                                choices=[Step(name=key, ...) for key, sid
                                in cfg.cases.items()], name)``
            - ``Loop``    -> ``Loop(steps=[build...],
                                max_iterations=cfg.max_iterations or 3,
                                end_condition=cfg.end_condition, name)``
            - ``Workflow``-> nested ``WorkflowFactory.build`` on the referenced
                              WorkflowConfig (deferred — slice #4 raises
                              NotImplementedError for nested workflow executor
                              refs; the matrix slot is documented).

        Emits ``_logger.warning`` for ``execute=False`` and ``finally_=True``
        (validate-and-warn; step is still built).

        Args:
            step_cfg: The ``StepConfig`` to translate. Its ``type`` selects the
                branch; its type-specific fields (``steps``, ``condition``,
                ``if_true``/``if_false``, ``expression``/``cases``,
                ``end_condition``/``max_iterations``) populate the primitive.
            agents: Pre-built agent registry (passed through to Step building).
            teams: Pre-built team registry (passed through to Step building).
            callables: Callable executor registry (passed through to Step
                building and to ``_resolve_callable_or_cel``).
            step_index: ``step-id -> StepConfig`` map for resolving
                ``if_true`` / ``if_false`` / ``cases`` references.

        Returns:
            The constructed Agno workflow primitive.

        Raises:
            KeyError: If an executor reference (agent/team/function) is absent
                from its registry.
            ValueError: If a Step-type config has no executor source.
            NotImplementedError: If ``step_cfg.type == StepType.WORKFLOW``
                (nested workflow executor — deferred beyond slice #4).
        """
        # --- Deferred features: validate-and-warn (do NOT drop the step) ---
        if not step_cfg.execute:
            _logger.warning(
                "Step %r has execute=False; Agno has no skip-on-build "
                "semantic. The step WILL be included in the workflow. "
                "Slice #4 does not enforce execute=False.",
                step_cfg.step,
            )
        if step_cfg.finally_:
            _logger.warning(
                "Step %r has finally_=True; Agno has no cleanup-on-exit "
                "semantic at the Step level. The step will run in normal "
                "order. Slice #4 does not enforce finally_.",
                step_cfg.step,
            )

        t = step_cfg.type

        # --- Step (4 executor sources; exactly one required) ---
        if t == StepType.STEP or t == StepType.FUNCTION:
            return WorkflowFactory._build_step_executor(
                step_cfg=step_cfg,
                agents=agents,
                teams=teams,
                callables=callables,
            )

        # --- Steps (sequential pipeline) ---
        if t == StepType.STEPS:
            nested = [
                WorkflowFactory._build_step(
                    step_cfg=StepConfig(**raw),
                    agents=agents,
                    teams=teams,
                    callables=callables,
                    step_index=step_index,
                )
                for raw in step_cfg.steps
            ]
            return Steps(name=step_cfg.step, description=step_cfg.description, steps=nested)

        # --- Parallel (variadic) ---
        if t == StepType.PARALLEL:
            built = [
                WorkflowFactory._build_step(
                    step_cfg=StepConfig(**raw),
                    agents=agents,
                    teams=teams,
                    callables=callables,
                    step_index=step_index,
                )
                for raw in step_cfg.steps
            ]
            return Parallel(*built, name=step_cfg.step, description=step_cfg.description)

        # --- Condition (CEL or callable evaluator + two branches) ---
        if t == StepType.CONDITION:
            if_steps: list[Any] = []
            if step_cfg.if_true and step_cfg.if_true in step_index:
                if_steps.append(
                    WorkflowFactory._build_step(
                        step_cfg=step_index[step_cfg.if_true],
                        agents=agents,
                        teams=teams,
                        callables=callables,
                        step_index=step_index,
                    )
                )
            else_steps: list[Any] | None = None
            if step_cfg.if_false and step_cfg.if_false in step_index:
                else_steps = [
                    WorkflowFactory._build_step(
                        step_cfg=step_index[step_cfg.if_false],
                        agents=agents,
                        teams=teams,
                        callables=callables,
                        step_index=step_index,
                    )
                ]
            evaluator = step_cfg.condition if step_cfg.condition is not None else True
            return Condition(
                steps=if_steps,
                evaluator=evaluator,
                else_steps=else_steps,
                name=step_cfg.step,
                description=step_cfg.description,
            )

        # --- Router (CEL selector + choices named by case key) ---
        if t == StepType.ROUTER:
            choices: list[Any] = []
            for case_key, step_id in step_cfg.cases.items():
                if step_id not in step_index:
                    # Integrity is guaranteed by WorkflowConfig; defensive only.
                    continue
                referenced = step_index[step_id]
                # CRITICAL (A3): the choice Step MUST be named with the case
                # KEY (what the CEL selector returns), not the referenced
                # step-id. Router._step_name_map (router.py:420-423) keys on
                # .name, and _resolve_selector_result (router.py:520-522) looks
                # up the selector's returned string there.
                built_choice = WorkflowFactory._build_step(
                    step_cfg=referenced,
                    agents=agents,
                    teams=teams,
                    callables=callables,
                    step_index=step_index,
                )
                # Override the .name to the case key so the Router can resolve
                # the selector's returned string against _step_name_map.
                built_choice.name = case_key  # type: ignore[union-attr]
                choices.append(built_choice)
            return Router(
                choices=choices,
                selector=step_cfg.expression,
                name=step_cfg.step,
                description=step_cfg.description,
            )

        # --- Loop (steps + max_iterations + optional end_condition) ---
        if t == StepType.LOOP:
            loop_steps = [
                WorkflowFactory._build_step(
                    step_cfg=StepConfig(**raw),
                    agents=agents,
                    teams=teams,
                    callables=callables,
                    step_index=step_index,
                )
                for raw in step_cfg.steps
            ]
            return Loop(
                steps=loop_steps,
                name=step_cfg.step,
                description=step_cfg.description,
                max_iterations=step_cfg.max_iterations if step_cfg.max_iterations is not None else 3,
                end_condition=step_cfg.end_condition,
            )

        # --- Nested workflow executor (deferred beyond slice #4) ---
        if t == StepType.WORKFLOW:
            raise NotImplementedError(
                f"Step {step_cfg.step!r} has type=Workflow (nested workflow "
                "executor). Nested-workflow resolution is not implemented in "
                "slice #4; it requires a registry of pre-built Workflow "
                "objects or recursive WorkflowConfig resolution. See SPEC_01 "
                "slice #4 follow-up."
            )

        # Unreachable: StepType is a closed str-enum and all 8 members are
        # handled above (FUNCTION folds into STEP). Defensive guard for safety.
        raise ValueError(
            f"Unsupported step type {t!r} on step {step_cfg.step!r}. "
            "Supported types: Step, Function, Steps, Parallel, Condition, "
            "Router, Loop."
        )

    @staticmethod
    def _build_step_executor(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
    ) -> Step:
        """Build an ``agno.Step`` from the first available executor source.

        Resolves exactly one of ``agent`` / ``team`` / ``function`` /
        ``workflow`` (checked in that order) and constructs
        ``Step(name=step_cfg.step, <executor>, description=...)``.

        Args:
            step_cfg: A ``StepConfig`` with ``type`` in (Step, Function).
            agents: Pre-built agent registry.
            teams: Pre-built team registry.
            callables: Callable executor registry.

        Returns:
            A constructed ``agno.Step`` with exactly one executor slot set.

        Raises:
            ValueError: If none of agent/team/function/workflow is set.
            KeyError: If a referenced name is absent from its registry.
        """
        if step_cfg.agent is not None:
            if step_cfg.agent not in agents:
                raise KeyError(
                    f"Agent not found: {step_cfg.agent!r} (step {step_cfg.step!r}). "
                    "Check the 'agents:' section of your YAML."
                )
            return Step(
                name=step_cfg.step,
                agent=agents[step_cfg.agent],
                description=step_cfg.description,
            )

        if step_cfg.team is not None:
            if step_cfg.team not in teams:
                raise KeyError(
                    f"Team not found: {step_cfg.team!r} (step {step_cfg.step!r}). "
                    "Check the 'teams:' section of your YAML."
                )
            return Step(
                name=step_cfg.step,
                team=teams[step_cfg.team],
                description=step_cfg.description,
            )

        if step_cfg.function is not None:
            # Reuse Agno's is_cel_expression: simple identifier -> callable
            # lookup; CEL-looking string -> pass through (Agno compiles).
            executor = WorkflowFactory._resolve_callable_or_cel(
                step_cfg.function, callables
            )
            # If _resolve_callable_or_cel returned a string (CEL expression),
            # Agno's Step does not accept a CEL string for `executor` — that
            # path is for Condition/Router/Loop. For a Step executor we require
            # an actual callable; a CEL string here is a config error.
            if isinstance(executor, str):
                raise ValueError(
                    f"Step {step_cfg.step!r} has function={step_cfg.function!r} "
                    "which looks like a CEL expression, but Step.executor "
                    "requires a callable. Register the callable under a simple "
                    "name (no dots/operators) or use a Condition/Router/Loop."
                )
            return Step(
                name=step_cfg.step,
                executor=executor,
                description=step_cfg.description,
            )

        if step_cfg.workflow is not None:
            raise NotImplementedError(
                f"Step {step_cfg.step!r} references workflow "
                f"{step_cfg.workflow!r} as an executor. Nested-workflow "
                "resolution is not implemented in slice #4."
            )

        raise ValueError(
            f"Step {step_cfg.step!r} (type=Step) has no executor source: "
            "set exactly one of 'agent', 'team', 'function', or 'workflow'."
        )

    @staticmethod
    def _resolve_callable_or_cel(
        value: str,
        callables: dict[str, Callable[..., Any]],
    ) -> Callable[..., Any] | str:
        """Resolve a string to a callable or pass it through as a CEL string.

        Uses ``agno.workflow.cel.is_cel_expression`` (the authoritative Agno
        discriminator, ``cel.py:87-96``) to decide:

            - Returns ``False`` (simple identifier, no dots/operators):
              look up ``value`` in ``callables``. Raises ``KeyError`` if absent.
            - Returns ``True`` (CEL-looking): return ``value`` unchanged; the
              caller decides whether a CEL string is acceptable for its slot.

        This mirrors Agno's own ``Condition.from_dict`` / ``Router.from_dict``
        / ``Loop.from_dict`` deserialization logic.

        Args:
            value: The string to resolve.
            callables: The callable registry.

        Returns:
            The resolved callable if ``value`` is a simple identifier, or the
            string unchanged if it looks like a CEL expression.

        Raises:
            KeyError: If ``value`` is a simple identifier not present in
                ``callables``.
        """
        if is_cel_expression(value):
            # CEL expression — pass through; Agno compiles it.
            return value
        if value not in callables:
            raise KeyError(
                f"Callable not found: {value!r}. Register it under this name "
                "in the callables registry passed to WorkflowFactory.build()."
            )
        return callables[value]
```

### `src/yaml_agno/factories/__init__.py`

```python
"""Factories package — builds native Agno objects from validated configs.

Re-exports the public factory classes so callers can do
``from yaml_agno.factories import AgentFactory`` or
``from yaml_agno.factories import WorkflowFactory``.
"""

from yaml_agno.factories.agent_factory import AgentFactory
from yaml_agno.factories.team_factory import TeamFactory
from yaml_agno.factories.workflow_factory import WorkflowFactory

__all__ = ["AgentFactory", "TeamFactory", "WorkflowFactory"]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `_build_step_executor` — all 4 executor sources (agent/team/function/workflow-deferred) | Pass a `StepConfig` + minimal registries; assert the returned `Step` has the right slot set and `name`/`description` match. Assert `KeyError` for missing refs, `ValueError` for no-source, `NotImplementedError` for nested workflow. |
| Unit | `_build_step` Step/Steps/Parallel branches | Build a `StepConfig(type=Parallel, steps=[{...}, {...}])` from raw dicts; assert the result is a `Parallel` whose `.steps` has length 2 and whose `.name == cfg.step`. |
| Unit | `_build_step` Condition branch — CEL evaluator + both branches | Pass `condition='input.contains("x")'`, `if_true='stepA'`, `if_false='stepB'` with a step-index containing both; assert `Condition.evaluator == cfg.condition` (string passthrough), `len(steps) == 1`, `else_steps` is a 1-element list. |
| Unit | `_build_step` Router branch — choices named by case KEY | Pass `cases={'billing': 'stepA', 'support': 'stepB'}`, `expression='additional_data.route'`; assert `Router.choices[0].name == 'billing'` and `Router.choices[1].name == 'support'` (NOT the step-ids). This is the A3 invariant. |
| Unit | `_build_step` Loop branch — defaults + CEL passthrough | Pass `type=Loop` with no `max_iterations`; assert `Loop.max_iterations == 3` (Agno default). Pass `end_condition='all_success'`; assert `Loop.end_condition == 'all_success'` (string passthrough). |
| Unit | `_resolve_callable_or_cel` dispatch | `is_cel_expression('my_func')` → False → registry lookup. `is_cel_expression('a.b.c')` → True → pass-through. Assert `KeyError` for missing simple identifier. |
| Unit | `build` end-to-end assembly | A 3-step `WorkflowConfig` (agent step + parallel + condition); assert the returned `Workflow.steps` has length 3, `Workflow.name == cfg.name`, `Workflow.description == cfg.description`. |
| Unit | execute/finally_ validate-and-warn | Pass `execute=False` and `finally_=True` on a StepConfig; assert `_logger.warning` was called (use `caplog`) AND the step is still in `Workflow.steps`. |
| Integration | Full primitive matrix via a representative YAML | Parse a YAML exercising all 7 primitives (incl. nested Parallel inside Loop); assert the resulting `Workflow` structure matches a hand-built equivalent. (Does NOT call `.run()` — construction-only, per factory contract.) |
| E2E | Not in slice #4 | Deferred — running a workflow requires models/LLMs and is owned by a runtime integration spec. |

## TDD Approach

Strict TDD mode is active for this project (per `sdd-init`). The TDD cycle for
slice #4:

1. **Red**: Write a failing test for ONE row of the primitive matrix (e.g.
   `_build_step_executor` agent branch). Run `pytest` — it fails (module +
   class don't exist yet).
2. **Green**: Create `workflow_factory.py` with just enough to pass that test
   (the `_build_step_executor` method + minimal `build` shell). Run `pytest` —
   it passes.
3. **Refactor**: Pull shared lookup logic into helpers; keep tests green.
4. Repeat for each matrix row: Steps, Parallel, Condition (CEL + branches),
   Router (case-key naming), Loop (defaults + CEL), `_resolve_callable_or_cel`,
   execute/finally_ warnings, end-to-end `build`.

**Test isolation**: all unit tests construct `StepConfig` / `WorkflowConfig`
directly (no YAML parsing, no file I/O). Registries are plain dicts of stubs
or real `Agent`/`Team` instances built with no model (construction-only). No
test calls `Workflow.run()` — that would require an LLM and belongs to E2E.

## Verification

Against the explore artifact (obs #1962) and the 4 KEY DESIGN QUESTIONS:

1. **CEL pass-through vs pre-compile**: PASS-THROUGH. Verified at
   `condition.py:395-404`, `router.py:569-581`, `loop.py:306-316` — all three
   primitives type-accept `str` and call `evaluate_cel_*` internally. The
   factory passes raw strings. (Decision A1.)
2. **if_true/if_false resolution**: step-id→StepConfig index built at top of
   `build()`, recursed via `_build_step`. Integrity guaranteed by
   `WorkflowConfig.validate_steps_integrity`. (Decision A4.)
3. **Router choices naming**: each case's built Step is renamed to the case KEY
   (A3). Verified at `router.py:420-423` (`_step_name_map` keys on `.name`)
   and `router.py:520-522` (selector string lookup). Non-obvious and
   load-bearing — documented inline in `_build_step`.
4. **execute/finally_**: validate-and-warn via stdlib `logging`. Steps are
   still built (not dropped). (Decisions A5/A6.)

## Rollback

This change adds 2 files (1 new, 1 modified) and touches nothing else. Rollback:

1. Revert `src/yaml_agno/factories/__init__.py` to remove the `WorkflowFactory`
   import + `__all__` entry.
2. Delete `src/yaml_agno/factories/workflow_factory.py`.

No data migration, no config flags, no runtime state. The `WorkflowConfig` /
`StepConfig` schemas are unchanged (consumed read-only). A rollback restores
the codebase to the state where workflows cannot be built from YAML — agents
and teams factories remain fully functional (slices #1 and #3 are independent).

## Open Questions

- [ ] Nested workflow executor (`StepType.WORKFLOW` with `cfg.workflow` ref):
      deferred beyond slice #4 with `NotImplementedError`. Requires either a
      pre-built `workflows` registry (analogous to `agents`/`teams`) or
      recursive `WorkflowConfig` resolution. Tracked as a follow-up.
- [ ] Per-Step `human_review` dict (opaque in `StepConfig`): NOT forwarded in
      slice #4. SPEC_29 owns HITL resolution. The factory accepts it silently
      (it is a valid `StepConfig` field) and does not warn.
