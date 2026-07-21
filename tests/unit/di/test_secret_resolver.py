"""Unit tests for SecretResolver + ConfigSecretResolver (SPEC_14 slice #3).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses the core-cenf
InMemoryConfigAdapter double — no os.environ, no network.

Covers:
  - ConfigSecretResolver reads ``secrets.<env_lower>`` from ConfigManager.
  - ConfigSecretResolver returns None when the key is absent.
  - ConfigSecretResolver structurally satisfies the SecretResolver Protocol.
"""

from __future__ import annotations

import pytest
from core_infrastructure.config.adapters.in_memory_config_adapter import (
    InMemoryConfigAdapter,
)

from yaml_agno.di.secret_resolver import ConfigSecretResolver, SecretResolver


@pytest.mark.unit
def test_config_secret_resolver_reads_secrets_namespace() -> None:
    """ConfigSecretResolver resolves ``OPENAI_API_KEY`` via ``secrets.openai_api_key``.

    The env name is lowercased to match typical YAML key conventions.
    """
    cfg = InMemoryConfigAdapter()
    cfg.set_value("secrets.openai_api_key", "sk-cfg")
    resolver = ConfigSecretResolver(cfg)
    assert resolver("OPENAI_API_KEY") == "sk-cfg"


@pytest.mark.unit
def test_config_secret_resolver_returns_none_when_key_missing() -> None:
    """A missing secrets namespace entry yields None (not an exception)."""
    cfg = InMemoryConfigAdapter()
    resolver = ConfigSecretResolver(cfg)
    assert resolver("OPENAI_API_KEY") is None


@pytest.mark.unit
def test_config_secret_resolver_satisfies_protocol() -> None:
    """ConfigSecretResolver structurally satisfies the SecretResolver Protocol."""
    cfg = InMemoryConfigAdapter()
    resolver = ConfigSecretResolver(cfg)
    assert isinstance(resolver, SecretResolver)


# ---------------------------------------------------------------------------
# FIX 4 (resolver-bootstrap-fix): ConfigSecretResolver MUST fall back to
# os.environ when ConfigManager returns None. Config remains authoritative;
# env is consulted only on a miss. SPEC_00 §9.3 bans os.environ in app code,
# but SecretResolver IS the infrastructure layer that abstracts env access.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_config_secret_resolver_falls_back_to_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIX 4 Scenario 4.1 — config miss + env present MUST return env value.

    Typical user workflow: set OPENROUTER_API_KEY in the shell, do not bother
    with a YAML secrets block. The resolver picks it up via os.environ.
    """
    cfg = InMemoryConfigAdapter()  # no secrets.* set
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")
    resolver = ConfigSecretResolver(cfg)
    assert resolver("OPENROUTER_API_KEY") == "sk-env"


@pytest.mark.unit
def test_config_secret_resolver_config_wins_over_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIX 4 Scenario 4.2 — config value MUST win when both config and env set.

    ConfigManager is authoritative. The env fallback only fires on a miss.
    """
    cfg = InMemoryConfigAdapter()
    cfg.set_value("secrets.openai_api_key", "sk-cfg")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    resolver = ConfigSecretResolver(cfg)
    assert resolver("OPENAI_API_KEY") == "sk-cfg"


@pytest.mark.unit
def test_config_secret_resolver_both_missing_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIX 4 Scenario 4.3 — config miss + env absent MUST return None."""
    cfg = InMemoryConfigAdapter()
    monkeypatch.delenv("MISSING_API_KEY", raising=False)
    resolver = ConfigSecretResolver(cfg)
    assert resolver("MISSING_API_KEY") is None
