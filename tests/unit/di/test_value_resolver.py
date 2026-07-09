"""RED tests for ValueResolver — fail until ``src/yaml_agno/di/value_resolver.py`` exists.

Verifies the abstraction that translates ``${provider.key}`` tokens (validated
by DIReference, SPEC_02) into the flat ``"provider.key" -> value`` dict that
``DIReference.resolve()`` consumes. MVP supports ``env.*`` only; other providers
raise ``NotImplementedError`` (deferred to SPEC_23). Tagged ``@pytest.mark.unit``.

Covers 6 scenarios from SPEC_01 §ValueResolver.
"""

from __future__ import annotations

import pytest

from yaml_agno.di.value_resolver import ValueResolver
from yaml_agno.models.value_objects.di_reference import DIReference


# ---------------------------------------------------------------------------
# Helper: construct an InMemoryConfigAdapter (the config adapter __init__ in
# the installed core-cenf v0.1.0 does not re-export the class).
# ---------------------------------------------------------------------------


def _config_with(initial_data: dict | None = None):
    from core_infrastructure.config.adapters.in_memory_config_adapter import (
        InMemoryConfigAdapter,
    )

    return InMemoryConfigAdapter(initial_data=initial_data)


# ---------------------------------------------------------------------------
# env provider scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_env_single_token() -> None:
    """${env.api_key} + config{api_key:'sk-x'} -> {'env.api_key': 'sk-x'}."""
    cfg = _config_with({"api_key": "sk-x"})
    vr = ValueResolver(cfg)
    ref = DIReference(template="${env.api_key}")
    result = vr.resolve(ref)
    assert result == {"env.api_key": "sk-x"}


@pytest.mark.unit
def test_resolve_env_feeds_direference_resolve_e2e() -> None:
    """ValueResolver.resolve(ref) -> DIReference.resolve(dict) end-to-end."""
    cfg = _config_with({"api_key": "sk-x"})
    vr = ValueResolver(cfg)
    ref = DIReference(template="key=${env.api_key}")
    resolved = vr.resolve(ref)
    final = ref.resolve(resolved)
    assert final == "key=sk-x"


# ---------------------------------------------------------------------------
# Deferred providers — must raise NotImplementedError (not silent None).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_db_raises_not_implemented() -> None:
    """db provider is deferred to SPEC_23 → NotImplementedError."""
    cfg = _config_with()
    vr = ValueResolver(cfg)
    ref = DIReference(template="${db.user_db.name}")
    with pytest.raises(NotImplementedError):
        vr.resolve(ref)


@pytest.mark.unit
def test_resolve_api_raises_not_implemented() -> None:
    """api provider is deferred to SPEC_23 → NotImplementedError."""
    cfg = _config_with()
    vr = ValueResolver(cfg)
    ref = DIReference(template="${api.foo.bar}")
    with pytest.raises(NotImplementedError):
        vr.resolve(ref)


@pytest.mark.unit
def test_resolve_file_raises_not_implemented() -> None:
    """file provider is deferred to SPEC_23 → NotImplementedError."""
    cfg = _config_with()
    vr = ValueResolver(cfg)
    ref = DIReference(template="${file.path.x}")
    with pytest.raises(NotImplementedError):
        vr.resolve(ref)


# ---------------------------------------------------------------------------
# Separation of concerns — ValueResolver is independent of AgnoResolver.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_value_resolver_independent_of_agno_resolver() -> None:
    """ValueResolver works with only a ConfigManager — no AgnoResolver needed."""
    cfg = _config_with({"api_key": "sk-x"})
    vr = ValueResolver(cfg)
    ref = DIReference(template="${env.api_key}")
    # This call never touches AgnoResolver; it resolves purely via config.
    result = vr.resolve(ref)
    assert result == {"env.api_key": "sk-x"}
