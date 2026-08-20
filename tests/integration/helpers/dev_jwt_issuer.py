"""Dev JWT issuer for integration tests and local token minting.

This module is strictly test-only (never imported in src/).
It mints HS256 JWTs with composite sub="{tenant_id}:{principal_id}"
built via yaml_agno.memory.resolve_user_id (VQ012 invariant).
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any

import jwt
from agno.os.middleware.jwt import is_reserved_principal

import yaml_agno.memory


class DevJwtIssuer:
    """Test helper for minting HS256 JWT tokens for Agno JWT / user_isolation testing."""

    def __init__(self, signing_key: str) -> None:
        if not signing_key:
            raise ValueError("signing_key must be a non-empty string")
        self.signing_key = signing_key

    def mint(
        self,
        tenant_id: str,
        principal_id: str,
        *,
        scopes: Sequence[str] = (),
        expires_delta: datetime.timedelta = datetime.timedelta(minutes=10),
    ) -> str:
        """Mint an HS256 JWT token with composite subject.

        Args:
            tenant_id: The tenant ID (must not contain ':').
            principal_id: The principal/user ID (must not contain ':').
            scopes: Optional sequence of scopes (claim name 'scopes').
            expires_delta: Token expiration delta from now (default: 10 minutes).

        Returns:
            Encoded HS256 JWT token string.

        Raises:
            ValueError: If tenant_id or principal_id contains ':', or if
                tenant_id, principal_id, or the resulting subject is a
                reserved principal.
        """
        if ":" in tenant_id:
            raise ValueError(f"tenant_id must not contain ':': {tenant_id!r}")
        if ":" in principal_id:
            raise ValueError(f"principal_id must not contain ':': {principal_id!r}")
        if is_reserved_principal(tenant_id):
            raise ValueError(f"Tenant {tenant_id!r} is a reserved principal")
        if is_reserved_principal(principal_id):
            raise ValueError(f"Principal {principal_id!r} is a reserved principal")

        # VQ012: Build composite sub ONLY via resolve_user_id (never inline f"{tenant_id}:{principal_id}")
        sub = yaml_agno.memory.resolve_user_id(None, principal_id=principal_id, tenant_id=tenant_id)

        if is_reserved_principal(sub):
            raise ValueError(f"Subject {sub!r} is a reserved principal")

        now = datetime.datetime.now(datetime.UTC)
        payload: dict[str, Any] = {
            "sub": sub,
            "scopes": list(scopes),
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
        }
        return jwt.encode(payload, self.signing_key, algorithm="HS256")

    @staticmethod
    def auth_header(token: str) -> dict[str, str]:
        """Return the HTTP Authorization header dict for the given token."""
        return {"Authorization": f"Bearer {token}"}
