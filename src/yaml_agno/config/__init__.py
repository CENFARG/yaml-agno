"""yaml-agno Config & Secrets module (SPEC_23).

Public surface of the SPEC_23 wiring layer: strict settings schemas, the
validated config facade, secret auditing/rotation, feature-flag persistence
and the hot-reload coordinator. Business logic imports the *functions and
classes* below; adapters stay inside core-cenf and are injected by
``bootstrap``.
"""

from yaml_agno.config.audit import (
    NoopSecretAuditRecorder,
    RepositorySecretAuditRecorder,
    SecretAuditRecorder,
)
from yaml_agno.config.bootstrap import (
    YamlAgnoConfigAdapter,
    build_config_manager,
    build_flag_manager,
    build_secret_manager,
)
from yaml_agno.config.flags_repository import FlagRepository
from yaml_agno.config.hotreload import HotReloadCoordinator
from yaml_agno.config.merge import _deep_merge, _merge_tenant
from yaml_agno.config.rotator import SecretRotator
from yaml_agno.config.schemas import (
    AppConfig,
    FlagDefaults,
    ObservabilityConfig,
    PersistenceConfig,
    RuntimeConfig,
    SecurityConfig,
    YamlAgnoSettings,
    normalize_env,
)
from yaml_agno.config.secrets import SecretAccessAuditor

__all__ = [
    "AppConfig",
    "FlagDefaults",
    "FlagRepository",
    "HotReloadCoordinator",
    "NoopSecretAuditRecorder",
    "ObservabilityConfig",
    "PersistenceConfig",
    "RepositorySecretAuditRecorder",
    "RuntimeConfig",
    "SecretAccessAuditor",
    "SecretAuditRecorder",
    "SecretRotator",
    "SecurityConfig",
    "YamlAgnoConfigAdapter",
    "YamlAgnoSettings",
    "_deep_merge",
    "_merge_tenant",
    "build_config_manager",
    "build_flag_manager",
    "build_secret_manager",
    "normalize_env",
]
