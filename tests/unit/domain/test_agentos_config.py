"""RED tests for AgentOSConfig schema — Slice 1, PR 1.

These tests reference ``yaml_agno.models.config.agentos_config.AgentOSConfig``
which does NOT exist yet (RED phase). They cover the SPEC_12 §2.2 scenarios:

    1. Golden path — valid config validates, to_agno_kwargs() produces correct dict
    2. At-least-one-target validator rejects empty agents/teams/workflows
    3. CORS wildcard forbidden under RBAC authorization
    4. CORS wildcard allowed without RBAC
    5. to_agno_kwargs excludes None-valued fields
    6. to_agno_kwargs includes explicit False booleans
    7. Default values via default_factory
    8. Extra fields forbidden via ConfigDict(extra="forbid")
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yaml_agno.models.config.agentos_config import AgentOSConfig, AuthorizationSettings

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. Golden path
# ---------------------------------------------------------------------------

class TestAgentOSConfigGoldenPath:
    """Valid configs are accepted and to_agno_kwargs() produces expected output."""

    def test_valid_config_does_not_raise(self) -> None:
        """A config with name + agents validates cleanly."""
        cfg = AgentOSConfig(
            name="research-os",
            agents=["researcher", "summarizer"],
            teams=["research_team"],
        )
        assert cfg.name == "research-os"
        assert cfg.agents == ["researcher", "summarizer"]
        assert cfg.teams == ["research_team"]

    def test_to_agno_kwargs_golden_path(self) -> None:
        """to_agno_kwargs() returns expected keys for a valid config.

        Per SPEC_12 §2.2 scenario: None-valued fields (db, config, base_app,
        lifespan, cors_allowed_origins, knowledge) are ABSENT from the dict.
        """
        cfg = AgentOSConfig(
            name="research-os",
            agents=["researcher"],
            teams=["research_team"],
        )
        kwargs = cfg.to_agno_kwargs()

        # Present keys (have non-None values)
        assert "name" in kwargs
        assert "agents" in kwargs
        assert "teams" in kwargs
        assert "workflows" in kwargs
        assert "a2a_interface" in kwargs
        assert "auto_provision_dbs" in kwargs
        assert "run_hooks_in_background" in kwargs
        assert "tracing" in kwargs

        # Absent keys (fields whose default value is None)
        assert "db" not in kwargs
        assert "config" not in kwargs
        assert "base_app" not in kwargs
        assert "lifespan" not in kwargs
        assert "cors_allowed_origins" not in kwargs


# ---------------------------------------------------------------------------
# 2. At-least-one-target validator
# ---------------------------------------------------------------------------

class TestAgentOSConfigAtLeastOneTarget:
    """Validator rejects configs with no agents, teams, OR workflows."""

    def test_empty_targets_raises_valueerror(self) -> None:
        """When all three target lists are empty, validation MUST fail."""
        with pytest.raises(ValidationError) as exc:
            AgentOSConfig(name="empty-os", agents=[], teams=[], workflows=[])
        # The message must reference "at least one" per SPEC_12 §2.2 validator 1.
        assert "at least one" in str(exc.value)


# ---------------------------------------------------------------------------
# 3 & 4. CORS wildcard validator
# ---------------------------------------------------------------------------

class TestAgentOSConfigCorsWildcard:
    """CORS wildcard (*) behaviour under RBAC authorization."""

    def test_cors_wildcard_forbidden_under_rbac(self) -> None:
        """When authorization.enabled is True, cors_allowed_origins MUST NOT include '*'."""
        with pytest.raises(ValidationError) as exc:
            AgentOSConfig(
                name="secure-os",
                agents=["a"],
                authorization=AuthorizationSettings(enabled=True),
                cors_allowed_origins=["*"],
            )
        assert "CORS" in str(exc.value) or "cors" in str(exc.value) or "RBAC" in str(exc.value) or "wildcard" in str(exc.value)

    def test_cors_wildcard_allowed_without_rbac(self) -> None:
        """When authorization is disabled, '*' in cors_allowed_origins is fine."""
        cfg = AgentOSConfig(
            name="dev-os",
            agents=["a"],
            authorization=AuthorizationSettings(enabled=False),
            cors_allowed_origins=["*"],
        )
        assert cfg.cors_allowed_origins == ["*"]


# ---------------------------------------------------------------------------
# 5 & 6. to_agno_kwargs() edge cases
# ---------------------------------------------------------------------------

class TestAgentOSConfigToAgnoKwargs:
    """to_agno_kwargs() contract: exclude None, include False, exclude_unset=False."""

    def test_to_agno_kwargs_excludes_none(self) -> None:
        """None-valued fields are ABSENT from the dict (exclude_none=True)."""
        cfg = AgentOSConfig(name="minimal", agents=["a"])
        kwargs = cfg.to_agno_kwargs()
        # db, cors_allowed_origins, base_app are all None by default → excluded
        assert "db" not in kwargs
        assert "cors_allowed_origins" not in kwargs
        assert "base_app" not in kwargs
        assert "lifespan" not in kwargs
        assert "config" not in kwargs

    def test_to_agno_kwargs_includes_false_booleans(self) -> None:
        """Explicit False booleans ARE forwarded (exclude_unset=False means
        they're treated as set, not excluded)."""
        cfg = AgentOSConfig(
            name="explicit-false",
            agents=["a"],
            a2a_interface=False,
            run_hooks_in_background=False,
            tracing=False,
        )
        kwargs = cfg.to_agno_kwargs()
        assert kwargs["a2a_interface"] is False
        assert kwargs["run_hooks_in_background"] is False
        assert kwargs["tracing"] is False


# ---------------------------------------------------------------------------
# 7. Defaults via default_factory
# ---------------------------------------------------------------------------

class TestAgentOSConfigDefaults:
    """Nested settings models are constructed via default_factory."""

    def test_defaults_applied_when_fields_omitted(self) -> None:
        """Omitted nested settings get their default_factory instances."""
        cfg = AgentOSConfig(name="defaults-os", agents=["a"])
        assert cfg.authorization.enabled is False
        assert cfg.mcp.enabled is False
        assert cfg.scheduler.enabled is False
        assert cfg.scheduler.poll_interval == 15
        assert cfg.resync.enabled is False
        assert cfg.resync.watch is False
        assert cfg.resync.debounce_ms == 500

    def test_nested_settings_are_independent_instances(self) -> None:
        """Each AgentOSConfig gets its OWN nested settings instances (no shared state)."""
        cfg1 = AgentOSConfig(name="os1", agents=["a"])
        cfg2 = AgentOSConfig(name="os2", agents=["b"])
        assert cfg1.authorization is not cfg2.authorization
        assert cfg1.scheduler is not cfg2.scheduler


# ---------------------------------------------------------------------------
# 8. Extra fields forbidden
# ---------------------------------------------------------------------------

class TestAgentOSConfigExtraForbidden:
    """ConfigDict(extra='forbid') rejects unknown top-level keys."""

    def test_extra_fields_forbidden(self) -> None:
        """Providing an undeclared field raises ValidationError."""
        with pytest.raises(ValidationError) as exc:
            AgentOSConfig(name="bad", agents=["a"], unknown_field=42)
        assert "unknown_field" in str(exc.value)
