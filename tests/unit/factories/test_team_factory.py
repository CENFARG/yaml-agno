"""Unit tests for ``TeamFactory.build`` — SPEC_01 slice #3.

Covers the 11 scenarios of
``openspec/changes/team-factory/specs/team-factory/spec.md``:

    - GREEN golden 2-member resolution
    - GREEN golden instructions passthrough
    - GREEN member order preserved
    - RED missing agent raises ValueError (no partial Team)
    - GREEN mode passthrough (same instance)
    - GREEN instructions None is OK
    - GREEN no model field (result.model is None)
    - GREEN opaque workflows tolerated
    - GREEN all 4 TeamMode values construct
    - GREEN schema delegation (route+1 member fails before factory)
    - GREEN import + callable contract
    - GREEN collection with ``@pytest.mark.unit``

Verified Agno behavior (Agno 2.6.22): ``Team(members=[Agent(...)], mode=TeamMode,
name=..., instructions=...)`` constructs without network. ``cfg.mode`` is already a
``TeamMode`` enum (Pydantic coerces at the schema boundary) and is forwarded verbatim.
"""

import pytest
from agno.agent import Agent
from agno.team.mode import TeamMode
from agno.team.team import Team
from pydantic import ValidationError

from yaml_agno.factories import TeamFactory
from yaml_agno.models.config.team_config import TeamConfig, TeamMemberConfig

pytestmark = pytest.mark.unit


def _agent(name: str) -> Agent:
    """Build a real ``agno.Agent`` with a trivial model string (no network)."""
    return Agent(name=name, model="openai:gpt-4o")


class TestTeamFactoryBuild:
    """RED→GREEN tests for ``TeamFactory.build(cfg, agents) -> agno.Team``."""

    def test_build_returns_agno_team_with_two_members(self) -> None:
        """Scenario: Golden path — equipo de 2 miembros resueltos.

        ``build`` returns an ``agno.Team`` whose ``members`` are the two
        pre-built agents in YAML order, with ``mode`` and ``name`` mapped.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            members=[
                TeamMemberConfig(member="m1", agent="a1"),
                TeamMemberConfig(member="m2", agent="a2"),
            ],
        )
        agent_a = _agent("a1")
        agent_b = _agent("a2")
        agents = {"a1": agent_a, "a2": agent_b}

        result = TeamFactory.build(cfg, agents)

        assert isinstance(result, Team)
        assert result.members == [agent_a, agent_b]
        assert result.mode is TeamMode.coordinate
        assert result.name == "t"

    def test_build_passes_instructions_complete(self) -> None:
        """Scenario: Golden path con instructions pasadas por completo.

        ``cfg.instructions`` (a non-empty string) is forwarded verbatim.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            instructions="You orchestrate invoices.",
            members=[TeamMemberConfig(member="m1", agent="a1")],
        )
        agents = {"a1": _agent("a1")}

        result = TeamFactory.build(cfg, agents)

        assert result.instructions == "You orchestrate invoices."

    def test_build_preserves_member_order(self) -> None:
        """Scenario: Orden de miembros preservado.

        ``members=[agent=z, agent=a, agent=m]`` resolves to the exact same
        order in ``result.members`` (non-alphabetical, proves order matters).
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            members=[
                TeamMemberConfig(member="mz", agent="z"),
                TeamMemberConfig(member="ma", agent="a"),
                TeamMemberConfig(member="mm", agent="m"),
            ],
        )
        agents = {"z": _agent("z"), "a": _agent("a"), "m": _agent("m")}

        result = TeamFactory.build(cfg, agents)

        assert result.members == [agents["z"], agents["a"], agents["m"]]

    def test_build_raises_valueerror_on_missing_agent(self) -> None:
        """Scenario: RED — referencia de agente inexistente.

        A ``member.agent`` absent from ``agents`` raises ``ValueError``
        including the offending name, before ``agno.Team`` is constructed.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            members=[TeamMemberConfig(member="x", agent="no_existe")],
        )
        agents: dict[str, Agent] = {}

        with pytest.raises(ValueError, match="no_existe"):
            TeamFactory.build(cfg, agents)

    def test_build_mode_passthrough_preserves_identity(self) -> None:
        """Scenario: Passthrough de mode.

        ``result.mode is cfg.mode`` — the same enum instance, no conversion.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.route,
            members=[
                TeamMemberConfig(member="m1", agent="a1"),
                TeamMemberConfig(member="m2", agent="a2"),
            ],
        )
        agents = {"a1": _agent("a1"), "a2": _agent("a2")}

        result = TeamFactory.build(cfg, agents)

        assert result.mode is TeamMode.route
        assert result.mode is cfg.mode

    def test_build_accepts_instructions_none(self) -> None:
        """Scenario: Instructions None no rompe.

        ``cfg.instructions is None`` produces ``result.instructions is None``.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            instructions=None,
            members=[TeamMemberConfig(member="m1", agent="a1")],
        )
        agents = {"a1": _agent("a1")}

        result = TeamFactory.build(cfg, agents)

        assert result.instructions is None

    def test_build_no_model_field_means_team_model_is_none(self) -> None:
        """Scenario: Sin model — Team se construye igual.

        ``TeamConfig`` has no ``model`` field; ``result.model is None``.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            members=[TeamMemberConfig(member="m1", agent="a1")],
        )
        agents = {"a1": _agent("a1")}

        result = TeamFactory.build(cfg, agents)

        assert result.model is None

    def test_build_tolerates_opaque_workflows_slot(self) -> None:
        """Scenario: Workflows presentes, sin error.

        A populated ``cfg.workflows`` does NOT raise; nothing derived from
        workflows reaches ``agno.Team``. Opaque slots that DO map to valid
        Team kwargs (description, metadata) are ALSO NOT forwarded — the
        result holds Agno's defaults, proving the factory ignored them.
        """
        cfg = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            members=[TeamMemberConfig(member="m1", agent="a1")],
            workflows=[{"workflow": "x", "steps": [{"name": "s1"}]}],
            description="should-not-forward",
            tags=["prod"],
            metadata={"owner": "team-foo"},
        )
        agents = {"a1": _agent("a1")}

        result = TeamFactory.build(cfg, agents)

        assert isinstance(result, Team)
        # Non-forwarding: opaque slots MUST NOT reach the Team. These map to
        # valid Team params, so assert they hold Agno's defaults, not cfg's.
        assert result.description != cfg.description
        assert result.metadata != cfg.metadata

    def test_build_constructs_all_four_team_modes(self) -> None:
        """Scenario: coordinate/route/broadcast/tasks construyen.

        One sub-case per ``TeamMode`` value with a valid member count.
        """
        # coordinate: 1+ member
        cfg_coord = TeamConfig(
            name="t",
            mode=TeamMode.coordinate,
            members=[TeamMemberConfig(member="m1", agent="a1")],
        )
        result_coord = TeamFactory.build(cfg_coord, {"a1": _agent("a1")})
        assert result_coord.mode is TeamMode.coordinate

        # route: >= 2 members
        cfg_route = TeamConfig(
            name="t",
            mode=TeamMode.route,
            members=[
                TeamMemberConfig(member="m1", agent="a1"),
                TeamMemberConfig(member="m2", agent="a2"),
            ],
        )
        result_route = TeamFactory.build(
            cfg_route, {"a1": _agent("a1"), "a2": _agent("a2")}
        )
        assert result_route.mode is TeamMode.route

        # broadcast: >= 2 members
        cfg_broad = TeamConfig(
            name="t",
            mode=TeamMode.broadcast,
            members=[
                TeamMemberConfig(member="m1", agent="a1"),
                TeamMemberConfig(member="m2", agent="a2"),
            ],
        )
        result_broad = TeamFactory.build(
            cfg_broad, {"a1": _agent("a1"), "a2": _agent("a2")}
        )
        assert result_broad.mode is TeamMode.broadcast

        # tasks: 1+ member
        cfg_tasks = TeamConfig(
            name="t",
            mode=TeamMode.tasks,
            members=[TeamMemberConfig(member="m1", agent="a1")],
        )
        result_tasks = TeamFactory.build(cfg_tasks, {"a1": _agent("a1")})
        assert result_tasks.mode is TeamMode.tasks

    def test_build_does_not_revalidate_schema_invariants(self) -> None:
        """Scenario: Modo route con 1 miembro — error viene del schema.

        Pydantic raises ``ValidationError`` at ``TeamConfig`` construction
        (before ``build()`` is ever reached); the factory is never invoked.
        """
        with pytest.raises(ValidationError):
            TeamConfig(
                name="t",
                mode=TeamMode.route,
                members=[TeamMemberConfig(member="m1", agent="a1")],
            )


class TestTeamFactoryImportContract:
    """Scenario: GREEN — Import desde el paquete raíz + callable."""

    def test_team_factory_importable_from_factories_package(self) -> None:
        """``from yaml_agno.factories import TeamFactory`` succeeds at runtime."""
        from yaml_agno.factories import TeamFactory as Factory

        assert Factory is not None
        assert Factory is TeamFactory

    def test_team_factory_build_is_callable(self) -> None:
        """``TeamFactory.build`` is callable (static method)."""
        assert callable(TeamFactory.build)
