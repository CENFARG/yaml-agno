"""yaml-agno skills layer — SPEC_30 (slice A).

Public API:
    from yaml_agno.skills import SkillsConfig, SkillsFactory
"""

from yaml_agno.skills.factory import SkillsFactory
from yaml_agno.skills.schema import SkillsConfig

__all__ = ["SkillsConfig", "SkillsFactory"]
