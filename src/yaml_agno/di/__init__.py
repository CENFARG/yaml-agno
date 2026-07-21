"""yaml-agno DI package — fachada Agno + ValueResolver.

API pública:
    - AgnoResolver: fachada de dominio sobre ImportlibDependencyAdapter.
    - build_agno_resolver: fábrica síncrona (ensambla managers core-cenf).
    - ValueResolver: traduce ${provider.key} a dict para DIReference.resolve().
    - MODEL_REGISTRY / STORAGE_REGISTRY / WORKFLOW_REGISTRY: catálogos DATA.
    - PROVIDER_REGISTRY / SUPPORTED_PROVIDERS / LOCAL_PROVIDERS: catálogo
      enriquecido de capabilities (SPEC_14 slice #1).
    - PROVIDER_ALIASES: alias de back-compat (openai → openai_chat).
    - AGNO_ALLOWLIST_PREFIXES: prefijos para sembrar el allowlist.

@ai-directive: NO re-exportar ImportlibDependencyAdapter aquí — los consumidores
    pasan por AgnoResolver. El adapter es un detalle de implementación.
"""

from __future__ import annotations

from yaml_agno.di.agno_model_adapter import AgnoModelAdapter
from yaml_agno.di.agno_resolver import AgnoResolver, build_agno_resolver
from yaml_agno.di.capabilities_validator import ModelCapabilitiesValidator
from yaml_agno.di.provider_capabilities import (
    LOCAL_PROVIDERS,
    PROVIDER_REGISTRY,
    SUPPORTED_PROVIDERS,
)
from yaml_agno.di.provider_factory import ModelConstructionError, ProviderFactory
from yaml_agno.di.registries import (
    AGNO_ALLOWLIST_PREFIXES,
    MODEL_REGISTRY,
    PROVIDER_ALIASES,
    STORAGE_REGISTRY,
    WORKFLOW_REGISTRY,
)
from yaml_agno.di.secret_resolver import ConfigSecretResolver, SecretResolver
from yaml_agno.di.value_resolver import ValueResolver

__all__ = [
    "AGNO_ALLOWLIST_PREFIXES",
    "LOCAL_PROVIDERS",
    "MODEL_REGISTRY",
    "PROVIDER_ALIASES",
    "PROVIDER_REGISTRY",
    "STORAGE_REGISTRY",
    "SUPPORTED_PROVIDERS",
    "WORKFLOW_REGISTRY",
    "AgnoModelAdapter",
    "AgnoResolver",
    "ConfigSecretResolver",
    "ModelCapabilitiesValidator",
    "ModelConstructionError",
    "ProviderFactory",
    "SecretResolver",
    "ValueResolver",
    "build_agno_resolver",
]
