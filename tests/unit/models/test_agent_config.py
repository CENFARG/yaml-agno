"""RED tests for AgentConfig schema.

These tests reference ``yaml_agno.models.config.agent_config.AgentConfig`` which
does NOT exist yet (RED). They cover the spec scenarios for:
    - GREEN minimal instantiation + 9 opaque slots accept dicts
    - RED invalid model format (no-slash / empty provider / empty model_id)
    - RED invalid name characters
    - RED extra field forbidden
    - RED user_id absent (not in model_fields)
"""

import pytest
from pydantic import ValidationError

from yaml_agno.models.config.agent_config import AgentConfig

pytestmark = pytest.mark.unit


class TestAgentConfigGoldenPaths:
    """GREEN scenarios — valid configs accepted."""

    def test_agent_config_creation_minimal(self) -> None:
        """Minimal valid instantiation: name + model."""
        cfg = AgentConfig(name="my_agent", model="openai/gpt-4o")
        assert cfg.name == "my_agent"
        assert cfg.model == "openai/gpt-4o"

    def test_agent_config_creation_with_hyphen(self) -> None:
        """name with hyphen and digits is valid per [A-Za-z0-9_-]+."""
        cfg = AgentConfig(name="agent-01", model="anthropic/claude-3-5-sonnet")
        assert cfg.name == "agent-01"

    def test_agent_config_all_nine_opaque_slots_accept_dicts(self) -> None:
        """The 9 opaque slots each accept an arbitrary dict without internal validation."""
        cfg = AgentConfig(
            name="a1",
            model="openai/gpt-4o",
            tools=[{"name": "tool1"}],
            knowledge={"db": "pg"},
            memory={"backends": ["db"]},
            session={"storage": "sqlite"},
            reasoning={"effort": "high"},
            skills={"list": ["s1"]},
            human_review={"enabled": True},
            culture={"locale": "es-AR"},
            persistence={"mode": "auto"},
        )
        assert cfg.tools == [{"name": "tool1"}]
        assert cfg.memory == {"backends": ["db"]}
        assert cfg.human_review == {"enabled": True}
        assert cfg.persistence == {"mode": "auto"}

    def test_agent_config_tools_is_list(self) -> None:
        """tools is a list (not dict) per design."""
        cfg = AgentConfig(name="a1", model="openai/gpt-4o", tools=[{"a": 1}, {"b": 2}])
        assert isinstance(cfg.tools, list)
        assert len(cfg.tools) == 2

    def test_agent_config_model_config_extra_forbid(self) -> None:
        """model_config declares extra='forbid'."""
        assert AgentConfig.model_config.get("extra") == "forbid"

    def test_agent_config_defaults(self) -> None:
        """Optional fields default sensibly (tools=[], metadata={})."""
        cfg = AgentConfig(name="a1", model="openai/gpt-4o")
        assert cfg.tools == []
        assert cfg.metadata == {}
        assert cfg.tags == []
        assert cfg.instructions is None


class TestAgentConfigModelFormat:
    """RED scenarios — invalid model format rejected."""

    def test_invalid_model_format_no_slash(self) -> None:
        """model without slash is rejected."""
        with pytest.raises(ValidationError) as exc:
            AgentConfig(name="a1", model="no-slash")
        assert "Invalid model format" in str(exc.value)

    def test_invalid_model_format_empty_provider(self) -> None:
        """model with empty provider is rejected."""
        with pytest.raises(ValidationError) as exc:
            AgentConfig(name="a1", model="/gpt-4o")
        assert "Invalid model format" in str(exc.value)

    def test_invalid_model_format_empty_model_id(self) -> None:
        """model with empty model_id is rejected."""
        with pytest.raises(ValidationError) as exc:
            AgentConfig(name="a1", model="openai/")
        assert "Invalid model format" in str(exc.value)


class TestAgentConfigNameCharacters:
    """RED scenarios — invalid name characters rejected."""

    def test_invalid_name_with_space_and_punct(self) -> None:
        """name with space and punctuation is rejected."""
        with pytest.raises(ValidationError) as exc:
            AgentConfig(name="bad name!", model="openai/gpt-4o")
        assert "Invalid agent name" in str(exc.value)

    def test_invalid_name_with_non_ascii(self) -> None:
        """name with non-ASCII is rejected."""
        with pytest.raises(ValidationError):
            AgentConfig(name="naïve", model="openai/gpt-4o")


class TestAgentConfigExtraForbiddenAndUserId:
    """RED scenario — extra field forbidden + user_id absent."""

    def test_extra_field_forbidden(self) -> None:
        """An unknown top-level field is rejected by extra='forbid'."""
        with pytest.raises(ValidationError) as exc:
            AgentConfig(name="a1", model="openai/gpt-4o", foo="bar")
        # Pydantic mentions the extra field in the error.
        assert "foo" in str(exc.value)

    def test_user_id_absent_from_model_fields(self) -> None:
        """user_id is NOT a declared field (composite, runtime-only, SPEC_04)."""
        assert "user_id" not in AgentConfig.model_fields

    def test_user_id_rejected_as_extra(self) -> None:
        """user_id provided in YAML is rejected by extra='forbid'."""
        with pytest.raises(ValidationError):
            AgentConfig(name="a1", model="openai/gpt-4o", user_id="u1")
