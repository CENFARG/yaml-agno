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
