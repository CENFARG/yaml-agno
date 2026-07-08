"""RED tests for TeamConfig + TeamMemberConfig schemas.

These tests reference ``yaml_agno.models.config.team_config.{TeamConfig,TeamMemberConfig}``
which do NOT exist yet (RED). They cover the spec scenarios for:
    - GREEN coordinate default mode
    - GREEN mode from string "route" -> TeamMode.route
    - RED invalid mode "coroutine"
    - RED duplicate members
    - RED route with 1 member (min 2)
    - RED broadcast with 1 member (min 2)
    - GREEN coordinate with 1 member OK
    - RED extra field forbidden
"""

import pytest
from pydantic import ValidationError

from yaml_agno.models.config.team_config import TeamConfig, TeamMemberConfig

pytestmark = pytest.mark.unit


def _member(mid: str, agent: str = "a1") -> TeamMemberConfig:
    return TeamMemberConfig(member=mid, agent=agent)


class TestTeamConfigGoldenPaths:
    """GREEN scenarios — valid team configs accepted."""

    def test_team_config_creation_coordinate_default(self) -> None:
        """Default mode is TeamMode.coordinate."""
        cfg = TeamConfig(name="t1")
        assert cfg.name == "t1"
        assert cfg.mode.value == "coordinate"

    def test_team_config_mode_from_string_route(self) -> None:
        """mode='route' (string) maps to TeamMode.route enum."""
        cfg = TeamConfig(name="t1", mode="route", members=[_member("m1"), _member("m2")])
        assert cfg.mode.value == "route"

    def test_team_config_mode_from_string_broadcast(self) -> None:
        """mode='broadcast' (string) maps to TeamMode.broadcast enum."""
        cfg = TeamConfig(
            name="t1", mode="broadcast", members=[_member("m1"), _member("m2")]
        )
        assert cfg.mode.value == "broadcast"

    def test_coordinate_mode_allows_single_member(self) -> None:
        """coordinate mode has no minimum member count (1 is OK)."""
        cfg = TeamConfig(name="t1", mode="coordinate", members=[_member("m1")])
        assert len(cfg.members) == 1

    def test_team_config_model_config_extra_forbid(self) -> None:
        """TeamConfig declares extra='forbid'."""
        assert TeamConfig.model_config.get("extra") == "forbid"

    def test_team_config_two_members_same_agent_ok(self) -> None:
        """Two members with distinct ids but same agent are allowed (multi-role)."""
        cfg = TeamConfig(
            name="t1",
            members=[_member("m1", "a1"), _member("m2", "a1")],
        )
        assert len(cfg.members) == 2


class TestTeamConfigInvalidMode:
    """RED scenarios — invalid mode rejected."""

    def test_invalid_mode_rejected(self) -> None:
        """An invalid mode string is rejected (Agno enum validation)."""
        with pytest.raises(ValidationError):
            TeamConfig(name="t1", mode="coroutine")


class TestTeamConfigMembersUnique:
    """RED scenario — duplicate member ids rejected."""

    def test_duplicate_members_rejected(self) -> None:
        """Two members with the same member id are rejected."""
        with pytest.raises(ValidationError) as exc:
            TeamConfig(
                name="t1",
                members=[_member("m1"), _member("m1")],
            )
        assert "Duplicate member ids" in str(exc.value)


class TestTeamConfigModeRequirements:
    """RED scenarios — mode-specific minimum member counts."""

    def test_route_mode_requires_two_members(self) -> None:
        """route with 1 member is rejected (needs >= 2)."""
        with pytest.raises(ValidationError) as exc:
            TeamConfig(name="t1", mode="route", members=[_member("m1")])
        assert "requires at least 2 members" in str(exc.value)

    def test_broadcast_mode_requires_two_members(self) -> None:
        """broadcast with 1 member is rejected (needs >= 2)."""
        with pytest.raises(ValidationError) as exc:
            TeamConfig(name="t1", mode="broadcast", members=[_member("m1")])
        assert "requires at least 2 members" in str(exc.value)

    def test_route_mode_with_two_members_ok(self) -> None:
        """route with 2 members is accepted."""
        cfg = TeamConfig(
            name="t1", mode="route", members=[_member("m1"), _member("m2")]
        )
        assert cfg.mode.value == "route"
        assert len(cfg.members) == 2


class TestTeamConfigExtraAndMemberConfig:
    """RED scenario — extra field forbidden + TeamMemberConfig basics."""

    def test_extra_field_forbidden(self) -> None:
        """An unknown top-level field is rejected."""
        with pytest.raises(ValidationError):
            TeamConfig(name="t1", foo="bar")

    def test_team_member_config_basic(self) -> None:
        """TeamMemberConfig accepts member + agent + optional role."""
        m = TeamMemberConfig(member="m1", agent="a1", role="leader")
        assert m.member == "m1"
        assert m.agent == "a1"
        assert m.role == "leader"

    def test_user_id_absent_from_team_config(self) -> None:
        """user_id is NOT a declared field on TeamConfig (SPEC_04)."""
        assert "user_id" not in TeamConfig.model_fields
