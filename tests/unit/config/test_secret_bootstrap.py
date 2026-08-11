"""Unit tests for build_secret_manager + AuditedSecretManager (SPEC_23 §2.4-2.5).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses the real core
InMemorySecretAdapter and a fake audit recorder — no files, no network.

Covers (TASK_234, TASK_235, TASK_236):
  - dev uses InMemorySecretAdapter, prod uses EncryptedSecretAdapter.
  - get_secret() delegates to the core adapter (no local cache re-implemented).
  - missing secret raises the core ValidationError and audits ok=False.
  - successful access audits ok=True.
"""

from __future__ import annotations

import pytest
from core_infrastructure.common.errors import ValidationError as CoreValidationError
from core_infrastructure.config.adapters.in_memory_config_adapter import (
    InMemoryConfigAdapter,
)
from core_infrastructure.secrets.adapters.encrypted_secret_adapter import (
    EncryptedSecretAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)

from yaml_agno.config.audit import SecretAuditRecorder
from yaml_agno.config.bootstrap import build_secret_manager
from yaml_agno.config.secrets import SecretAccessAuditor


class FakeAuditRecorder(SecretAuditRecorder):
    """In-memory audit double capturing (ok, hit, secret_name) records."""

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


def _build_dev_manager() -> tuple[SecretAccessAuditor, FakeAuditRecorder]:
    cfg = InMemoryConfigAdapter()
    recorder = FakeAuditRecorder()
    return build_secret_manager("dev", cfg, auditor=recorder), recorder


@pytest.mark.unit
def test_dev_uses_in_memory_adapter() -> None:
    """TASK_236 — non-prod MUST select the core InMemorySecretAdapter."""
    cfg = InMemoryConfigAdapter()
    manager = build_secret_manager("dev", cfg)
    assert isinstance(manager, InMemorySecretAdapter)


@pytest.mark.unit
def test_staging_uses_in_memory_adapter() -> None:
    """staging also uses the in-memory adapter (prod-only encryption)."""
    cfg = InMemoryConfigAdapter()
    manager = build_secret_manager("staging", cfg)
    assert isinstance(manager, InMemorySecretAdapter)


@pytest.mark.unit
def test_prod_uses_encrypted_adapter(tmp_path: pytest.TempPathFactory) -> None:
    """TASK_236 — prod MUST select the core EncryptedSecretAdapter."""
    cfg = InMemoryConfigAdapter()
    storage = tmp_path / "secrets.json"
    cfg.set_value("secrets.storage_path", str(storage))
    manager = build_secret_manager("prod", cfg)
    assert isinstance(manager, EncryptedSecretAdapter)


@pytest.mark.unit
async def test_audited_get_secret_delegates_to_core() -> None:
    """TASK_234 — get_secret MUST delegate to the core adapter and audit ok=True."""
    manager, recorder = _build_dev_manager()
    assert isinstance(manager, SecretAccessAuditor)
    core: InMemorySecretAdapter = manager._core
    core.set_secret("db_password", "s3cr3t")

    value = await manager.get_secret("db_password")
    assert value == "s3cr3t"
    assert recorder.records == [
        {
            "secret_name": "db_password",
            "ok": True,
            "hit": "remote",
            "actor": "yaml-agno",
            "tenant_id": None,
            "trace_id": None,
        }
    ]


@pytest.mark.unit
async def test_missing_secret_raises_and_audits_failure() -> None:
    """TASK_235 — missing key MUST raise the core ValidationError + audit ok=False."""
    manager, recorder = _build_dev_manager()

    with pytest.raises(CoreValidationError):
        await manager.get_secret("missing")

    assert len(recorder.records) == 1
    assert recorder.records[0]["secret_name"] == "missing"
    assert recorder.records[0]["ok"] is False
    assert recorder.records[0]["hit"] == "miss"


@pytest.mark.unit
async def test_audited_rotate_delegates_to_core() -> None:
    """rotate_secret MUST delegate to the core (stores + evicts cache)."""
    manager, recorder = _build_dev_manager()
    core: InMemorySecretAdapter = manager._core
    core.set_secret("k", "old")

    await manager.rotate_secret("k", "new")

    value = await manager.get_secret("k")
    assert value == "new"
    assert any(r["ok"] is True for r in recorder.records)


@pytest.mark.unit
def test_invalidate_cache_delegates_to_core() -> None:
    """invalidate_cache MUST be forwarded to the core adapter."""
    manager, _ = _build_dev_manager()
    core: InMemorySecretAdapter = manager._core
    core.set_secret("k", "v")
    manager.invalidate_cache("k")
    assert core._cache.get("k") is None


@pytest.mark.unit
def test_get_json_schema_delegates_to_core() -> None:
    """get_json_schema MUST come from the core adapter."""
    manager, _ = _build_dev_manager()
    schema = manager.get_json_schema()
    assert "properties" in schema
