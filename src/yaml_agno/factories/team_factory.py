"""TeamFactory — builds a native ``agno.Team`` from a ``TeamConfig`` and a
dict of pre-built agents.

This is slice #3 of SPEC_01 (4-slice factory chain). It composes an
``agno.Team`` by (1) resolving each ``TeamMemberConfig.agent`` (string name)
against the supplied ``agents`` dict of already-constructed ``agno.Agent``
instances, and (2) mapping the 3 identity/behavior fields of ``TeamConfig``
(SPEC_02) — ``name``, ``mode``, ``instructions`` — plus the resolved
``members`` list to the corresponding ``agno.Team`` constructor kwargs.

The opaque ``workflows`` slot, plus ``description``, ``tags``, and
``metadata``, are intentionally NOT forwarded in this slice. ``workflows``
resolution is owned by WorkflowFactory (slice #4) and SPEC_01 §4;
``description``/``tags``/``metadata`` forwarding is owned by SPEC_05. The
per-member fields ``TeamMemberConfig.role`` and ``TeamMemberConfig.member``
(local id) are not consumed: ``agno.Team`` has no per-member metadata slot in
its slice-#3 constructor surface.

Contract:
    - ``TeamConfig`` is already Pydantic-validated (member uniqueness, mode
      minimum counts, non-empty name). This factory performs NO re-validation.
    - ``agents`` is supplied pre-built by the caller (runtime loader). The
      factory does NOT instantiate agents — that is ``AgentFactory.build()``
      (slice #1).
    - ``TeamConfig`` has NO ``model`` field. ``agno.Team(model=None)`` is the
      Agno default (``agno/team/team.py:441``); the team delegates the model to
      its members at ``run()`` time. This factory MUST NOT pass ``model=``.
    - Construction is pure assignment; no network, no LLM instantiation, no
      provider resolution occurs until ``run()`` or ``arun()`` is invoked.

@ai-directive: Behavioral SSOT is
openspec/changes/team-factory/specs/team-factory/spec.md; architectural SSOT is
specs/SPEC_01_AGENT_FACTORY.md. Discrepancies resolve in their favor. This
module consumes SPEC_02 (TeamConfig) read-only.
"""

from __future__ import annotations

from agno.agent import Agent
from agno.team.team import Team

from yaml_agno.models.config.team_config import TeamConfig

__all__ = ["TeamFactory"]


class TeamFactory:
    """Builds ``agno.Team`` instances from a validated ``TeamConfig`` and a
    dict of pre-built ``agno.Agent`` instances.

    Slice #3 scope (composition + 3 identity fields):

        +--------------------------+--------------------------+-----------+
        | TeamConfig field         | agno.Team kwarg          | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | mode: TeamMode           | mode                     | passthru  |
        | instructions: str | None | instructions             | direct    |
        | members: list[MemberCfg] | members                  | resolve   |
        +--------------------------+--------------------------+-----------+
        | workflows                | (not forwarded)          | deferred  |
        | description, tags,       | (not forwarded)          | deferred  |
        | metadata                 |                          |           |
        +--------------------------+--------------------------+-----------+

    ``members`` resolution: for each ``TeamMemberConfig`` in ``cfg.members``,
    the factory looks up ``member.agent`` (the referenced AgentConfig name) in
    the ``agents`` dict and collects the resulting ``Agent`` instances in YAML
    order. A missing reference raises ``ValueError`` with the offending name
    **before** ``agno.Team`` is constructed (no partial Team is ever built).

    Deferred slots are accepted silently (they are valid members of
    ``TeamConfig``) and will be resolved by their owner SPECs.

    This class exposes a static ``build()`` method; it holds no state and is
    not instantiated.
    """

    @staticmethod
    def build(cfg: TeamConfig, agents: dict[str, Agent]) -> Team:
        """Build a native ``agno.Team`` from a ``TeamConfig`` and pre-built agents.

        Member resolution iterates ``cfg.members`` in order and looks up each
        ``member.agent`` (string name) in ``agents``. The resolved ``Agent``
        instances are passed to ``agno.Team(members=...)`` preserving YAML
        order. Only ``name``, ``mode``, ``instructions``, and the resolved
        ``members`` are mapped; ``workflows``, ``description``, ``tags``, and
        ``metadata`` are intentionally ignored in this slice (see class
        docstring).

        Args:
            cfg: A validated ``TeamConfig`` (SPEC_02). Its ``mode`` field is
                already a ``agno.team.mode.TeamMode`` enum instance (Pydantic
                coerces it at the schema boundary) and is forwarded verbatim.
                Its ``members`` is a list of ``TeamMemberConfig``, each
                carrying an ``agent`` field naming an ``AgentConfig``.
            agents: A mapping from AgentConfig name to a pre-built
                ``agno.Agent`` instance (produced by ``AgentFactory.build()``,
                slice #1). The factory does NOT instantiate agents; the caller
                is responsible for building every agent referenced by
                ``cfg.members``.

        Returns:
            A constructed ``agno.Team``. Per ``agno/team/team.py:437-468``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked. The returned team has ``model=None`` (Agno
            default) because ``TeamConfig`` has no ``model`` field; the team
            delegates the model to its members at run time.

        Raises:
            ValueError: If any ``TeamMemberConfig.agent`` references a name
                absent from ``agents``. The message includes the offending
                name and a hint to check the YAML ``agents:`` section. Raised
                before ``agno.Team`` is constructed, so no partial Team is
                ever produced.
        """
        # Annotated as ``list[Agent | Team]`` (not ``list[Agent]``) to satisfy
        # mypy strict invariance: ``Team.__init__`` expects
        # ``list[Agent | Team]``. The list holds only ``Agent`` instances at
        # runtime — this is a variance-safe annotation, not a logic change.
        resolved_members: list[Agent | Team] = []
        for member in cfg.members:
            agent_name = member.agent
            if agent_name not in agents:
                raise ValueError(
                    f"Agent not found: {agent_name!r}. "
                    "Check the 'agents:' section of your YAML."
                )
            resolved_members.append(agents[agent_name])

        return Team(
            members=resolved_members,
            mode=cfg.mode,
            name=cfg.name,
            instructions=cfg.instructions,
        )
