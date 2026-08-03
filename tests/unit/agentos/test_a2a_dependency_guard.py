"""Unit tests for a2a-sdk dependency guard — SPEC_26 TASK_005.

TDD cycle: RED → GREEN → TRIANGULATE → REFACTOR.
Tests _require_a2a_sdk() — the lazy import guard.
"""

from __future__ import annotations

import sys

import pytest

from yaml_agno.agentos.a2a_interface import A2ADependencyError, _require_a2a_sdk

pytestmark = pytest.mark.unit


class TestA2ADependencyGuard:
    def test_missing_sdk_raises_actionable_error(self, mocker):
        """_require_a2a_sdk() raises A2ADependencyError with pip install message."""
        # Simulate a2a module not installed by temporarily removing it
        mocker.patch.dict(sys.modules, {"a2a": None})

        with pytest.raises(A2ADependencyError, match="pip install"):
            _require_a2a_sdk()

    def test_sdk_present_passes_silently(self):
        """_require_a2a_sdk() completes without error when a2a is importable."""
        # a2a is not installed in this env, but we mock it via sys.modules
        try:
            original = sys.modules.get("a2a")
            sys.modules["a2a"] = type(sys)("a2a")
            # Must not raise
            _require_a2a_sdk()
        finally:
            if original is None:
                sys.modules.pop("a2a", None)
            else:
                sys.modules["a2a"] = original
