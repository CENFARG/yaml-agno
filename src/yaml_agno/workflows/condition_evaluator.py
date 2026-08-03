"""CEL condition evaluator — YAML template stripping + Agno CEL delegation.

SPEC_05, TD-05: Evaluates YAML condition expressions like
``${input.amount > 1000}`` by stripping the ``${...}`` template
delimiters and delegating to Agno's ``_evaluate_cel`` with a
``{"input": <context>}`` bridge.

The Agno Framework requires ``cel-python``. When it is not installed,
``ConditionEvaluator()`` raises ``RuntimeError`` at construction time so
callers get a clear error message rather than an obscure import failure.
"""

from __future__ import annotations

from typing import Any


class ConditionEvaluator:
    """Evaluates CEL condition expressions from YAML workflow definitions.

    Strips ``${...}`` template delimiters from YAML condition expressions
    and delegates actual CEL evaluation to ``agno.workflow.cel._evaluate_cel``.

    Raises:
        RuntimeError: If ``cel-python`` is not installed.
    """

    def __init__(self) -> None:
        from agno.workflow.cel import CEL_AVAILABLE

        if not CEL_AVAILABLE:
            raise RuntimeError(
                "cel-python is not installed. Install with: pip install cel-python"
            )

    @staticmethod
    def _strip_template(expr: str) -> str:
        """Strip ``${...}`` template delimiters from a YAML condition expression.

        Handles both ``${input.amount > 1000}`` and ``input.amount > 1000``.
        Leading/trailing whitespace is removed.
        """
        expr = expr.strip()
        if expr.startswith("${") and expr.endswith("}"):
            expr = expr[2:-1]
        return expr.strip()

    def evaluate(self, expression: str, context: dict[str, Any]) -> bool:
        """Evaluate a CEL condition expression against the given context.

        Args:
            expression: A CEL expression, optionally wrapped in ``${...}``.
            context: Key-value pairs injected as ``input`` for CEL
                evaluation (e.g. ``{"amount": 1500}`` becomes
                ``input.amount`` in CEL).

        Returns:
            ``True`` if the CEL expression evaluates to truthy,
            ``False`` otherwise.
        """
        from agno.workflow.cel import _evaluate_cel

        expr = self._strip_template(expression)
        cel_context: dict[str, Any] = {"input": context}
        return _evaluate_cel(expr, cel_context)
