"""AgentFactory — builds a native ``agno.Agent`` from an ``AgentConfig``.

This is slice #1 of SPEC_01 (4-slice factory chain). It maps the 4 identity
fields of ``AgentConfig`` (SPEC_02) to the corresponding ``agno.Agent``
constructor kwargs. The 9 opaque sub-system slots (tools, knowledge, memory,
session, reasoning, skills, human_review, culture, persistence) plus tags and
metadata are intentionally NOT forwarded in this slice — their resolution
(dict -> native Agno object) is owned by dedicated SPECs (03/04/10/11/13/
28/29/30/31) and the DependencyManager (change #2).

Contract:
    - Construction is pure assignment (agno/agent/agent.py:504: ``self.model =
      model``); no network, no LLM instantiation, no provider resolution.
    - ``model`` is passed through as the raw ``provider:id`` string. Agno parses
      it natively; yaml-agno performs no translation.

@ai-directive: SSOT is specs/SPEC_01_AGENT_FACTORY.md. Discrepancies resolve in
its favor. This module consumes SPEC_02 (AgentConfig) read-only.
"""

from __future__ import annotations

from agno.agent import Agent

from yaml_agno.models.config.agent_config import AgentConfig

__all__ = ["AgentFactory"]


class AgentFactory:
    """Builds ``agno.Agent`` instances from validated ``AgentConfig`` objects.

    Slice #1 scope (identity + model only):

        +--------------------------+--------------------------+-----------+
        | AgentConfig field        | agno.Agent kwarg         | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | instructions: str | None | instructions             | direct    |
        | description: str | None  | description              | direct    |
        | model: str               | model                    | passthru  |
        +--------------------------+--------------------------+-----------+
        | tools, knowledge, ...    | (not forwarded)          | deferred  |
        | tags, metadata           | (not forwarded)          | deferred  |
        +--------------------------+--------------------------+-----------+

    Deferred slots are accepted silently (they are valid ``dict | None`` members
    of ``AgentConfig``) and will be resolved by their owner SPECs + the
    DependencyManager in change #2.

    This class exposes a static ``build()`` method; it holds no state and is not
    instantiated.
    """

    @staticmethod
    def build(cfg: AgentConfig) -> Agent:
        """Build a native ``agno.Agent`` from an ``AgentConfig``.

        Only the 4 identity/behavior fields are mapped. The 9 opaque sub-system
        slots, ``tags``, and ``metadata`` are intentionally ignored in this
        slice (see class docstring).

        Args:
            cfg: A validated ``AgentConfig`` (SPEC_02). Its ``model`` field is a
                ``provider:id`` string forwarded verbatim to Agno.

        Returns:
            A constructed ``agno.Agent``. Per ``agno/agent/agent.py:504``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked.

        Raises:
            (none directly) Any exception raised by ``agno.Agent.__init__`` on
                invalid input propagates unchanged. Per verified contract, the 4
                mapped fields are accepted as-is by Agno 2.6.22.
        """
        return Agent(
            name=cfg.name,
            instructions=cfg.instructions,
            description=cfg.description,
            model=cfg.model,
        )
