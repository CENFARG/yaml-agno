"""Registros declarativos Agno — catálogos de providers como DATA.

Estos dicts son la única fuente de verdad de qué clases nativas Agno son
alcanzables vía AgnoResolver. Son DATOS, no lógica: AgnoResolver los consulta
y delega el importlib real al ImportlibDependencyAdapter inyectado.

@ai-directive: NO añadir lógica de resolución aquí. Un nuevo provider se agrega
    como una entrada más en el dict correspondiente.
"""

from __future__ import annotations

from typing import Final

# Mapping logico provider-key -> (module_path, class_name, [packages]).
# module_path DEBE estar cubierto por AGNO_ALLOWLIST_PREFIXES para que
# ImportlibDependencyAdapter.resolve_class lo acepte en strict mode.
MODEL_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    "openai": ("agno.models.openai", "OpenAIChat", ["openai>=1.0"]),
    "anthropic": ("agno.models.anthropic", "Claude", ["anthropic>=0.40"]),
    "google": ("agno.models.google", "Gemini", ["google-genai>=1.0"]),
    "groq": ("agno.models.groq", "Groq", ["groq>=0.11"]),
    "mistral": ("agno.models.mistral", "Mistral", ["mistralai>=1.0"]),
    "cohere": ("agno.models.cohere", "Cohere", ["cohere>=5.0"]),
}

# Storage providers. memory/sqlite: sin connection_string (constructores verificados
# InMemoryDb(), SqliteDb(db_file=None)). postgres/redis: requieren conn_str.
STORAGE_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    "memory": ("agno.db.in_memory", "InMemoryDb", []),
    "sqlite": ("agno.db.sqlite", "SqliteDb", ["sqlalchemy>=2.0"]),
    "postgres": ("agno.db.postgres", "PostgresDb", ["sqlalchemy>=2.0", "psycopg[binary]>=3.0"]),
    "redis": ("agno.db.redis", "RedisDb", ["redis>=5.0"]),
}

# Nombres de primitivas de workflow resolubles como clases (slice #4 consumirá
# los que faltan). Mapeo lógico -> (module, class).
WORKFLOW_REGISTRY: Final[dict[str, tuple[str, str]]] = {
    "Step": ("agno.workflow", "Step"),
    "Parallel": ("agno.workflow", "Parallel"),
    "Condition": ("agno.workflow", "Condition"),
    "Router": ("agno.workflow", "Router"),
    "Loop": ("agno.workflow", "Loop"),
    "Workflow": ("agno.workflow", "Workflow"),
}

# Prefijos siembrados en dependency.allowlist_paths. Prefix-match en
# ImportlibDependencyAdapter._is_allowlisted (verificado importlib_dependency_adapter.py:88).
# Todos los module_path de los REGISTRY anteriores caen bajo estos prefijos.
AGNO_ALLOWLIST_PREFIXES: Final[list[str]] = [
    "agno.models.",
    "agno.db.",
    "agno.workflow.",
    "agno.team.",
    "agno.agent",
]

__all__ = [
    "AGNO_ALLOWLIST_PREFIXES",
    "MODEL_REGISTRY",
    "STORAGE_REGISTRY",
    "WORKFLOW_REGISTRY",
]
