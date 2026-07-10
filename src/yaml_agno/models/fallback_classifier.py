"""FallbackErrorClassifier — adaptador delgado sobre agno.exceptions (SPEC_14 #4).

Agno YA clasifica excepciones de modelo en ``agno/exceptions.py``:
``ModelProviderError.classify(error)`` es un classmethod que inspecciona
status_code (429/529 -> ModelRateLimitError) y message patterns
(``CONTEXT_WINDOW_PATTERNS`` -> ContextWindowExceededError). Este módulo NO
reimplementa esa lógica — es un adaptador ``isinstance`` que mapea la
jerarquía Agno al enum de routing que ``FallbackConfig`` define
(``on_rate_limit | on_context_overflow | on_error``).

@ai-directive: NO reimplementes status_code/patterns — delega a
    ModelProviderError.classify. NO uses los nombres del draft SPEC_14
    (``RateLimitError``, ``ContextOverflowError``) — NO existen en agno.exceptions.
"""

from __future__ import annotations

from typing import Literal

from agno.exceptions import (
    ContextWindowExceededError,
    ModelProviderError,
    ModelRateLimitError,
)

__all__ = ["ErrorCategory", "FallbackErrorClassifier"]

# Tipo de retorno público. Mapea 1:1 a los routing enums de FallbackConfig
# (on_rate_limit / on_context_overflow / on_error).
ErrorCategory = Literal["rate_limit", "context_overflow", "error"]


class FallbackErrorClassifier:
    """Map an Agno model exception to a routing category.

    Thin adapter (ADR A2): the classification logic lives in Agno. This class
    only selects the right branch by ``isinstance`` and, for the ambiguous
    ``ModelProviderError`` case, delegates to ``ModelProviderError.classify``.

    Example:
        >>> try:
        ...     invoke_model()
        ... except Exception as exc:
        ...     cat = FallbackErrorClassifier.classify(exc)
        ...     # cat in {"rate_limit", "context_overflow", "error"}
    """

    @staticmethod
    def classify(exc: Exception) -> ErrorCategory:
        """Classify ``exc`` into one of three routing categories.

        Order matters: check the most specific subclasses first.
          1. ``ModelRateLimitError`` -> ``"rate_limit"``.
          2. ``ContextWindowExceededError`` -> ``"context_overflow"``.
          3. ``ModelProviderError`` (generic) -> delegate to
             ``ModelProviderError.classify(exc)`` and map its result. If the
             Agno classmethod returns a subclass of one of the two above, map
             accordingly; otherwise fall back to ``"error"``. If delegation
             itself raises, treat as ``"error"`` (defensive — never let the
             classifier crash the runtime).
          4. Anything else -> ``"error"``.

        Args:
            exc: The exception raised by an Agno Model invocation.

        Returns:
            One of ``"rate_limit"``, ``"context_overflow"``, ``"error"``.
        """
        if isinstance(exc, ModelRateLimitError):
            return "rate_limit"
        if isinstance(exc, ContextWindowExceededError):
            return "context_overflow"
        if isinstance(exc, ModelProviderError):
            try:
                classified = ModelProviderError.classify(exc)
            except Exception:
                # Delegación Agno lanzó — no dejes que el clasificador rompa
                # el runtime. Trata como error genérico.
                return "error"
            if isinstance(classified, ModelRateLimitError):
                return "rate_limit"
            if isinstance(classified, ContextWindowExceededError):
                return "context_overflow"
            return "error"
        return "error"
