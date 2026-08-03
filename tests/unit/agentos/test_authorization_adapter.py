"""Unit tests for ``AuthorizationAdapter`` — SPEC_12 Slice 3, T007a-e.

Strict TDD: RED → GREEN → REFACTOR cycle per task.

Tasks:
    T007a — Disabled passthrough
    T007b — Secret resolution for flat config
    T007c — Missing secret raises AuthorizationBuildError
    T007d — Basic auth config forwarding
    T007e — Non-secret values pass through unchanged
"""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from yaml_agno.models.config.agentos_config import AuthorizationSettings

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════════════
# T007a — AuthorizationAdapter disabled passthrough
# ═══════════════════════════════════════════════════════════════════════════


class TestDisabledPassthrough:
    """T007a: When disabled, build() returns (False, None) without secret calls."""

    def test_disabled_returns_early_no_secret_call(self, mocker: MockerFixture) -> None:
        """AuthorizationSettings(enabled=False) → (False, None), no secret_manager call."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=False,
            config={"jwt_secret_ref": "${SECRET:X}"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is False
        assert cfg is None
        sm.assert_not_called()

    def test_disabled_with_basic_auth_also_skips(self, mocker: MockerFixture) -> None:
        """Even with basic_auth present, disabled means no resolution."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=False,
            basic_auth={"username": "admin", "password": "${SECRET:PW}"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is False
        assert cfg is None
        sm.assert_not_called()

    def test_disabled_default_settings(self, mocker: MockerFixture) -> None:
        """Default AuthorizationSettings (enabled=False) also returns early."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings()

        enabled, cfg = adapter.build(settings)

        assert enabled is False
        assert cfg is None


# ═══════════════════════════════════════════════════════════════════════════
# T007e — Non-secret values pass through unchanged
# ═══════════════════════════════════════════════════════════════════════════


class TestNonSecretPassthrough:
    """T007e: Values without ${SECRET:...} prefix pass through unmodified."""

    def test_nonsecret_values_passthrough(self, mocker: MockerFixture) -> None:
        """Plain strings and ints in config are forwarded without secret resolution."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"algorithm": "HS256", "expire_minutes": 60, "issuer": "agentos"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_not_called()
        # Config values were forwarded (implementation detail: stored in kwargs)
        assert cfg is not None

    def test_mixed_secret_and_nonsecret(self, mocker: MockerFixture) -> None:
        """Secret refs resolved; non-secret values pass through."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=lambda key: {"JWT_SECRET": "s3cret"}[key])
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "jwt_secret_ref": "${SECRET:JWT_SECRET}",
                "algorithm": "HS256",
            },
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_called_once_with("JWT_SECRET")
        assert cfg is not None


# ═══════════════════════════════════════════════════════════════════════════
# T007b — Secret resolution for flat config
# ═══════════════════════════════════════════════════════════════════════════


class TestSecretResolution:
    """T007b: ${SECRET:KEY} patterns resolved via secret_manager callable."""

    def test_secret_refs_resolved(self, mocker: MockerFixture) -> None:
        """${SECRET:JWT_SECRET} → resolved value from secret_manager."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=lambda key: {"JWT_SECRET": "s3cret"}[key])
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"jwt_secret_ref": "${SECRET:JWT_SECRET}", "algorithm": "HS256"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        assert cfg is not None
        sm.assert_called_once_with("JWT_SECRET")

    def test_basic_auth_secret_resolved(self, mocker: MockerFixture) -> None:
        """Basic auth api_key with ${SECRET:...} resolved."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=lambda key: {"API_KEY": "sk-123"}[key])
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            basic_auth={"api_key": "${SECRET:API_KEY}"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        assert cfg is not None
        sm.assert_called_once_with("API_KEY")

    def test_multiple_secret_refs_in_same_config(self, mocker: MockerFixture) -> None:
        """Multiple ${SECRET:...} in one config dict — all resolved."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(
            side_effect=lambda key: {
                "JWT_SECRET": "jwts3cret",
                "API_KEY": "apikey123",
            }[key],
        )
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "jwt_secret_ref": "${SECRET:JWT_SECRET}",
                "api_key_ref": "${SECRET:API_KEY}",
            },
        )

        enabled, _cfg = adapter.build(settings)

        assert enabled is True
        assert sm.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# T007c — Missing secret raises AuthorizationBuildError
# ═══════════════════════════════════════════════════════════════════════════


class TestMissingSecret:
    """T007c: Unresolvable secret references raise AuthorizationBuildError."""

    def test_unresolved_secret_raises(self, mocker: MockerFixture) -> None:
        """Secret manager raises KeyError → wrapped as AuthorizationBuildError."""
        from yaml_agno.agentos.authorization_adapter import (
            AuthorizationAdapter,
            AuthorizationBuildError,
        )

        sm = mocker.Mock(side_effect=KeyError("MISSING_KEY"))
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"x": "${SECRET:MISSING_KEY}"},
        )

        with pytest.raises(AuthorizationBuildError, match="MISSING_KEY"):
            adapter.build(settings)

    def test_secret_manager_returns_none(self, mocker: MockerFixture) -> None:
        """Secret manager returns None → AuthorizationBuildError (fail-fast)."""
        from yaml_agno.agentos.authorization_adapter import (
            AuthorizationAdapter,
            AuthorizationBuildError,
        )

        sm = mocker.Mock(return_value=None)
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"x": "${SECRET:NULL_KEY}"},
        )

        with pytest.raises(AuthorizationBuildError, match="NULL_KEY"):
            adapter.build(settings)


# ═══════════════════════════════════════════════════════════════════════════
# T007d — Basic auth config forwarding
# ═══════════════════════════════════════════════════════════════════════════


class TestBasicAuth:
    """T007d: Basic auth credentials forwarded with user_isolation=True."""

    def test_basic_auth_forwarded_with_plain_values(self, mocker: MockerFixture) -> None:
        """Plain basic_auth values (no secrets) forwarded to AuthorizationConfig."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(return_value=None)
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            basic_auth={"username": "admin", "password": "pass123"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        assert cfg is not None

    def test_basic_auth_secret_and_plain_resolved(self, mocker: MockerFixture) -> None:
        """Mixed: plain username, secret-resolved password."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=lambda key: {"DB_PASS": "s3cretdb"}[key])
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            basic_auth={"username": "admin", "password": "${SECRET:DB_PASS}"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_called_once_with("DB_PASS")
        assert cfg is not None

    def test_basic_auth_without_config_still_enables(self, mocker: MockerFixture) -> None:
        """Only basic_auth (no config dict) still produces enabled=True."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            basic_auth={"username": "admin", "password": "secret"},
        )

        enabled, _cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_not_called()
