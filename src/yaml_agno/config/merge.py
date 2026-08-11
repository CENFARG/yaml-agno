"""Multi-tenant YAML deep merge (SPEC_23 §2.8, TASK_2313).

This is the yaml-agno *wiring* step: tenant overrides are deep-merged over
the default config BEFORE the merged dict is fed to the core ConfigManager.
Merge strategy ``default <- tenant`` — the tenant wins on conflict, but
un-touched siblings survive (deep merge never replaces a whole section unless
the tenant defines the full section).

Pure functions, no I/O, no mutation of the inputs.
"""

from __future__ import annotations

from typing import Any

__all__ = ["_deep_merge", "_merge_tenant"]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``.

    Args:
        base: The default config dict (never mutated).
        override: The tenant/override dict (never mutated). Wins on conflict.

    Returns:
        A new merged dict (shallow-copies leaves, deep-copies nested dicts).
    """
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _merge_tenant(default: dict[str, Any], tenant: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a tenant override over the default config.

    Args:
        default: The default (global) config dict.
        tenant: The tenant override dict, or None/{} for no override.

    Returns:
        The merged dict. Returns ``default`` unchanged when ``tenant`` is
        falsy (None or empty).
    """
    if not tenant:
        return default
    return _deep_merge(default, tenant)
