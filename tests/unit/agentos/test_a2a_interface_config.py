"""Unit tests for A2AInterfaceConfig and A2APrefix — SPEC_26 TASK_002.

TDD cycle: RED (write tests) → GREEN (implement) → TRIANGULATE → REFACTOR.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yaml_agno.agentos.a2a_interface import A2AInterfaceConfig, A2APrefix

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════════════
# A2APrefix
# ═══════════════════════════════════════════════════════════════════════════


class TestA2APrefix:
    def test_default_prefix_is_a2a(self):
        """Default value is '/a2a'."""
        prefix = A2APrefix()
        assert prefix.value == "/a2a"

    def test_prefix_must_start_with_slash(self):
        """Prefix values without leading '/' are rejected."""
        with pytest.raises(ValueError, match="start with '/'"):
            A2APrefix(value="a2a")

    def test_custom_prefix_accepted(self):
        """Custom prefix with leading '/' is accepted."""
        prefix = A2APrefix(value="/interop")
        assert prefix.value == "/interop"

    def test_prefix_is_frozen(self):
        """A2APrefix is immutable (frozen=True)."""
        prefix = A2APrefix(value="/v2")
        with pytest.raises(ValidationError):
            prefix.value = "/v3"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# A2AInterfaceConfig
# ═══════════════════════════════════════════════════════════════════════════


class TestA2AInterfaceConfig:
    def test_requires_at_least_one_component(self):
        """Empty config (no agents, teams, workflows) is rejected."""
        with pytest.raises(ValueError, match="at least one"):
            A2AInterfaceConfig()

    def test_agents_only_is_valid(self):
        """Config with only agents is valid."""
        cfg = A2AInterfaceConfig(agents=["researcher"])
        assert cfg.agents == ["researcher"]
        assert cfg.teams == []
        assert cfg.workflows == []

    def test_all_refs_lists_every_kind(self):
        """all_refs() returns all three component kinds as a dict."""
        cfg = A2AInterfaceConfig(
            agents=["a1", "a2"],
            teams=["t1"],
            workflows=["w1"],
        )
        refs = cfg.all_refs()
        assert refs == {
            "agents": ["a1", "a2"],
            "teams": ["t1"],
            "workflows": ["w1"],
        }

    def test_extra_fields_forbidden(self):
        """Unknown fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            A2AInterfaceConfig(agents=["a"], unknown_field=1)  # type: ignore[call-arg]

    def test_default_prefix_is_a2a(self):
        """Default prefix is A2APrefix with value '/a2a'."""
        cfg = A2AInterfaceConfig(agents=["researcher"])
        assert cfg.prefix.value == "/a2a"

    def test_tags_default_none(self):
        """Default tags is None (not empty list)."""
        cfg = A2AInterfaceConfig(agents=["researcher"])
        assert cfg.tags is None

    def test_custom_tags_preserved(self):
        """Custom tags list is preserved."""
        cfg = A2AInterfaceConfig(agents=["a"], tags=["public", "v2"])
        assert cfg.tags == ["public", "v2"]

    def test_teams_and_workflows_alone_also_valid(self):
        """Config with only teams or only workflows is valid."""
        cfg_t = A2AInterfaceConfig(teams=["t1"])
        assert cfg_t.agents == []
        assert cfg_t.teams == ["t1"]

        cfg_w = A2AInterfaceConfig(workflows=["w1"])
        assert cfg_w.workflows == ["w1"]
