"""AuthorizationAdapter — fail-fast RBAC config build (agentos-authorization-build).

Bridges yaml-agno's declarative ``AuthorizationSettings`` to Agno's runtime
``AuthorizationConfig``. The build contract is fail-fast (VQ011, D-F1-10):
only the whitelisted fields map, ``user_isolation`` is an adapter-owned
invariant, and ``basic_auth``/unknown keys raise ``AuthorizationBuildError``
instead of being silently dropped by pydantic ``extra=ignore`` (the R1
declarative fail-open).

Design (spec/agentos-authorization-build):
    - Constructor-injected ``secret_manager`` callable ``(key: str) -> str``.
    - SYNC ``build()`` (consistent with ``AgentOSFactory.build()`` call site).
    - Shared module-level ``_map_authorization_config`` used by the adapter
      AND the legacy factory path (one contract, two call sites).
    - Secret resolution ONLY on whitelisted keys; flat strings plus list
      elements (e.g. ``verification_keys``) are resolved.
    - ``user_isolation=True`` always (RBAC security invariant).
    - No ``os.environ`` — all resolution through the callable.
    - ``AuthorizationBuildError`` on unknown keys, ``basic_auth``,
      ``user_isolation`` override, or unresolvable secrets.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from agno.os.config import AuthorizationConfig

from yaml_agno.agentos.errors import AuthorizationBuildError
from yaml_agno.models.config.agentos_config import AuthorizationSettings

__all__ = ["AuthorizationAdapter", "AuthorizationBuildError"]

# Pattern: ${SECRET:KEY} where KEY is one or more word chars / hyphens / underscores
_SECRET_PATTERN = re.compile(r"^\$\{SECRET:([\w\-]+)\}$")

# agno 2.8.7 AuthorizationConfig accepts EXACTLY these 7 fields (verified
# 2026-08-18). ``user_isolation`` is an adapter-owned security invariant; the
# other 6 are settable from ``settings.config``.
_SUPPORTED_FIELDS: tuple[str, ...] = (
    "verification_keys",
    "jwks_file",
    "algorithm",
    "verify_audience",
    "audience",
    "admin_scope",
    "user_isolation",
)
_SUPPORTED_FIELD_SET: frozenset[str] = frozenset(_SUPPORTED_FIELDS)
_SETTABLE_FIELDS: frozenset[str] = _SUPPORTED_FIELD_SET - {"user_isolation"}
_SUPPORTED_FIELDS_LISTING = ", ".join(_SUPPORTED_FIELDS)


def _map_authorization_config(
    settings: AuthorizationSettings,
    secret_manager: Callable[[str], str] | None = None,
) -> tuple[bool, AuthorizationConfig | None]:
    """Map ``AuthorizationSettings`` to ``AuthorizationConfig`` fail-fast.

    Single shared mapping contract for the adapter (pass a ``secret_manager``)
    and the legacy factory path (``secret_manager=None`` — any residual
    ``${SECRET:...}`` reference then raises instead of being forwarded as a
    literal, which would be another silent fail-open).

    Validation order is part of the contract (VQ011):
        1. Guard: ``enabled=False`` → ``(False, None)`` — wins over every
           rejection below.
        2. Reject ``basic_auth`` (no sink in agno 2.8.7).
        3. Whitelist: unknown config keys → error listing the 7 fields.
        4. Reject explicit ``user_isolation`` (adapter-owned invariant).
        5. Resolve ``${SECRET:...}`` only on the whitelisted keys.
        6. Build ``AuthorizationConfig(**kwargs, user_isolation=True)``.

    Args:
        settings: Validated ``AuthorizationSettings``.
        secret_manager: Optional callable ``(key: str) -> str`` resolving
            ``${SECRET:KEY}`` references. When ``None``, residual references
            raise instead of resolving.

    Returns:
        ``(True, AuthorizationConfig)`` when enabled, or ``(False, None)``
        when disabled.

    Raises:
        AuthorizationBuildError: On unknown keys, ``basic_auth``,
            ``user_isolation`` override, or an unresolvable secret.
    """
    if not settings.enabled:
        return False, None

    if settings.basic_auth is not None:
        raise AuthorizationBuildError(
            "AuthorizationSettings.basic_auth is UNSUPPORTED in agno 2.8.7: "
            "AuthorizationConfig has no basic_auth sink, so this value would "
            "be silently ignored (fail-open). The future sink is "
            "BasicAuthMiddleware (SPEC_19 §1.2, slice S5a.2)."
        )

    config: dict[str, Any] = settings.config or {}

    # user_isolation is a documented field, so it is never "unknown" — the
    # invariant rejection below is the only path that rejects it.
    unknown = set(config) - _SUPPORTED_FIELD_SET
    if unknown:
        keys = ", ".join(sorted(unknown))
        raise AuthorizationBuildError(
            f"Unknown AuthorizationConfig key(s) '{keys}'. agno 2.8.7 accepts "
            f"exactly: {_SUPPORTED_FIELDS_LISTING}."
        )

    if "user_isolation" in config:
        raise AuthorizationBuildError(
            "user_isolation is a security invariant always set to True by the "
            "authorization adapter and is not settable from YAML."
        )

    kwargs: dict[str, Any] = {}
    for key, value in config.items():
        if key in _SETTABLE_FIELDS:
            kwargs[key] = _resolve_value(value, secret_manager)

    kwargs["user_isolation"] = True

    return True, AuthorizationConfig(**kwargs)


def _require_isolated_auth(
    authorization: bool,
    authorization_config: AuthorizationConfig | None,
) -> str | None:
    """Return the VQ010 refusal message, or None when the config is acceptable.

    Shared isolation predicate (VQ010, D-F1-02) for every authenticated startup
    entry point: fires iff ``authorization is True`` AND (``authorization_config
    is None`` OR ``authorization_config.user_isolation is not True``). Agno
    defaults ``user_isolation`` to ``False``, which would boot an
    authenticated-but-unisolated server (Judgment Day CRITICAL #3120).

    Strict identity (``is True``) on BOTH flags: truthy non-booleans such as
    ``1`` or ``"true"`` do NOT satisfy the guard. An ``authorization`` other
    than ``True`` returns None — the dev path (``authorization=False``) stays
    unchanged and ``run_server`` keeps its own refuse-to-start guard.

    Call sites raise their own exception type from the returned message:
    ``YamlAgentOS.__init__`` raises ``ValueError`` (JD-01 convention);
    ``run_server`` raises ``RuntimeError`` (existing VQ010 tests).

    Args:
        authorization: Authorization flag as forwarded to Agno.
        authorization_config: ``AuthorizationConfig`` or None.

    Returns:
        The canonical VQ010 refusal message when authenticated startup would
        be unisolated, or None when the configuration is acceptable.
    """
    if authorization is not True:
        return None
    if authorization_config is not None and authorization_config.user_isolation is True:
        return None
    return (
        "VQ010 isolation refusal: authorization=True requires an "
        "AuthorizationConfig with user_isolation=True. Agno defaults "
        "user_isolation to False, which boots an authenticated-but-unisolated "
        "server. Pass authorization_config=AuthorizationConfig("
        "user_isolation=True, ...). For dev/test workflows without JWT, use "
        "create_app() with authorization=False."
    )


def _resolve_value(
    value: Any,
    secret_manager: Callable[[str], str] | None,
) -> Any:
    """Resolve secret references in a single config value.

    Handles flat strings (``"${SECRET:KEY}"``) and list elements (e.g.
    ``verification_keys=["${SECRET:KEY}"]``). Non-string, non-matching values
    pass through unchanged.
    """
    if isinstance(value, str):
        if _is_secret_ref(value):
            return _resolve_secret(value, secret_manager)
        return value
    if isinstance(value, list):
        return [_resolve_value(item, secret_manager) for item in value]
    return value


def _resolve_secret(
    value: str,
    secret_manager: Callable[[str], str] | None,
) -> str:
    """Resolve a ``${SECRET:KEY}`` literal via ``secret_manager``.

    Raises:
        AuthorizationBuildError: When no ``secret_manager`` is available
            (legacy path) or the reference cannot be resolved.
    """
    secret_key = _SECRET_PATTERN.match(value).group(1)  # type: ignore[union-attr]
    if secret_manager is None:
        raise AuthorizationBuildError(
            f"Cannot resolve secret '{secret_key}': no secret resolution is "
            f"available in this path; refusing to forward the literal "
            f"'${{SECRET:{secret_key}}}' (would be a silent fail-open)."
        )
    try:
        result = secret_manager(secret_key)
    except KeyError as exc:
        raise AuthorizationBuildError(
            f"Cannot resolve secret '{secret_key}': {exc}"
        ) from exc
    if result is None:
        raise AuthorizationBuildError(
            f"Cannot resolve secret '{secret_key}': secret_manager returned None"
        )
    return result


def _is_secret_ref(value: str) -> bool:
    """Return True if ``value`` matches ``${SECRET:KEY}``."""
    return bool(_SECRET_PATTERN.match(value))


class AuthorizationAdapter:
    """Build ``AuthorizationConfig`` from ``AuthorizationSettings`` with secret resolution.

    Args:
        secret_manager: Callable ``(key: str) -> str`` that resolves
            ``${SECRET:KEY}`` references. Must raise ``KeyError`` for
            unknown keys.
    """

    def __init__(self, secret_manager: Callable[[str], str]) -> None:
        self._secret_manager = secret_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, settings: AuthorizationSettings) -> tuple[bool, Any | None]:
        """Build an ``AuthorizationConfig`` from settings (fail-fast whitelist).

        Delegates to the shared module-level ``_map_authorization_config``
        with this adapter's ``secret_manager``.

        Args:
            settings: Validated ``AuthorizationSettings`` from ``AgentOSConfig``.

        Returns:
            ``(True, AuthorizationConfig)`` when enabled, or ``(False, None)``
            when disabled.

        Raises:
            AuthorizationBuildError: On unknown keys, ``basic_auth``,
                ``user_isolation`` override, or an unresolvable secret.
        """
        return _map_authorization_config(settings, self._secret_manager)
