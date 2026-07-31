"""FastAPIAppBuilder — constructs the FastAPI application that AgentOS serves.

Resolves ``base_app`` factory references via importlib, applies CORS
middleware, and conditionally mounts routers based on ``EndpointGroup``
definitions evaluated against ``AgentOSConfig`` feature flags.

Design (Slice 1):
    - ``EndpointGroup`` is a labelled APIRouter with an optional
      ``conditional`` expression evaluated via ``getattr`` chain.
    - ``_import_factory(path)`` uses ``importlib.import_module`` + ``getattr``
      — same pattern as ``di/agno_resolver.py`` dotted-path resolution.
    - CORS uses Starlette's ``CORSMiddleware`` directly.
    - Lifespan stub: optional ``lifespan`` callable passed to ``FastAPI()``.

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §3 (app-builder).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from yaml_agno.models.config.agentos_config import AgentOSConfig

__all__ = ["EndpointGroup", "FastAPIAppBuilder", "_import_factory"]


# ---------------------------------------------------------------------------
# EndpointGroup — labelled router with optional conditional mounting
# ---------------------------------------------------------------------------


@dataclass
class EndpointGroup:
    """A labelled ``APIRouter`` with an optional conditional mounting expression.

    Fields:
        router: The ``APIRouter`` to mount when the condition passes (or
            unconditionally when ``conditional`` is ``None``).
        prefix: URL prefix passed to ``app.include_router(router, prefix=...)``.
        conditional: A dotted expression evaluated against ``AgentOSConfig``
            (e.g. ``"tracing"``, ``"scheduler.enabled"``). ``None`` means
            always mount.

    Example:
        >>> schedules = EndpointGroup(
        ...     router=schedules_router,
        ...     prefix="/schedules",
        ...     conditional="scheduler.enabled",
        ... )
    """

    router: APIRouter
    prefix: str
    conditional: str | None = None


# ---------------------------------------------------------------------------
# Module-level factory importer
# ---------------------------------------------------------------------------


def _import_factory(path: str) -> Callable[[], FastAPI]:
    """Dynamically import a zero-argument callable from a dotted path.

    Format: ``"module.path:callable_name"`` — the module is imported via
    ``importlib.import_module`` and the callable is resolved via ``getattr``.

    Args:
        path: A colon-separated dotted path (e.g. ``"myapp.factories:build_app"``).

    Returns:
        The resolved callable.

    Raises:
        ModuleNotFoundError: If the module portion of ``path`` cannot be imported.
        ImportError: If ``path`` does not contain a colon separator.
        AttributeError: If the callable name is not found on the module.
    """
    if ":" not in path:
        raise ImportError(
            f"base_app path must use 'module:callable' format; got {path!r}"
        )

    module_path, attr_name = path.rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        raise ImportError(
            f"base_app module {module_path!r} not found (full path: {path!r})"
        ) from None

    factory = getattr(module, attr_name, None)
    if factory is None:
        raise ImportError(
            f"module {module_path!r} has no attribute {attr_name!r} "
            f"(full path: {path!r})"
        )
    if not callable(factory):
        raise ImportError(
            f"base_app path {path!r} resolved to {factory!r}, which is not callable"
        )

    return factory


# ---------------------------------------------------------------------------
# FastAPIAppBuilder
# ---------------------------------------------------------------------------


class FastAPIAppBuilder:
    """Builds the FastAPI application that AgentOS serves.

    Receives an ``AgentOSConfig`` (read-only) and an optional list of
    ``EndpointGroup`` instances via constructor injection. The ``build()``
    method resolves the base app, applies CORS, wires lifespan, and mounts
    endpoint routers conditionally.

    Slice 1 scope:
        - Resolves ``config.base_app`` import path (or creates default FastAPI).
        - Applies CORS when ``config.cors_allowed_origins`` is non-None.
        - Mounts routers conditionally based on ``EndpointGroup.conditional``.
        - Lifespan stub: optional ``lifespan`` passed to ``FastAPI()``.
    """

    def __init__(
        self,
        config: AgentOSConfig,
        *,
        endpoint_groups: list[EndpointGroup] | None = None,
        lifespan: Callable[[FastAPI], Any] | None = None,
    ) -> None:
        """Wire the builder with its configuration and endpoint groups.

        Args:
            config: A validated ``AgentOSConfig`` aggregate (read-only).
            endpoint_groups: Optional list of ``EndpointGroup`` to mount.
                Defaults to an empty list.
            lifespan: Optional ASGI lifespan callable.
        """
        self._config = config
        self._endpoint_groups = endpoint_groups or []
        self._lifespan = lifespan

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> FastAPI:
        """Construct and return a fully-configured FastAPI application.

        Pipeline:
            1. Resolve base_app (import or default FastAPI).
            2. Apply CORS middleware when origins are configured.
            3. Wire lifespan when provided.
            4. Mount endpoint routers conditionally.

        Returns:
            A ``fastapi.FastAPI`` instance ready to serve.
        """
        # 1. Base app
        if self._config.base_app is not None:
            app = _import_factory(self._config.base_app)()
        else:
            app = FastAPI(title=f"AgentOS: {self._config.name}")

        # 2. CORS
        self._apply_cors(app)

        # 3. Lifespan
        if self._lifespan is not None:
            app = FastAPI(
                title=app.title,
                lifespan=self._lifespan,
            )

        # 4. Routers
        self._mount_routers(app)

        return app

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_cors(self, app: FastAPI) -> None:
        """Apply CORS middleware when ``config.cors_allowed_origins`` is non-None.

        Registers Starlette's ``CORSMiddleware`` with the exact origins list.
        Uses permissive defaults for methods and headers (standard for AgentOS).

        Args:
            app: The FastAPI app to attach middleware to.
        """
        if self._config.cors_allowed_origins is not None:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self._config.cors_allowed_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

    def _mount_routers(self, app: FastAPI) -> None:
        """Mount endpoint routers, evaluating conditional expressions.

        For each ``EndpointGroup``:
            - If ``conditional`` is ``None`` → always mounted.
            - If ``conditional`` is a dotted expression → mounted only when
              the corresponding ``AgentOSConfig`` attribute evaluates truthy.

        Args:
            app: The FastAPI app to attach routers to.
        """
        for group in self._endpoint_groups:
            if group.conditional is None or self._evaluate_conditional(group.conditional):
                app.include_router(group.router, prefix=group.prefix)

    def _evaluate_conditional(self, expr: str) -> bool:
        """Evaluate a dotted expression against ``AgentOSConfig`` attributes.

        Walks ``getattr`` along the dot-separated path starting from
        ``self._config``. Examples:

            - ``"tracing"`` → ``self._config.tracing``
            - ``"scheduler.enabled"`` → ``self._config.scheduler.enabled``
            - ``"authorization.enabled"`` → ``self._config.authorization.enabled``

        Args:
            expr: A dotted attribute path string.

        Returns:
            The boolean value of the resolved attribute.

        Raises:
            AttributeError: If any segment of the path is not a valid attribute.
            TypeError: If the resolved value is not a primitive.
        """
        parts = expr.split(".")
        current: Any = self._config
        for part in parts:
            current = getattr(current, part)
        return bool(current)
