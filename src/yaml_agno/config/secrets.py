"""Audited SecretManager wrapper (SPEC_23 §2.4, TASK_236).

Wraps a core-cenf :class:`SecretManager` (``core_infrastructure.secrets.ports``)
and adds the audit trail without re-implementing secret storage, caching or
rotation. Core Manager === Secrets; this wrapper only *observes* access.

The core adapter owns cache/remote semantics; this wrapper records the
*effective* hit kind: ``remote`` on success, ``miss`` on failure. Audited
access is best-effort: a recording failure never breaks the secret read.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.secrets.ports import SecretManager

from yaml_agno.config.audit import HitKind, NoopSecretAuditRecorder, SecretAuditRecorder

__all__ = ["SecretAccessAuditor"]

logger = logging.getLogger(__name__)


class SecretAccessAuditor:
    """Observability wrapper around a core :class:`SecretManager`.

    Args:
        core: The core-cenf SecretManager being wrapped. Imported from the
            ``core_infrastructure`` protocol layer, never an adapter: the
            wiring (``bootstrap.build_secret_manager``) injects the adapter.
        auditor: Optional :class:`SecretAuditRecorder`. When None, access is
            audited to :class:`NoopSecretAuditRecorder` (no-op).
        actor: Default actor name stamped on audit records.
    """

    def __init__(
        self,
        core: SecretManager,
        *,
        auditor: SecretAuditRecorder | None = None,
        actor: str = "yaml-agno",
    ) -> None:
        self._core = core
        self._auditor: SecretAuditRecorder = auditor or NoopSecretAuditRecorder()
        self._actor = actor

    @property
    def core(self) -> SecretManager:
        """The wrapped core manager (protocol dependency, not an adapter)."""
        return self._core

    async def get_secret(self, key: str) -> Any:
        """Read a secret, recording the access attempt.

        Args:
            key: Secret identifier.

        Returns:
            The secret value.

        Raises:
            ValidationError: If the secret is missing or the core adapter
                fails (the audit records ``hit="miss"``, ``ok=False`` first).
        """
        try:
            value = await self._core.get_secret(key)
        except ValidationError:
            await self._audit(secret_name=key, ok=False, hit="miss")
            raise
        await self._audit(secret_name=key, ok=True, hit="remote")
        return value

    def invalidate_cache(self, key: str | None = None) -> None:
        """Delegate cache invalidation to the core manager."""
        self._core.invalidate_cache(key)

    async def rotate_secret(self, key: str, new_value: str) -> None:
        """Rotate a secret, recording the successful rotation."""
        await self._core.rotate_secret(key, new_value)
        await self._audit(secret_name=key, ok=True, hit="remote")

    def get_json_schema(self) -> dict[str, Any]:
        """Delegate schema introspection to the core manager."""
        return cast(dict[str, Any], self._core.get_json_schema())

    async def _audit(self, *, secret_name: str, ok: bool, hit: HitKind) -> None:
        try:
            await self._auditor.record(secret_name=secret_name, ok=ok, hit=hit, actor=self._actor)
        except Exception:
            logger.warning("secret audit recording failed for %s", secret_name, exc_info=True)
