"""Runtime import contract tests for Agno enums.

These tests verify the REAL runtime import paths against Agno 2.6.22. They are
NOT mypy checks (mypy stubs use ignore_missing_imports=true, so a wrong import
path would NOT fail type-check). This file is the actual contract that the enum
values and import paths are correct.

Covers:
    - TeamMode importable from agno.team.mode (4 lowercase members).
    - StepType importable from agno.workflow.types (8 Capitalized members).
"""

import pytest

pytestmark = pytest.mark.unit


class TestTeamModeContract:
    """Runtime contract: agno.team.mode.TeamMode."""

    def test_team_mode_importable_from_agno(self) -> None:
        """``from agno.team.mode import TeamMode`` succeeds at runtime."""
        from agno.team.mode import TeamMode

        assert TeamMode is not None

    def test_team_mode_has_four_members(self) -> None:
        """TeamMode has exactly the 4 lowercase members verified in agno source."""
        from agno.team.mode import TeamMode

        values = {m.value for m in TeamMode}
        assert values == {"coordinate", "route", "broadcast", "tasks"}

    def test_team_mode_members_are_lowercase(self) -> None:
        """All TeamMode member values are lowercase (asymmetry with StepType)."""
        from agno.team.mode import TeamMode

        for member in TeamMode:
            assert member.value == member.value.lower()


class TestStepTypeContract:
    """Runtime contract: agno.workflow.types.StepType."""

    def test_step_type_importable_from_agno(self) -> None:
        """``from agno.workflow.types import StepType`` succeeds at runtime."""
        from agno.workflow.types import StepType

        assert StepType is not None

    def test_step_type_has_eight_members(self) -> None:
        """StepType has exactly 8 Capitalized members verified in agno source."""
        from agno.workflow.types import StepType

        values = {m.value for m in StepType}
        assert values == {
            "Step",
            "Parallel",
            "Condition",
            "Router",
            "Loop",
            "Function",
            "Steps",
            "Workflow",
        }
