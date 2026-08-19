"""Unit tests for ``AuthorizationAdapter`` — fail-fast authorization build.

SPEC: ``agentos-authorization-build`` (7 requirements, 27 scenarios) — the
build contract that kills the R1 declarative fail-open (VQ011, D-F1-10).

Contract rules under test:
    - Whitelist: ONLY the 6 settable fields map from ``settings.config``;
      ``user_isolation`` is an adapter-owned invariant (always ``True``).
    - ``basic_auth`` present while enabled → ``AuthorizationBuildError``
      (no sink in agno 2.8.7) with pointer to ``BasicAuthMiddleware``.
    - Unknown key → ``AuthorizationBuildError`` listing the 7 fields.
    - Whitelist check runs BEFORE secret resolution.
    - Disabled guard wins over every rejection → ``(False, None)``.
    - ``${SECRET:KEY}`` resolves ONLY on whitelisted keys; ``KeyError`` or
      ``None`` from the resolver → ``AuthorizationBuildError``.

Strict TDD: RED → GREEN. Contract assertions check CONTENT (values), never
mere existence (Req 6).
"""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from yaml_agno.agentos.authorization_adapter import (
    AuthorizationAdapter,
    AuthorizationBuildError,
)
from yaml_agno.models.config.agentos_config import AuthorizationSettings

pytestmark = pytest.mark.unit

# agno 2.8.7 AuthorizationConfig accepts EXACTLY these 7 fields.
_SUPPORTED_FIELDS = (
    "verification_keys",
    "jwks_file",
    "algorithm",
    "verify_audience",
    "audience",
    "admin_scope",
    "user_isolation",
)


# ═══════════════════════════════════════════════════════════════════════════
# Req 1 — Whitelist mapping
# ═══════════════════════════════════════════════════════════════════════════


class TestWhitelist:
    """Req 1: only whitelisted keys map; everything else fails fast."""

    def test_valid_config_maps_every_field(self, mocker: MockerFixture) -> None:
        """All 6 settable fields pass through unchanged to the config."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "verification_keys": ["vk-1", "vk-2"],
                "jwks_file": "/etc/agentos/jwks.json",
                "algorithm": "HS256",
                "verify_audience": True,
                "audience": "agentos-api",
                "admin_scope": "agentos:admin",
            },
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_not_called()
        assert cfg.verification_keys == ["vk-1", "vk-2"]
        assert cfg.jwks_file == "/etc/agentos/jwks.json"
        assert cfg.algorithm == "HS256"
        assert cfg.verify_audience is True
        assert cfg.audience == "agentos-api"
        assert cfg.admin_scope == "agentos:admin"

    def test_unknown_key_rejected(self, mocker: MockerFixture) -> None:
        """Unknown key raises; the message names it and lists all 7 fields."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(enabled=True, config={"foo": 1})

        with pytest.raises(AuthorizationBuildError) as exc_info:
            adapter.build(settings)

        message = str(exc_info.value)
        assert "foo" in message
        for field in _SUPPORTED_FIELDS:
            assert field in message

    def test_whitelist_error_wins_over_secret(self, mocker: MockerFixture) -> None:
        """Unknown key with a secret ref reports the key, never resolves."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"foo": "${SECRET:JWT_SIGNING_KEY}"},
        )

        with pytest.raises(AuthorizationBuildError, match="foo"):
            adapter.build(settings)

        sm.assert_not_called()

    def test_empty_config_dict_valid(self, mocker: MockerFixture) -> None:
        """Empty config dict builds with the user_isolation invariant applied."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(enabled=True, config={})

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_not_called()
        assert cfg.user_isolation is True

    def test_none_config_valid(self, mocker: MockerFixture) -> None:
        """None config builds with the user_isolation invariant applied."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(enabled=True, config=None)

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_not_called()
        assert cfg.user_isolation is True

    def test_disabled_guard_wins(self, mocker: MockerFixture) -> None:
        """enabled=False → (False, None) even with an unknown key present."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(enabled=False, config={"foo": 1})

        enabled, cfg = adapter.build(settings)

        assert enabled is False
        assert cfg is None
        sm.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Req 2 — basic_auth rejection (no sink in agno 2.8.7)
# ═══════════════════════════════════════════════════════════════════════════


class TestBasicAuthRejection:
    """Req 2: basic_auth is rejected by field presence, not content."""

    def test_basic_auth_rejected(self, mocker: MockerFixture) -> None:
        """Non-empty basic_auth while enabled → actionable error."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            basic_auth={"admin": "s3cr3t-pw"},
        )

        with pytest.raises(AuthorizationBuildError) as exc_info:
            adapter.build(settings)

        message = str(exc_info.value)
        assert "basic_auth" in message
        assert "agno 2.8.7" in message
        assert "BasicAuthMiddleware" in message

    def test_empty_basic_auth_rejected(self, mocker: MockerFixture) -> None:
        """Empty basic_auth dict is still rejected (presence, not content)."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(enabled=True, basic_auth={})

        with pytest.raises(AuthorizationBuildError, match="basic_auth"):
            adapter.build(settings)

    def test_disabled_guard_wins_over_basic_auth(self, mocker: MockerFixture) -> None:
        """enabled=False → (False, None), no basic_auth rejection."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=False,
            basic_auth={"admin": "s3cr3t-pw"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is False
        assert cfg is None
        sm.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Req 3 — user_isolation invariant (adapter-owned, never settable from YAML)
# ═══════════════════════════════════════════════════════════════════════════


class TestUserIsolationInvariant:
    """Req 3: user_isolation is always True; explicit override is rejected."""

    def test_user_isolation_invariant_applied(self, mocker: MockerFixture) -> None:
        """Key absent → cfg.user_isolation is True."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"algorithm": "HS256"},
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        assert cfg.user_isolation is True

    @pytest.mark.parametrize("value", [True, False])
    def test_user_isolation_override_rejected(
        self, mocker: MockerFixture, value: bool
    ) -> None:
        """Explicit user_isolation (any value) → invariant error."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"user_isolation": value, "algorithm": "HS256"},
        )

        with pytest.raises(AuthorizationBuildError) as exc_info:
            adapter.build(settings)

        message = str(exc_info.value)
        assert "user_isolation" in message
        assert "invariant" in message


# ═══════════════════════════════════════════════════════════════════════════
# Req 4 — Secret resolution restricted to whitelisted keys
# ═══════════════════════════════════════════════════════════════════════════


class TestSecretResolution:
    """Req 4: ${SECRET:KEY} resolves only on whitelisted keys."""

    def test_secret_resolved_on_whitelisted_key(self, mocker: MockerFixture) -> None:
        """Real whitelisted key: verification_keys resolves; algorithm stays."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(
            side_effect=lambda key: {"JWT_SIGNING_KEY": "hush-hush"}[key]
        )
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "algorithm": "HS256",
                "verification_keys": ["${SECRET:JWT_SIGNING_KEY}"],
            },
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        assert cfg.verification_keys == ["hush-hush"]
        assert cfg.algorithm == "HS256"

    def test_mixed_secret_and_nonsecret(self, mocker: MockerFixture) -> None:
        """Secret refs resolved; non-secret whitelisted values pass through."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=lambda key: {"JWT_SIGNING_KEY": "s3cret"}[key])
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "algorithm": "HS256",
                "verification_keys": ["${SECRET:JWT_SIGNING_KEY}"],
            },
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_called_once_with("JWT_SIGNING_KEY")
        assert cfg.verification_keys == ["s3cret"]
        assert cfg.algorithm == "HS256"

    def test_unresolvable_secret_raises(self, mocker: MockerFixture) -> None:
        """Secret manager raises KeyError → error naming the key."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(side_effect=KeyError("MISSING_KEY"))
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"verification_keys": ["${SECRET:MISSING_KEY}"]},
        )

        with pytest.raises(AuthorizationBuildError, match="MISSING_KEY"):
            adapter.build(settings)

    def test_resolver_none_raises(self, mocker: MockerFixture) -> None:
        """Secret manager returns None → error (no None leaks into config)."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(return_value=None)
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={"algorithm": "${SECRET:NULL_KEY}"},
        )

        with pytest.raises(AuthorizationBuildError, match="NULL_KEY"):
            adapter.build(settings)

    def test_multiple_secret_refs_in_same_config(self, mocker: MockerFixture) -> None:
        """Multiple ${SECRET:...} on whitelisted keys — all resolved."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock(
            side_effect=lambda key: {
                "JWT_SIGNING_KEY": "jwts3cret",
                "ADMIN_SCOPE_KEY": "agentos:admin",
            }[key],
        )
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "verification_keys": ["${SECRET:JWT_SIGNING_KEY}"],
                "admin_scope": "${SECRET:ADMIN_SCOPE_KEY}",
            },
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        assert sm.call_count == 2
        assert cfg.verification_keys == ["jwts3cret"]
        assert cfg.admin_scope == "agentos:admin"


# ═══════════════════════════════════════════════════════════════════════════
# Req 6 — Contract tests assert content (T007e rewrite)
# ═══════════════════════════════════════════════════════════════════════════


class TestNonSecretPassthrough:
    """Req 6: valid build asserts CONTENT, not mere existence."""

    def test_nonsecret_values_passthrough(self, mocker: MockerFixture) -> None:
        """Plain whitelisted values forwarded; every field asserted by content."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=True,
            config={
                "algorithm": "HS256",
                "verification_keys": ["vk-1"],
                "verify_audience": True,
            },
        )

        enabled, cfg = adapter.build(settings)

        assert enabled is True
        sm.assert_not_called()
        assert cfg.user_isolation is True
        assert cfg.algorithm == "HS256"
        assert cfg.verification_keys == ["vk-1"]
        assert cfg.verify_audience is True


# ═══════════════════════════════════════════════════════════════════════════
# T007a — Disabled passthrough (guard wins over every rejection)
# ═══════════════════════════════════════════════════════════════════════════


class TestDisabledPassthrough:
    """T007a: When disabled, build() returns (False, None) without secret calls."""

    def test_disabled_returns_early_no_secret_call(self, mocker: MockerFixture) -> None:
        """enabled=False with a config dict → (False, None), no resolution."""
        from yaml_agno.agentos.authorization_adapter import AuthorizationAdapter

        sm = mocker.Mock()
        adapter = AuthorizationAdapter(secret_manager=sm)
        settings = AuthorizationSettings(
            enabled=False,
            config={"verification_keys": ["${SECRET:X}"]},
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
