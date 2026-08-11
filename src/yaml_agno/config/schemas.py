"""Pydantic V2 strict settings schema for yaml-agno (SPEC_23 §2.2).

yaml-agno owns this model; the core-cenf ``PydanticConfigAdapter`` owns
precedence (Env > Files > Defaults). The adapter validates the *resulting*
materialized config against ``YamlAgnoSettings`` so that fail-fast semantics
(max_concurrent_agents bounds, ``extra=forbid``, basic-auth-in-prod) are
enforced on yaml-agno's own contract without re-implementing precedence.

@ai-directive (Env SSOT): the yaml-agno environment enum is ``dev|staging|prod``.
There is no ``local`` and no ``test`` value: local development uses ``env=dev``
(``local==dev``) and tests select adapters via ``InMemorySecretAdapter``. The
core-cenf ``Env`` literal is wider (``local|dev|staging|prod``,
``core_infrastructure/config/ports.py``); the wiring layer normalizes a core
``"local"`` value to ``"dev"`` at the yaml-agno boundary (see
``normalize_env``). This is a deliberate project decision (Wave 5), not drift.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Doc

__all__ = [
    "AppConfig",
    "FlagDefaults",
    "ObservabilityConfig",
    "PersistenceConfig",
    "RuntimeConfig",
    "SecurityConfig",
    "YamlAgnoSettings",
    "normalize_env",
]

# yaml-agno SSOT env values (SPEC_23 §2.2). local==dev is normalized by
# normalize_env() before validation; there is deliberately no "local"/"test".
EnvName = Literal["dev", "staging", "prod"]

AppEnv = Annotated[str, Doc("Environment pattern: dev|staging|prod only.")]


def normalize_env(env: str) -> EnvName:
    """Normalize a raw environment string to the yaml-agno Env SSOT.

    Maps the core-cenf ``"local"`` value to ``"dev"`` (local==dev) and rejects
    any value outside ``dev|staging|prod``.

    Args:
        env: Raw environment identifier (e.g. ``"local"``, ``"dev"``,
            ``"staging"``, ``"prod"``).

    Returns:
        The normalized environment, one of ``"dev"``, ``"staging"``, ``"prod"``.

    Raises:
        ValueError: If ``env`` is not one of local/dev/staging/prod.
    """
    if env == "local":
        return "dev"
    if env in ("dev", "staging", "prod"):
        return env  # type: ignore[return-value]
    raise ValueError(f"Invalid environment: {env!r}. Expected dev|staging|prod.")


class AppConfig(BaseModel):
    """Application identity block (SPEC_23 §2.2)."""

    model_config = {"extra": "forbid"}

    name: Annotated[str, Field(min_length=1, max_length=64)] = Field(description="Application name.")
    env: AppEnv = Field(pattern="^(dev|staging|prod)$", description="Deployment environment.")


class RuntimeConfig(BaseModel):
    """Runtime tuning block (SPEC_23 §2.2)."""

    model_config = {"extra": "forbid"}

    max_concurrent_agents: Annotated[int, Field(ge=1, le=500)] = Field(description="Max concurrent agents.")
    request_timeout_s: Annotated[int, Field(ge=1, le=600)] = Field(description="Request timeout in seconds.")


class PersistenceConfig(BaseModel):
    """Persistence / pool block (SPEC_23 §2.2)."""

    model_config = {"extra": "forbid"}

    pool_size: Annotated[int, Field(ge=1, le=100)] = Field(description="Connection pool size.")
    pool_max_overflow: Annotated[int, Field(ge=0, le=100)] = Field(description="Pool overflow allowance.")
    statement_timeout_ms: Annotated[int, Field(ge=100, le=60000)] = Field(description="Statement timeout (ms).")


class ObservabilityConfig(BaseModel):
    """Observability block (SPEC_23 §2.2)."""

    model_config = {"extra": "forbid"}

    otlp_endpoint: HttpUrl = Field(description="OpenTelemetry collector endpoint.")
    sample_rate: Annotated[float, Field(ge=0.0, le=1.0)] = Field(description="Trace sampling rate (0..1).")


class SecurityConfig(BaseModel):
    """Security block (SPEC_23 §2.2)."""

    model_config = {"extra": "forbid"}

    auth_mode: str = Field(pattern="^(basic|jwt)$", description="Authentication mode.")
    token_ttl_minutes: Annotated[int, Field(ge=1, le=1440)] = Field(description="Token TTL in minutes.")


class FlagDefaults(BaseModel):
    """Feature-flag defaults block (SPEC_23 §2.2). Fail-safe: default False."""

    model_config = {"extra": "forbid"}

    enable_experimental_rag: bool = Field(default=False, description="Experimental RAG toggle.")


class YamlAgnoSettings(BaseSettings):
    """Root strict settings model for yaml-agno (SPEC_23 §2.2).

    ``extra=forbid`` gives fail-fast: a typo'd key aborts the boot instead of
    silently drifting. Env overrides use the ``YA_`` prefix with ``__`` as the
    nested delimiter (e.g. ``YA_RUNTIME__REQUEST_TIMEOUT_S``).

    Precedence (Env > Files > Defaults) is materialized by the core-cenf
    ``PydanticConfigAdapter``; this model validates the merged result.
    """

    model_config = SettingsConfigDict(
        env_prefix="YA_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="forbid",  # fail-fast: unknown key -> error
    )

    app: AppConfig
    runtime: RuntimeConfig
    persistence: PersistenceConfig
    observability: ObservabilityConfig
    security: SecurityConfig
    flags: FlagDefaults

    @field_validator("security")
    @classmethod
    def _jwt_required_in_prod(cls, v: SecurityConfig, info: ValidationInfo) -> SecurityConfig:
        env = info.data.get("app")
        if env and getattr(env, "env", None) == "prod" and v.auth_mode == "basic":
            raise ValueError("auth_mode=basic forbidden in prod")
        return v
