"""Unit tests for AgnoModelAdapter (SPEC_14 slice #3).

RED-GREEN strict TDD. Tagged @pytest.mark.unit. Pure-Python cache, no Agno.

Covers:
  - get_or_build caches by alias: builder invoked once, same instance returned.
  - invalidate(alias) drops one entry; invalidate(None) clears all.
  - __len__ and __contains__ reflect cache state.
"""

from __future__ import annotations

import pytest

from yaml_agno.di.agno_model_adapter import AgnoModelAdapter


@pytest.mark.unit
def test_get_or_build_caches_instance() -> None:
    """Two get_or_build calls with the same alias invoke builder once and return is-identical."""
    adapter = AgnoModelAdapter()
    calls: list[int] = []

    def builder() -> dict[str, int]:
        calls.append(1)
        return {"built": len(calls)}

    first = adapter.get_or_build("openai:gpt-4o", builder)
    second = adapter.get_or_build("openai:gpt-4o", builder)
    assert first is second
    assert len(calls) == 1, "builder must be invoked exactly once on cache hit"


@pytest.mark.unit
def test_get_or_build_distinct_aliases_build_distinct_instances() -> None:
    """Different aliases yield different cached instances."""
    adapter = AgnoModelAdapter()
    a = adapter.get_or_build("openai:gpt-4o", lambda: object())
    b = adapter.get_or_build("anthropic:claude", lambda: object())
    assert a is not b
    assert len(adapter) == 2


@pytest.mark.unit
def test_invalidate_selective_drops_one_entry() -> None:
    """invalidate(alias) drops exactly that entry; others survive."""
    adapter = AgnoModelAdapter()
    adapter.get_or_build("openai:gpt-4o", lambda: object())
    adapter.get_or_build("anthropic:claude", lambda: object())
    assert "openai:gpt-4o" in adapter
    adapter.invalidate("openai:gpt-4o")
    assert "openai:gpt-4o" not in adapter
    assert "anthropic:claude" in adapter
    assert len(adapter) == 1


@pytest.mark.unit
def test_invalidate_none_clears_all() -> None:
    """invalidate(None) clears the entire cache."""
    adapter = AgnoModelAdapter()
    adapter.get_or_build("openai:gpt-4o", lambda: object())
    adapter.get_or_build("anthropic:claude", lambda: object())
    adapter.invalidate(None)
    assert len(adapter) == 0
    assert "openai:gpt-4o" not in adapter


@pytest.mark.unit
def test_invalidate_unknown_alias_is_noop() -> None:
    """Invalidating an alias that was never cached does not raise."""
    adapter = AgnoModelAdapter()
    adapter.get_or_build("openai:gpt-4o", lambda: object())
    # Should not raise KeyError.
    adapter.invalidate("never:cached")
    assert len(adapter) == 1
