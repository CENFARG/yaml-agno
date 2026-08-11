"""Config & Secrets wiring (SPEC_23 §2.3-2.6, TASK_232-TASK_239).

yaml-agno NEVER re-implements precedence, storage or evaluation: the core-cenf
managers (ConfigManager / SecretManager / FeatureFlagManager) own those. This
module *wires* them:

- ``YamlAgnoConfigAdapter`` — validated facade over the core ConfigManager.
  The core materializes Env > Files > Defaults; this wrapper re-validates the
  result against :class:`YamlAgnoSettings` (fail-fast on boot, keep-old on
  invalid reload) and exposes a typed ``.settings`` snapshot.
- ``build_config_manager`` — core ``PydanticConfigAdapter(env_prefix="YA_")``
  wrapped in the validated facade.
- ``build_secret_manager`` — prod: core ``EncryptedSecretAdapter`` (requires
  ``secrets.storage_path``); dev/staging: ``InMemorySecretAdapter``. Optional
  audit wrapper via ``SecretAccessAuditor``.
- ``build_flag_manager`` — core ``MemoryFeatureFlagAdapter`` seeded with flag
  definitions.

Imports from core are at the *module* level (adapter classes), never the
business-logic golden-rule violation: this module IS the composition root
(the one place adapters are constructed and injected).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.adapters.pydantic_config_adapter import (
    PydanticConfigAdapter,
)
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FeatureFlag
from core_infrastructure.feature_flags.ports import FeatureFlagManager
from core_infrastructure.secrets.adapters.encrypted_secret_adapter import (
    EncryptedSecretAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)
from core_infrastructure.secrets.models import SecretConfig
from core_infrastructure.secrets.ports import SecretManager

from yaml_agno.config.audit import SecretAuditRecorder
from yaml_agno.config.schemas import YamlAgnoSettings, normalize_env
from yaml_agno.config.secrets import SecretAccessAuditor

__all__ = [
    "YamlAgnoConfigAdapter",
    "build_config_manager",
    "build_flag_manager",
    "build_secret_manager",
]

#: The yaml-agno config sections that must be present in the config file.
#: These are the *validated* keys of :class:`YamlAgnoSettings` (SPEC_23 §2.2).
SECTIONS: tuple[str, ...] = (
    "app",
    "runtime",
    "persistence",
    "observability",
    "security",
    "flags",
)


def _resolve_dotted(data: dict[str, Any], key: str) -> Any:
    """Resolve a dot-notation key against a nested dict (``None`` if absent)."""
    current: Any = data
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class YamlAgnoConfigAdapter:
    """Validated facade over the core-cenf ConfigManager (SPEC_23 §2.3).

    The core owns precedence (Env > Files > Defaults) and re-materialization
    on ``reload()``. This wrapper:

    - validates the materialized result against :class:`YamlAgnoSettings` on
      boot (fail-fast: an invalid value aborts construction),
    - keeps a validated snapshot so ``get_*`` reads NEVER observe an invalid
      value (keep-old on failed reload),
    - re-validates on ``reload()``: invalid new values raise and the previous
      snapshot is kept.

    Args:
        core: The core ConfigManager (protocol) being wrapped. Injected by
            ``build_config_manager``; never imported by business logic.
        settings_type: The strict settings model to validate against
            (defaults to :class:`YamlAgnoSettings`).

    Raises:
        ValidationError (pydantic): If the materialized config does not satisfy
            the strict settings model (fail-fast).
    """

    def __init__(
        self,
        core: ConfigManager,
        *,
        settings_type: type[YamlAgnoSettings] = YamlAgnoSettings,
    ) -> None:
        self._core = core
        self._settings_type = settings_type
        self._snapshot: dict[str, Any] = {}
        self._settings: YamlAgnoSettings = self._materialize()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _materialize(self) -> YamlAgnoSettings:
        """Read the core's materialized sections and validate them strictly.

        Returns:
            The validated :class:`YamlAgnoSettings`.

        Raises:
            PydanticValidationError: If any section violates the strict schema.
        """
        snapshot = {section: self._core.get_section(section) for section in SECTIONS}
        settings = self._settings_type.model_validate(snapshot)
        # Only swap the readable snapshot AFTER validation succeeds.
        self._snapshot = snapshot
        return settings

    # ------------------------------------------------------------------
    # Public API — core ConfigManager Protocol
    # ------------------------------------------------------------------

    @property
    def settings(self) -> YamlAgnoSettings:
        """The current validated settings snapshot (typed access)."""
        return self._settings

    def get_env(self) -> str:
        """Return the normalized yaml-agno environment (dev|staging|prod).

        Reads ``app.env`` from the validated snapshot — the yaml-agno SSOT —
        not the core's ``env`` field (which mirrors CoreSettings defaults).
        """
        return self._settings.app.env

    def get_string(self, key: str, default_value: str | None = None) -> str:
        value = _resolve_dotted(self._snapshot, key)
        if value is not None:
            return str(value)
        if default_value is not None:
            return default_value
        raise ValidationError(f"Missing required config key: {key}", details={"key": key})

    def get_number(self, key: str, default_value: float | None = None) -> float:
        value = _resolve_dotted(self._snapshot, key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Config key '{key}' is not a number: {value!r}",
                    details={"key": key, "value": str(value)},
                ) from None
        if default_value is not None:
            return default_value
        raise ValidationError(f"Missing required config key: {key}", details={"key": key})

    def get_boolean(self, key: str, default_value: bool | None = None) -> bool:
        value = _resolve_dotted(self._snapshot, key)
        if value is not None:
            if isinstance(value, bool):
                return value
            raise ValidationError(
                f"Config key '{key}' is not a boolean: {value!r}",
                details={"key": key, "value": str(value)},
            )
        if default_value is not None:
            return default_value
        raise ValidationError(f"Missing required config key: {key}", details={"key": key})

    def get_json(self, key: str, default_value: Any = None) -> Any:
        value = _resolve_dotted(self._snapshot, key)
        if value is not None:
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValidationError(
                        f"Config key '{key}' is not valid JSON: {exc}",
                        details={"key": key, "value": value},
                    ) from exc
            return value
        if default_value is not None:
            return default_value
        raise ValidationError(f"Missing required config key: {key}", details={"key": key})

    def get_section(self, namespace: str) -> dict[str, Any]:
        value = _resolve_dotted(self._snapshot, namespace)
        if isinstance(value, dict):
            return value
        return {}

    async def reload(self) -> None:
        """Re-materialize from the core and re-validate (keep-old on failure).

        The core re-reads YAML + env; this wrapper then re-validates against
        the strict schema. If the new materialization is invalid, the previous
        validated snapshot is KEPT and the pydantic error propagates.

        Raises:
            PydanticValidationError: If the new config violates the schema
                (the previous snapshot remains readable).
        """
        await self._core.reload()
        new_settings = self._materialize()  # raises -> snapshot not swapped
        self._settings = new_settings

    def get_json_schema(self) -> dict[str, Any]:
        """Return the strict settings JSON Schema (LLM discovery)."""
        return self._settings_type.model_json_schema()


def build_config_manager(
    env: str,
    *,
    config_path: str | Path | None = None,
) -> YamlAgnoConfigAdapter:
    """Build the validated config manager.

    Args:
        env: Raw environment identifier (normalized via
            :func:`normalize_env`; fail-fast on unknown values).
        config_path: Optional YAML config file path. When None, only env vars
            and defaults are used.

    Returns:
        A :class:`YamlAgnoConfigAdapter` over the core PydanticConfigAdapter
        (env prefix ``YA_``, nested separator ``__``).

    Raises:
        ValueError: If ``env`` is not dev/staging/prod (after local->dev).
        ValidationError: If the materialized config violates
            :class:`YamlAgnoSettings`.
    """
    normalize_env(env)
    path: str | None = str(config_path) if config_path is not None else None
    core = PydanticConfigAdapter(env_prefix="YA_", config_path=path)
    return YamlAgnoConfigAdapter(core)


def build_secret_manager(
    env: str,
    config: ConfigManager,
    *,
    auditor: SecretAuditRecorder | None = None,
) -> SecretManager:
    """Build the SecretManager for the given environment.

    - ``prod``: core :class:`EncryptedSecretAdapter` (Fernet, file-backed).
      Requires ``secrets.storage_path`` in config, otherwise a
      ``ValidationError`` is raised (fail-fast: never fall back silently).
    - ``dev``/``staging``: core :class:`InMemorySecretAdapter` (no I/O).
    - When ``auditor`` is provided, the chosen adapter is wrapped in a
      :class:`SecretAccessAuditor`.

    Args:
        env: Environment selector (normalized; ``local`` maps to ``dev``).
        config: ConfigManager used to read ``secrets.storage_path`` (prod).
        auditor: Optional audit recorder wired into the wrapper.

    Returns:
        A core SecretManager (adapter or audited wrapper).

    Raises:
        ValueError: If ``env`` is unknown.
        ValidationError: If prod is selected but ``secrets.storage_path`` is
            missing.
    """
    normalized = normalize_env(env)
    if normalized == "prod":
        storage_path = config.get_string("secrets.storage_path", default_value=None)
        if storage_path is None:
            raise ValidationError(
                "secrets.storage_path is required in prod (EncryptedSecretAdapter)",
                details={"env": "prod", "key": "secrets.storage_path"},
            )
        adapter: SecretManager = EncryptedSecretAdapter(
            config=SecretConfig(),
            secret_storage_path=storage_path,
        )
    else:
        adapter = InMemorySecretAdapter()

    if auditor is not None:
        return SecretAccessAuditor(adapter, auditor=auditor)
    return adapter


def build_flag_manager(env: str, flags: list[FeatureFlag] | None = None) -> FeatureFlagManager:
    """Build the core FeatureFlagManager seeded with flag definitions.

    Args:
        env: Environment selector (validated; unused by the memory adapter).
        flags: Initial flag definitions registered via ``set_flag``.

    Returns:
        A core :class:`MemoryFeatureFlagAdapter` (unknown flags fail safe to
        False; rule evaluation owned by the core adapter).
    """
    normalize_env(env)
    adapter = MemoryFeatureFlagAdapter()
    for flag in flags or []:
        adapter.set_flag(flag)
    return cast(FeatureFlagManager, adapter)
