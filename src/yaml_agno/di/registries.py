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
#
# 27 entradas verificadas contra Agno 2.6.22 (cada __init__.py confirmado):
#   - 26 provider_ids del catálogo SPEC_14 §2.2 (incluye el alias "openai").
#   - "mistral_gateway" extra (design §8): gateway alias que apunta a la misma
#     clase MistralChat de "mistral".
# "openai" es un alias de back-compat de "openai_chat" (ver PROVIDER_ALIASES):
# se mantiene además como entrada directa del dict para que los consumers que
# indexan MODEL_REGISTRY["openai"] sigan funcionando; resolve_model aplica el
# alias vía PROVIDER_ALIASES antes del lookup.
# BUG FIXES vs shipped:
#   - mistral: era "Mistral" (no existe) → "MistralChat".
#   - vertex: parent agno.models.vertexai tiene __init__.py VACÍO → submodule
#     "agno.models.vertexai.claude" donde vive la clase Claude.
MODEL_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    # --- Native ---
    "anthropic": ("agno.models.anthropic", "Claude", ["anthropic>=0.40"]),
    "openai": ("agno.models.openai", "OpenAIChat", ["openai>=1.0"]),
    "openai_chat": ("agno.models.openai", "OpenAIChat", ["openai>=1.0"]),
    "openai_responses": ("agno.models.openai", "OpenAIResponses", ["openai>=1.0"]),
    "google": ("agno.models.google", "Gemini", ["google-genai>=1.0"]),
    "mistral": ("agno.models.mistral", "MistralChat", ["mistralai>=1.0"]),
    "deepseek": ("agno.models.deepseek", "DeepSeek", ["openai>=1.0"]),
    "cohere": ("agno.models.cohere", "Cohere", ["cohere>=5.0"]),
    "perplexity": ("agno.models.perplexity", "Perplexity", ["openai>=1.0"]),
    "xai": ("agno.models.xai", "xAI", ["openai>=1.0"]),
    "meta": ("agno.models.meta", "Llama", ["openai>=1.0"]),
    "dashscope": ("agno.models.dashscope", "DashScope", ["openai>=1.0"]),
    "vercel": ("agno.models.vercel", "V0", ["openai>=1.0"]),
    # --- Local (sin api_key_env) ---
    "ollama": ("agno.models.ollama", "Ollama", ["ollama>=0.3"]),
    "llamacpp": ("agno.models.llama_cpp", "LlamaCpp", ["llama-cpp-python>=0.3"]),
    "lm_studio": ("agno.models.lmstudio", "LMStudio", ["openai>=1.0"]),
    "vllm": ("agno.models.vllm", "VLLM", ["vllm>=0.6"]),
    # --- Cloud ---
    "bedrock": ("agno.models.aws", "AwsBedrock", ["boto3>=1.34"]),
    "azure": ("agno.models.azure", "OpenAIChat", ["openai>=1.0"]),
    "vertex": ("agno.models.vertexai.claude", "Claude", ["anthropic>=0.40"]),
    # --- Gateway ---
    "openrouter": ("agno.models.openrouter", "OpenRouter", ["openai>=1.0"]),
    "together": ("agno.models.together", "Together", ["openai>=1.0"]),
    "groq": ("agno.models.groq", "Groq", ["groq>=0.11"]),
    "fireworks": ("agno.models.fireworks", "Fireworks", ["openai>=1.0"]),
    "langdb": ("agno.models.langdb", "LangDB", ["openai>=1.0"]),
    "nebius": ("agno.models.nebius", "Nebius", ["openai>=1.0"]),
    "mistral_gateway": ("agno.models.mistral", "MistralChat", ["mistralai>=1.0"]),
}

# Alias de compatibilidad: "openai" (legacy) → "openai_chat" (canonical SPEC_14).
# AgnoResolver.resolve_model aplica esto ANTES de indexar MODEL_REGISTRY.
# Mantiene back-compat con configs que usan provider: "openai". "openai" se
# conserva además como entrada directa de MODEL_REGISTRY (mismo tuple) para que
# consumers que indexan el dict directamente no se rompan; el alias es la vía
# canónica declarada para slice #2 (ProviderResolver).
PROVIDER_ALIASES: Final[dict[str, str]] = {
    "openai": "openai_chat",
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
    "PROVIDER_ALIASES",
    "STORAGE_REGISTRY",
    "WORKFLOW_REGISTRY",
]
