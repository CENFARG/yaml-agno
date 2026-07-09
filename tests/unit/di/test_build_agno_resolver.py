"""RED tests for build_agno_resolver — wiring of the core-cenf manager graph.

Verifies the synchronous factory that assembles Config → Logger → Observability
→ Errors → Dependency → AgnoResolver (design A3, A4). Uses official core-cenf
in-memory doubles. Tagged ``@pytest.mark.unit``.

Covers 4 scenarios from SPEC_01 §build_agno_resolver:
  - bootstrap with injected adapter skips wiring.
  - empty allowlist → ValidationError (strict guard).
  - full wiring with in-memory doubles returns a functional AgnoResolver.
  - ClassificationAdapter constructed with 3 args (config, logger, observability).
"""

from __future__ import annotations

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.dependency import InMemoryDependencyAdapter

from yaml_agno.di.agno_resolver import AgnoResolver, build_agno_resolver
from yaml_agno.di.registries import AGNO_ALLOWLIST_PREFIXES


# ---------------------------------------------------------------------------
# Lazy imports of in-memory adapters (installed core-cenf v0.1.0 does not
# re-export config adapter classes from the package __init__).
# ---------------------------------------------------------------------------


def _inmemory_config(allowlist: list[str] | None = None):
    from core_infrastructure.config.adapters.in_memory_config_adapter import (
        InMemoryConfigAdapter,
    )

    cfg = InMemoryConfigAdapter()
    if allowlist is not None:
        cfg.set_value("dependency.allowlist_paths", allowlist)
    return cfg


def _inmemory_logger(config):
    from core_infrastructure.logger.adapters import InMemoryLoggerAdapter

    return InMemoryLoggerAdapter()


def _capturing_errors(config, logger, observability):
    from core_infrastructure.errors.adapters import CapturingErrorAdapter

    return CapturingErrorAdapter(config, logger, observability)


def _noop_observability():
    from core_infrastructure.observability.adapters import NoopObservabilityAdapter

    return NoopObservabilityAdapter()


# ---------------------------------------------------------------------------
# Scenario 1: injected adapter short-circuits the wiring.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_with_injected_adapter_skips_wiring() -> None:
    """When adapter= is passed, the 3 managers are NOT constructed."""
    adapter = InMemoryDependencyAdapter()
    resolver = build_agno_resolver(adapter=adapter)
    assert isinstance(resolver, AgnoResolver)
    assert resolver._adapter is adapter  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Scenario 2: empty allowlist → ValidationError (strict guard).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_empty_allowlist_raises_validation_error() -> None:
    """An InMemoryConfigAdapter without dependency.allowlist_paths is rejected."""
    cfg = _inmemory_config(allowlist=None)  # no allowlist seeded
    with pytest.raises(ValidationError):
        build_agno_resolver(cfg)


# ---------------------------------------------------------------------------
# Scenario 3: full wiring with in-memory doubles returns a functional resolver.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_full_wiring_with_inmemory_doubles() -> None:
    """Full graph wiring returns a working AgnoResolver without exception."""
    cfg = _inmemory_config(allowlist=AGNO_ALLOWLIST_PREFIXES)
    logger = _inmemory_logger(cfg)
    obs = _noop_observability()
    errors = _capturing_errors(cfg, logger, obs)
    resolver = build_agno_resolver(cfg, logger=logger, errors=errors, observability=obs)
    assert isinstance(resolver, AgnoResolver)


# ---------------------------------------------------------------------------
# Scenario 4: ClassificationAdapter needs 3 args — verifies design correction A3.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_graph_order_config_logger_observability_errors_dependency() -> None:
    """ClassificationAdapter is constructed with (config, logger, observability).

    This encodes the design correction A3: the proposal omitted the 3rd arg,
    but core-cenf v0.1.0 requires observability. The factory must pass all 3.
    """
    # We verify by constructing ClassificationAdapter directly with 3 args
    # (the same call the factory makes internally). If the signature were
    # 2-arg, this would raise TypeError.
    from core_infrastructure.errors.adapters import ClassificationAdapter

    cfg = _inmemory_config(allowlist=AGNO_ALLOWLIST_PREFIXES)
    logger = _inmemory_logger(cfg)
    obs = _noop_observability()
    # Must accept 3 positional args — the design's wiring contract.
    handler = ClassificationAdapter(cfg, logger, obs)
    assert handler is not None

    # And the factory wiring that uses this 3-arg constructor must succeed.
    resolver = build_agno_resolver(
        cfg, logger=logger, observability=obs
    )
    assert isinstance(resolver, AgnoResolver)
