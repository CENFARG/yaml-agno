"""Unit tests for the YamlAgnoSettings Pydantic V2 schema (SPEC_23 §2.2).

RED-GREEN strict TDD. Tagged @pytest.mark.unit.

Covers (TASK_231, TASK_2314):
  - max_concurrent_agents=0 is rejected (Field ge=1 le=500).
  - unknown top-level keys are rejected (extra="forbid").
  - auth_mode=basic in prod is rejected (cross-field validator).
  - a fully-valid settings payload passes.
  - normalize_env maps local->dev and rejects unknown envs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yaml_agno.config.schemas import (
    AppConfig,
    FlagDefaults,
    ObservabilityConfig,
    PersistenceConfig,
    RuntimeConfig,
    SecurityConfig,
    YamlAgnoSettings,
    normalize_env,
)

VALID_SETTINGS = {
    "app": {"name": "yaml-agno", "env": "dev"},
    "runtime": {"max_concurrent_agents": 10, "request_timeout_s": 30},
    "persistence": {
        "pool_size": 5,
        "pool_max_overflow": 2,
        "statement_timeout_ms": 5000,
    },
    "observability": {
        "otlp_endpoint": "http://otel-collector:4317",
        "sample_rate": 0.1,
    },
    "security": {"auth_mode": "jwt", "token_ttl_minutes": 15},
    "flags": {"enable_experimental_rag": False},
}


@pytest.mark.unit
def test_rejects_zero_concurrent_agents() -> None:
    """TASK_231 — max_concurrent_agents=0 MUST fail validation (ge=1)."""
    payload = {
        **VALID_SETTINGS,
        "runtime": {**VALID_SETTINGS["runtime"], "max_concurrent_agents": 0},
    }
    with pytest.raises(ValidationError):
        YamlAgnoSettings.model_validate(payload)


@pytest.mark.unit
def test_rejects_overflow_concurrent_agents() -> None:
    """max_concurrent_agents above 500 MUST fail validation (le=500)."""
    payload = {
        **VALID_SETTINGS,
        "runtime": {**VALID_SETTINGS["runtime"], "max_concurrent_agents": 501},
    }
    with pytest.raises(ValidationError):
        YamlAgnoSettings.model_validate(payload)


@pytest.mark.unit
def test_extra_forbidden_key_rejected() -> None:
    """TASK_2314 — an unknown top-level key MUST fail fast (extra=forbid)."""
    payload = {**VALID_SETTINGS, "unknown_section": {"a": 1}}
    with pytest.raises(ValidationError):
        YamlAgnoSettings.model_validate(payload)


@pytest.mark.unit
def test_extra_forbidden_nested_key_rejected() -> None:
    """extra=forbid also rejects unknown keys inside a section."""
    payload = {
        **VALID_SETTINGS,
        "runtime": {**VALID_SETTINGS["runtime"], "not_a_real_option": True},
    }
    with pytest.raises(ValidationError):
        YamlAgnoSettings.model_validate(payload)


@pytest.mark.unit
def test_basic_auth_forbidden_in_prod() -> None:
    """SPEC_23 §3 — auth_mode=basic in prod MUST raise a cross-field error."""
    payload = {
        **VALID_SETTINGS,
        "app": {"name": "yaml-agno", "env": "prod"},
        "security": {"auth_mode": "basic", "token_ttl_minutes": 15},
    }
    with pytest.raises(ValidationError, match="auth_mode=basic forbidden in prod"):
        YamlAgnoSettings.model_validate(payload)


@pytest.mark.unit
def test_jwt_auth_allowed_in_prod() -> None:
    """jwt in prod MUST pass the cross-field validator."""
    payload = {
        **VALID_SETTINGS,
        "app": {"name": "yaml-agno", "env": "prod"},
    }
    settings = YamlAgnoSettings.model_validate(payload)
    assert settings.security.auth_mode == "jwt"


@pytest.mark.unit
def test_accepts_valid_settings() -> None:
    """A fully-valid payload MUST validate and expose typed sections."""
    settings = YamlAgnoSettings.model_validate(VALID_SETTINGS)
    assert settings.app.name == "yaml-agno"
    assert settings.app.env == "dev"
    assert settings.runtime.max_concurrent_agents == 10
    assert settings.persistence.pool_size == 5
    assert settings.observability.sample_rate == 0.1
    assert settings.security.token_ttl_minutes == 15
    assert settings.flags.enable_experimental_rag is False


@pytest.mark.unit
def test_section_models_enforce_their_bounds() -> None:
    """Each section model enforces its own Pydantic bounds (SPEC_23 §2.2)."""
    with pytest.raises(ValidationError):
        RuntimeConfig(max_concurrent_agents=10, request_timeout_s=0)
    with pytest.raises(ValidationError):
        PersistenceConfig(pool_size=0, pool_max_overflow=1, statement_timeout_ms=5000)
    with pytest.raises(ValidationError):
        ObservabilityConfig(otlp_endpoint="http://x:4317", sample_rate=1.5)
    with pytest.raises(ValidationError):
        SecurityConfig(auth_mode="hmac", token_ttl_minutes=15)
    # AppConfig env pattern is dev|staging|prod (no local, no test).
    with pytest.raises(ValidationError):
        AppConfig(name="yaml-agno", env="local")
    # FlagDefaults default is False (fail-safe).
    assert FlagDefaults().enable_experimental_rag is False


@pytest.mark.unit
def test_normalize_env_maps_local_to_dev() -> None:
    """SPEC_23 §2.2 — core "local" MUST map to yaml-agno "dev" at the boundary."""
    assert normalize_env("local") == "dev"
    assert normalize_env("dev") == "dev"
    assert normalize_env("staging") == "staging"
    assert normalize_env("prod") == "prod"


@pytest.mark.unit
def test_normalize_env_rejects_unknown_values() -> None:
    """A value outside dev|staging|prod (after local->dev) MUST raise."""
    for bad in ("test", "qa", "", "PROD"):
        with pytest.raises(ValueError):
            normalize_env(bad)
