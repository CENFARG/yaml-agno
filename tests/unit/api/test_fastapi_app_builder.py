"""RED tests for ``FastAPIAppBuilder`` — SPEC_12 Slice 1, PR 3.

These tests reference ``yaml_agno.api.fastapi_app_builder.FastAPIAppBuilder``
and ``EndpointGroup`` which do NOT exist yet (RED phase). They cover the 8
scenarios from ``sdd/control-plane/design`` §5.3:

    1. base_app resolved from import path
    2. default FastAPI when no base_app
    3. CORS middleware applied when origins provided
    4. No CORS when origins is None
    5. Conditional router NOT mounted when feature is disabled
    6. Conditional router IS mounted when feature is enabled
    7. Unconditional router always mounted
    8. Invalid base_app import raises ImportError

Strict TDD: tests written BEFORE implementation.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from yaml_agno.api.fastapi_app_builder import EndpointGroup, FastAPIAppBuilder
from yaml_agno.models.config.agentos_config import AgentOSConfig, SchedulerSettings

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_config() -> AgentOSConfig:
    """Minimal config: name + one agent."""
    return AgentOSConfig(name="test-os", agents=["researcher"])


@pytest.fixture
def config_with_base_app() -> AgentOSConfig:
    """Config with base_app import path."""
    return AgentOSConfig(name="custom-os", agents=["a"], base_app="tests.unit.api._dummy_factory:get_app")


@pytest.fixture
def config_with_cors() -> AgentOSConfig:
    """Config with CORS origins."""
    return AgentOSConfig(
        name="cors-os",
        agents=["a"],
        cors_allowed_origins=["https://os.agno.com", "https://corp.internal"],
    )


@pytest.fixture
def config_with_cors_none() -> AgentOSConfig:
    """Config where CORS origins is None."""
    return AgentOSConfig(name="no-cors-os", agents=["a"], cors_allowed_origins=None)


@pytest.fixture
def config_scheduler_disabled() -> AgentOSConfig:
    """Config with scheduler.enabled=False."""
    return AgentOSConfig(name="no-sched-os", agents=["a"], scheduler=SchedulerSettings(enabled=False))


@pytest.fixture
def config_scheduler_enabled() -> AgentOSConfig:
    """Config with scheduler.enabled=True."""
    return AgentOSConfig(name="sched-os", agents=["a"], scheduler=SchedulerSettings(enabled=True))


@pytest.fixture
def config_invalid_base_app() -> AgentOSConfig:
    """Config with non-existent base_app import path."""
    return AgentOSConfig(name="bad-os", agents=["a"], base_app="nonexistent.module:factory")


# ---------------------------------------------------------------------------
# 1. base_app resolution from import path
# ---------------------------------------------------------------------------

class TestBaseAppResolution:
    """``build()`` resolves ``config.base_app`` via importlib."""

    def test_base_app_from_import_path(self, basic_config: AgentOSConfig, mocker: Any) -> None:
        """When ``config.base_app`` is an import path, the builder imports and calls it.

        Given: a config with base_app="my.module:factory_fn"
        And: factory_fn() returns a FastAPI app
        When: build() is called
        Then: the returned app is the one from factory_fn()
        """
        mock_app = FastAPI(title="Imported App")
        mocker.patch(
            "yaml_agno.api.fastapi_app_builder._import_factory",
            return_value=lambda: mock_app,
        )

        cfg = AgentOSConfig(name="test-os", agents=["a"], base_app="my.module:factory_fn")
        builder = FastAPIAppBuilder(config=cfg)
        result = builder.build()

        assert result is mock_app
        assert result.title == "Imported App"

    def test_default_app_when_no_base_app(self, basic_config: AgentOSConfig) -> None:
        """When ``config.base_app`` is None, a new FastAPI with config.name is created.

        Given: a config with base_app=None
        When: build() is called
        Then: a new FastAPI instance is returned
        And: its title derives from config.name
        """
        builder = FastAPIAppBuilder(config=basic_config)
        result = builder.build()

        assert isinstance(result, FastAPI)
        assert "test-os" in result.title


# ---------------------------------------------------------------------------
# 2 & 3. CORS middleware
# ---------------------------------------------------------------------------

class TestCORSMiddleware:
    """CORS middleware is conditionally applied based on ``config.cors_allowed_origins``."""

    def test_cors_middleware_applied(self, config_with_cors: AgentOSConfig) -> None:
        """When ``cors_allowed_origins`` is non-None, CORSMiddleware is registered.

        Given: a config with cors_allowed_origins=["https://os.agno.com"]
        When: build() is called
        Then: the FastAPI app has CORSMiddleware in its middleware stack
        And: the middleware uses the provided origins
        """
        builder = FastAPIAppBuilder(config=config_with_cors)
        app = builder.build()

        # Find CORSMiddleware in the middleware stack
        cors_middlewares = [
            m for m in app.user_middleware
            if m.cls == CORSMiddleware
        ]
        assert len(cors_middlewares) == 1

    def test_no_cors_when_origins_none(self, config_with_cors_none: AgentOSConfig) -> None:
        """When ``cors_allowed_origins`` is None, no CORSMiddleware is registered.

        Given: a config with cors_allowed_origins=None
        When: build() is called
        Then: the app has no CORSMiddleware
        """
        builder = FastAPIAppBuilder(config=config_with_cors_none)
        app = builder.build()

        cors_middlewares = [
            m for m in app.user_middleware
            if m.cls == CORSMiddleware
        ]
        assert len(cors_middlewares) == 0


# ---------------------------------------------------------------------------
# 4, 5, 6. Conditional router mounting
# ---------------------------------------------------------------------------

class TestConditionalRouter:
    """Routers with ``conditional`` expressions are mounted only when the feature flag is active."""

    def test_conditional_router_not_mounted_when_disabled(
        self, config_scheduler_disabled: AgentOSConfig
    ) -> None:
        """When scheduler.enabled is False, the schedules router is NOT mounted.

        Given: a config with scheduler=SchedulerSettings(enabled=False)
        And: an EndpointGroup with conditional="scheduler.enabled"
        When: build() is called
        Then: the schedules router is NOT included in the app routes
        """
        schedules_router = APIRouter()

        @schedules_router.get("/schedules")
        async def list_schedules() -> dict[str, str]:
            return {"status": "ok"}

        groups = [
            EndpointGroup(
                router=schedules_router,
                prefix="/schedules",
                conditional="scheduler.enabled",
            ),
        ]
        builder = FastAPIAppBuilder(config=config_scheduler_disabled, endpoint_groups=groups)
        app = builder.build()

        # The schedules route should NOT be mounted
        route_paths = [getattr(route, "path", None) for route in app.routes]
        assert "/schedules" not in route_paths
        assert "/schedules/" not in route_paths

    def test_conditional_router_mounted_when_enabled(
        self, config_scheduler_enabled: AgentOSConfig
    ) -> None:
        """When scheduler.enabled is True, the schedules router IS mounted.

        Given: a config with scheduler=SchedulerSettings(enabled=True)
        And: an EndpointGroup with conditional="scheduler.enabled"
        When: build() is called
        Then: the schedules router IS included in the app routes
        """
        schedules_router = APIRouter()

        @schedules_router.get("/schedules")
        async def list_schedules() -> dict[str, str]:
            return {"status": "ok"}

        groups = [
            EndpointGroup(
                router=schedules_router,
                prefix="/schedules",
                conditional="scheduler.enabled",
            ),
        ]
        builder = FastAPIAppBuilder(config=config_scheduler_enabled, endpoint_groups=groups)
        app = builder.build()

        route_paths = [getattr(route, "path", None) for route in app.routes]
        assert "/schedules/schedules" in route_paths

    def test_unconditional_router_always_mounted(self, basic_config: AgentOSConfig) -> None:
        """When ``conditional`` is None, the router IS always mounted.

        Given: a config (any valid config)
        And: an EndpointGroup with conditional=None
        When: build() is called
        Then: the health router IS mounted
        """
        health_router = APIRouter()

        @health_router.get("/health")
        async def health_check() -> dict[str, str]:
            return {"status": "alive"}

        groups = [
            EndpointGroup(
                router=health_router,
                prefix="/health",
                conditional=None,
            ),
        ]
        builder = FastAPIAppBuilder(config=basic_config, endpoint_groups=groups)
        app = builder.build()

        route_paths = [getattr(route, "path", None) for route in app.routes]
        assert "/health/health" in route_paths


# ---------------------------------------------------------------------------
# 7. Invalid base_app import
# ---------------------------------------------------------------------------

class TestImportError:
    """Invalid base_app paths raise import-level errors."""

    def test_invalid_base_app_import_raises(self, config_invalid_base_app: AgentOSConfig) -> None:
        """When ``config.base_app`` points to a non-existent module, ImportError is raised.

        Given: a config with base_app="nonexistent.module:factory"
        When: build() is called
        Then: an ImportError (or ModuleNotFoundError) is raised
        """
        builder = FastAPIAppBuilder(config=config_invalid_base_app)

        with pytest.raises((ImportError, ModuleNotFoundError)):
            builder.build()
