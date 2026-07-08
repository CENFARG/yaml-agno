"""RED tests for DIReference value object (frozen, tokens, resolve).

These tests reference ``yaml_agno.models.value_objects.di_reference.DIReference`` which
does NOT exist yet (RED). They cover the spec scenarios for:
    - Valid single/multi token templates (golden)
    - tokens extraction (golden)
    - resolve basic + literal + missing-key (KeyError) (golden + RED)
    - invalid format (no token / uppercase) (RED)
    - frozen immutability (invariant)
"""

import pytest
from pydantic import ValidationError

from yaml_agno.models.value_objects.di_reference import DIReference

pytestmark = pytest.mark.unit


class TestDIReferenceGoldenPaths:
    """GREEN scenarios — valid templates accepted, tokens/resolve work."""

    def test_di_reference_valid_single_token(self) -> None:
        """A template with a single well-formed token is accepted."""
        ref = DIReference(template="${db.user}")
        assert ref.template == "${db.user}"

    def test_di_reference_valid_multiple_tokens(self) -> None:
        """A template with multiple tokens is accepted."""
        ref = DIReference(template="Hello ${db.name} ${env.ID}")
        assert "db.name" in ref.template
        assert "env.ID" in ref.template

    def test_di_reference_tokens_extraction_single(self) -> None:
        """tokens returns a list of (provider, key) tuples in order."""
        ref = DIReference(template="${db.name}")
        assert ref.tokens == [("db", "name")]

    def test_di_reference_tokens_extraction_multiple(self) -> None:
        """tokens returns every token in order of appearance."""
        ref = DIReference(template="Hello ${user_db.name} ${env.API_KEY}")
        assert ref.tokens == [("user_db", "name"), ("env", "API_KEY")]

    def test_di_reference_resolve_basic(self) -> None:
        """resolve replaces a bare token with its value."""
        ref = DIReference(template="${db.name}")
        assert ref.resolve({"db.name": "Alice"}) == "Alice"

    def test_di_reference_resolve_with_literal(self) -> None:
        """resolve preserves literal text around tokens."""
        ref = DIReference(template="Hello ${db.name}!")
        assert ref.resolve({"db.name": "Alice"}) == "Hello Alice!"

    def test_di_reference_resolve_multiple(self) -> None:
        """resolve replaces every token."""
        ref = DIReference(template="${a.x} meets ${b.y}")
        assert ref.resolve({"a.x": "Alpha", "b.y": "Beta"}) == "Alpha meets Beta"


class TestDIReferenceErrorPaths:
    """RED scenarios — invalid input rejected."""

    def test_di_reference_resolve_missing_key_raises_keyerror(self) -> None:
        """resolve raises KeyError when a token has no resolved value."""
        ref = DIReference(template="${db.name}")
        with pytest.raises(KeyError):
            ref.resolve({})  # "db.name" absent

    def test_di_reference_invalid_format_no_token(self) -> None:
        """A template with no token is rejected by the validator."""
        with pytest.raises(ValidationError) as exc:
            DIReference(template="no-token-here")
        assert "Invalid DI reference format" in str(exc.value)

    def test_di_reference_invalid_format_uppercase(self) -> None:
        """A template with uppercase inside ${} is rejected (regex requires lowercase)."""
        with pytest.raises(ValidationError):
            DIReference(template="${DB.NAME}")

    def test_di_reference_invalid_format_empty_string(self) -> None:
        """An empty template is rejected (no token)."""
        with pytest.raises(ValidationError):
            DIReference(template="")


class TestDIReferenceFrozen:
    """Invariant: DIReference is immutable (frozen=True)."""

    def test_di_reference_frozen_immutable(self) -> None:
        """Assigning to template after construction raises (ValidationError)."""
        ref = DIReference(template="${db.name}")
        with pytest.raises(ValidationError):
            ref.template = "other"  # type: ignore[misc]

    def test_di_reference_model_config_frozen_true(self) -> None:
        """model_config declares frozen=True (the ONLY frozen model in this change)."""
        assert DIReference.model_config.get("frozen") is True
