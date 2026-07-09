"""yaml-agno DI package — fachada Agno + ValueResolver.

API pública:
    - AgnoResolver: fachada de dominio sobre ImportlibDependencyAdapter.
    - build_agno_resolver: fábrica síncrona (ensambla managers core-cenf).
    - ValueResolver: traduce ${provider.key} a dict para DIReference.resolve().
    - MODEL_REGISTRY / STORAGE_REGISTRY / WORKFLOW_REGISTRY: catálogos DATA.
    - AGNO_ALLOWLIST_PREFIXES: prefijos para sembrar el allowlist.

@ai-directive: NO re-exportar ImportlibDependencyAdapter aquí — los consumidores
    pasan por AgnoResolver. El adapter es un detalle de implementación.
"""

from __future__ import annotations

from yaml_agno.di.agno_resolver import AgnoResolver, build_agno_resolver
from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    STORAGE_REGISTRY,
    WORKFLOW_REGISTRY,
)
from yaml_agno.di.value_resolver import ValueResolver

__all__ = [
    "AGNO_ALLOWLIST_PREFIXES",
    "MODEL_REGISTRY",
    "STORAGE_REGISTRY",
    "WORKFLOW_REGISTRY",
    "AgnoResolver",
    "ValueResolver",
    "build_agno_resolver",
]
