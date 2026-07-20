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
