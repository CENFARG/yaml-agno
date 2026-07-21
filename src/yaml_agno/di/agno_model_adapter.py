"""AgnoModelAdapter — cache de instancias Agno Model por alias (SPEC_14 #3, A4).

Cache simple (dict proceso-vida) que guarda la instancia Agno Model ya
construida indexada por ``alias or f"{provider}:{id}"``. Reusar la instancia
entre agentes comparte el pool de conexiones HTTP que el Model construye
lazily. ``invalidate()`` es el hook para rotation/audit (SPEC_23 §2.9, slice
posterior) — sin TTL en este slice.

@ai-directive: NO agregues TTL aquí. La rotation es EXPLICITA via invalidate().
    El builder siempre se llama a través de get_or_build para mantener una sola
    via de entrada al cache.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = ["AgnoModelAdapter"]


class AgnoModelAdapter:
    """Process-lifetime cache of Agno Model instances, keyed by alias.

    Attributes:
        _cache: Dict ``alias -> Agno Model instance``.

    Example:
        >>> adapter = AgnoModelAdapter()
        >>> model = adapter.get_or_build("openai_chat:gpt-4o", lambda: factory.build(spec))
        >>> same = adapter.get_or_build("openai_chat:gpt-4o", lambda: factory.build(spec))
        >>> model is same
        True
    """

    def __init__(self) -> None:
        """Initialize an empty cache."""
        self._cache: dict[str, Any] = {}

    def get_or_build(self, alias: str, builder: Callable[[], Any]) -> Any:
        """Return the cached instance for ``alias``, or build+cache it.

        ``builder`` is invoked at most once per alias for the lifetime of the
        adapter (unless invalidated). This guarantees a single Agno Model
        instance per alias — sharing its lazy HTTP client across consumers.

        Args:
            alias: Cache key. Convention: ``f"{provider}:{id}"`` or a user-set
                alias from the spec.
            builder: Zero-arg callable that constructs the instance (typically
                ``lambda: factory.build(spec)``). Called ONLY on cache miss.

        Returns:
            The cached or freshly-built Agno Model instance.
        """
        if alias not in self._cache:
            self._cache[alias] = builder()
        return self._cache[alias]

    def invalidate(self, alias: str | None = None) -> None:
        """Drop one entry (``alias`` set) or the whole cache (``alias=None``).

        Used by the future secret-rotation path (SPEC_23 §2.9): after rotating a
        key, call ``invalidate("openai_chat:gpt-4o")`` so the next
        ``get_or_build`` rebuilds with the new secret.

        Args:
            alias: Specific alias to drop, or None to clear the entire cache.
        """
        if alias is None:
            self._cache.clear()
        else:
            self._cache.pop(alias, None)

    def __len__(self) -> int:
        """Return the number of cached entries (useful for tests/diagnostics)."""
        return len(self._cache)

    def __contains__(self, alias: str) -> bool:
        """Return True if ``alias`` is cached."""
        return alias in self._cache
