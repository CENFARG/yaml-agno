"""Pytest fixtures for L-03 JWT isolation integration tests (S5a.1).

Sets up the L-03 test environment:
- Session signing key and AuthorizationConfig with user_isolation=True
- DevJwtIssuer with token fixtures for alice in tenant-a, alice in tenant-b, and admin
- YamlAgentOS with StaticReplyModel and SQLite auto-provisioning
- FastAPI TestClient wrapped in a lifespan context manager
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.os.config import AuthorizationConfig
from fastapi.testclient import TestClient

from tests.integration.helpers import DevJwtIssuer, StaticReplyModel
from tests.integration.helpers.conftest import (
    authorization_config,
    dev_jwt_issuer,
    dev_jwt_signing_key,
    dev_token,
)
from yaml_agno.api.app import YamlAgentOS

__all__ = [
    "USER_SCOPES",
    "admin_headers",
    "admin_token",
    "alice_a_headers",
    "alice_a_token",
    "alice_b_headers",
    "alice_b_token",
    "authorization_config",
    "dev_jwt_issuer",
    "dev_jwt_signing_key",
    "dev_token",
    "l03_agent",
    "l03_app",
    "l03_client",
    "l03_db",
]

# Standard scopes for regular user tokens in L-03 tests
USER_SCOPES = [
    "agents:run",
    "agents:read",
    "sessions:read",
    "sessions:write",
    "memories:read",
    "memories:write",
]


@pytest.fixture
def l03_db(tmp_path: Path) -> SqliteDb:
    """Provide an isolated SQLite database file per test."""
    db_file = str(tmp_path / "l03_isolation.db")
    return SqliteDb(db_file=db_file)


@pytest.fixture
def l03_agent() -> Agent:
    """Provide a test agent with StaticReplyModel."""
    return Agent(name="l03-agent", model=StaticReplyModel())


@pytest.fixture
def l03_app(
    l03_agent: Agent,
    authorization_config: AuthorizationConfig,
    l03_db: SqliteDb,
) -> YamlAgentOS:
    """Construct a YamlAgentOS instance in JWT isolation mode."""
    return YamlAgentOS(
        agents=[l03_agent],
        authorization=True,
        authorization_config=authorization_config,
        mount_tenant_context=False,
        db=l03_db,
    )


@pytest.fixture
def l03_client(l03_app: YamlAgentOS) -> Iterator[TestClient]:
    """Provide a TestClient with lifespan context (initializes auto-provisioned DBs)."""
    with TestClient(l03_app.get_app()) as client:
        yield client


@pytest.fixture
def alice_a_token(dev_jwt_issuer: DevJwtIssuer) -> str:
    """Mint a token for principal 'alice' under 'tenant-a'."""
    return dev_jwt_issuer.mint("tenant-a", "alice", scopes=USER_SCOPES)


@pytest.fixture
def alice_b_token(dev_jwt_issuer: DevJwtIssuer) -> str:
    """Mint a token for principal 'alice' under 'tenant-b'."""
    return dev_jwt_issuer.mint("tenant-b", "alice", scopes=USER_SCOPES)


@pytest.fixture
def alice_a_headers(dev_jwt_issuer: DevJwtIssuer, alice_a_token: str) -> dict[str, str]:
    """Authorization headers for alice in tenant-a."""
    return dev_jwt_issuer.auth_header(alice_a_token)


@pytest.fixture
def alice_b_headers(dev_jwt_issuer: DevJwtIssuer, alice_b_token: str) -> dict[str, str]:
    """Authorization headers for alice in tenant-b."""
    return dev_jwt_issuer.auth_header(alice_b_token)


@pytest.fixture
def admin_token(dev_jwt_issuer: DevJwtIssuer) -> str:
    """Mint an admin token with agent_os:admin scope."""
    return dev_jwt_issuer.mint("tenant-a", "admin-user", scopes=["agent_os:admin"])


@pytest.fixture
def admin_headers(dev_jwt_issuer: DevJwtIssuer, admin_token: str) -> dict[str, str]:
    """Authorization headers for admin."""
    return dev_jwt_issuer.auth_header(admin_token)
