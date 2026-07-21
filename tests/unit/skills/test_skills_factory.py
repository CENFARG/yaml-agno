"""Unit tests for ``yaml_agno.skills`` — SPEC_30 slice A (skills-foundation).

Covers two surfaces:
    - ``SkillsConfig`` Pydantic V2 schema (validation, extra-forbid, defaults).
    - ``SkillsFactory.build`` thin adapter to ``agno.skills.Skills`` / ``LocalSkills``.

The factory tests use ``tmp_path`` to create real ``SKILL.md`` fixtures (no
Agno mocks) so the thin-adapter contract — de-opacify dict, construct
``LocalSkills``, wrap in ``Skills``, propagate ``SkillValidationError`` — is
exercised end-to-end against the installed Agno 2.6.22.
"""

from __future__ import annotations

import pytest
from agno.skills import Skills, SkillValidationError
from pydantic import ValidationError

from yaml_agno.skills import SkillsConfig, SkillsFactory


def _write_valid_skill(skill_dir, name="my-skill"):
    """Write a structurally valid ``SKILL.md`` (lowercase, hyphenated name).

    Args:
        skill_dir: The directory that will hold ``SKILL.md`` (created if
            missing).
        name: The skill name written into frontmatter. MUST be lowercase +
            hyphenated to satisfy Agno's ``validate_skill_directory`` when
            ``validate=True``. An UPPERCASE name (e.g. ``BadName``) is used
            deliberately to exercise the ``SkillValidationError`` path.
    """
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: A test skill.\n"
        "---\n"
        "# My Skill\n"
        "Instructions here.\n",
        encoding="utf-8",
    )


# --- SkillsFactory.build contract (R2, R3, R4, R5, R6, R7) -------------------


@pytest.mark.unit
def test_build_none_returns_none() -> None:
    """R7: ``build(None)`` returns ``None`` (None on empty config)."""
    assert SkillsFactory.build(None) is None


@pytest.mark.unit
def test_build_missing_path_rejected(tmp_path) -> None:
    """R2: a raw dict missing ``path`` is rejected by the TypeAdapter."""
    with pytest.raises(ValidationError):
        SkillsFactory.build({"validate": True})


@pytest.mark.unit
def test_build_extra_keys_rejected(tmp_path) -> None:
    """R1/R2: ``extra="forbid"`` rejects unknown keys in the raw dict."""
    with pytest.raises(ValidationError):
        SkillsFactory.build({"path": str(tmp_path), "bogus": 1})


@pytest.mark.unit
def test_build_dict_returns_skills_with_localskills(tmp_path) -> None:
    """R2/R3/R4: a valid dict yields a ``Skills`` wrapping one ``LocalSkills``.

    Golden path: a temp dir with a valid ``SKILL.md`` builds a native
    ``Skills`` whose single loader has ``validate`` forwarded from config.
    """
    _write_valid_skill(tmp_path / "my-skill")
    result = SkillsFactory.build({"path": str(tmp_path), "validate": True})
    assert isinstance(result, Skills)
    assert len(result.loaders) == 1
    assert result.loaders[0].validate is True


@pytest.mark.unit
def test_build_invalid_skill_raises_when_validate_true(tmp_path) -> None:
    """R5: ``validate=True`` propagates ``SkillValidationError`` from Agno.

    An UPPERCASE skill name violates Agno's ``validate_skill_directory``; the
    factory MUST NOT swallow or mask the error.
    """
    _write_valid_skill(tmp_path / "BadName", name="BadName")
    with pytest.raises(SkillValidationError):
        SkillsFactory.build({"path": str(tmp_path), "validate": True})


@pytest.mark.unit
def test_build_invalid_skill_skipped_when_validate_false(tmp_path) -> None:
    """R6: ``validate=False`` skips structural validation (Agno logs + skips).

    The same invalid bundle that raises under ``validate=True`` completes
    without error and returns a ``Skills`` instance.
    """
    _write_valid_skill(tmp_path / "BadName", name="BadName")
    result = SkillsFactory.build({"path": str(tmp_path), "validate": False})
    assert isinstance(result, Skills)


# --- SkillsConfig schema (R1) — pure validation, no Agno ---------------------


@pytest.mark.unit
def test_skillsconfig_valid_entry() -> None:
    """R1: ``path`` + ``validate=True`` accepted as a valid entry."""
    cfg = SkillsConfig.model_validate({"path": "./skills/brand-audit", "validate": True})
    assert cfg.path == "./skills/brand-audit"
    assert cfg.validate_skills is True


@pytest.mark.unit
def test_skillsconfig_rejects_unknown_keys() -> None:
    """R1: ``extra="forbid"`` raises ``ValidationError`` on unknown keys."""
    with pytest.raises(ValidationError):
        SkillsConfig(path=".", body="inline no permitido")


@pytest.mark.unit
def test_skillsconfig_validate_defaults_true() -> None:
    """R1: ``validate`` defaults to ``True`` (Agno default) when omitted.

    Constructed via ``model_validate`` with only ``path`` so the default
    applies through the alias path the factory uses.
    """
    cfg = SkillsConfig.model_validate({"path": "."})
    assert cfg.validate_skills is True


@pytest.mark.unit
def test_skillsconfig_path_min_length_1() -> None:
    """R1: an empty ``path`` is rejected (``min_length=1``)."""
    with pytest.raises(ValidationError):
        SkillsConfig(path="")
