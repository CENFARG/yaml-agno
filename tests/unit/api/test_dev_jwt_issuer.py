"""Contract tests for DevJwtIssuer (S5a.1 WU1).

Verifies the test-only dev JWT issuer helper:
- Composite subject built via resolve_user_id (VQ012 invariant)
- Fail-fast validation on ':' in tenant_id and principal_id
- Fail-fast rejection of reserved principals (sa:x, __scheduler__, __oauth__:x)
- Claims structure (sub, scopes, iat, exp) with HS256 algorithm
- auth_header formatting ("Bearer <token>")
"""

import datetime

import jwt
import pytest
from pytest_mock import MockerFixture

import yaml_agno.memory
from tests.integration.helpers.dev_jwt_issuer import DevJwtIssuer

TEST_KEY = "dev-secret-signing-key-for-unit-tests-only-48bytes"


def test_dev_jwt_issuer_mints_valid_hs256_token() -> None:
    """DevJwtIssuer mints a valid HS256 JWT with sub, scopes, iat, and exp claims."""
    issuer = DevJwtIssuer(TEST_KEY)
    token = issuer.mint("tenant-a", "alice", scopes=["agents:read", "sessions:read"])

    payload = jwt.decode(token, TEST_KEY, algorithms=["HS256"])
    assert payload["sub"] == "tenant-a:alice"
    assert payload["scopes"] == ["agents:read", "sessions:read"]
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] - payload["iat"] == 600  # Default 10 minutes


def test_dev_jwt_issuer_uses_resolve_user_id(mocker: MockerFixture) -> None:
    """DevJwtIssuer must build composite sub via resolve_user_id, never inline string formatting."""
    spy = mocker.spy(yaml_agno.memory, "resolve_user_id")
    issuer = DevJwtIssuer(TEST_KEY)

    token = issuer.mint("tenant-corp", "bob")
    payload = jwt.decode(token, TEST_KEY, algorithms=["HS256"])

    assert payload["sub"] == "tenant-corp:bob"
    assert spy.call_count == 1
    # Verify resolve_user_id was called with tenant_id and principal_id
    call_args = spy.call_args
    assert call_args.kwargs.get("tenant_id") == "tenant-corp" or (
        len(call_args.args) >= 3 and call_args.args[2] == "tenant-corp"
    )


def test_dev_jwt_issuer_rejects_colon_in_tenant_id() -> None:
    """Fail-fast if tenant_id contains ':' to ensure 2-part parseable composite."""
    issuer = DevJwtIssuer(TEST_KEY)
    with pytest.raises(ValueError, match="tenant_id"):
        issuer.mint("tenant:with:colon", "alice")


def test_dev_jwt_issuer_rejects_colon_in_principal_id() -> None:
    """Fail-fast if principal_id contains ':' to ensure 2-part parseable composite."""
    issuer = DevJwtIssuer(TEST_KEY)
    with pytest.raises(ValueError, match="principal_id"):
        issuer.mint("tenant-a", "alice:admin")


@pytest.mark.parametrize(
    ("tenant_id", "principal_id"),
    [
        ("sa", "alice"),  # sub becomes "sa:alice" -> reserved
        ("sa:admin", "user"),  # colon + reserved prefix
        ("__oauth__", "service"),  # sub becomes "__oauth__:service" -> reserved
        ("tenant-a", "__scheduler__"),  # principal is __scheduler__ -> reserved
        ("__scheduler__", "worker"),  # tenant is __scheduler__ -> reserved
    ],
)
def test_dev_jwt_issuer_rejects_reserved_principals(tenant_id: str, principal_id: str) -> None:
    """Fail-fast if sub or principal resolves to a system-reserved principal."""
    issuer = DevJwtIssuer(TEST_KEY)
    with pytest.raises(ValueError, match="[Rr]eserved|[Cc]olon|tenant_id|principal_id"):
        issuer.mint(tenant_id, principal_id)


def test_dev_jwt_issuer_custom_expiration_and_empty_scopes() -> None:
    """Custom expires_delta and default empty scopes are correctly encoded."""
    issuer = DevJwtIssuer(TEST_KEY)
    custom_delta = datetime.timedelta(minutes=30)
    token = issuer.mint("tenant-b", "charlie", expires_delta=custom_delta)

    payload = jwt.decode(token, TEST_KEY, algorithms=["HS256"])
    assert payload["sub"] == "tenant-b:charlie"
    assert payload["scopes"] == []
    assert payload["exp"] - payload["iat"] == 1800


def test_dev_jwt_issuer_auth_header_format() -> None:
    """auth_header returns {'Authorization': 'Bearer <token>'} matching HTTP Bearer scheme."""
    issuer = DevJwtIssuer(TEST_KEY)
    header = issuer.auth_header("dummy.jwt.token")
    assert header == {"Authorization": "Bearer dummy.jwt.token"}

    # Static access
    assert DevJwtIssuer.auth_header("another.token") == {"Authorization": "Bearer another.token"}


def test_dev_jwt_issuer_empty_signing_key_rejected() -> None:
    """DevJwtIssuer refuses empty signing keys."""
    with pytest.raises(ValueError, match="signing_key"):
        DevJwtIssuer("")
