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
    | Condition    | Condition(evaluator=<resolved>,           | CEL/cbl  |
    |              |   steps=[build(if_true ref)],             |          |
    |              |   else_steps=[build(if_false ref)], name) |          |
    | Router       | Router(selector=<resolved>,               | choices  |
    |              |   choices=[Step(name=case_key, ...)],     | named by |
    |              |   name)                                   | case key |
    | Loop         | Loop(steps=[build...],                    |          |
    |              |   max_iterations=cfg.max_iterations or 3,  |          |
    |              |   end_condition=<resolved>, name)         |          |
    +--------------+-------------------------------------------+----------+

Assembly: ``Workflow(name=cfg.name, description=cfg.description, steps=[...])``.

HYBRID CEL/CALLABLE RESOLUTION (applied in ALL FOUR expression branches):
``_resolve_callable_or_cel`` is invoked for ``function`` (Step executor),
``condition`` (Condition.evaluator), ``expression`` (Router.selector), and
``end_condition`` (Loop.end_condition). It uses ``is_cel_expression`` to decide:
simple identifier (no dots/operators) -> callable ref resolved from the
``callables`` registry (raises ``ValueError`` if absent); otherwise the string is
CEL and is passed raw to the Agno constructor (Agno compiles it internally).

.. note::

    Open Item #1 (tasks.md): the design's literal code only applied
    ``_resolve_callable_or_cel`` in the ``function`` branch. That is WRONG per
    spec: a simple identifier like ``"check_threshold"`` is NOT a CEL expression
    (``is_cel_expression`` returns False) and Agno does NOT resolve identifiers
    to callables. The apply phase reconciles this by applying the resolver in
    all four branches. Tests 2.6/2.8/2.10 assert this behavior.

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
read-only. The design literal (``design.md``) is OVERRIDDEN on Open Item #1 —
see the note above.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from agno.agent import Agent
from agno.team.team import Team
from agno.workflow.cel import is_cel_expression
from agno.workflow.condition import Condition
from agno.workflow.loop import Loop
from agno.workflow.parallel import Parallel
from agno.workflow.router import Router
from agno.workflow.step import Step
from agno.workflow.steps import Steps
from agno.workflow.types import StepType
from agno.workflow.workflow import Workflow

from yaml_agno.models.config.workflow_config import StepConfig, WorkflowConfig
from yaml_agno.workflows.step_executor import StepExecutor

__all__ = ["WorkflowFactory"]

_logger = logging.getLogger("yaml_agno.factories.workflow_factory")

# Union of all workflow constructs the factory can return from _build_step.
# Kept as a type alias for readability; mypy sees it as the broad union.
_BuiltStep = Step | Steps | Parallel | Condition | Router | Loop | Workflow


class WorkflowFactory:
    """Builds ``agno.Workflow`` instances from a validated ``WorkflowConfig``
    and dicts of pre-built agents, teams, and callables.

    Slice #4 scope (the 7-primitive matrix):

        +--------------------------+------------------------------------+
        | StepConfig field         | agno primitive mapping             |
        +--------------------------+------------------------------------+
        | type=Step + agent        | Step(agent=agents[cfg.agent])      |
        | type=Step + team         | Step(team=teams[cfg.team])         |
        | type=Step + function     | Step(executor=<resolved callable>) |
        | type=Step + workflow     | NotImplementedError (deferred)     |
        | type=Parallel + steps    | Parallel(*[build...], name=step)   |
        | type=Condition +         | Condition(evaluator=<resolved>,    |
        |   condition/if_true/...  |   steps=[build(if_true)],          |
        |                          |   else_steps=[build(if_false)])    |
        | type=Router +            | Router(selector=<resolved>,        |
        |   expression/cases       |   choices=[Step(name=key, ...)],   |
        |                          |   name=step)                       |
        | type=Loop + steps/       | Loop(steps=[build...],             |
        |   end_condition/         |   max_iterations=max_iter or 3,    |
        |   max_iterations         |   end_condition=<resolved>)        |
        +--------------------------+------------------------------------+

    Hybrid CEL/callable resolution (Open Item #1): ``_resolve_callable_or_cel``
    is applied in ALL FOUR expression branches — ``function``, ``condition``,
    ``expression``, ``end_condition``. A simple identifier (no dots/operators)
    resolves to a callable from ``callables`` (``ValueError`` if absent); a CEL
    expression is passed raw to the Agno constructor.

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
        step_executor: StepExecutor | None = None,
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
                unresolved callable ref will then raise ``ValueError``.
            step_executor: An optional ``StepExecutor`` for resilience wrapping.
                When provided, function-executor steps are wrapped in a closure
                that calls ``step_executor.execute_step()``. When ``None``,
                function steps behave as before (backward compatible). Agent,
                team, and workflow steps are never wrapped.

        Returns:
            A constructed ``agno.Workflow``. Per ``agno/workflow/workflow.py:
            457-490``, construction is pure assignment — no network call, no
            session, no db is created until ``.run()`` / ``.arun()``.

        Raises:
            ValueError: If a ``StepConfig`` references an ``agent``, ``team``,
                or callable name absent from the corresponding registry, if a
                Step-type config has no executor source, or if a ``function``
                ref looks like a CEL expression (Step.executor requires a
                callable). Raised before ``agno.Workflow`` is constructed, so no
                partial Workflow is ever produced.
            NotImplementedError: If ``step_cfg.type == StepType.WORKFLOW``
                (nested workflow executor — deferred beyond slice #4).
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
                    step_executor=step_executor,
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
        step_executor: StepExecutor | None = None,
    ) -> _BuiltStep:
        """Dispatch a single ``StepConfig`` to its Agno primitive.

        Pure dispatcher (CC <= 8): emits the validate-and-warn logs for the
        deferred ``execute``/``finally_`` features, then delegates each
        ``StepType`` to a dedicated private builder. ``StepType.STEP`` and
        ``StepType.FUNCTION`` share ``_build_step_executor``; ``StepType.WORKFLOW``
        raises ``NotImplementedError`` (deferred beyond slice #4); the five
        composite types (Steps/Parallel/Condition/Router/Loop) are looked up in
        the module-level ``_STEP_BUILDERS`` dispatch table.

        Emits ``_logger.warning`` for ``execute=False`` and ``finally_=True``
        (validate-and-warn; step is still built).

        Args:
            step_cfg: The ``StepConfig`` to translate. Its ``type`` selects the
                branch; its type-specific fields populate the primitive.
            agents: Pre-built agent registry (passed through to Step building).
            teams: Pre-built team registry (passed through to Step building).
            callables: Callable executor registry (passed through to Step
                building and to ``_resolve_callable_or_cel``).
            step_index: ``step-id -> StepConfig`` map for resolving
                ``if_true`` / ``if_false`` / ``cases`` references.

        Returns:
            The constructed Agno workflow primitive.

        Raises:
            ValueError: If the step type is unsupported (defensive guard; the
                StepType str-enum is closed and all 8 members are handled).
            NotImplementedError: If ``step_cfg.type == StepType.WORKFLOW``.
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
        if t in (StepType.STEP, StepType.FUNCTION):
            return WorkflowFactory._build_step_executor(
                step_cfg=step_cfg,
                agents=agents,
                teams=teams,
                callables=callables,
                step_executor=step_executor,
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

        # --- Composite types: table-driven dispatch (Steps/Parallel/
        # Condition/Router/Loop) ---
        builder = _STEP_BUILDERS.get(t)
        if builder is None:
            # Unreachable: StepType is a closed str-enum and all 8 members are
            # handled above (FUNCTION folds into STEP). Defensive guard for safety.
            raise ValueError(
                f"Unsupported step type {t!r} on step {step_cfg.step!r}. "
                "Supported types: Step, Function, Steps, Parallel, Condition, "
                "Router, Loop."
            )
        return builder(
            step_cfg=step_cfg,
            agents=agents,
            teams=teams,
            callables=callables,
            step_index=step_index,
            step_executor=step_executor,
        )

    @staticmethod
    def _build_step_executor(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_executor: StepExecutor | None = None,
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
            ValueError: If a referenced name is absent from its registry, if
                none of agent/team/function/workflow is set, or if the
                referenced name is absent from its registry.
            NotImplementedError: If ``workflow`` is set (deferred).
        """
        if step_cfg.agent is not None:
            if step_cfg.agent not in agents:
                raise ValueError(
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
                raise ValueError(
                    f"Team not found: {step_cfg.team!r} (step {step_cfg.step!r}). "
                    "Check the 'teams:' section of your YAML."
                )
            return Step(
                name=step_cfg.step,
                team=teams[step_cfg.team],
                description=step_cfg.description,
            )

        if step_cfg.function is not None:
            # Reuse Agno's is_cel_expression via _resolve_callable_or_cel: simple
            # identifier -> callable lookup; CEL-looking string -> pass through.
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
            # TD-06: Resilience binding — wrap the raw callable in a closure
            # that calls step_executor.execute_step(). The wrapper is an async
            # def so Agno's _is_async_callable detects it and awaits it.
            if step_executor is not None:
                raw_fn = executor

                async def _resilient_executor(si: Any, **kwargs: Any) -> Any:
                    """Resilience wrapper: delegate to step_executor.execute_step.

                    Creates a thunk that calls raw_fn with the StepInput and any
                    additional kwargs Agno passes (run_context, session_state).
                    """
                    if asyncio.iscoroutinefunction(raw_fn):
                        # Async raw_fn: thunk returns a coroutine directly.
                        return await step_executor.execute_step(
                            lambda: raw_fn(si, **kwargs)
                        )
                    else:
                        # Sync raw_fn: thunk must be an async def.
                        async def _work() -> Any:
                            return raw_fn(si, **kwargs)
                        return await step_executor.execute_step(_work)

                executor = _resilient_executor
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
              look up ``value`` in ``callables``. Raises ``ValueError`` if
              absent (the value is an unresolvable callable reference).
            - Returns ``True`` (CEL-looking): return ``value`` unchanged; the
              caller decides whether a CEL string is acceptable for its slot.

        This mirrors Agno's own ``Condition.from_dict`` / ``Router.from_dict``
        / ``Loop.from_dict`` deserialization logic.

        Applied in ALL FOUR expression branches (Open Item #1): ``function``,
        ``condition``, ``expression``, ``end_condition``.

        Args:
            value: The string to resolve.
            callables: The callable registry.

        Returns:
            The resolved callable if ``value`` is a simple identifier, or the
            string unchanged if it looks like a CEL expression.

        Raises:
            ValueError: If ``value`` is a simple identifier not present in
                ``callables`` (unresolvable callable reference).
        """
        if is_cel_expression(value):
            # CEL expression — pass through; Agno compiles it.
            return value
        if value not in callables:
            raise ValueError(
                f"Unresolvable callable reference: {value!r}. "
                "Register it in the callables map."
            )
        return callables[value]

    @staticmethod
    def _build_steps_group(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_index: dict[str, StepConfig],
        step_executor: StepExecutor | None = None,
    ) -> Steps:
        """Build a sequential ``agno.Steps`` pipeline from nested step dicts.

        Each entry in ``step_cfg.steps`` is re-validated into a ``StepConfig``
        and dispatched recursively through ``_build_step``.

        Args:
            step_cfg: A ``StepConfig`` with ``type == StepType.STEPS``.
            agents: Pre-built agent registry (recursion passthrough).
            teams: Pre-built team registry (recursion passthrough).
            callables: Callable executor registry (recursion passthrough).
            step_index: ``step-id -> StepConfig`` map (recursion passthrough).
            step_executor: Optional ``StepExecutor`` for resilience wrapping.

        Returns:
            An ``agno.Steps`` with the recursively built nested primitives
            (empty list when ``step_cfg.steps`` is empty).
        """
        nested = [
            WorkflowFactory._build_step(
                step_cfg=StepConfig(**raw),
                agents=agents,
                teams=teams,
                callables=callables,
                step_index=step_index,
                step_executor=step_executor,
            )
            for raw in step_cfg.steps
        ]
        return Steps(name=step_cfg.step, description=step_cfg.description, steps=nested)

    @staticmethod
    def _build_parallel_group(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_index: dict[str, StepConfig],
        step_executor: StepExecutor | None = None,
    ) -> Parallel:
        """Build a variadic ``agno.Parallel`` from nested step dicts.

        Each entry in ``step_cfg.steps`` is re-validated and dispatched
        recursively; the built primitives are passed as ``*args`` (Agno flattens
        them into ``Parallel.steps``).

        Args:
            step_cfg: A ``StepConfig`` with ``type == StepType.PARALLEL``.
            agents: Pre-built agent registry (recursion passthrough).
            teams: Pre-built team registry (recursion passthrough).
            callables: Callable executor registry (recursion passthrough).
            step_index: ``step-id -> StepConfig`` map (recursion passthrough).
            step_executor: Optional ``StepExecutor`` for resilience wrapping.

        Returns:
            An ``agno.Parallel`` with all nested primitives as children.
        """
        built = [
            WorkflowFactory._build_step(
                step_cfg=StepConfig(**raw),
                agents=agents,
                teams=teams,
                callables=callables,
                step_index=step_index,
                step_executor=step_executor,
            )
            for raw in step_cfg.steps
        ]
        return Parallel(*built, name=step_cfg.step, description=step_cfg.description)  # type: ignore[arg-type]

    @staticmethod
    def _build_condition_group(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_index: dict[str, StepConfig],
        step_executor: StepExecutor | None = None,
    ) -> Condition:
        """Build an ``agno.Condition`` (evaluator + if_true/if_false branches).

        ``if_true`` / ``if_false`` are step-id strings resolved against
        ``step_index``; a reference absent from the index degrades defensively
        to an empty ``steps`` list / ``else_steps=None``. The evaluator is
        resolved via ``_resolve_callable_or_cel`` (Open Item #1): a simple
        identifier is looked up in ``callables``, a CEL expression passes
        through raw; ``None`` defaults to ``True``.

        Args:
            step_cfg: A ``StepConfig`` with ``type == StepType.CONDITION``.
            agents: Pre-built agent registry (recursion passthrough).
            teams: Pre-built team registry (recursion passthrough).
            callables: Callable executor registry (evaluator resolution).
            step_index: ``step-id -> StepConfig`` map (branch resolution).
            step_executor: Optional ``StepExecutor`` for resilience wrapping.

        Returns:
            An ``agno.Condition`` with the resolved evaluator and branches.
        """
        if_steps: list[Any] = []
        if step_cfg.if_true and step_cfg.if_true in step_index:
            if_steps.append(
                WorkflowFactory._build_step(
                    step_cfg=step_index[step_cfg.if_true],
                    agents=agents,
                    teams=teams,
                    callables=callables,
                    step_index=step_index,
                    step_executor=step_executor,
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
                    step_executor=step_executor,
                )
            ]
        # Open Item #1: resolve evaluator via _resolve_callable_or_cel.
        # A simple identifier (e.g. "check_threshold") is NOT a CEL
        # expression and MUST be resolved from the callables registry; a CEL
        # expression is passed raw (Agno compiles it). None defaults to True.
        evaluator: Any = True
        if step_cfg.condition is not None:
            evaluator = WorkflowFactory._resolve_callable_or_cel(
                step_cfg.condition, callables
            )
        return Condition(
            steps=if_steps,
            evaluator=evaluator,
            else_steps=else_steps,
            name=step_cfg.step,
            description=step_cfg.description,
        )

    @staticmethod
    def _build_router_group(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_index: dict[str, StepConfig],
        step_executor: StepExecutor | None = None,
    ) -> Router:
        """Build an ``agno.Router`` (selector + choices named by case key).

        Each ``cases`` entry maps a selector-returned string (key) to a step-id;
        the referenced step is built recursively and re-named with the case KEY
        (A3 invariant: ``Router._step_name_map`` keys on ``.name``). A case
        pointing to a step-id absent from ``step_index`` is skipped defensively.

        Args:
            step_cfg: A ``StepConfig`` with ``type == StepType.ROUTER``.
            agents: Pre-built agent registry (recursion passthrough).
            teams: Pre-built team registry (recursion passthrough).
            callables: Callable executor registry (selector resolution).
            step_index: ``step-id -> StepConfig`` map (case resolution).
            step_executor: Optional ``StepExecutor`` for resilience wrapping.

        Returns:
            An ``agno.Router`` with case-key-named choices and resolved selector.
        """
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
                step_executor=step_executor,
            )
            # Override the .name to the case key so the Router can resolve
            # the selector's returned string against _step_name_map.
            built_choice.name = case_key
            choices.append(built_choice)
        # Open Item #1: resolve selector via _resolve_callable_or_cel.
        selector: Any = None
        if step_cfg.expression is not None:
            selector = WorkflowFactory._resolve_callable_or_cel(
                step_cfg.expression, callables
            )
        return Router(
            choices=choices,
            selector=selector,
            name=step_cfg.step,
            description=step_cfg.description,
        )

    @staticmethod
    def _build_loop_group(
        step_cfg: StepConfig,
        agents: dict[str, Agent],
        teams: dict[str, Team],
        callables: dict[str, Callable[..., Any]],
        step_index: dict[str, StepConfig],
        step_executor: StepExecutor | None = None,
    ) -> Loop:
        """Build an ``agno.Loop`` (nested body + max_iterations + end_condition).

        The Loop body builds recursively from ``step_cfg.steps`` (SPEC_05 slice
        A). ``max_iterations`` defaults to 3 when absent. ``end_condition`` is
        resolved via ``_resolve_callable_or_cel`` (Open Item #1).

        Args:
            step_cfg: A ``StepConfig`` with ``type == StepType.LOOP``.
            agents: Pre-built agent registry (recursion passthrough).
            teams: Pre-built team registry (recursion passthrough).
            callables: Callable executor registry (end_condition resolution).
            step_index: ``step-id -> StepConfig`` map (recursion passthrough).
            step_executor: Optional ``StepExecutor`` for resilience wrapping.

        Returns:
            An ``agno.Loop`` with the nested body, iteration cap, and condition.
        """
        # SPEC_05 slice A: Loop body now builds recursively, mirroring the
        # Parallel/Steps branches. The validator admits `steps` on Loop.
        nested = [
            WorkflowFactory._build_step(
                step_cfg=StepConfig(**raw),
                agents=agents,
                teams=teams,
                callables=callables,
                step_index=step_index,
                step_executor=step_executor,
            )
            for raw in step_cfg.steps
        ]
        # Open Item #1: resolve end_condition via _resolve_callable_or_cel.
        end_condition: Any = None
        if step_cfg.end_condition is not None:
            end_condition = WorkflowFactory._resolve_callable_or_cel(
                step_cfg.end_condition, callables
            )
        return Loop(
            steps=nested,  # type: ignore[arg-type]
            name=step_cfg.step,
            description=step_cfg.description,
            max_iterations=step_cfg.max_iterations if step_cfg.max_iterations is not None else 3,
            end_condition=end_condition,
        )


# Dispatch table for the five composite StepTypes. STEP/FUNCTION and WORKFLOW
# are handled directly in ``_build_step``; the rest are looked up here so the
# dispatcher stays a pure table-driven switch.
_STEP_BUILDERS: dict[StepType, Callable[..., _BuiltStep]] = {
    StepType.STEPS: WorkflowFactory._build_steps_group,
    StepType.PARALLEL: WorkflowFactory._build_parallel_group,
    StepType.CONDITION: WorkflowFactory._build_condition_group,
    StepType.ROUTER: WorkflowFactory._build_router_group,
    StepType.LOOP: WorkflowFactory._build_loop_group,
}
