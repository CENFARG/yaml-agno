"""Unit tests for A2AInterfaceFactory — SPEC_26 TASK_004 + TASK_006.

TDD cycle: RED → GREEN → TRIANGULATE → REFACTOR.
Tests the factory's resolve → instantiate pipeline with mocked registries.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from yaml_agno.agentos.a2a_interface import (
    A2AInterfaceConfig,
    A2AInterfaceFactory,
    A2APrefix,
    A2AReferenceError,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _mock_a2a_module(mocker):
    """Create a fake ``agno.os.interfaces.a2a`` module with a mock A2A class.

    Agno 2.8.3 does not ship the A2A module yet (it's in development), so
    we simulate it in ``sys.modules`` so the lazy ``from agno.os.interfaces.a2a
    import A2A`` inside ``build()`` succeeds.
    """
    # Ensure the parent chain exists
    _ensure_parent("agno")
    _ensure_parent("agno.os")
    _ensure_parent("agno.os.interfaces")

    fake_a2a = MagicMock()
    sys.modules["agno.os.interfaces.a2a"] = fake_a2a

    mock_a2a_cls = mocker.MagicMock(name="A2A")
    fake_a2a.A2A = mock_a2a_cls

    return mock_a2a_cls


def _ensure_parent(name: str) -> None:
    if name not in sys.modules:
        pkg = MagicMock()
        pkg.__name__ = name
        pkg.__path__ = []
        sys.modules[name] = pkg


def _cleanup_modules(*names: str) -> None:
    for name in names:
        sys.modules.pop(name, None)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def factory():
    """A fresh A2AInterfaceFactory."""
    return A2AInterfaceFactory()


@pytest.fixture(autouse=True)
def _clean_a2a_module():
    """Ensure the fake a2a module is removed after each test."""
    yield
    _cleanup_modules(
        "agno.os.interfaces.a2a",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Factory — resolution + instantiation
# ═══════════════════════════════════════════════════════════════════════════


class TestA2AInterfaceFactory:
    def test_factory_instantiates_agno_a2a_with_resolved_refs(self, mocker):
        """build() resolves refs through registries and instantiates Agno A2A."""
        mock_a2a_cls = _mock_a2a_module(mocker)
        mocker.patch(
            "yaml_agno.agentos.a2a_interface._require_a2a_sdk"
        )

        registries = mocker.Mock()
        registries.agents.resolve.side_effect = [
            mocker.Mock(name="agent_obj"),
        ]

        cfg = A2AInterfaceConfig(
            agents=["researcher"],
            prefix=A2APrefix(value="/a2a"),
        )
        A2AInterfaceFactory().build(cfg, registries)

        mock_a2a_cls.assert_called_once()
        kwargs = mock_a2a_cls.call_args.kwargs
        assert len(kwargs["agents"]) == 1
        assert kwargs["teams"] is None
        assert kwargs["workflows"] is None
        assert kwargs["prefix"] == "/a2a"

    def test_factory_raises_on_unresolvable_ref(self, mocker):
        """build() raises A2AReferenceError when a declared ref cannot be resolved."""
        _mock_a2a_module(mocker)
        mocker.patch(
            "yaml_agno.agentos.a2a_interface._require_a2a_sdk"
        )

        registries = mocker.Mock()
        registries.agents.resolve.side_effect = KeyError("ghost")

        cfg = A2AInterfaceConfig(agents=["ghost"])

        with pytest.raises(A2AReferenceError, match="ghost"):
            A2AInterfaceFactory().build(cfg, registries)

    def test_factory_resolves_multiple_agents(self, mocker):
        """build() resolves multiple agents and passes them all to A2A."""
        mock_a2a_cls = _mock_a2a_module(mocker)
        mocker.patch(
            "yaml_agno.agentos.a2a_interface._require_a2a_sdk"
        )

        agent_a = mocker.Mock(name="agent_a")
        agent_b = mocker.Mock(name="agent_b")

        registries = mocker.Mock()
        registries.agents.resolve.side_effect = [agent_a, agent_b]

        cfg = A2AInterfaceConfig(agents=["a", "b"])
        A2AInterfaceFactory().build(cfg, registries)

        kwargs = mock_a2a_cls.call_args.kwargs
        assert kwargs["agents"] == [agent_a, agent_b]

    def test_factory_passes_empty_lists_as_none(self, mocker):
        """build() passes None for empty teams/workflows (not empty lists)."""
        mock_a2a_cls = _mock_a2a_module(mocker)
        mocker.patch(
            "yaml_agno.agentos.a2a_interface._require_a2a_sdk"
        )

        registries = mocker.Mock()
        registries.agents.resolve.return_value = mocker.Mock(name="agent")

        cfg = A2AInterfaceConfig(agents=["a"])
        A2AInterfaceFactory().build(cfg, registries)

        kwargs = mock_a2a_cls.call_args.kwargs
        assert kwargs["teams"] is None
        assert kwargs["workflows"] is None

    # --- TASK_006: prefix/tags forwarding ---

    def test_prefix_and_tags_forwarded(self, mocker):
        """Custom prefix and tags are forwarded to Agno A2A constructor."""
        mock_a2a_cls = _mock_a2a_module(mocker)
        mocker.patch(
            "yaml_agno.agentos.a2a_interface._require_a2a_sdk"
        )

        registries = mocker.Mock()
        registries.agents.resolve.return_value = mocker.Mock(name="agent_obj")

        cfg = A2AInterfaceConfig(
            agents=["a"],
            prefix=A2APrefix(value="/interop"),
            tags=["public"],
        )
        A2AInterfaceFactory().build(cfg, registries)

        kwargs = mock_a2a_cls.call_args.kwargs
        assert kwargs["prefix"] == "/interop"
        assert kwargs["tags"] == ["public"]
