"""SkillsFactory — maps ``SkillsConfig`` to a native ``agno.skills.Skills``
instance (SPEC_30 slice A).

The factory is the SINGLE wiring point between the opaque
``AgentConfig.skills`` dict (Option B) and ``agno.Agent(skills=...)``. It
accepts either a raw dict (opaque ``AgentConfig.skills``), a pre-parsed
``SkillsConfig``, or ``None``, validates raw dicts via
``TypeAdapter(SkillsConfig)``, constructs ``LocalSkills(path, validate)``,
wraps it in ``Skills(loaders=[...])``, and returns the orchestrator Agent
accepts.

Thin adapter by design (A1): all skill logic — validation, loading, system
prompt injection, tool exposure — lives in Agno 2.6.22 (verified
obs-2137). yaml-agno does NOT reimplement any of it.

Synchronous by design: ``LocalSkills.__init__`` calls ``Path.resolve()`` but
does NOT load skills; ``Skills.__init__`` calls ``_load_skills()`` which
runs ``LocalSkills.load()`` synchronously (verified
``agent_skills.py:29-52``). No ``await`` is needed on the construction path.
"""

from __future__ import annotations

from typing import Any

from agno.skills import LocalSkills, Skills
from pydantic import TypeAdapter

from yaml_agno.skills.schema import SkillsConfig

__all__ = ["SkillsFactory"]


# Reusable validator: raw dict -> SkillsConfig instance. Built ONCE at
# import (TypeAdapter is the documented Pydantic V2 pattern for validating
# outside a model field). Option B: validation boundary lives here, NOT in
# AgentConfig.
_CONFIG_ADAPTER: TypeAdapter[SkillsConfig] = TypeAdapter(SkillsConfig)


class SkillsFactory:
    """Map ``SkillsConfig`` (or raw dict) to a native ``Skills`` instance.

    Stateless: every ``build()`` call is independent. No instance state is
    held — the class is used for namespace + convention alignment with
    ``ToolFactory`` (A3).

    Scope: schema validation + ``LocalSkills``/``Skills`` construction
    (slice A). AgentFactory wiring is DEFERRED to slice B (A4). Agno owns
    all skill execution logic (A1).
    """

    @classmethod
    def build(cls, config: SkillsConfig | dict[str, Any] | None) -> Skills | None:
        """Build a native ``Skills`` instance from config.

        Accepts EITHER a raw dict (opaque ``AgentConfig.skills``, Option B),
        a pre-parsed ``SkillsConfig``, or ``None``. Raw dicts are validated
        against ``SkillsConfig`` via ``TypeAdapter`` (the validation boundary
        moves from config-parse to factory-build; it does NOT disappear).

        Args:
            config: The raw ``AgentConfig.skills`` dict, a parsed
                ``SkillsConfig``, or ``None`` when no skills are configured.
                ``None`` short-circuits to ``None`` (no Agno object built).

        Returns:
            A native ``agno.skills.Skills`` instance wrapping one
            ``LocalSkills`` loader, or ``None`` if ``config`` is ``None``.

        Raises:
            ValidationError: If a raw dict fails ``SkillsConfig`` validation
                (re-raised from ``TypeAdapter.validate_python``).
            FileNotFoundError: If ``path`` does not exist (propagated from
                ``LocalSkills.load()`` via ``Skills.__init__`` when the
                path is absent).
            SkillValidationError: If ``validate=True`` and a skill fails
                Agno's ``validate_skill_directory`` (propagated from
                ``Skills.__init__``).
        """
        if config is None:
            return None

        cfg = (
            _CONFIG_ADAPTER.validate_python(config)
            if isinstance(config, dict)
            else config
        )

        local_skills = LocalSkills(path=cfg.path, validate=cfg.validate_skills)
        return Skills(loaders=[local_skills])
