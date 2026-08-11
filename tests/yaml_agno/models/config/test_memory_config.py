"""RED tests for MemoryConfig schema (SPEC_04 leaf).

Covers the cases from design.md §Testing Strategy and tasks.md §1.2:
  - golden-canonical-parse (6 scalars, 4 nested None)
  - RED-extra-forbid (unknown key rejected)
  - RED-missing-required-scalar (enable_agentic_memory omitted)
  - RED-system_user_id-empty (min_length=1)
  - RED-num_history-negative (ge=0)
  - RED-storage_type-out-of-Literal (sqlite|postgres|memory)
  - optional-nested-blocks-None (only 6 scalars -> nested are None)

These tests reference ``yaml_agno.models.config.memory_config`` which does NOT
exist yet (RED phase). They MUST fail on ImportError until Phase 2.2 lands.
"""

import pytest
from pydantic import ValidationError

from yaml_agno.models.config.memory_config import MemoryConfig

pytestmark = pytest.mark.unit


def _valid_scalars() -> dict:
    """The 6 required scalar fields with valid values."""
    return {
        "enable_agentic_memory": True,
        "update_memory_on_run": True,
        "add_memories_to_context": True,
        "num_history_runs": 5,
        "num_history_messages": 50,
        "system_user_id": "agent:my_agent",
    }


class TestMemoryConfigGoldenPaths:
    """GREEN scenarios — valid configs accepted."""

    def test_golden_canonical_parse_six_scalars_nested_none(self) -> None:
        """Parse with only the 6 required scalars; nested blocks default to None."""
        cfg = MemoryConfig.model_validate(_valid_scalars())
        assert cfg.enable_agentic_memory is True
        assert cfg.update_memory_on_run is True
        assert cfg.add_memories_to_context is True
        assert cfg.num_history_runs == 5
        assert cfg.num_history_messages == 50
        assert cfg.system_user_id == "agent:my_agent"
        # All four nested blocks are optional and default to None.
        assert cfg.session is None
        assert cfg.working is None
        assert cfg.learning is None
        assert cfg.retention is None

    def test_optional_nested_blocks_all_none_when_omitted(self) -> None:
        """Explicitly confirm optional nested blocks stay None when omitted."""
        cfg = MemoryConfig(**_valid_scalars())
        for attr in ("session", "working", "learning", "retention"):
            assert getattr(cfg, attr) is None


class TestMemoryConfigRedCases:
    """RED scenarios — invalid configs rejected fast."""

    def test_red_extra_field_forbidden(self) -> None:
        """Unknown key MUST be rejected (extra=forbid)."""
        data = _valid_scalars() | {"unknown_field": 123}
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig.model_validate(data)
        assert "extra_forbidden" in str(exc_info.value) or "Unexpected" in str(exc_info.value)

    def test_red_missing_required_scalar(self) -> None:
        """Omitting enable_agentic_memory MUST fail."""
        data = _valid_scalars()
        del data["enable_agentic_memory"]
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig.model_validate(data)
        assert "enable_agentic_memory" in str(exc_info.value)

    def test_red_system_user_id_empty_rejected(self) -> None:
        """Empty system_user_id MUST fail (min_length=1)."""
        data = _valid_scalars() | {"system_user_id": ""}
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig.model_validate(data)
        assert "system_user_id" in str(exc_info.value)

    def test_red_num_history_runs_negative_rejected(self) -> None:
        """Negative num_history_runs MUST fail (ge=0)."""
        data = _valid_scalars() | {"num_history_runs": -1}
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig.model_validate(data)
        assert "num_history_runs" in str(exc_info.value)

    def test_red_storage_type_out_of_literal_rejected(self) -> None:
        """session.storage_type outside sqlite|postgres|memory MUST fail."""
        data = _valid_scalars() | {
            "session": {"storage_type": "redis", "max_messages": 10},
        }
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig.model_validate(data)
        assert "storage_type" in str(exc_info.value)


class TestMemoryConfigUpdateUserMemoryGotcha:
    """RED scenarios — the Agno 2.8.7 `update_user_memory` tool-name collision.

    Agno 2.8.7 (verified in agno/agent/agent.py): ``enable_agentic_memory``
    must NOT be combined with a LearningMachine that has a ``user_memory``
    store. Both register a tool named ``update_user_memory``; tool parsing
    keeps the first name it sees and the learning store's tool is silently
    dropped. In yaml-agno, ``learning.enabled=True`` wires the rich
    LearningMachine (6 stores, including ``user_memory``) per SPEC_04 §2.2, so
    the combination MUST be rejected at config-build time (fail fast, never a
    silent drop by Agno).
    """

    @staticmethod
    def _valid_learning_cfg() -> dict:
        """A fully-populated learning block (SPEC_04 §1.3)."""
        return {
            "enabled": True,
            "recall_on_start": True,
            "save_on_decision": True,
            "save_on_discovery": True,
            "save_on_bugfix": True,
            "scope": "tenant:acme",
            "learned_knowledge": {"scope": "tenant:acme"},
            "entity_memory": {"scope": "tenant:acme"},
        }

    def test_red_agentic_memory_with_learning_enabled_rejected(self) -> None:
        """enable_agentic_memory=True + learning.enabled=True MUST be rejected
        (both would register the Agno tool `update_user_memory`)."""
        data = _valid_scalars() | {
            "enable_agentic_memory": True,
            "learning": self._valid_learning_cfg(),
        }
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig.model_validate(data)
        assert "update_user_memory" in str(exc_info.value)

    def test_golden_agentic_memory_without_learning_accepted(self) -> None:
        """enable_agentic_memory=True with no learning block is valid (no
        LearningMachine user_memory store -> no tool collision)."""
        data = _valid_scalars() | {"enable_agentic_memory": True}
        cfg = MemoryConfig.model_validate(data)
        assert cfg.enable_agentic_memory is True
        assert cfg.learning is None

    def test_golden_learning_enabled_without_agentic_memory_accepted(self) -> None:
        """learning.enabled=True with enable_agentic_memory=False is valid
        (the only `update_user_memory` tool is the learning store's)."""
        data = _valid_scalars() | {
            "enable_agentic_memory": False,
            "learning": self._valid_learning_cfg(),
        }
        cfg = MemoryConfig.model_validate(data)
        assert cfg.enable_agentic_memory is False
        assert cfg.learning is not None and cfg.learning.enabled is True

    def test_golden_agentic_memory_with_learning_disabled_accepted(self) -> None:
        """enable_agentic_memory=True + learning.enabled=False is valid (the
        simple MemoryManager path has no user_memory store tool)."""
        data = _valid_scalars() | {
            "enable_agentic_memory": True,
            "learning": self._valid_learning_cfg() | {"enabled": False},
        }
        cfg = MemoryConfig.model_validate(data)
        assert cfg.enable_agentic_memory is True
        assert cfg.learning is not None and cfg.learning.enabled is False
