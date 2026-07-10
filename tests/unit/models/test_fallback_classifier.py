"""Unit tests for FallbackErrorClassifier (SPEC_14 slice #4 — DOMAIN).

RED-GREEN strict TDD. Tagged ``@pytest.mark.unit``. Uses REAL Agno exceptions
for the three ``isinstance`` branches and a mock subclass for the delegation
branch (Req 6 + Req 7). No network.

Covers:
  - Agno import contract guard (R1/R5 mitigation — skip with reason if missing).
  - ``ModelRateLimitError`` -> ``"rate_limit"``.
  - ``ContextWindowExceededError`` -> ``"context_overflow"``.
  - Plain ``ValueError`` (non-Agno) -> ``"error"``.
  - Generic ``ModelProviderError`` subclass delegates to Agno's
    ``ModelProviderError.classify`` and maps the result.
"""

from __future__ import annotations

import pytest

# Guard (Task 2.1 / Open Item R1-R5): if Agno renamed the exceptions, the whole
# slice is blocked. SKIP with a clear reason rather than xfailing silently — the
# first GREEN test re-confirms the runtime contract the design assumed.
agno_exc = pytest.importorskip("agno.exceptions", reason="agno.exceptions not importable")
if not hasattr(agno_exc.ModelProviderError, "classify"):  # pragma: no cover - guard
    pytest.skip("ModelProviderError.classify missing — Agno contract changed", allow_module_level=True)

from agno.exceptions import (  # noqa: E402
    ContextWindowExceededError,
    ModelProviderError,
    ModelRateLimitError,
)

# Pre-existing circular-import guard (model_spec -> di -> model_spec). The
# ``yaml_agno.models`` package __init__ transitively imports model_spec (via
# cache_key/fallback_chain re-exports), so importing any submodule triggers the
# cycle unless di/__init__ is loaded first. test_provider_factory.py uses the
# same pattern.
from yaml_agno.di.agno_resolver import AgnoResolver  # noqa: E402,F401
from yaml_agno.models.fallback_classifier import FallbackErrorClassifier  # noqa: E402

# ---------------------------------------------------------------------------
# Req 6 — classify maps Agno exception types to the routing Literal
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classify_rate_limit_from_model_rate_limit_error() -> None:
    """``ModelRateLimitError`` instance -> ``"rate_limit"``.

    Spec scenario: classify rate_limit desde ModelRateLimitError.
    """
    exc = ModelRateLimitError("429 too many requests")
    assert FallbackErrorClassifier.classify(exc) == "rate_limit"


@pytest.mark.unit
def test_classify_context_overflow_from_context_window_exceeded_error() -> None:
    """``ContextWindowExceededError`` instance -> ``"context_overflow"``.

    Spec scenario: classify context_overflow.
    """
    exc = ContextWindowExceededError("context window exceeded")
    assert FallbackErrorClassifier.classify(exc) == "context_overflow"


@pytest.mark.unit
def test_classify_error_for_generic_non_agno_exception() -> None:
    """A plain ``ValueError`` (not an Agno exception) -> ``"error"``.

    Spec scenario: classify error genérico.
    """
    exc = ValueError("something unrelated went wrong")
    assert FallbackErrorClassifier.classify(exc) == "error"


# ---------------------------------------------------------------------------
# Req 7 — thin adapter: generic ModelProviderError delegates to Agno classify
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classify_generic_model_provider_error_delegates_to_agno() -> None:
    """A generic ``ModelProviderError`` subclass delegates to Agno's ``classify``.

    Spec scenario: ModelProviderError genérico delega a Agno classify.

    We construct a subclass of ``ModelProviderError`` that is NOT one of the two
    specific subclasses, then monkeypatch ``ModelProviderError.classify`` to
    return a ``ModelRateLimitError`` instance. The adapter MUST map that
    delegation result to ``"rate_limit"`` rather than reimplementing the
    status/pattern inspection.
    """

    class _AmbiguousProviderError(ModelProviderError):
        """A provider error that is neither RateLimit nor ContextWindow."""

    exc = _AmbiguousProviderError("ambiguous upstream blip")

    def _fake_classify(error: Exception) -> ModelProviderError:
        # Agno's classify inspects status/patterns; here we simulate it deciding
        # the ambiguous error is actually a rate-limit case.
        assert error is exc, "classify must receive the original exception"
        return ModelRateLimitError("reclassified as rate limit")

    original = ModelProviderError.classify
    ModelProviderError.classify = _fake_classify  # type: ignore[assignment]
    try:
        assert FallbackErrorClassifier.classify(exc) == "rate_limit"
    finally:
        ModelProviderError.classify = original  # type: ignore[assignment]


@pytest.mark.unit
def test_classify_delegation_falls_back_to_error_when_agno_classify_raises() -> None:
    """If Agno's ``classify`` itself raises, the adapter returns ``"error"``.

    Defensive branch (design §fallback_classifier.py): the classifier must never
    crash the runtime. A delegation that raises is treated as a generic error.
    """

    class _AmbiguousProviderError(ModelProviderError):
        pass

    exc = _AmbiguousProviderError("upstream blip")

    def _exploding_classify(error: Exception) -> ModelProviderError:
        raise RuntimeError("classify blew up")

    original = ModelProviderError.classify
    ModelProviderError.classify = _exploding_classify  # type: ignore[assignment]
    try:
        assert FallbackErrorClassifier.classify(exc) == "error"
    finally:
        ModelProviderError.classify = original  # type: ignore[assignment]


@pytest.mark.unit
def test_classify_delegation_maps_context_overflow_result() -> None:
    """When Agno's ``classify`` returns a ``ContextWindowExceededError``, the
    adapter maps it to ``"context_overflow"``.

    Triangulation for the delegation branch: the previous test only covered the
    rate_limit mapping. This confirms the context_overflow mapping path too.
    """

    class _AmbiguousProviderError(ModelProviderError):
        pass

    exc = _AmbiguousProviderError("ambiguous")

    def _fake_classify(error: Exception) -> ModelProviderError:
        return ContextWindowExceededError("reclassified as context overflow")

    original = ModelProviderError.classify
    ModelProviderError.classify = _fake_classify  # type: ignore[assignment]
    try:
        assert FallbackErrorClassifier.classify(exc) == "context_overflow"
    finally:
        ModelProviderError.classify = original  # type: ignore[assignment]
