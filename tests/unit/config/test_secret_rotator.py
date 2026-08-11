"""Unit tests for SecretRotator TTL compliance (SPEC_23 §2.9, TASK_238).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses the real core
InMemorySecretAdapter — no files, no network.

Covers:
  - a secret 88/90 days old with alert_days=7 is flagged as expiring.
  - a freshly rotated secret is not flagged.
  - rotate() delegates to the core rotate_secret and audits the event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)

from yaml_agno.config.audit import SecretAuditRecorder
from yaml_agno.config.rotator import SecretRotator


class FakeAuditRecorder(SecretAuditRecorder):
    """In-memory audit double capturing rotation events."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(
        self,
        *,
        secret_name: str,
        ok: bool,
        hit: str,
        actor: str = "test",
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.records.append(
            {
                "secret_name": secret_name,
                "ok": ok,
                "hit": hit,
                "actor": actor,
                "tenant_id": tenant_id,
                "trace_id": trace_id,
            }
        )


NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


@pytest.mark.unit
def test_flags_secret_near_expiry() -> None:
    """TASK_238 — 88/90 days with alert 7 MUST be flagged (expiring in 2 days)."""
    rotator = SecretRotator(InMemorySecretAdapter())
    rotated_at = NOW - timedelta(days=88)
    assert rotator.is_expiring(rotated_at, ttl_days=90, alert_days=7, now=NOW) is True


@pytest.mark.unit
def test_does_not_flag_fresh_secret() -> None:
    """A secret rotated 10 days ago (ttl 90, alert 7) MUST NOT be flagged."""
    rotator = SecretRotator(InMemorySecretAdapter())
    rotated_at = NOW - timedelta(days=10)
    assert rotator.is_expiring(rotated_at, ttl_days=90, alert_days=7, now=NOW) is False


@pytest.mark.unit
def test_flags_on_exact_alert_threshold() -> None:
    """rotated_at + ttl - alert_days == now MUST be flagged (<=)."""
    rotator = SecretRotator(InMemorySecretAdapter())
    # Boundary: rotated_at + 90 - 7 = now  =>  rotated_at = now - 83 days.
    rotated_at = NOW - timedelta(days=83)
    assert rotator.is_expiring(rotated_at, ttl_days=90, alert_days=7, now=NOW) is True


@pytest.mark.unit
async def test_rotate_delegates_to_core_and_audits() -> None:
    """TASK_238 — rotate() calls core rotate_secret and records the audit event."""
    core = InMemorySecretAdapter()
    core.set_secret("model/openai_key", "old-value")
    recorder = FakeAuditRecorder()
    rotator = SecretRotator(core, auditor=recorder)

    await rotator.rotate("model/openai_key", "new-value")

    value = await core.get_secret("model/openai_key")
    assert value == "new-value"
    assert len(recorder.records) == 1
    assert recorder.records[0]["secret_name"] == "model/openai_key"
    assert recorder.records[0]["ok"] is True


@pytest.mark.unit
def test_rotation_compliance_flags_multiple_secrets() -> None:
    """compliance_flags() reports every secret whose TTL is within the alert window."""
    core = InMemorySecretAdapter()
    rotator = SecretRotator(core)
    near = {
        "model/openai_key": NOW - timedelta(days=88),
        "db_password": NOW - timedelta(days=10),
    }
    flagged = rotator.compliance_flags(near, ttl_days=90, alert_days=7, now=NOW)
    assert flagged == ["model/openai_key"]
