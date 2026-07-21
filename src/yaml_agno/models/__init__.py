"""yaml-agno domain model — Pydantic V2 schemas + DIReference value object.

Public API: import from ``yaml_agno.models`` directly.
    from yaml_agno.models import AgentConfig, TeamConfig, TeamMemberConfig
    from yaml_agno.models import WorkflowConfig, StepConfig, DIReference
"""

from yaml_agno.models.cache_key import CacheKeyBuilder
from yaml_agno.models.config.agent_config import AgentConfig
from yaml_agno.models.config.team_config import TeamConfig, TeamMemberConfig
from yaml_agno.models.config.workflow_config import StepConfig, WorkflowConfig
from yaml_agno.models.fallback_chain import build_fallback_chain
from yaml_agno.models.fallback_classifier import FallbackErrorClassifier
from yaml_agno.models.value_objects.di_reference import DIReference

__all__ = [
    "AgentConfig",
    "CacheKeyBuilder",
    "DIReference",
    "FallbackErrorClassifier",
    "StepConfig",
    "TeamConfig",
    "TeamMemberConfig",
    "WorkflowConfig",
    "build_fallback_chain",
]
