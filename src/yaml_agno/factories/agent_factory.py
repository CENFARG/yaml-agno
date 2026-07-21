"""AgentFactory — builds a native ``agno.Agent`` from an ``AgentConfig``.

Slice #1 (SPEC_01) mapped the 4 identity fields. Slice C (SPEC_11) adds
optional tools wiring: when ``resolver`` is provided and ``cfg.tools`` is
non-empty, ``ToolFactory(resolver).build(cfg.tools)`` resolves the opaque
dicts into the mixed list ``agno.Agent(tools=...)`` accepts (Option B —
AgentConfig.tools stays opaque; validation happens inside the factory).
Slice B (SPEC_30) adds optional skills wiring: when ``cfg.skills`` is
non-None, ``SkillsFactory.build(cfg.skills)`` resolves the opaque dict into a
``agno.skills.Skills`` forwarded to ``Agent(skills=...)`` (Option B —
AgentConfig.skills stays opaque; validation happens inside the factory).

FIX 2 (resolver-bootstrap-fix): adds an optional ``provider_factory`` keyword
to ``build()``. When provided, ``cfg.model`` is parsed via
``parse_model_spec()`` and routed through ``ProviderFactory.build()`` to
produce a real Agno ``Model`` instance (with api_key injected); that instance
is forwarded to ``Agent(model=instance)`` instead of the raw string. When
``provider_factory is None``, current string passthru is preserved.

Contract:
    - Construction stays pure assignment + factory dispatch. No network, no
      LLM instantiation, no provider resolution. ``MCPResolver`` returns
      UNCONNECTED instances; ``agno.Agent`` auto-connects at run time.
    - When ``resolver is None`` (the default), behavior is UNCHANGED from
      slice #1: ``tools=[]`` is forwarded and existing callers/tests are
      untouched (zero breaking tests).
    - When ``cfg.skills is None`` (the default), ``skills=None`` is forwarded
      (zero breaking tests; slice #1 backward-compat invariant).
    - When ``provider_factory is None`` (the default), ``model=cfg.model``
      (raw string) is forwarded unchanged (slice #1 backward-compat invariant).

@ai-directive: SSOT is specs/SPEC_01_AGENT_FACTORY.md (identity) +
specs/SPEC_11_TOOLS_AND_MCP.md (tools wiring) +
specs/SPEC_30_SKILLS.md (skills wiring). Discrepancies resolve in their
favor. This module consumes SPEC_02 (AgentConfig) read-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agno.agent import Agent

from yaml_agno.models.config.agent_config import AgentConfig
from yaml_agno.models.model_spec import ModelExpandedSpec, parse_model_spec
from yaml_agno.skills import SkillsFactory
from yaml_agno.tools.tool_factory import ToolFactory

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver
    from yaml_agno.di.provider_factory import ProviderFactory

__all__ = ["AgentFactory"]


class AgentFactory:
    """Builds ``agno.Agent`` instances from validated ``AgentConfig`` objects.

    Scope (identity + model + optional tools + optional skills):

        +--------------------------+--------------------------+-----------+
        | AgentConfig field        | agno.Agent kwarg         | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | instructions: str | None | instructions             | direct    |
        | description: str | None  | description              | direct    |
        | model: str               | model                    | passthru  |
        | tools: list[dict]        | tools                    | factory*  |
        | tool_call_limit: int|None| tool_call_limit          | direct    |
        | skills: dict | None      | skills                   | factory** |
        +--------------------------+--------------------------+-----------+
        | knowledge, memory, ...   | (not forwarded)          | deferred  |
        | tags, metadata           | (not forwarded)          | deferred  |
        +--------------------------+--------------------------+-----------+

        * tools is resolved ONLY when ``resolver`` is passed to ``build()``.
          Otherwise tools stays ``[]`` (slice #1 behavior, zero broken tests).
        ** skills is resolved via ``SkillsFactory.build`` whenever
           ``cfg.skills`` is non-None; no resolver needed (Option B).

    Deferred slots are accepted silently and resolved by their owner SPECs +
    the DependencyManager. This class exposes a static ``build()`` method; it
    holds no state and is not instantiated.
    """

    @staticmethod
    def build(
        cfg: AgentConfig,
        resolver: AgnoResolver | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> Agent:
        """Build a native ``agno.Agent`` from an ``AgentConfig``.

        Maps the identity/behavior fields directly. When ``resolver`` is
        provided AND ``cfg.tools`` is non-empty, resolves the opaque tools
        dicts into the mixed list ``agno.Agent(tools=...)`` accepts via
        ``ToolFactory`` (Option B). When ``cfg.skills`` is non-None, resolves
        the opaque skills dict into a ``Skills`` instance via
        ``SkillsFactory.build`` and forwards it to ``Agent(skills=...)``.

        FIX 2 (resolver-bootstrap-fix): when ``provider_factory`` is provided,
        ``cfg.model`` is parsed via ``parse_model_spec()`` and the resulting
        spec is routed through ``provider_factory.build()`` to obtain a real
        Agno ``Model`` instance (with api_key injected by the factory's
        SecretResolver). That instance is forwarded to ``Agent(model=...)``
        instead of the raw string. When ``provider_factory is None``, the
        string is forwarded as-is (slice #1 backward-compat).

        Args:
            cfg: A validated ``AgentConfig`` (SPEC_02). Its ``model`` field is
                a ``provider:id`` string forwarded verbatim to Agno when no
                ``provider_factory`` is given, or parsed-and-built into a Model
                instance when one is. Its ``tools`` field is an opaque
                ``list[dict]`` resolved here when a resolver is supplied. Its
                ``skills`` field is an opaque ``dict[str, Any] | None``
                resolved here whenever non-None.
            resolver: Optional ``AgnoResolver`` for allowlisted dotted-path
                resolution of custom tools / toolkit classes / MCP
                ``header_provider``. When ``None`` (default), tools are
                skipped — callers that do not need tools pass nothing. Skills
                do not use the resolver. When ``provider_factory`` is given,
                the same resolver is typically wired into it by the caller.
            provider_factory: Optional ``ProviderFactory`` (FIX 2). When
                provided, ``cfg.model`` is routed through it to produce a
                fully-configured Agno Model instance (with api_key). When
                ``None`` (default), ``cfg.model`` is forwarded as a raw string
                and Agno resolves it (slice #1 behavior).

        Returns:
            A constructed ``agno.Agent``. Per ``agno/agent/agent.py:504``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked. MCP tools are UNCONNECTED at this point;
            Agent auto-connects them during ``aget_tools`` (A2). Skills loaders
            run synchronously inside ``SkillsFactory.build`` (slice A).

        Raises:
            (none directly) Any exception raised by ``agno.Agent.__init__``,
                ``ToolFactory.build()`` (``UnknownBuiltinError``,
                ``SecurityError``, ``ValidationError``),
                ``SkillsFactory.build()`` (``ValidationError``,
                ``FileNotFoundError``, ``SkillValidationError``), or
                ``ProviderFactory.build()`` (``KeyError``,
                ``ModelConstructionError``) propagates unchanged.
        """
        tools: list[Any] = []
        if cfg.tools and resolver is not None:
            factory = ToolFactory(resolver)
            tools = factory.build(cfg.tools)
        skills = SkillsFactory.build(cfg.skills) if cfg.skills else None

        # FIX 2: when a provider_factory is wired, parse cfg.model and build a
        # real Agno Model instance (with api_key injected) instead of passing
        # the raw string. Backward-compat: provider_factory=None keeps the
        # slice-#1 string passthru that Agno resolves itself.
        model: Any = cfg.model
        if provider_factory is not None:
            parsed = parse_model_spec(cfg.model)
            # ModelExpandedSpec carries the generation params; ModelStringSpec
            # only carries provider+id. ProviderFactory.build type-annotates its
            # param as ModelExpandedSpec and consumes the spec via attribute
            # access (model_dump), so we promote a ModelStringSpec to the
            # expanded form. We round-trip via model_validate to preserve all
            # carried fields (works for either spec type) without naming every
            # optional ModelExpandedSpec field at the construction site.
            if not isinstance(parsed, ModelExpandedSpec):
                spec = ModelExpandedSpec.model_validate(parsed.model_dump())
            else:
                spec = parsed
            model = provider_factory.build(spec)

        return Agent(
            name=cfg.name,
            instructions=cfg.instructions,
            description=cfg.description,
            model=model,
            tools=tools or None,
            tool_call_limit=cfg.tool_call_limit,
            skills=skills,
        )
