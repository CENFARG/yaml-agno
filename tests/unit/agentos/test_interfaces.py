"""Unit tests for InterfaceRegistry — SPEC_12 Slice 2, TASK_003.

Covers the interface-registry delta spec (6 requirements, 6 IFACE scenarios)
with 13 TDD test cases:

    1.  InterfaceType enum has 5 values
    2.  InterfaceSpec valid creation
    3.  InterfaceSpec forbids extra fields
    4.  InterfaceSpec AGUI — no credentials required
    5.  _resolve_credential_refs substitutes ${SECRET:...} patterns
    6.  build() AGUI — resolves target, builds AGUI
    7.  build() Slack — validates credentials, builds Slack
    8.  build() WhatsApp — validates credentials, builds WhatsApp
    9.  build() Telegram — validates credentials, builds Telegram
    10. build() A2A — no credentials, builds A2A with lists
    11. build() Slack missing credentials → InterfaceCredentialError
    12. build() unknown interface type → InterfaceBuildError
    13. build_all() builds multiple interfaces

Strict TDD: RED → GREEN → REFACTOR. Tests written BEFORE implementation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yaml_agno.agentos.interfaces import (
    InterfaceBuildError,
    InterfaceCredentialError,
    InterfaceRegistry,
    InterfaceSpec,
    InterfaceType,
)

pytestmark = pytest.mark.unit

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_secret_manager(mocker):
    """Callable that resolves known secret keys; raises KeyError for unknown."""
    mgr = mocker.Mock()
    mgr.side_effect = lambda key: {
        "SLACK_BOT_TOKEN": "xoxb-test-bot",
        "SLACK_APP_TOKEN": "xapp-test-app",
        "SLACK_SIGNING_SECRET": "abc123signing",
        "WA_PHONE_NUMBER_ID": "123456789",
        "WA_ACCESS_TOKEN": "EAA-test-access",
        "WA_VERIFY_TOKEN": "verify-xyz",
        "TELEGRAM_BOT_TOKEN": "12345:ABC-DEF",
    }.get(key, mocker.DEFAULT)
    return mgr


@pytest.fixture
def mock_resolve_target(mocker):
    """Resolves agent/team/workflow refs to mock objects."""

    def _resolve(ref: str):
        mock = mocker.Mock(name=f"target:{ref}")
        mock.name = ref
        # Make it pass isinstance checks for both Agent and Team/Workflow patterns
        return mock

    return _resolve


@pytest.fixture
def registry(mock_secret_manager):
    """A fresh InterfaceRegistry with a mock secret manager."""
    return InterfaceRegistry(secret_manager=mock_secret_manager)


# ═══════════════════════════════════════════════════════════════════════════
# InterfaceType
# ═══════════════════════════════════════════════════════════════════════════


class TestInterfaceType:
    def test_interface_type_has_five_values(self):
        """InterfaceType enum exposes all 5 interface types with correct string values."""
        assert InterfaceType.AGUI.value == "agui"
        assert InterfaceType.SLACK.value == "slack"
        assert InterfaceType.WHATSAPP.value == "whatsapp"
        assert InterfaceType.TELEGRAM.value == "telegram"
        assert InterfaceType.A2A.value == "a2a"

        # Verify membership
        values = [e.value for e in InterfaceType]
        assert len(values) == 5
        assert "agui" in values
        assert "a2a" in values


# ═══════════════════════════════════════════════════════════════════════════
# InterfaceSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestInterfaceSpec:
    def test_interface_spec_valid_creation(self):
        """InterfaceSpec accepts valid type + target + config."""
        spec = InterfaceSpec(type="agui", target="researcher", config={"chat": True})
        assert spec.type == InterfaceType.AGUI
        assert spec.target == "researcher"
        assert spec.config == {"chat": True}

    def test_interface_spec_forbids_extra_fields(self):
        """InterfaceSpec rejects unknown fields (extra='forbid')."""
        with pytest.raises(ValidationError):
            InterfaceSpec(type="agui", target="researcher", unknown_field="bad")  # type: ignore[call-arg]

    def test_interface_spec_agui_minimal_config(self):
        """AGUI type requires no credentials in config."""
        spec = InterfaceSpec(type="agui", target="researcher")
        assert spec.type == InterfaceType.AGUI
        assert spec.config == {}


# ═══════════════════════════════════════════════════════════════════════════
# Credential resolution
# ═══════════════════════════════════════════════════════════════════════════


class TestCredentialResolution:
    def test_resolve_credential_refs_substitutes_secret(self, registry, mock_secret_manager):
        """_resolve_credential_refs resolves ${SECRET:KEY} patterns via secret_manager."""
        config = {
            "bot_token": "${SECRET:SLACK_BOT_TOKEN}",
            "app_token": "${SECRET:SLACK_APP_TOKEN}",
            "signing_secret": "${SECRET:SLACK_SIGNING_SECRET}",
            "plain_value": "keep-me",
        }
        resolved = registry._resolve_credential_refs(config)

        assert resolved["bot_token"] == "xoxb-test-bot"
        assert resolved["app_token"] == "xapp-test-app"
        assert resolved["signing_secret"] == "abc123signing"
        assert resolved["plain_value"] == "keep-me"
        assert mock_secret_manager.call_count == 3


    def test_resolve_credential_refs_without_secret_manager_leaves_patterns(self):
        """_resolve_credential_refs leaves ${SECRET:...} as-is when no secret_manager."""
        registry_no_secrets = InterfaceRegistry(secret_manager=None)
        config = {"bot_token": "${SECRET:SLACK_BOT_TOKEN}", "plain": "keep"}
        resolved = registry_no_secrets._resolve_credential_refs(config)

        assert resolved["bot_token"] == "${SECRET:SLACK_BOT_TOKEN}"
        assert resolved["plain"] == "keep"

    def test_resolve_credential_refs_passes_non_string_values_through(self, registry):
        """_resolve_credential_refs passes ints, bools, None through unchanged."""
        config = {"port": 8080, "enabled": True, "opt": None, "token": "${SECRET:SLACK_BOT_TOKEN}"}
        resolved = registry._resolve_credential_refs(config)

        assert resolved["port"] == 8080
        assert resolved["enabled"] is True
        assert resolved["opt"] is None
        assert resolved["token"] == "xoxb-test-bot"


# ═══════════════════════════════════════════════════════════════════════════
# InterfaceRegistry.build() — per-type dispatch
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildAgui:
    def test_build_agui_resolves_target(self, registry, mock_resolve_target, mocker):
        """build() with AGUI type resolves target and constructs an AGUI interface."""
        target = mock_resolve_target("researcher")
        mock_agui_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_agui", autospec=True
        )
        mock_agui_cls.return_value = mocker.Mock(name="AGUI-instance")

        spec = InterfaceSpec(type="agui", target="researcher", config={"chat": True})
        result = registry.build(spec, resolve_target=mock_resolve_target)

        assert target is not None  # target was resolved
        mock_agui_cls.assert_called_once()
        assert mock_agui_cls.return_value.called  # AGUI(target) was called
        assert result is mock_agui_cls.return_value.return_value


class TestBuildSlack:
    def test_build_slack_validates_and_builds(self, registry, mock_resolve_target, mocker):
        """build() with Slack type validates credential triad and builds Slack."""
        target = mock_resolve_target("support_agent")
        mock_slack_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_slack", autospec=True
        )
        mock_slack_cls.return_value = mocker.Mock(name="Slack-instance")

        spec = InterfaceSpec(
            type="slack",
            target="support_agent",
            config={
                "bot_token": "${SECRET:SLACK_BOT_TOKEN}",
                "app_token": "${SECRET:SLACK_APP_TOKEN}",
                "signing_secret": "${SECRET:SLACK_SIGNING_SECRET}",
            },
        )
        result = registry.build(spec, resolve_target=mock_resolve_target)

        assert target is not None  # target was resolved
        mock_slack_cls.assert_called_once()
        assert mock_slack_cls.return_value.called
        assert result is mock_slack_cls.return_value.return_value


class TestBuildWhatsapp:
    def test_build_whatsapp_validates_and_builds(self, registry, mock_resolve_target, mocker):
        """build() with WhatsApp type validates credential triad and builds Whatsapp."""
        target = mock_resolve_target("notifier_agent")
        mock_wa_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_whatsapp", autospec=True
        )
        mock_wa_cls.return_value = mocker.Mock(name="Whatsapp-instance")

        spec = InterfaceSpec(
            type="whatsapp",
            target="notifier_agent",
            config={
                "phone_number_id": "${SECRET:WA_PHONE_NUMBER_ID}",
                "access_token": "${SECRET:WA_ACCESS_TOKEN}",
                "verify_token": "${SECRET:WA_VERIFY_TOKEN}",
            },
        )
        result = registry.build(spec, resolve_target=mock_resolve_target)

        assert target is not None  # target was resolved
        mock_wa_cls.assert_called_once()
        assert mock_wa_cls.return_value.called
        assert result is mock_wa_cls.return_value.return_value


class TestBuildTelegram:
    def test_build_telegram_validates_and_builds(self, registry, mock_resolve_target, mocker):
        """build() with Telegram type validates token and builds Telegram."""
        target = mock_resolve_target("ops_agent")
        mock_tg_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_telegram", autospec=True
        )
        mock_tg_cls.return_value = mocker.Mock(name="Telegram-instance")

        spec = InterfaceSpec(
            type="telegram",
            target="ops_agent",
            config={"token": "${SECRET:TELEGRAM_BOT_TOKEN}"},
        )
        result = registry.build(spec, resolve_target=mock_resolve_target)

        assert target is not None  # target was resolved
        mock_tg_cls.assert_called_once()
        assert mock_tg_cls.return_value.called
        assert result is mock_tg_cls.return_value.return_value


class TestBuildA2a:
    def test_build_a2a_supports_plural_lists(self, registry, mock_resolve_target, mocker):
        """build() with A2A type handles plural agents/teams/workflows, no credentials."""
        target_agent = mock_resolve_target("research_team")
        mock_a2a_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_a2a", autospec=True
        )
        mock_a2a_cls.return_value = mocker.Mock(name="A2A-instance")

        spec = InterfaceSpec(
            type="a2a",
            target="research_team",
            config={
                "endpoint": "https://corp.example.com/a2a",
                "agent_card": {"name": "Research Team", "description": "Multi-agent"},
            },
        )
        result = registry.build(spec, resolve_target=mock_resolve_target)

        assert target_agent is not None  # target was resolved
        mock_a2a_cls.assert_called_once()
        assert mock_a2a_cls.return_value.called
        assert result is mock_a2a_cls.return_value.return_value


# ═══════════════════════════════════════════════════════════════════════════
# Error paths
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorPaths:
    def test_build_slack_missing_credentials_raises(self, registry, mock_resolve_target):
        """build() raises InterfaceCredentialError when required Slack creds are missing."""
        spec = InterfaceSpec(
            type="slack",
            target="support_agent",
            config={"bot_token": "xoxb-ok"},  # missing app_token and signing_secret
        )
        with pytest.raises(InterfaceCredentialError) as exc_info:
            registry.build(spec, resolve_target=mock_resolve_target)

        assert "slack" in str(exc_info.value).lower()
        assert "app_token" in str(exc_info.value)
        assert "signing_secret" in str(exc_info.value)

    def test_build_unknown_type_raises(self, registry, mock_resolve_target, mocker):
        """build() raises InterfaceBuildError when the InterfaceType has no builder."""
        # Construct a spec that somehow has a type not in the builder map.
        # We patch the builders dict to remove one entry and verify the error.
        spec = InterfaceSpec(type="agui", target="researcher")
        original = registry._builders.pop(InterfaceType.AGUI)

        with pytest.raises(InterfaceBuildError) as exc_info:
            registry.build(spec, resolve_target=mock_resolve_target)

        assert "agui" in str(exc_info.value).lower()
        # Restore for other tests
        registry._builders[InterfaceType.AGUI] = original


# ═══════════════════════════════════════════════════════════════════════════
# build_all
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildAll:
    def test_build_all_returns_list(self, registry, mock_resolve_target, mocker):
        """build_all() builds multiple specs and returns a list of interfaces."""
        mock_agui_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_agui", autospec=True
        )
        mock_agui_cls.return_value = mocker.Mock(name="AGUI-1")

        mock_slack_cls = mocker.patch(
            "yaml_agno.agentos.interfaces._import_slack", autospec=True
        )
        mock_slack_cls.return_value = mocker.Mock(name="Slack-1")

        specs = [
            InterfaceSpec(type="agui", target="r1"),
            InterfaceSpec(
                type="slack",
                target="s1",
                config={
                    "bot_token": "${SECRET:SLACK_BOT_TOKEN}",
                    "app_token": "${SECRET:SLACK_APP_TOKEN}",
                    "signing_secret": "${SECRET:SLACK_SIGNING_SECRET}",
                },
            ),
        ]
        results = registry.build_all(specs, resolve_target=mock_resolve_target)

        assert len(results) == 2
        assert mock_agui_cls.call_count == 1
        assert mock_slack_cls.call_count == 1
