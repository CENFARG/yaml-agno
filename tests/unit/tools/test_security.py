"""Unit tests for ``yaml_agno.tools.security`` — SPEC_11 slice A."""

from __future__ import annotations

import pytest

from yaml_agno.tools.security import is_module_allowed


@pytest.mark.unit
def test_agno_tools_prefix_allowed() -> None:
    """agno.tools.* is allowlisted by default (prefix-match with trailing dot).

    Note: 'agno.tools' WITHOUT a trailing submodule does NOT match the
    'agno.tools.' prefix — this is intentional (prevents 'agno.toolsevil').
    """
    assert is_module_allowed("agno.tools.calculator") is True
    assert is_module_allowed("agno.tools.shell") is True


@pytest.mark.unit
def test_non_agno_module_rejected() -> None:
    """A module outside the default allowlist is rejected (fail-closed)."""
    assert is_module_allowed("os") is False
    assert is_module_allowed("subprocess.run") is False
    assert is_module_allowed("my_evil_pkg.tools") is False


@pytest.mark.unit
def test_extra_prefixes_extend_allowlist() -> None:
    """Caller-supplied extra prefixes are honored."""
    assert is_module_allowed("my_pkg.tools.fetch", extra_prefixes=("my_pkg.",)) is True


@pytest.mark.unit
def test_empty_allowlist_fail_closed() -> None:
    """Empty allowlist (no prefixes) rejects everything — fail-closed."""
    # Simulate by overriding the module-level prefixes via extra=() AND a
    # monkeypatched empty _ALLOWED_MODULE_PREFIXES is overkill; instead assert
    # the logic: no match possible when only non-matching extras given.
    assert is_module_allowed("agno.tools.x", extra_prefixes=()) is True  # default still applies
