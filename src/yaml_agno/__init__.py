"""yaml-agno: declarative YAML-driven agent orchestration on top of Agno."""

from importlib.metadata import PackageNotFoundError, version

# ---------------------------------------------------------------------------
# SPEC_12 Control Plane — Slice 1 public surface
# ---------------------------------------------------------------------------
from yaml_agno.api.fastapi_app_builder import (
    EndpointGroup,
    FastAPIAppBuilder,
)
from yaml_agno.factories.agentos_factory import AgentOSFactory
from yaml_agno.models.config.agentos_config import (
    AgentOSConfig,
    AuthorizationSettings,
    MCPServerSettings,
    ResyncSettings,
    SchedulerSettings,
)
from yaml_agno.ports.agentos_ports import AgentOSFactoryPort

try:
    __version__ = version("yaml-agno")
except PackageNotFoundError:  # pragma: no cover - editable install fallback
    __version__ = "0.0.0"

__all__ = [
    "AgentOSConfig",
    "AgentOSFactory",
    "AgentOSFactoryPort",
    "AuthorizationSettings",
    "EndpointGroup",
    "FastAPIAppBuilder",
    "MCPServerSettings",
    "ResyncSettings",
    "SchedulerSettings",
    "__version__",
]
