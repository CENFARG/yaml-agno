"""Unit tests for ``yaml_agno.tools.registry`` — SPEC_11 slice A.

BUILTIN_REGISTRY ships 5 adapters. ToolkitAdapter normalizes aliases and
filters kwargs via inspect.signature (Toolkits are NOT dataclasses).
"""

from __future__ import annotations

import pytest

from yaml_agno.tools.registry import BUILTIN_REGISTRY, ToolkitAdapter


class _StubResolver:
    """Returns a fake toolkit class with a configurable __init__ signature."""

    def __init__(self, fake_cls: type) -> None:
        self._fake_cls = fake_cls

    def resolve_class(self, module_path: str, class_name: str) -> type:
        return self._fake_cls


@pytest.mark.unit
def test_registry_has_five_builtins() -> None:
    """The 5 shipped adapters are present."""
    expected = {"calculator", "yfinance", "hackernews", "duckduckgo", "shell"}
    assert expected <= set(BUILTIN_REGISTRY)


@pytest.mark.unit
def test_registry_adapter_metadata() -> None:
    """calculator adapter points at the real Agno class."""
    adapter = BUILTIN_REGISTRY["calculator"]
    assert adapter.module_path == "agno.tools.calculator"
    assert adapter.class_name == "CalculatorTools"


@pytest.mark.unit
def test_alias_normalization_applied_before_build() -> None:
    """yfinance shorthand 'stock_price' -> 'enable_stock_price' before filtering."""
    received: dict[str, object] = {}

    class _FakeYFinance:
        def __init__(self, enable_stock_price: bool = False, **kwargs: object) -> None:
            received.update(enable_stock_price=enable_stock_price, **kwargs)

    adapter = BUILTIN_REGISTRY["yfinance"]
    resolver = _StubResolver(_FakeYFinance)
    adapter.build(resolver, {"stock_price": True})  # shorthand alias
    assert received["enable_stock_price"] is True


@pytest.mark.unit
def test_filter_kwargs_drops_unknown_when_no_var_kw() -> None:
    """A class with explicit params (no **kwargs) drops unknown kwargs."""

    class _StrictToolkit:
        def __init__(self, base_dir: str = "/tmp", all: bool = False) -> None:
            self.base_dir = base_dir

    adapter = ToolkitAdapter(
        module_path="fake", class_name="Fake", packages=(), alias_map={}
    )
    filtered = adapter._filter_kwargs(_StrictToolkit, {"base_dir": "/x", "bogus": 1})
    assert filtered == {"base_dir": "/x"}


@pytest.mark.unit
def test_filter_kwargs_keeps_all_when_var_kw() -> None:
    """A class with **kwargs (e.g. CalculatorTools) accepts everything."""

    class _VarKwToolkit:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    adapter = ToolkitAdapter(module_path="fake", class_name="Fake", packages=(), alias_map={})
    filtered = adapter._filter_kwargs(_VarKwToolkit, {"anything": 1, "goes": 2})
    assert filtered == {"anything": 1, "goes": 2}


@pytest.mark.unit
def test_build_instantiates_real_calculator() -> None:
    """Integration: build real agno CalculatorTools via the adapter."""
    from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
    from core_infrastructure.dependency import ImportlibDependencyAdapter
    from core_infrastructure.errors.adapters.capturing_error_adapter import (
        CapturingErrorAdapter,
    )
    from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
    from core_infrastructure.observability.adapters import NoopObservabilityAdapter

    from yaml_agno.di.agno_resolver import AgnoResolver

    cfg = InMemoryConfigAdapter()
    cfg.set_value("dependency.allowlist_paths", ["agno.tools."])
    resolver = AgnoResolver(
        ImportlibDependencyAdapter(
            cfg,
            InMemoryLoggerAdapter(),
            CapturingErrorAdapter(cfg, InMemoryLoggerAdapter(), NoopObservabilityAdapter()),
        )
    )
    adapter = BUILTIN_REGISTRY["calculator"]
    instance = adapter.build(resolver, {})
    from agno.tools.toolkit import Toolkit

    assert isinstance(instance, Toolkit)
