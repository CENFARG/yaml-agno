"""Contract tests for YamlAgentOS JWT mode and JD-01 mutual exclusion (S5a.1 WU2).

Verifies the JWT mode contract:
- JD-01 guard: ``YamlAgentOS(authorization=True, mount_tenant_context=True)`` raises ValueError
  (structural mutual exclusion: JWT mode must NOT mount TenantContextMiddleware).
- ``authorization_config`` keyword argument is accepted and forwarded to ``super().__init__``.
- JWT mode app does NOT mount ``TenantContextMiddleware`` (absent from ``app.user_middleware``).
- Dev mode app (``authorization=False``, ``mount_tenant_context=True``) continues mounting
  ``TenantContextMiddleware`` as expected.
"""

from __future__ import annotations

import pytest
from agno.agent import Agent
from agno.os.config import AuthorizationConfig

from yaml_agno.api.app import YamlAgentOS
from yaml_agno.api.middleware.tenant_context import TenantContextMiddleware

pytest_plugins = ["tests.integration.helpers.conftest"]
pytestmark = pytest.mark.unit


def _build_test_agent(name: str = "jwt-test-agent") -> Agent:
    """Build a minimal real agno.Agent for test fixtures."""
    return Agent(name=name, model="openai:gpt-4o")


class TestYamlAgentOSJwtMode:
    """Contract tests for YamlAgentOS JWT mode and JD-01 structural exclusion."""

    def test_jd01_guard_rejects_authorization_true_with_mount_tenant_context_true(
        self,
    ) -> None:
        """JD-01: authorization=True and mount_tenant_context=True raises ValueError."""
        agent = _build_test_agent()
        with pytest.raises(
            ValueError,
            match=r"JD-01|authorization.*mount_tenant_context|mutually exclusive|JWT",
        ):
            YamlAgentOS(
                agents=[agent],
                authorization=True,
                mount_tenant_context=True,
            )

    def test_jd01_guard_rejects_authorization_true_with_default_mount_tenant_context(
        self,
    ) -> None:
        """JD-01: authorization=True with default mount_tenant_context=True raises ValueError."""
        agent = _build_test_agent()
        with pytest.raises(
            ValueError,
            match=r"JD-01|authorization.*mount_tenant_context|mutually exclusive|JWT",
        ):
            YamlAgentOS(
                agents=[agent],
                authorization=True,
            )

    def test_jd01_guard_allows_authorization_true_with_mount_tenant_context_false(
        self, authorization_config: AuthorizationConfig
    ) -> None:
        """JD-01: authorization=True is allowed when mount_tenant_context=False."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(
            agents=[agent],
            authorization=True,
            authorization_config=authorization_config,
            mount_tenant_context=False,
        )
        assert os_app.authorization is True
        assert os_app._mount_tenant_context is False

    def test_init_accepts_and_forwards_authorization_config(
        self, authorization_config: AuthorizationConfig
    ) -> None:
        """authorization_config is accepted and forwarded to super().__init__."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(
            agents=[agent],
            authorization=True,
            authorization_config=authorization_config,
            mount_tenant_context=False,
        )
        assert os_app.authorization_config is authorization_config
        assert os_app.authorization_config.user_isolation is True

    def test_init_default_authorization_config_is_none(self) -> None:
        """Default authorization_config is None when not provided."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(agents=[agent])
        assert os_app.authorization_config is None

    def test_jwt_mode_app_does_not_mount_tenant_context_middleware(
        self, authorization_config: AuthorizationConfig
    ) -> None:
        """In JWT mode, get_app() does NOT mount TenantContextMiddleware."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(
            agents=[agent],
            authorization=True,
            authorization_config=authorization_config,
            mount_tenant_context=False,
        )
        app = os_app.get_app()

        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantContextMiddleware not in middleware_classes
        # Verify AuthMiddleware IS mounted by Agno
        assert any(cls.__name__ == "AuthMiddleware" for cls in middleware_classes)

    def test_dev_mode_app_mounts_tenant_context_middleware(self) -> None:
        """In dev mode (authorization=False, mount_tenant_context=True), middleware is mounted."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(
            agents=[agent],
            authorization=False,
            mount_tenant_context=True,
        )
        app = os_app.get_app()

        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantContextMiddleware in middleware_classes

    def test_dev_mode_app_skips_tenant_context_middleware_when_disabled(
        self,
    ) -> None:
        """In dev mode with mount_tenant_context=False, middleware is not mounted."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(
            agents=[agent],
            authorization=False,
            mount_tenant_context=False,
        )
        app = os_app.get_app()

        middleware_classes = [m.cls for m in app.user_middleware]
        assert TenantContextMiddleware not in middleware_classes
