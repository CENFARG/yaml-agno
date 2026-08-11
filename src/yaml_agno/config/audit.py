"""Secret access audit trail (SPEC_23 §2.4, TASK_236).

Every access to a secret through the yaml-agno wiring layer is recorded in
``yamlagno.secret_audit`` (see ``db/models/secret_audit.py``): who accessed
which secret, when, and whether it was a hit or a miss. The recorder protocol
keeps the audited wrapper (``secrets.SecretAccessAuditor``) decoupled from
the storage adapter.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from core_infrastructure.database.ports import GenericRepository

from yaml_agno.db.models.secret_audit import SecretAuditRecord

__all__ = [
    "NoopSecretAuditRecorder",
    "RepositorySecretAuditRecorder",
    "SecretAuditRecorder",
]

# Sentinel: audited wrapper cannot know whether the core adapter served the
# value from cache or remote storage — the core does not expose the hit kind.
# The wrapper therefore records the *effective* access as "remote" on success
# and "miss" on failure. RepositorySecretAuditRecorder persists what it gets.
HitKind = str  # "cache" | "remote" | "miss"


@runtime_checkable
class SecretAuditRecorder(Protocol):
    """Records a single secret access event.

    Implementations are async-only (storage is async in yaml-agno).
    """

    async def record(
        self,
        *,
        secret_name: str,
        ok: bool,
        hit: HitKind,
        actor: str = "yaml-agno",
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> None: ...


class NoopSecretAuditRecorder:
    """Discards every audit event.

    Used when no audit recorder is wired (e.g. dev adapter with audit
    disabled): the wrapper still has the same behavior, but nothing is stored.
    """

    async def record(
        self,
        *,
        secret_name: str,
        ok: bool,
        hit: HitKind,
        actor: str = "yaml-agno",
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        return None


class RepositorySecretAuditRecorder:
    """Persists audit events into ``yamlagno.secret_audit``.

    Args:
        repo: Generic repository over :class:`SecretAuditRecord`.
        actor: Default actor name when ``record(actor=...)`` is not provided.
    """

    def __init__(self, repo: GenericRepository[SecretAuditRecord], *, actor: str = "yaml-agno") -> None:
        self._repo = repo
        self._default_actor = actor

    async def record(
        self,
        *,
        secret_name: str,
        ok: bool,
        hit: HitKind,
        actor: str = "yaml-agno",
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        # The audit column is PgUUID; tolerate a plain-string tenant id by
        # trying to parse it, falling back to None when it is not a UUID.
        tenant_uuid: uuid.UUID | None = None
        if tenant_id is not None:
            try:
                tenant_uuid = uuid.UUID(tenant_id)
            except ValueError:
                tenant_uuid = None

        await self._repo.insert(
            SecretAuditRecord(
                secret_name=secret_name,
                actor=actor or self._default_actor,
                hit=hit,
                ok=ok,
                tenant_id=tenant_uuid,
                trace_id=trace_id,
            )
        )
