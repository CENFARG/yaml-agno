"""Module-allowlist guard for custom tool dotted-path resolution.

Custom tools are the ONE place yaml-agno resolves user-supplied Python paths
(per SPEC_00, the 30% Python). The allowlist prevents arbitrary module
loading.
"""

from __future__ import annotations

__all__ = ["SecurityError", "is_module_allowed"]


class SecurityError(Exception):
    """Raised when a dotted-path module is not in the allowlist."""


# Agno toolkits + a sane user-packages default. Extend via the resolver's
# allowlist configuration (slice C bootstrap). Empty = fail-closed.
_ALLOWED_MODULE_PREFIXES: tuple[str, ...] = ("agno.tools.",)


def is_module_allowed(
    dotted_path: str,
    extra_prefixes: tuple[str, ...] = (),
    *,
    base_prefixes: tuple[str, ...] | None = None,
) -> bool:
    """Return True iff ``dotted_path`` starts with an allowlisted prefix.

    Fail-closed: an empty allowlist rejects everything. Prefix-match lets
    ``agno.tools.`` cover all submodules (calculator, yfinance, ...).

    Args:
        dotted_path: The dotted module path to check (e.g. 'agno.tools.calculator').
        extra_prefixes: Additional allowed prefixes (e.g. user package roots).
        base_prefixes: Optional override of the default allowlist (testing).
            When an empty tuple is passed explicitly, the result is fail-closed
            (no match possible) — this exercises the fail-closed branch.

    Returns:
        True if any prefix matches.
    """
    prefixes = (_ALLOWED_MODULE_PREFIXES if base_prefixes is None else base_prefixes) + extra_prefixes
    if not prefixes:
        return False
    return any(dotted_path.startswith(p) for p in prefixes)
