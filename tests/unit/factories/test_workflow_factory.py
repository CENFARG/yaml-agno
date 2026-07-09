"""Unit tests for ``WorkflowFactory.build`` — SPEC_01 slice #4 (the hardest).

Covers the 22+ scenarios of
``openspec/changes/workflow-factory/specs/workflow-factory/spec.md`` plus the
behavioral matrix in ``tasks.md`` Phase 2 (tasks 2.1-2.25):

    - GREEN golden path — linear 2-Step workflow with agents
    - GREEN description propagated (no runtime kwargs)
    - GREEN Parallel dispatch (variadic, 3 sub-steps)
    - GREEN Condition CEL evaluator + if_true/if_false branches
    - GREEN Condition else_steps None when no if_false
    - GREEN Condition callable evaluator (Open Item #1)
    - GREEN Router choices named by case KEY (A3) + CEL selector
    - GREEN Router callable selector (Open Item #1)
    - GREEN Loop CEL end_condition + max_iterations
    - GREEN Loop callable end_condition (Open Item #1)
    - GREEN Loop default max_iterations (3)
    - GREEN Step executor: agent resolved
    - GREEN Step executor: team resolved
    - GREEN Step executor: function callable resolved
    - RED Step executor: CEL-looking function string raises ValueError
    - RED Step executor: missing agent raises (no partial Step)
    - RED Step executor: missing team raises
    - RED callable ref unresolvable raises (Open Item #1)
    - GREEN execute=False warns AND builds (validate-and-warn)
    - GREEN finally_=True warns AND builds
    - GREEN nested Parallel inside Condition
    - GREEN 7-type dispatch disjoint table (+ Workflow raises NotImplementedError)
    - GREEN human_review present — no error, no wiring
    - GREEN branch ref trust — no re-validation
    - GREEN CEL string passthrough to Condition.evaluator

Verified Agno behavior (Agno 2.6.22): ``Condition(evaluator=str)``,
``Router(selector=str)``, ``Loop(end_condition=str)`` construct without network
(Agno compiles CEL lazily at ``.run()`` time). ``is_cel_expression('my_func')``
returns False; ``is_cel_expression('a.b.c')`` returns True.

Open Item #1 (CRITICAL): the design literal only resolves callables in the
``function`` branch; tests 2.6/2.8/2.10 force the impl to apply
``_resolve_callable_or_cel`` in ALL FOUR branches (function/condition/expression/
end_condition). A simple identifier like ``"check_threshold"`` is NOT a CEL
expression (``is_cel_expression`` returns False) and MUST be resolved from the
``callables`` registry.
"""

import logging

import pytest
from agno.agent import Agent
from agno.team.mode import TeamMode
from agno.team.team import Team
from agno.workflow.condition import Condition
from agno.workflow.loop import Loop
from agno.workflow.parallel import Parallel
from agno.workflow.router import Router
from agno.workflow.step import Step
from agno.workflow.steps import Steps
from agno.workflow.workflow import Workflow

from yaml_agno.factories import WorkflowFactory
from yaml_agno.models.config.workflow_config import StepConfig, WorkflowConfig

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Helpers — build real Agno objects without network (construction is pure).
# --------------------------------------------------------------------------- #


def _agent(name: str) -> Agent:
    """Build a real ``agno.Agent`` with a trivial model string (no network)."""
    return Agent(name=name, model="openai:gpt-4o")


def _team(name: str) -> Team:
    """Build a real ``agno.Team`` with one trivial member (no network)."""
    return Team(name=name, members=[_agent(f"{name}-m1")], mode=TeamMode.coordinate)


def _fn_factory(label: str):
    """Build a trivial executor callable tagged with a label for identity tests."""

    def _executor(step_input):  # pragma: no cover - never invoked at build time
        return label

    _executor.__label__ = label  # type: ignore[attr-defined]
    return _executor


def _workflow_cfg(steps: list[StepConfig], name: str = "w", description: str | None = None) -> WorkflowConfig:
    """Build a ``WorkflowConfig`` from explicit ``StepConfig`` objects."""
    return WorkflowConfig(name=name, description=description, steps=steps)


# --------------------------------------------------------------------------- #
# Phase 2.1 / 2.2 — build() returns agno.Workflow + description propagation.
# --------------------------------------------------------------------------- #


class TestBuildReturnsAgnoWorkflow:
    """RED→GREEN tests for the top-level assembly contract."""

    def test_build_returns_agno_workflow(self) -> None:
        """Scenario: Golden path — workflow lineal de 2 Steps con agentes.

        ``build`` returns ``isinstance(agno.Workflow)`` with 2 ``agno.Step``.
        """
        cfg = _workflow_cfg([
            StepConfig(step="s1", type="Step", agent="a1"),
            StepConfig(step="s2", type="Step", agent="a2"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1"), "a2": _agent("a2")}, teams={})
        assert isinstance(result, Workflow)
        assert len(result.steps) == 2
        assert all(isinstance(s, Step) for s in result.steps)

    def test_build_propagates_description(self) -> None:
        """Scenario: Workflow con description propagada (sin kwargs runtime).

        ``result.description == cfg.description`` and the factory MUST NOT pass
        ``db``/``session_id``/``user_id`` to the Workflow constructor.
        """
        cfg = _workflow_cfg(
            [StepConfig(step="s1", type="Step", agent="a1")],
            description="pipeline de facturacion",
        )
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        assert result.description == "pipeline de facturacion"
        # Runtime-only kwargs MUST NOT be set by the factory (Agno defaults).
        assert result.session_id is None
        assert result.user_id is None
        assert result.db is None


# --------------------------------------------------------------------------- #
# Phase 2.3 / 2.21 — nested Parallel (variadic) + deep nesting.
# --------------------------------------------------------------------------- #


class TestParallelDispatch:
    """RED→GREEN tests for Parallel variadic construction + deep nesting."""

    def test_dispatch_parallel_variadic(self) -> None:
        """Scenario: Parallel con 3 sub-steps anidados.

        ``result.steps[0]`` is ``agno.Parallel`` with 3 sub-primitives and
        ``.name == cfg.step``.
        """
        cfg = _workflow_cfg([
            StepConfig(
                step="p",
                type="Parallel",
                steps=[
                    {"step": "v1", "type": "Step", "agent": "a1"},
                    {"step": "v2", "type": "Step", "agent": "a1"},
                    {"step": "v3", "type": "Step", "agent": "a1"},
                ],
            ),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        parallel = result.steps[0]
        assert isinstance(parallel, Parallel)
        assert parallel.name == "p"
        # Parallel stores sub-steps in .steps (Agno flattens *args into steps list).
        assert len(parallel.steps) == 3

    def test_nested_parallel_inside_condition(self) -> None:
        """Scenario: Anidamiento profundo (Parallel dentro de Condition).

        ``Condition.steps`` is an ``agno.Parallel`` with 2 sub-primitives.
        """
        cfg = _workflow_cfg([
            StepConfig(
                step="c",
                type="Condition",
                condition="amount > 1000",
                if_true="branch_true",
                if_false=None,
            ),
            StepConfig(
                step="branch_true",
                type="Parallel",
                steps=[
                    {"step": "bt1", "type": "Step", "agent": "a1"},
                    {"step": "bt2", "type": "Step", "agent": "a1"},
                ],
            ),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        condition = result.steps[0]
        assert isinstance(condition, Condition)
        # if_true resolves to the Parallel branch.
        assert isinstance(condition.steps[0], Parallel)
        assert len(condition.steps[0].steps) == 2


# --------------------------------------------------------------------------- #
# Phase 2.4 / 2.5 / 2.6 / 2.25 — Condition (CEL, branches, callable, passthrough).
# --------------------------------------------------------------------------- #


class TestConditionDispatch:
    """RED→GREEN tests for the Condition primitive (evaluator + branches)."""

    def test_dispatch_condition_cel_evaluator_and_branches(self) -> None:
        """Scenario: Condition con if_true e if_false (CEL evaluator).

        ``Condition.evaluator == "amount > 1000"`` (CEL string),
        ``steps`` maps to ``approve``, ``else_steps`` to ``reject``.
        """
        cfg = _workflow_cfg([
            StepConfig(step="c", type="Condition", condition="amount > 1000",
                       if_true="approve", if_false="reject"),
            StepConfig(step="approve", type="Step", agent="a1"),
            StepConfig(step="reject", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        cond = result.steps[0]
        assert isinstance(cond, Condition)
        assert cond.evaluator == "amount > 1000"
        assert cond.steps[0].name == "approve"
        assert cond.else_steps is not None
        assert cond.else_steps[0].name == "reject"

    def test_dispatch_condition_else_steps_none_when_no_if_false(self) -> None:
        """Scenario: Condition sin if_false (else_steps None)."""
        cfg = _workflow_cfg([
            StepConfig(step="c", type="Condition", condition="flag",
                       if_true="sink", if_false=None),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        cond = result.steps[0]
        assert isinstance(cond, Condition)
        assert cond.else_steps is None

    def test_dispatch_condition_callable_evaluator(self) -> None:
        """Scenario: Identificador simple resuelto como callable (Open Item #1).

        ``condition="check_threshold"`` (NOT a CEL expression) resolves to the
        callable from ``callables``; ``Condition.evaluator is fn``.
        """
        fn = _fn_factory("check_threshold")
        cfg = _workflow_cfg([
            StepConfig(step="c", type="Condition", condition="check_threshold",
                       if_true="sink", if_false=None),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(
            cfg, agents={"a1": _agent("a1")}, teams={}, callables={"check_threshold": fn}
        )
        cond = result.steps[0]
        assert isinstance(cond, Condition)
        assert cond.evaluator is fn

    def test_cel_string_passthrough_condition(self) -> None:
        """Scenario: CEL expression pasada como string a Condition.evaluator.

        ``condition='input.contains("urgent")'`` is a CEL expression (has dots);
        passed raw to ``Condition.evaluator`` (no compilation, no callable lookup).
        """
        cfg = _workflow_cfg([
            StepConfig(step="c", type="Condition", condition='input.contains("urgent")',
                       if_true="sink", if_false=None),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={}, callables=None)
        cond = result.steps[0]
        assert isinstance(cond, Condition)
        assert cond.evaluator == 'input.contains("urgent")'


# --------------------------------------------------------------------------- #
# Phase 2.7 / 2.8 — Router (choices named by case KEY + CEL/callable selector).
# --------------------------------------------------------------------------- #


class TestRouterDispatch:
    """RED→GREEN tests for the Router primitive (A3 case-key naming invariant)."""

    def test_dispatch_router_cases_named_by_key_cel_selector(self) -> None:
        """Scenario: Router con 3 cases y CEL selector.

        ``Router.choices`` has 3 elements whose ``.name`` are the case KEYS
        (``billing``/``support``/``sales``), NOT the step-ids; ``selector`` is
        the CEL string ``"input.category"``.
        """
        cfg = _workflow_cfg([
            StepConfig(step="r", type="Router", expression="input.category", cases={
                "billing": "step_a", "support": "step_b", "sales": "step_c",
            }),
            StepConfig(step="step_a", type="Step", agent="a1"),
            StepConfig(step="step_b", type="Step", agent="a1"),
            StepConfig(step="step_c", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        router = result.steps[0]
        assert isinstance(router, Router)
        assert router.selector == "input.category"
        choice_names = [c.name for c in router.choices]
        assert choice_names == ["billing", "support", "sales"]

    def test_dispatch_router_callable_selector(self) -> None:
        """Scenario: Router con callable selector (Open Item #1).

        ``expression="pick_route"`` (simple identifier, NOT CEL) resolves to the
        callable; ``Router.selector is fn``.
        """
        fn = _fn_factory("pick_route")
        cfg = _workflow_cfg([
            StepConfig(step="r", type="Router", expression="pick_route",
                       cases={"a": "step_a", "b": "step_b"}),
            StepConfig(step="step_a", type="Step", agent="a1"),
            StepConfig(step="step_b", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(
            cfg, agents={"a1": _agent("a1")}, teams={}, callables={"pick_route": fn}
        )
        router = result.steps[0]
        assert isinstance(router, Router)
        assert router.selector is fn


# --------------------------------------------------------------------------- #
# Phase 2.9 / 2.10 / 2.11 — Loop (CEL/callable end_condition + defaults).
# --------------------------------------------------------------------------- #


class TestLoopDispatch:
    """RED→GREEN tests for the Loop primitive."""

    def test_dispatch_loop_cel_end_condition_and_max_iter(self) -> None:
        """Scenario: Loop con CEL end_condition y max_iterations.

        ``Loop.max_iterations == 10``, ``end_condition == "all_success"``,
        ``steps`` contains the built ``intento`` primitive.
        """
        cfg = _workflow_cfg([
            StepConfig(step="l", type="Loop", max_iterations=10,
                       end_condition="all_success",
                       steps=[{"step": "intento", "type": "Step", "agent": "a1"}]),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        loop = result.steps[0]
        assert isinstance(loop, Loop)
        assert loop.max_iterations == 10
        assert loop.end_condition == "all_success"
        assert len(loop.steps) == 1
        assert loop.steps[0].name == "intento"

    def test_dispatch_loop_callable_end_condition(self) -> None:
        """Scenario: Loop con callable end_condition (Open Item #1).

        ``end_condition="should_stop"`` (simple identifier) resolves to the
        callable; ``Loop.end_condition is fn``.
        """
        fn = _fn_factory("should_stop")
        cfg = _workflow_cfg([
            StepConfig(step="l", type="Loop", end_condition="should_stop",
                       steps=[{"step": "intento", "type": "Step", "agent": "a1"}]),
        ])
        result = WorkflowFactory.build(
            cfg, agents={"a1": _agent("a1")}, teams={}, callables={"should_stop": fn}
        )
        loop = result.steps[0]
        assert isinstance(loop, Loop)
        assert loop.end_condition is fn

    def test_dispatch_loop_default_max_iterations(self) -> None:
        """Implicit requirement: Loop defaults to max_iterations=3 (Agno default)."""
        cfg = _workflow_cfg([
            StepConfig(step="l", type="Loop",
                       steps=[{"step": "intento", "type": "Step", "agent": "a1"}]),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        loop = result.steps[0]
        assert isinstance(loop, Loop)
        assert loop.max_iterations == 3


# --------------------------------------------------------------------------- #
# Phase 2.12-2.18 — Step executor resolution (agent/team/function/cel/missing).
# --------------------------------------------------------------------------- #


class TestStepExecutorResolution:
    """RED→GREEN tests for the 4 executor sources + missing-ref errors."""

    def test_step_executor_agent_resolved(self) -> None:
        """Scenario: Step con agent resuelto desde el dict.

        ``result.steps[0].agent is agentA`` and ``.name == "s"``.
        """
        agent_a = _agent("a1")
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", agent="a1")])
        result = WorkflowFactory.build(cfg, agents={"a1": agent_a}, teams={})
        step = result.steps[0]
        assert isinstance(step, Step)
        assert step.agent is agent_a
        assert step.name == "s"

    def test_step_executor_team_resolved(self) -> None:
        """Scenario: Step con team resuelto.

        ``result.steps[0].team is teamX``.
        """
        team_x = _team("t1")
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", team="t1")])
        result = WorkflowFactory.build(cfg, agents={}, teams={"t1": team_x})
        step = result.steps[0]
        assert isinstance(step, Step)
        assert step.team is team_x

    def test_step_executor_function_callable(self) -> None:
        """Implicit requirement: function ref resolves to a callable executor.

        ``result.steps[0].executor is fn``.
        """
        fn = _fn_factory("my_fn")
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", function="my_fn")])
        result = WorkflowFactory.build(cfg, agents={}, teams={}, callables={"my_fn": fn})
        step = result.steps[0]
        assert isinstance(step, Step)
        assert step.executor is fn

    def test_step_executor_function_cel_string_raises(self) -> None:
        """Implicit requirement: CEL-looking function string raises ValueError.

        ``function="a.b.c"`` looks like CEL but ``Step.executor`` requires a
        callable, not a CEL string.
        """
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", function="a.b.c")])
        with pytest.raises(ValueError, match="s"):
            WorkflowFactory.build(cfg, agents={}, teams={}, callables={})

    def test_step_executor_missing_agent_raises(self) -> None:
        """Scenario: RED — agente referenciado no existe.

        Raises mentioning ``"ghost"`` AND ``agno.Step`` is never instantiated.
        """
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", agent="ghost")])
        with pytest.raises((ValueError, KeyError)) as exc_info:
            WorkflowFactory.build(cfg, agents={}, teams={})
        assert "ghost" in str(exc_info.value)

    def test_step_executor_missing_team_raises(self) -> None:
        """Scenario: RED — equipo referenciado no existe.

        Raises mentioning ``"ghost_team"``.
        """
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", team="ghost_team")])
        with pytest.raises((ValueError, KeyError)) as exc_info:
            WorkflowFactory.build(cfg, agents={}, teams={})
        assert "ghost_team" in str(exc_info.value)

    def test_callable_ref_unresolvable_raises(self) -> None:
        """Scenario: RED — callable ref no resuelto (Open Item #1).

        ``condition="missing_fn"`` (simple identifier) + ``callables=None`` raises
        mentioning ``"missing_fn"``.
        """
        cfg = _workflow_cfg([
            StepConfig(step="c", type="Condition", condition="missing_fn",
                       if_true="sink", if_false=None),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        with pytest.raises((ValueError, KeyError)) as exc_info:
            WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={}, callables=None)
        assert "missing_fn" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Phase 2.19 / 2.20 — execute/finally_ validate-and-warn.
# --------------------------------------------------------------------------- #


class TestValidateAndWarn:
    """RED→GREEN tests for deferred execute/finally_ semantics."""

    def test_execute_false_warns_and_builds(self, caplog: pytest.LogCaptureFixture) -> None:
        """Scenario: execute=False registra warning pero construye el step.

        Warning mentions step-id ``"s"`` and ``"execute"``; the step is still
        ``agno.Step`` and NOT omitted/duplicated (``len==1``).
        """
        cfg = _workflow_cfg([StepConfig(step="s", type="Step", agent="a1", execute=False)])
        with caplog.at_level(logging.WARNING, logger="yaml_agno.factories.workflow_factory"):
            result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        assert isinstance(result.steps[0], Step)
        assert len(result.steps) == 1
        joined = " ".join(r.message for r in caplog.records)
        assert "s" in joined
        assert "execute" in joined.lower()

    def test_finally_true_warns_and_builds(self, caplog: pytest.LogCaptureFixture) -> None:
        """Scenario: finally_=True registra warning pero construye el step.

        Warning mentions step-id ``"cleanup"`` and ``"finally"``; step built in position.
        """
        fn = _fn_factory("cleanup_fn")
        cfg = _workflow_cfg([
            StepConfig(step="cleanup", type="Step", function="cleanup_fn",
                       **{"finally": True}),
        ])
        with caplog.at_level(logging.WARNING, logger="yaml_agno.factories.workflow_factory"):
            result = WorkflowFactory.build(cfg, agents={}, teams={}, callables={"cleanup_fn": fn})
        assert isinstance(result.steps[0], Step)
        assert result.steps[0].name == "cleanup"
        joined = " ".join(r.message for r in caplog.records)
        assert "cleanup" in joined
        assert "finally" in joined.lower()


# --------------------------------------------------------------------------- #
# Phase 2.22 — 7-type dispatch disjoint table.
# --------------------------------------------------------------------------- #


class TestSevenTypeDispatch:
    """RED→GREEN tests for the disjoint 7-primitive matrix (incl. Workflow raise)."""

    def test_seven_type_dispatch_disjoint(self) -> None:
        """Scenario: Cada tipo produce su primitiva (tabla excluyente).

        One workflow per ``StepType``; each ``result.steps[0]`` is ``isinstance``
        of exactly one primitive; ``Workflow`` type raises ``NotImplementedError``.
        """
        a1 = _agent("a1")
        agents = {"a1": a1}

        # Step
        step_cfg = _workflow_cfg([StepConfig(step="x", type="Step", agent="a1")])
        step_wf = WorkflowFactory.build(step_cfg, agents=agents, teams={})
        assert isinstance(step_wf.steps[0], Step)

        # Parallel
        par_cfg = _workflow_cfg([
            StepConfig(step="x", type="Parallel",
                       steps=[{"step": "v", "type": "Step", "agent": "a1"}]),
        ])
        par_wf = WorkflowFactory.build(par_cfg, agents=agents, teams={})
        assert isinstance(par_wf.steps[0], Parallel)

        # Steps
        steps_cfg = _workflow_cfg([
            StepConfig(step="x", type="Steps",
                       steps=[{"step": "v", "type": "Step", "agent": "a1"}]),
        ])
        steps_wf = WorkflowFactory.build(steps_cfg, agents=agents, teams={})
        assert isinstance(steps_wf.steps[0], Steps)

        # Condition
        cond_cfg = _workflow_cfg([
            StepConfig(step="x", type="Condition", condition="flag",
                       if_true="sink", if_false=None),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        cond_wf = WorkflowFactory.build(cond_cfg, agents=agents, teams={})
        assert isinstance(cond_wf.steps[0], Condition)

        # Router
        router_cfg = _workflow_cfg([
            StepConfig(step="x", type="Router", expression="input.cat",
                       cases={"a": "sink"}),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        router_wf = WorkflowFactory.build(router_cfg, agents=agents, teams={})
        assert isinstance(router_wf.steps[0], Router)

        # Loop
        loop_cfg = _workflow_cfg([
            StepConfig(step="x", type="Loop",
                       steps=[{"step": "v", "type": "Step", "agent": "a1"}]),
        ])
        loop_wf = WorkflowFactory.build(loop_cfg, agents=agents, teams={})
        assert isinstance(loop_wf.steps[0], Loop)

        # Disjointness: the 6 built primitives are mutually exclusive types.
        primitives = [
            step_wf.steps[0], par_wf.steps[0], steps_wf.steps[0],
            cond_wf.steps[0], router_wf.steps[0], loop_wf.steps[0],
        ]
        type_set = {type(p) for p in primitives}
        assert len(type_set) == 6

        # Workflow (nested) — deferred, raises NotImplementedError.
        wf_cfg = _workflow_cfg([StepConfig(step="x", type="Workflow", workflow="nested")])
        with pytest.raises(NotImplementedError):
            WorkflowFactory.build(wf_cfg, agents=agents, teams={})


# --------------------------------------------------------------------------- #
# Phase 2.23 / 2.24 — human_review opaque + branch ref trust.
# --------------------------------------------------------------------------- #


class TestOpaqueSlotsAndTrust:
    """RED→GREEN tests for human_review (opaque) + no re-validation."""

    def test_human_review_present_no_error_no_wiring(self) -> None:
        """Scenario: human_review presente sin error ni cableado.

        ``human_review={"requires_confirmation": True}`` on a Router builds
        without error and does NOT wire data into the Router.
        """
        cfg = _workflow_cfg([
            StepConfig(step="r", type="Router", expression="input.cat",
                       cases={"a": "sink"}, human_review={"requires_confirmation": True}),
            StepConfig(step="sink", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        router = result.steps[0]
        assert isinstance(router, Router)
        # Agno's Router.human_review defaults to None — factory did not wire cfg.
        assert router.human_review is None

    def test_branch_ref_trust_no_revalidation(self) -> None:
        """Scenario: Branch ref válido garantizado por schema.

        A valid config (unique step-ids, valid branch refs) builds without any
        integrity re-check raising.
        """
        cfg = _workflow_cfg([
            StepConfig(step="c", type="Condition", condition="flag",
                       if_true="s1", if_false="s2"),
            StepConfig(step="s1", type="Step", agent="a1"),
            StepConfig(step="s2", type="Step", agent="a1"),
        ])
        result = WorkflowFactory.build(cfg, agents={"a1": _agent("a1")}, teams={})
        assert isinstance(result, Workflow)
        cond = result.steps[0]
        assert isinstance(cond, Condition)
        assert cond.steps[0].name == "s1"
        assert cond.else_steps[0].name == "s2"


# --------------------------------------------------------------------------- #
# Import contract.
# --------------------------------------------------------------------------- #


class TestWorkflowFactoryImportContract:
    """Scenario: GREEN — Import desde el paquete raíz."""

    def test_workflow_factory_importable_from_factories_package(self) -> None:
        """``from yaml_agno.factories import WorkflowFactory`` succeeds."""
        from yaml_agno.factories import WorkflowFactory as Factory

        assert Factory is not None
        assert Factory is WorkflowFactory

    def test_workflow_factory_build_is_callable(self) -> None:
        """``WorkflowFactory.build`` is callable (static method)."""
        assert callable(WorkflowFactory.build)
