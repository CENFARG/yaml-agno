"""Secret rotation policy helper (SPEC_23 §2.5, TASK_237).

Rotation in yaml-agno is a *policy* helper: it decides WHEN a secret is due
(``is_expiring``) and delegates the actual rotation to the core
``SecretManager`` (the core adapter owns storage-specific rotation). The
rotation is audited so the compliance trail is complete.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core_infrastructure.secrets.ports import SecretManager

from yaml_agno.config.audit import SecretAuditRecorder

__all__ = ["SecretRotator"]

_UTC = UTC


def _as_aware(value: datetime) -> datetime:
    """Ensure UTC-aware datetime (naive DB timestamps are assumed UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_UTC)
    return value.astimezone(_UTC)


class SecretRotator:
    """Decides rotation due-dates and performs audited rotations.

    Args:
        secrets: The core :class:`SecretManager` that performs the rotation.
        auditor: Optional :class:`SecretAuditRecorder` for the audit trail.

    Note:
        The ``Secrets`` dependency is a *core protocol* — the wiring layer
        (``bootstrap.build_secret_manager``) injects the concrete adapter.
    """

    def __init__(self, secrets: SecretManager, *, auditor: SecretAuditRecorder | None = None) -> None:
        self._secrets = secrets
        self._auditor = auditor

    def is_expiring(
        self,
        rotated_at: datetime,
        *,
        ttl_days: int,
        alert_days: int,
        now: datetime | None = None,
    ) -> bool:
        """True when the secret must be rotated within ``alert_days``.

        The secret is considered *due* when the rotation window falls at or
        before ``now``: ``rotated_at + (ttl_days - alert_days) <= now``.

        Args:
            rotated_at: The timestamp of the last rotation.
            ttl_days: Total secret lifetime in days.
            alert_days: How many days in advance the alert must fire.
            now: Reference "now" (UTC-aware). Defaults to the current UTC time.

        Returns:
            True when the secret is due for rotation.
        """
        now_aware = _as_aware(now or datetime.now(_UTC))
        return _as_aware(rotated_at) + timedelta(days=ttl_days - alert_days) <= now_aware

    async def rotate(self, key: str, new_value: str) -> None:
        """Rotate a secret via the core manager and audit the rotation."""
        await self._secrets.rotate_secret(key, new_value)
        if self._auditor is not None:
            await self._auditor.record(secret_name=key, ok=True, hit="remote")

    def compliance_flags(
        self,
        secrets: dict[str, datetime],
        *,
        ttl_days: int,
        alert_days: int,
        now: datetime | None = None,
    ) -> list[str]:
        """Names of secrets that are due for rotation.

        Args:
            secrets: Mapping of secret name -> last rotation timestamp.
            ttl_days: Total secret lifetime in days.
            alert_days: Alert lead time in days.
            now: Reference "now" (UTC-aware). Defaults to the current UTC time.

        Returns:
            Sorted list of secret names that are due.
        """
        return sorted(
            name
            for name, rotated_at in secrets.items()
            if self.is_expiring(rotated_at, ttl_days=ttl_days, alert_days=alert_days, now=now)
        )
