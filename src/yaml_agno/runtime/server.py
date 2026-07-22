"""Runtime server entry point (SPEC_06 slice A).

Thin wrapper around ``YamlAgentOS`` that loads the agent source, builds the
FastAPI app, and (optionally) runs it under uvicorn. Two public functions:

- ``create_app(config_path=None, agents=None, **kwargs) -> FastAPI`` — pure;
  returns the wired app without starting a server. Use this from integration
  tests and from external ASGI runners (gunicorn, etc.).
- ``run_server(config_path=None, agents=None, host="127.0.0.1", port=8000,
  server_factory=None, **kwargs) -> None`` — constructs a ``uvicorn.Server`` via
  the injectable ``server_factory`` and calls ``.run()``. Tests inject a fake
  factory to assert the server is constructed correctly without binding a TCP
  port.

The injection seam avoids the anti-pattern of ``if os.environ.get("TESTING")``
inside production code and keeps ``run_server`` unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import uvicorn
from fastapi import FastAPI

from yaml_agno.api.app import AgentEntry, YamlAgentOS

__all__ = ["create_app", "run_server"]

# Type alias for the injectable server factory used by ``run_server``.
# A factory receives the built FastAPI app, host, and port, and returns an
# object exposing a ``.run()`` method (typically ``uvicorn.Server``).
ServerFactory = Callable[[FastAPI, str, int], Any]


def _default_server_factory(app: FastAPI, host: str, port: int) -> uvicorn.Server:
    """Default ``uvicorn.Server`` builder.

    Args:
        app: The FastAPI app returned by ``YamlAgentOS.get_app()``.
        host: Bind host.
        port: Bind port.

    Returns:
        A ``uvicorn.Server`` configured with the app, host, and port.
    """
    config = uvicorn.Config(app=app, host=host, port=port)
    return uvicorn.Server(config)


def create_app(
    *,
    config_path: str | None = None,
    agents: list[AgentEntry] | None = None,
    **yaml_agentos_kwargs: Any,
) -> FastAPI:
    """Build a ``YamlAgentOS`` and return its FastAPI app.

    Pure function: does NOT start a server. Use from integration tests or from
    an external ASGI runner.

    Args:
        config_path: Optional path to a YAML agent-definition file. Mutually
            exclusive with ``agents``.
        agents: Optional list of pre-built ``agno.Agent`` instances. Mutually
            exclusive with ``config_path``.
        **yaml_agentos_kwargs: Extra keyword arguments forwarded to
            ``YamlAgentOS.__init__`` (e.g. ``authorization``,
            ``mount_health``, ``enable_mcp_server``...).

    Returns:
        The fully wired ``fastapi.FastAPI`` instance produced by
        ``YamlAgentOS(...).get_app()``.
    """
    os_app = YamlAgentOS(
        config_path=config_path,
        agents=agents,
        **yaml_agentos_kwargs,
    )
    return os_app.get_app()


def run_server(
    *,
    config_path: str | None = None,
    agents: list[AgentEntry] | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    server_factory: ServerFactory | None = None,
    **yaml_agentos_kwargs: Any,
) -> None:
    """Build the app and run it under uvicorn.

    Args:
        config_path: Optional path to a YAML agent-definition file. Mutually
            exclusive with ``agents``.
        agents: Optional list of pre-built ``agno.Agent`` instances. Mutually
            exclusive with ``config_path``.
        host: Bind host (default ``127.0.0.1``).
        port: Bind port (default ``8000``).
        server_factory: Optional callable ``(app, host, port) -> server`` used
            to construct the server. Defaults to a ``uvicorn.Server`` builder.
            Tests inject a fake to avoid binding a TCP port.
        **yaml_agentos_kwargs: Extra keyword arguments forwarded to
            ``YamlAgentOS.__init__``.
    """
    app = create_app(
        config_path=config_path,
        agents=agents,
        **yaml_agentos_kwargs,
    )

    factory: ServerFactory = server_factory or _default_server_factory
    server = factory(app, host, port)
    server.run()
