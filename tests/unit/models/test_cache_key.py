"""Unit tests for CacheKeyBuilder (SPEC_14 slice #4 — DOMAIN).

RED-GREEN strict TDD. Tagged ``@pytest.mark.unit``. Pure determinism over a
Pydantic spec + caller-supplied hashes. No network.

Covers (Req 4 + Req 5):
  - Same inputs -> same 64-hex digest (with ``ya:ck:v1:`` prefix).
  - Different ``temperature`` -> different key.
  - Different ``messages_hash`` -> different key.
  - Dict-key reordering of ``model_dump`` -> same key (``sort_keys=True``).
  - Prefix shape: ``ya:ck:v1:`` + 64 hex chars.
"""

from __future__ import annotations

import pytest

from yaml_agno.models.cache_key import CacheKeyBuilder
from yaml_agno.models.model_spec import ModelExpandedSpec


def _spec(temperature: float = 0.7) -> ModelExpandedSpec:
    """A minimal spec for deterministic key tests."""
    return ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=temperature)


# ---------------------------------------------------------------------------
# Req 4 — deterministic sha256 hex digest
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_same_inputs_produce_same_key() -> None:
    """Golden determinism: identical inputs -> identical digest.

    Spec scenario: mismo input produce mismo key.
    """
    spec = _spec()
    key_a = CacheKeyBuilder.build(spec, messages_hash="abc", tool_defs_hash="t1", response_model_hash="r1")
    key_b = CacheKeyBuilder.build(spec, messages_hash="abc", tool_defs_hash="t1", response_model_hash="r1")
    assert key_a == key_b


@pytest.mark.unit
def test_key_has_ya_ck_v1_prefix_and_64_hex_body() -> None:
    """The key shape is ``ya:ck:v1:`` followed by exactly 64 hex chars.

    This fixes the contract callers (SPEC_09 traces) depend on for dedup.
    """
    spec = _spec()
    key = CacheKeyBuilder.build(spec, messages_hash="abc")
    assert key.startswith("ya:ck:v1:")
    body = key.removeprefix("ya:ck:v1:")
    # sha256 hexdigest is 64 lowercase hex chars.
    assert len(body) == 64
    assert all(c in "0123456789abcdef" for c in body)


@pytest.mark.unit
def test_different_temperature_produces_different_key() -> None:
    """Two specs differing only in ``temperature`` produce different keys.

    Spec scenario: temperatura distinta produce key distinto.
    """
    spec_warm = _spec(temperature=0.7)
    spec_hot = _spec(temperature=0.9)
    key_warm = CacheKeyBuilder.build(spec_warm, messages_hash="abc")
    key_hot = CacheKeyBuilder.build(spec_hot, messages_hash="abc")
    assert key_warm != key_hot


@pytest.mark.unit
def test_different_messages_hash_produces_different_key() -> None:
    """Different ``messages_hash`` (caller-supplied) -> different key.

    Spec scenario: messages_hash distinto -> key distinto. The builder does not
    hash messages itself; it incorporates the caller's hash into the digest.
    """
    spec = _spec()
    key_a = CacheKeyBuilder.build(spec, messages_hash="hash-a")
    key_b = CacheKeyBuilder.build(spec, messages_hash="hash-b")
    assert key_a != key_b


# ---------------------------------------------------------------------------
# Req 5 — stable serialization (sort_keys) + optional-hash defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_dump_key_reordering_produces_same_key() -> None:
    """``sort_keys=True`` makes the digest independent of dict insertion order.

    Spec scenario: messages reordenados -> mismo key (the builder serializes the
    spec dump with sorted keys so Pydantic field-order changes never affect the
    digest). We simulate a reordering by building two specs that serialize to
    the same sorted payload despite different construction order of optional
    fields.
    """
    spec_a = ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.7, top_p=0.9)
    spec_b = ModelExpandedSpec(provider="openai", id="gpt-4o", top_p=0.9, temperature=0.7)
    # model_dump dict ordering can differ, but sorted serialization must match.
    key_a = CacheKeyBuilder.build(spec_a, messages_hash="abc")
    key_b = CacheKeyBuilder.build(spec_b, messages_hash="abc")
    assert key_a == key_b


@pytest.mark.unit
def test_optional_hashes_default_to_empty_string() -> None:
    """When ``tool_defs_hash`` / ``response_model_hash`` are omitted, the key is
    still deterministic and equals the key built with explicit empty strings.

    This confirms the defaults are stable (empty string, not None) so a caller
    that omits them gets the same key as one passing ``""``.
    """
    spec = _spec()
    key_implicit = CacheKeyBuilder.build(spec, messages_hash="abc")
    key_explicit = CacheKeyBuilder.build(
        spec, messages_hash="abc", tool_defs_hash="", response_model_hash=""
    )
    assert key_implicit == key_explicit


@pytest.mark.unit
def test_different_tool_defs_hash_produces_different_key() -> None:
    """Triangulation: ``tool_defs_hash`` is load-bearing, not ignored."""
    spec = _spec()
    key_a = CacheKeyBuilder.build(spec, messages_hash="abc", tool_defs_hash="tools-v1")
    key_b = CacheKeyBuilder.build(spec, messages_hash="abc", tool_defs_hash="tools-v2")
    assert key_a != key_b
