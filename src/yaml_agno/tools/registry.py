"""BUILTIN_REGISTRY — declarative catalog of built-in Agno toolkits.

Each ``ToolkitAdapter`` carries the Agno (module, class) pair, an alias map
(yfinance shorthand -> enable_* canonical), and the Agno pip package. The
adapter instantiates the toolkit, filtering ``init_args`` against
``inspect.signature(cls.__init__)`` (Toolkits are NOT dataclasses).

Shipped with 5 adapters (calculator, yfinance, hackernews, duckduckgo, shell).
Slice D expands to 120+.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yaml_agno.di.agno_resolver import AgnoResolver

__all__ = ["BUILTIN_REGISTRY", "ToolkitAdapter", "UnknownBuiltinError"]


class UnknownBuiltinError(Exception):
    """Raised when a ``builtin`` name is not in BUILTIN_REGISTRY."""


@dataclasses.dataclass
class ToolkitAdapter:
    """Declarative metadata + instantiation logic for a built-in toolkit.

    Attributes:
        module_path: Agno module (e.g. 'agno.tools.calculator').
        class_name: Agno class (e.g. 'CalculatorTools').
        packages: Pip packages required (for Dockerfile/pyproject generation).
        alias_map: Shorthand -> canonical kwarg name (e.g. {'stock_price': 'enable_stock_price'}).
    """

    module_path: str
    class_name: str
    packages: tuple[str, ...]
    alias_map: dict[str, str] = dataclasses.field(default_factory=dict)

    def build(self, resolver: AgnoResolver, init_args: dict[str, Any]) -> Any:
        """Resolve the class, normalize aliases, filter kwargs, instantiate.

        Args:
            resolver: The AgnoResolver for allowlisted class resolution.
            init_args: Raw kwargs from the YAML (may use shorthand aliases).

        Returns:
            The instantiated Agno Toolkit.

        Raises:
            TypeError: If the toolkit constructor rejects a filtered kwarg
                (should not happen post-filtering, but defensive).
        """
        cls = resolver.resolve_class(self.module_path, self.class_name)
        normalized = self._normalize_aliases(init_args)
        filtered = self._filter_kwargs(cls, normalized)
        return cls(**filtered)

    def _normalize_aliases(self, init_args: dict[str, Any]) -> dict[str, Any]:
        """Apply the alias_map to rename shorthand keys to canonical."""
        return {self.alias_map.get(k, k): v for k, v in init_args.items()}

    def _filter_kwargs(self, cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Keep only kwargs the class __init__ accepts (Toolkits aren't dataclasses).

        Uses ``inspect.signature``. ``**kwargs`` in the signature (e.g.
        CalculatorTools) accepts everything, so nothing is dropped there.
        """
        try:
            # inspect.signature(cls) resolves to cls.__init__ without the
            # mypy "accessing __init__ on instance is unsound" warning.
            sig_params = inspect.signature(cls).parameters
        except (TypeError, ValueError):
            return kwargs
        allowed = set(sig_params) - {"self"}
        accepts_var_kw = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig_params.values()
        )
        if accepts_var_kw:
            return kwargs
        return {k: v for k, v in kwargs.items() if k in allowed}


BUILTIN_REGISTRY: dict[str, ToolkitAdapter] = {
    "calculator": ToolkitAdapter(
        module_path="agno.tools.calculator",
        class_name="CalculatorTools",
        packages=("agno",),
    ),
    "yfinance": ToolkitAdapter(
        module_path="agno.tools.yfinance",
        class_name="YFinanceTools",
        packages=("yfinance",),
        alias_map={
            "stock_price": "enable_stock_price",
            "company_info": "enable_company_info",
            "news": "enable_company_news",
            "analyst": "enable_analyst_recommendations",
        },
    ),
    "hackernews": ToolkitAdapter(
        module_path="agno.tools.hackernews",
        class_name="HackerNewsTools",
        packages=("agno",),
        alias_map={
            "top_stories": "enable_get_top_stories",
            "user_details": "enable_get_user_details",
        },
    ),
    "duckduckgo": ToolkitAdapter(
        module_path="agno.tools.duckduckgo",
        class_name="DuckDuckGoTools",
        packages=("ddgs",),
    ),
    "shell": ToolkitAdapter(
        module_path="agno.tools.shell",
        class_name="ShellTools",
        packages=("agno",),
    ),
}
