"""AuthorizationAdapter — resolves RBAC config from AuthorizationSettings (SPEC_12 Slice 3).

Bridges yaml-agno's declarative ``AuthorizationSettings`` to Agno's runtime
``AuthorizationConfig``. Resolves ``${SECRET:KEY}`` references via an injected
``secret_manager`` callable and builds ``AuthorizationConfig`` with mandatory
``user_isolation=True``.

Design (sdd/control-plane-s3/design):
    - Constructor-injected ``secret_manager`` callable ``(key: str) -> str``.
    - SYNC ``build()`` (consistent with ``AgentOSFactory.build()`` call site).
    - Flat secret resolution (only top-level keys checked for ``${SECRET:...}``).
    - ``user_isolation=True`` always (RBAC security invariant).
    - No ``os.environ`` — all resolution through the callable.
    - ``AuthorizationBuildError`` on unresolvable secrets.
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
        """Build an ``AuthorizationConfig`` from settings.

        Pipeline:
            1. Guard: if ``enabled=False``, return ``(False, None)``.
            2. Resolve ``${SECRET:...}`` refs in ``config`` dict.
            3. Resolve ``${SECRET:...}`` refs in ``basic_auth`` dict.
            4. Build ``AuthorizationConfig(**kwargs)`` with ``user_isolation=True``.

        Args:
            settings: Validated ``AuthorizationSettings`` from ``AgentOSConfig``.

        Returns:
            ``(True, AuthorizationConfig)`` when enabled, or ``(False, None)``
            when disabled.

        Raises:
            AuthorizationBuildError: A secret reference could not be resolved.
        """
        if not settings.enabled:
            return False, None

        kwargs: dict[str, Any] = {}

        # Resolve config dict
        if settings.config is not None:
            resolved_config = self._resolve_secrets(settings.config)
            kwargs.update(resolved_config)

        # Resolve basic_auth dict
        if settings.basic_auth is not None:
            kwargs["basic_auth"] = self._resolve_secrets(settings.basic_auth)

        # Security invariant: RBAC requires user isolation
        kwargs["user_isolation"] = True

        return True, AuthorizationConfig(**kwargs)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_secrets(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve ``${SECRET:KEY}`` patterns in dict values.

        Only string values matching the secret pattern are processed.
        Non-strings and non-matching strings pass through unchanged.

        Args:
            config: Raw config dict from ``AuthorizationSettings``.

        Returns:
            A new dict with secret references resolved.

        Raises:
            AuthorizationBuildError: A secret could not be resolved.
        """
        resolved: dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, str) and self._is_secret_ref(value):
                secret_key = _SECRET_PATTERN.match(value).group(1)  # type: ignore[union-attr]
                try:
                    result = self._secret_manager(secret_key)
                except KeyError as exc:
                    raise AuthorizationBuildError(
                        f"Cannot resolve secret '{secret_key}': {exc}"
                    ) from exc
                if result is None:
                    raise AuthorizationBuildError(
                        f"Cannot resolve secret '{secret_key}': secret_manager returned None"
                    )
                resolved[key] = result
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _is_secret_ref(value: str) -> bool:
        """Return True if ``value`` matches ``${SECRET:KEY}``."""
        return bool(_SECRET_PATTERN.match(value))
