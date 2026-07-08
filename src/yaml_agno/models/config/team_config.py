"""Team configuration schema (YAML root: team). Single source of truth for the
team YAML shape. TeamMode is imported from Agno (not redefined) so yaml-agno
evolves with Agno."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# IMPORTED from Agno — never redefined. 4 members: coordinate/route/broadcast/tasks.
from agno.team.mode import TeamMode


class TeamMemberConfig(BaseModel):
    """Schema for one member entry in a team YAML."""

    # NOTE: TeamMemberConfig does NOT set extra="forbid" in SPEC_02 — it inherits
    # Pydantic default (extra="ignore"). This is intentional: member entries may
    # carry per-mode hints. If strictness is wanted later, add ConfigDict here.
    member: str = Field(..., description="Unique member id within the team.")
    agent: str = Field(..., description="Name of the referenced AgentConfig.")
    role: str | None = Field(None, description="Role of the member in the team.")


class TeamConfig(BaseModel):
    """Schema for the ``team:`` YAML root.

    Invariants enforced at the boundary:
        - ``name`` is non-empty.
        - ``mode`` is a valid ``agno.team.TeamMode`` value (lowercase string).
        - member ids are unique.
        - mode-specific minimum member counts (route/broadcast need >= 2).
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    name: str = Field(..., min_length=1, max_length=100, description="Unique team name.")
    mode: TeamMode = Field(default=TeamMode.coordinate, description="Team execution mode (Agno enum).")

    # Behavior
    instructions: str | None = Field(None, max_length=50000, description="Team system prompt.")

    # Composition
    members: list[TeamMemberConfig] = Field(default_factory=list, description="Team members.")

    # Delegated
    workflows: list[dict[str, Any]] = Field(default_factory=list, description="Workflows. See SPEC_01 §4.")

    # Organization
    description: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # NOTE: `user_id` is INTENTIONALLY ABSENT (composite, runtime-only, SPEC_04).

    @field_validator("members")
    @classmethod
    def validate_members_unique(cls, v: list[TeamMemberConfig]) -> list[TeamMemberConfig]:
        """Ensure member ids are unique within the team."""
        member_ids = [m.member for m in v]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Duplicate member ids detected.")
        return v

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> "TeamConfig":
        """Enforce mode-specific minimum member counts.

        ``route`` delegates to one specialist — needs >= 2 members (leader + specialist).
        ``broadcast`` sends to all members simultaneously — needs >= 2 to be meaningful.
        ``coordinate`` and ``tasks`` have no minimum beyond the default (leader synthesizes).
        """
        n = len(self.members)
        if self.mode in (TeamMode.route, TeamMode.broadcast) and n < 2:
            raise ValueError(f"{self.mode.value} mode requires at least 2 members.")
        return self
