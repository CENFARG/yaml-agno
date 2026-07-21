"""Unit tests for ModelCapabilitiesValidator (SPEC_14 slice #3).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Pure-data validator — no Agno,
no network. Reads DECLARED ProviderCapabilities (not runtime-verified).

Covers:
  - reasoning_effort rejected on a non-reasoning provider (mistral).
  - reasoning_effort accepted on a reasoning provider (openai).
  - thinking rejected on a non-reasoning provider.
  - caching intent rejected on a non-caching provider.
  - no intent → empty error list.
"""

from __future__ import annotations

import pytest

from yaml_agno.di.capabilities_validator import ModelCapabilitiesValidator
from yaml_agno.di.provider_capabilities import PROVIDER_REGISTRY
from yaml_agno.models.model_spec import ModelExpandedSpec


@pytest.mark.unit
def test_validate_reasoning_intent_rejected_on_non_reasoning_provider() -> None:
    """mistral (capabilities.reasoning == False) + reasoning_effort → error list non-empty."""
    spec = ModelExpandedSpec(provider="mistral", id="mistral-large", reasoning_effort="high")
    caps = PROVIDER_REGISTRY["mistral"].capabilities
    assert caps.reasoning is False
    errors = ModelCapabilitiesValidator.validate(spec, caps)
    assert len(errors) >= 1
    assert any("reasoning_effort" in e for e in errors)


@pytest.mark.unit
def test_validate_reasoning_intent_accepted_on_reasoning_provider() -> None:
    """openai (capabilities.reasoning == True) + reasoning_effort → empty error list."""
    spec = ModelExpandedSpec(provider="openai", id="gpt-4o", reasoning_effort="high")
    caps = PROVIDER_REGISTRY["openai"].capabilities
    assert caps.reasoning is True
    errors = ModelCapabilitiesValidator.validate(spec, caps)
    assert errors == []


@pytest.mark.unit
def test_validate_thinking_rejected_on_non_reasoning_provider() -> None:
    """thinking=True on a non-reasoning provider is flagged."""
    spec = ModelExpandedSpec(provider="mistral", id="mistral-large", thinking=True)
    caps = PROVIDER_REGISTRY["mistral"].capabilities
    errors = ModelCapabilitiesValidator.validate(spec, caps)
    assert any("thinking" in e for e in errors)


@pytest.mark.unit
def test_validate_caching_intent_rejected_on_non_caching_provider() -> None:
    """cache_response on a non-caching provider is flagged."""
    spec = ModelExpandedSpec(provider="mistral", id="mistral-large", cache_response=True)
    caps = PROVIDER_REGISTRY["mistral"].capabilities
    assert caps.caching is False
    errors = ModelCapabilitiesValidator.validate(spec, caps)
    assert any("caching" in e for e in errors)


@pytest.mark.unit
def test_validate_no_intent_returns_empty_list() -> None:
    """A bare spec with no reasoning/caching intent produces no errors."""
    spec = ModelExpandedSpec(provider="mistral", id="mistral-large")
    caps = PROVIDER_REGISTRY["mistral"].capabilities
    errors = ModelCapabilitiesValidator.validate(spec, caps)
    assert errors == []
