"""Skills config schema (SPEC_30 slice A) — Pydantic V2 BaseModel for the
opaque ``AgentConfig.skills`` slot.

De-opacifies ``AgentConfig.skills`` from a raw dict to a validated config
carried into ``SkillsFactory.build``. Mirrors how ``tools/schema.py``
de-opacifies ``AgentConfig.tools``.

NOTE: this schema ships standalone. ``AgentConfig.skills`` stays the opaque
``dict[str, Any] | None``; the validation boundary lives in
``SkillsFactory.build`` (Option B), consistent with ``ToolFactory``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SkillsConfig"]


class SkillsConfig(BaseModel):
    """Local-skills source declaration for one agent.

    Maps to ``agno.skills.LocalSkills(path, validate)``. yaml-agno owns NO
    skill logic — validation, loading, and prompt injection all live in Agno
    2.6.22 (verified obs-2137: ``loaders/local.py:25``, ``validator.py``).

    The YAML/dict key is ``validate`` (matches Agno's ``LocalSkills`` kwarg),
    but the Python attribute is ``validate_skills`` to avoid shadowing
    ``pydantic.BaseModel.validate`` (a classmethod). ``populate_by_name=True``
    lets the factory read ``cfg.validate_skills`` while raw dicts still use
    the ``validate`` alias.

    Attributes:
        path: Filesystem path to a skill folder (contains ``SKILL.md``) or
            a directory of skill folders. Resolved via
            ``Path(path).resolve()`` inside ``LocalSkills``; a missing path
            raises ``FileNotFoundError`` at load time.
        validate_skills: If ``True`` (default), invalid skills raise
            ``SkillValidationError`` at load time. If ``False``, Agno logs
            and skips invalid skills. Forwarded directly to
            ``LocalSkills(validate=...)``. Serialized as ``validate``.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str = Field(
        ...,
        min_length=1,
        description="Path to a skill folder or a directory of skill folders.",
    )
    validate_skills: bool = Field(
        default=True,
        alias="validate",
        description="If True, invalid skills raise SkillValidationError (Agno default). "
        "Serialized as 'validate' to match the Agno LocalSkills kwarg.",
    )
