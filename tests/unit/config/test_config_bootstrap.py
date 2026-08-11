"""Unit tests for build_config_manager + YamlAgnoConfigAdapter (SPEC_23 §2.3).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Uses the real core
PydanticConfigAdapter against a temp YAML file (precedence owned by core) and
a temp-dir override for the hot-reload keep-old scenario.

Covers (TASK_232, TASK_233):
  - env var overrides file overrides defaults (core-owned precedence).
  - invalid boot value fails fast (YamlAgnoSettings validation, wrapper).
  - reload validates-before-swap: invalid new value keeps the old snapshot.
  - wrapper structurally satisfies the core ConfigManager Protocol.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from core_infrastructure.config.ports import ConfigManager
from pydantic import ValidationError

from yaml_agno.config.bootstrap import build_config_manager
from yaml_agno.config.schemas import YamlAgnoSettings


def minimal_yaml() -> dict:
    """Fresh copy per call — tests MUST NOT share mutable section dicts."""
    return {
        "app": {"name": "yaml-agno", "env": "dev"},
        "runtime": {"max_concurrent_agents": 10, "request_timeout_s": 30},
        "persistence": {
            "pool_size": 5,
            "pool_max_overflow": 2,
            "statement_timeout_ms": 5000,
        },
        "observability": {
            "otlp_endpoint": "http://otel-collector:4317",
            "sample_rate": 0.1,
        },
        "security": {"auth_mode": "jwt", "token_ttl_minutes": 15},
        "flags": {"enable_experimental_rag": False},
    }


def _write_yaml(path: pathlib.Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.mark.unit
def test_build_config_manager_returns_config_manager_protocol(
    tmp_path: pathlib.Path,
) -> None:
    """The wrapper MUST structurally satisfy the core ConfigManager Protocol."""
    cfg_file = tmp_path / "prod.yaml"
    _write_yaml(cfg_file, minimal_yaml())
    manager = build_config_manager("dev", config_path=cfg_file)
    assert isinstance(manager, ConfigManager)


@pytest.mark.unit
def test_build_config_manager_uses_core_precedence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK_232 — env var (5) > file (20) > default (30), core-owned precedence."""
    cfg_file = tmp_path / "dev.yaml"
    yaml_data = {**minimal_yaml()}
    yaml_data["runtime"]["request_timeout_s"] = 20
    _write_yaml(cfg_file, yaml_data)
    monkeypatch.setenv("YA_RUNTIME__REQUEST_TIMEOUT_S", "5")
    manager = build_config_manager("dev", config_path=cfg_file)
    assert manager.get_number("runtime.request_timeout_s") == 5


@pytest.mark.unit
def test_build_config_manager_reads_file_value_when_no_env(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an env override, the file value MUST win over the default."""
    cfg_file = tmp_path / "dev.yaml"
    yaml_data = {**minimal_yaml()}
    yaml_data["runtime"]["request_timeout_s"] = 20
    _write_yaml(cfg_file, yaml_data)
    monkeypatch.delenv("YA_RUNTIME__REQUEST_TIMEOUT_S", raising=False)
    manager = build_config_manager("dev", config_path=cfg_file)
    assert manager.get_number("runtime.request_timeout_s") == 20


@pytest.mark.unit
def test_build_config_manager_exposes_sections_and_settings(
    tmp_path: pathlib.Path,
) -> None:
    """get_section and the validated settings object MUST be accessible."""
    cfg_file = tmp_path / "dev.yaml"
    _write_yaml(cfg_file, minimal_yaml())
    manager = build_config_manager("dev", config_path=cfg_file)
    section = manager.get_section("persistence")
    assert section["pool_size"] == 5
    assert isinstance(manager.settings, YamlAgnoSettings)
    assert manager.settings.app.name == "yaml-agno"


@pytest.mark.unit
def test_build_config_manager_fails_fast_on_invalid_boot_value(
    tmp_path: pathlib.Path,
) -> None:
    """SPEC_23 §3 — max_concurrent_agents=0 MUST fail at boot (fail-fast)."""
    cfg_file = tmp_path / "dev.yaml"
    yaml_data = {**minimal_yaml()}
    yaml_data["runtime"]["max_concurrent_agents"] = 0
    _write_yaml(cfg_file, yaml_data)
    with pytest.raises(ValidationError):
        build_config_manager("dev", config_path=cfg_file)


@pytest.mark.unit
async def test_invalid_hotreload_value_keeps_old_snapshot(
    tmp_path: pathlib.Path,
) -> None:
    """TASK_233 — reload with pool_size=9999 (>100) MUST raise and keep old value."""
    cfg_file = tmp_path / "dev.yaml"
    _write_yaml(cfg_file, minimal_yaml())
    manager = build_config_manager("dev", config_path=cfg_file)
    assert manager.get_number("persistence.pool_size") == 5

    yaml_data = {**minimal_yaml()}
    yaml_data["persistence"]["pool_size"] = 9999
    _write_yaml(cfg_file, yaml_data)

    with pytest.raises(ValidationError):
        await manager.reload()

    # Keep-old: the snapshot MUST still expose pool_size=5.
    assert manager.get_number("persistence.pool_size") == 5
    assert manager.get_section("persistence")["pool_size"] == 5


@pytest.mark.unit
async def test_valid_hotreload_swaps_snapshot(tmp_path: pathlib.Path) -> None:
    """A valid new value MUST be picked up by reload() without restart."""
    cfg_file = tmp_path / "dev.yaml"
    _write_yaml(cfg_file, minimal_yaml())
    manager = build_config_manager("dev", config_path=cfg_file)

    yaml_data = {**minimal_yaml()}
    yaml_data["persistence"]["pool_size"] = 12
    _write_yaml(cfg_file, yaml_data)

    await manager.reload()
    assert manager.get_number("persistence.pool_size") == 12


@pytest.mark.unit
def test_get_env_returns_normalized_environment(tmp_path: pathlib.Path) -> None:
    """get_env() MUST expose the validated app.env (dev|staging|prod)."""
    cfg_file = tmp_path / "prod.yaml"
    yaml_data = {**minimal_yaml()}
    yaml_data["app"]["env"] = "prod"
    _write_yaml(cfg_file, yaml_data)
    manager = build_config_manager("prod", config_path=cfg_file)
    assert manager.get_env() == "prod"
