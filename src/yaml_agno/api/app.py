"""``YamlAgentOS`` — yaml-agno's ``AgentOS`` subclass (SPEC_06 slice A+B).

Inherits the full native Agno 2.6.22 router surface
(``POST /agents/{agent_id}/runs``, ``GET /health``, ``GET /agents``, ...) from
``agno.os.AgentOS``. Slice A adds:

1. Dual agent source resolution (pre-built list OR YAML config path).
2. A ``get_app()`` override that calls ``super().get_app()`` and OPTIONALLY
   mounts the slice-A health extensions (``/health/liveness`` + ``/health/readiness``).

Slice B adds:

3. ``TenantContextMiddleware`` (SPEC_06 §3.2) — registered in ``get_app()``
   when ``mount_tenant_context=True`` (default). Sets ``request.state.user_id``
   to the composite ``"{tenant_id}:{principal_id}"`` via ``resolve_user_id()``
   (SPEC_04).

Corrects the four SPEC_06 defects the exploration surfaced:

- ``from agno.os import AgentOS`` (NOT ``agno.app``).
- ``yaml_agno.factories.agent_factory.AgentFactory.build(cfg)`` (NOT a
  module-level ``build_agents`` function; the directory is ``factories/``).
- ``db=None`` + Agno's ``auto_provision_dbs=True`` (the SPEC_03 ``db.session``
  module does not exist yet).
- ``authorization=False`` slice-A default (SPEC_04's ``resolve_user_id`` is not
  implemented yet; tests cannot mint real JWTs).

@ai-directive: this class MUST NOT define its own ``/run``, ``/sessions``, or
``/agents`` config routes. All execution routes come from the inherited
``AgentOS.get_app()``. Extensions are registered in ``get_app()`` AFTER
``super().get_app()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from agno.agent import Agent
from agno.agent.factory import AgentFactory as AgnoAgentFactory
from agno.agent.protocol import AgentProtocol
from agno.agent.remote import RemoteAgent
from agno.os import AgentOS
from fastapi import FastAPI

from yaml_agno.api.health import get_liveness_router, get_readiness_router
from yaml_agno.api.middleware.tenant_context import TenantContextMiddleware
from yaml_agno.factories.agent_factory import AgentFactory
from yaml_agno.models.config.agent_config import AgentConfig

__all__ = ["AgentEntry", "YamlAgentOS"]

# Match Agno's accepted agents union (verified against agno==2.6.22): callers
# may pass real ``Agent`` instances, remote proxies, protocol adapters, or
# ``agno.AgentFactory`` instances. Widening here avoids mypy arg-type errors
# against ``super().__init__(agents=...)`` and documents the real contract.
AgentEntry = Agent | RemoteAgent | AgentProtocol | AgnoAgentFactory


class YamlAgentOS(AgentOS):
    """yaml-agno's subclass of ``agno.os.AgentOS`` (SPEC_06 slice A+B).

    Inherits every native router, middleware, and behaviour from ``AgentOS``.
    Slice A adds dual agent source resolution (pre-built list OR YAML config
    path) and an optional pair of health extension routers. Slice B adds the
    ``TenantContextMiddleware`` (SPEC_06 §3.2) for composite user_id resolution.

    WARNING (slice A authorization default):

        Slice A defaults ``authorization=False`` so integration tests can
        exercise ``get_app()`` without minting a real JWT and local dev can
        boot ``uvicorn`` immediately. **This default is NOT for production.**
        Once SPEC_04's ``resolve_user_id`` ships, production deployments MUST
        pass ``authorization=True`` and
        ``authorization_config=AuthorizationConfig(user_isolation=True)`` to
        avoid the NULL-bucket footgun (SPEC_06 §3.1).

    @ai-directive: this class MUST NOT define its own ``/run``, ``/sessions``,
    or ``/agents`` config routes. All execution routes come from the inherited
    ``AgentOS.get_app()``.
    """

    def __init__(
        self,
        *,
        config_path: str | None = None,
        agents: list[AgentEntry] | None = None,
        authorization: bool = False,
        mount_health: bool = True,
        mount_tenant_context: bool = True,
        memory_cfg: Any = None,
        **agentos_kwargs: Any,
    ) -> None:
        """Initialize ``YamlAgentOS`` from a pre-built agent list OR a YAML config path.

        Exactly one agent source may be provided:

        - ``agents`` — a list of pre-built ``agno.Agent`` instances (or any other
          entry Agno's ``agents=[...]`` accepts). Forwarded unchanged to
          ``super().__init__``. This is the primary path for integration tests.
        - ``config_path`` — a path to a YAML file whose top-level is a list of
          agent definitions. Each entry is validated via
          ``AgentConfig.model_validate`` (SPEC_02) and built via
          ``AgentFactory.build(cfg)`` (SPEC_01).

        Passing BOTH is ambiguous and raises ``ValueError``. Passing NEITHER is
        allowed by ``YamlAgentOS`` itself, but Agno's ``AgentOS.__init__`` then
        requires at least one of ``teams``, ``workflows``, ``knowledge``, or
        ``db`` via ``**agentos_kwargs`` (verified Agno 2.6.22 behavior).

        Args:
            config_path: Optional path to a YAML agent-definition file. Mutually
                exclusive with ``agents``.
            agents: Optional list of pre-built ``agno.Agent`` (or any
                ``AgentEntry``). Mutually exclusive with ``config_path``.
            authorization: Forwarded to ``super().__init__``. Slice A defaults
                to ``False`` for local dev + integration tests; production MUST
                pass ``True`` (see WARNING in the class docstring).
            mount_health: When ``True`` (default), mount ``/health/liveness`` and
                ``/health/readiness`` inside ``get_app()``. Set to ``False`` for
                unit tests that want the bare native surface.
            mount_tenant_context: When ``True`` (default), register the
                ``TenantContextMiddleware`` (SPEC_06 §3.2) inside ``get_app()``.
                Set to ``False`` for unit tests that don't supply ``memory_cfg``.
            memory_cfg: YAML ``memory:`` block (optional). Carries
                ``system_user_id`` used by ``resolve_user_id`` when no human
                principal is present on the request. Required when
                ``mount_tenant_context=True`` and no JWT auth is active.
            **agentos_kwargs: Extra keyword arguments forwarded verbatim to
                ``super().__init__`` (e.g. ``mcp_server``,
                ``telemetry``, ``teams``, ``workflows``, ``db``...).

        Raises:
            ValueError: If both ``agents`` and ``config_path`` are provided.
            pydantic.ValidationError: If a YAML entry fails ``AgentConfig``
                validation.
            yaml.YAMLError: If the YAML document at ``config_path`` is
                malformed.
            FileNotFoundError: If ``config_path`` does not exist.
        """
        if agents is not None and config_path is not None:
            raise ValueError(
                "YamlAgentOS received both 'agents' and 'config_path'; "
                "the call is ambiguous. Provide exactly one agent source."
            )

        resolved_agents = self._resolve_agents(agents=agents, config_path=config_path)

        self._mount_health = mount_health
        self._mount_tenant_context = mount_tenant_context
        self._memory_cfg = memory_cfg

        super().__init__(
            agents=resolved_agents,
            authorization=authorization,
            **agentos_kwargs,
        )

    @staticmethod
    def _resolve_agents(
        *,
        agents: list[AgentEntry] | None,
        config_path: str | None,
    ) -> list[AgentEntry] | None:
        """Resolve the agent source into a list of agent entries (or ``None``).

        Args:
            agents: Pre-built agent list (wins when provided).
            config_path: Path to a YAML file (used only when ``agents`` is None).

        Returns:
            The agent list, or ``None`` when neither source was provided.
        """
        if agents is not None:
            return list(agents)
        if config_path is None:
            return None

        path = Path(config_path)
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        if data is None:
            return []
        if not isinstance(data, list):
            raise ValueError(
                f"YAML config at {config_path!r} must be a top-level list of "
                f"agent definitions; got {type(data).__name__}."
            )

        built: list[AgentEntry] = []
        for entry in data:
            cfg = AgentConfig.model_validate(entry)
            built.append(AgentFactory.build(cfg))
        return built

    def get_app(self) -> FastAPI:
        """Return the FastAPI app with native routers plus yaml-agno extensions.

        Overrides ``AgentOS.get_app``. Calls ``super().get_app()`` so the
        inherited lifespan, exception handlers, DB auto-discovery, and the full
        native router set (``POST /agents/{agent_id}/runs``, ``GET /health``,
        ...) are preserved, then mounts the yaml-agno extensions on the returned
        app via ``app.include_router(...)`` and ``app.add_middleware(...)``.

        Extension middleware is registered LAST so it runs FIRST (outermost).
        ``TenantContextMiddleware`` must set ``request.state.user_id`` BEFORE
        native AgentOS handlers read it.

        @ai-directive: register extensions ONLY here, AFTER ``super().get_app()``.
        Do NOT override ``_add_built_in_routes`` or ``_add_router`` — those are
        AgentOS internals and ``super().get_app()`` already calls them.

        Returns:
            The fully wired ``fastapi.FastAPI`` instance.
        """
        app = super().get_app()

        if self._mount_health:
            app.include_router(get_liveness_router())
            app.include_router(get_readiness_router())

        if self._mount_tenant_context:
            app.add_middleware(TenantContextMiddleware, memory_cfg=self._memory_cfg)

        return app
