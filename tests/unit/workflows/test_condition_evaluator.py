"""RED tests for ConditionEvaluator (SPEC_05, TD-05: CEL Condition Evaluator).

Strict TDD — these tests are written BEFORE the implementation exists.
They cover CEL expression evaluation with ``${...}`` template stripping
and context bridging from YAML workflow condition expressions to
Agno's ``_evaluate_cel``.

When ``cel-python`` is not installed, CEL-dependent evaluation tests are
skipped. The ``test_cel_unavailable_raises`` test validates the guard
regardless of availability.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Determine CEL availability at import time
# ---------------------------------------------------------------------------

try:
    from agno.workflow.cel import CEL_AVAILABLE
except ImportError:
    CEL_AVAILABLE = False

_CEL_SKIP_REASON = "cel-python not installed — install with: pip install cel-python"


# ---------------------------------------------------------------------------
# Task 1: CEL unavailable → constructor raises RuntimeError
# ---------------------------------------------------------------------------


def test_cel_unavailable_raises() -> None:
    """When CEL_AVAILABLE is False, ConditionEvaluator() raises RuntimeError.

    This guard exists so callers get a clear error message at construction
    time rather than an obscure ``celpy`` import failure at evaluation time.

    Scenario: CEL unavailable guard (REQ: YAML condition evaluation).
    """
    if CEL_AVAILABLE:
        pytest.skip("CEL is available — this test only valid when cel-python is NOT installed")

    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    with pytest.raises(RuntimeError, match="cel-python"):
        ConditionEvaluator()


# ---------------------------------------------------------------------------
# Task 2: Evaluate simple comparison → True
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CEL_AVAILABLE, reason=_CEL_SKIP_REASON)
def test_evaluate_simple_comparison() -> None:
    """Expression ``${input.amount > 1000}`` with amount=1500 → True.

    The ``${...}`` template delimiters are stripped, and the context is
    bridged as ``{"input": context}`` before CEL evaluation.

    Scenario: Simple greater-than comparison returns True
    (REQ: YAML condition evaluation).
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    evaluator = ConditionEvaluator()
    result = evaluator.evaluate("${input.amount > 1000}", {"amount": 1500})
    assert result is True


# ---------------------------------------------------------------------------
# Task 3: Evaluate false condition → False
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CEL_AVAILABLE, reason=_CEL_SKIP_REASON)
def test_evaluate_false_condition() -> None:
    """Expression ``${input.amount > 1000}`` with amount=500 → False.

    Verifies that CEL correctly evaluates a condition that is logically
    false given the input context.

    Scenario: Simple greater-than comparison returns False
    (REQ: YAML condition evaluation).
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    evaluator = ConditionEvaluator()
    result = evaluator.evaluate("${input.amount > 1000}", {"amount": 500})
    assert result is False


# ---------------------------------------------------------------------------
# Task 4: Evaluate without ${} template wrapping
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CEL_AVAILABLE, reason=_CEL_SKIP_REASON)
def test_evaluate_without_template() -> None:
    """Expression ``input.amount > 1000`` (no ``${}``) → True.

    ``_strip_template`` is a no-op when there are no delimiters, so bare
    CEL expressions are evaluated directly.

    Scenario: Bare CEL expression without template delimiters
    (REQ: YAML condition evaluation).
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    evaluator = ConditionEvaluator()
    result = evaluator.evaluate("input.amount > 1000", {"amount": 1500})
    assert result is True


# ---------------------------------------------------------------------------
# Task 5: Template stripping handles whitespace edge cases
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CEL_AVAILABLE, reason=_CEL_SKIP_REASON)
def test_strip_template_handles_whitespace() -> None:
    """``_strip_template`` trims leading/trailing whitespace.

    Expressions from YAML files may contain extra whitespace around the
    ``${...}`` markers. The static method handles this robustly.

    Scenario: Template expression with surrounding whitespace
    (REQ: YAML condition evaluation).
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    evaluator = ConditionEvaluator()
    result = evaluator.evaluate("  ${input.amount > 1000}  ", {"amount": 1500})
    assert result is True


# ---------------------------------------------------------------------------
# QUALITY-FEEDBACK §Cobertura — coverage gap (55.6%): _strip_template direct
# (pure string logic, no CEL needed) + blank/invalid expression contracts.
# ---------------------------------------------------------------------------


def test_strip_template_wrapped_expression() -> None:
    """Direct ``_strip_template``: ``${...}`` wrapped → inner expression.

    Runs WITHOUT cel-python — pure string logic. Pins the stripping branch.
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    assert (
        ConditionEvaluator._strip_template("  ${input.amount > 1000}  ")
        == "input.amount > 1000"
    )


def test_strip_template_bare_expression_passthrough() -> None:
    """Direct ``_strip_template``: bare expression (no ``${}``) → unchanged."""
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    assert ConditionEvaluator._strip_template("input.amount > 1000") == "input.amount > 1000"


def test_strip_template_unbalanced_braces_passthrough() -> None:
    """Direct ``_strip_template``: unbalanced braces are NOT stripped.

    Only a FULL ``${...}`` wrapper is removed (startswith AND endswith). A
    dangling opener passes through unchanged (after trim) — pins the guard.
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    assert ConditionEvaluator._strip_template("${input.amount > 1000") == "${input.amount > 1000"


@pytest.mark.skipif(not CEL_AVAILABLE, reason=_CEL_SKIP_REASON)
def test_evaluate_blank_expression_raises_valueerror() -> None:
    """Contract: empty/blank expression raises ``ValueError`` (not falsy).

    Pins the current propagation contract: agno's ``_evaluate_cel`` compiles
    the expression and a blank one is a CEL parse error surfaced as
    ``ValueError`` — the caller decides how to handle it.
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    evaluator = ConditionEvaluator()
    with pytest.raises(ValueError, match="Failed to evaluate CEL"):
        evaluator.evaluate("   ", {"amount": 1500})


@pytest.mark.skipif(not CEL_AVAILABLE, reason=_CEL_SKIP_REASON)
def test_evaluate_invalid_cel_raises_valueerror() -> None:
    """Contract: malformed CEL propagates as ``ValueError`` (not swallowed).

    Pins the current exception contract of ``ConditionEvaluator.evaluate``:
    agno wraps the CEL parse/eval failure in ``ValueError`` and the evaluator
    does NOT catch it. The audit's "no propagar" would be a behavior CHANGE —
    out of scope for a coverage slice; propagation is the deliberate contract
    (Agno's Condition catches it at run time).
    """
    from yaml_agno.workflows.condition_evaluator import ConditionEvaluator

    evaluator = ConditionEvaluator()
    with pytest.raises(ValueError, match="not a cel"):
        evaluator.evaluate("not a cel (", {"amount": 1500})
