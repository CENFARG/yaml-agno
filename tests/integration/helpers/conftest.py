"""Pytest fixtures for DevJwtIssuer and Agno AuthorizationConfig (S5a.1).

Provides session-scoped signing key, authorization configuration, and
token-minting fixtures for L-03 integration tests.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

import pytest
from agno.os.config import AuthorizationConfig

from tests.integration.helpers.dev_jwt_issuer import DevJwtIssuer


@pytest.fixture(scope="session")
def dev_jwt_signing_key() -> str:
    """Generate a random 48-byte URL-safe signing key once per test session."""
    return secrets.token_urlsafe(48)


@pytest.fixture
def authorization_config(dev_jwt_signing_key: str) -> AuthorizationConfig:
    """Return an AuthorizationConfig wired with the session signing key and user_isolation=True."""
    return AuthorizationConfig(
        verification_keys=[dev_jwt_signing_key],
        algorithm="HS256",
        user_isolation=True,
    )


@pytest.fixture
def dev_jwt_issuer(dev_jwt_signing_key: str) -> DevJwtIssuer:
    """Return a DevJwtIssuer instance configured with the session signing key."""
    return DevJwtIssuer(dev_jwt_signing_key)


@pytest.fixture
def dev_token(dev_jwt_issuer: DevJwtIssuer) -> Callable[..., str]:
    """Factory fixture to mint dev JWT tokens."""
    return dev_jwt_issuer.mint
