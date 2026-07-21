"""Catálogo de capabilities por provider — DATA pura.

Extiende ``registries.py`` con metadata que el 3-tuple no puede llevar:
``api_key_env`` (None para providers locales) y ``ProviderCapabilities``.

Contrato (SPEC_14 §2.2 / §2.3):
    - Cada entrada está indexada por el mismo ``provider_id`` que
      ``MODEL_REGISTRY`` (mismo set de claves, incluyendo el alias "openai").
    - ``SUPPORTED_PROVIDERS`` se deriva de ``PROVIDER_REGISTRY`` (única fuente).
    - Las capabilities son **DECLARED, NOT RUNTIME-VERIFIED**: reflejan lo que
      la API pública de la clase Agno 2.6.22 declara (parámetros aceptados,
      firma del método), NO lo que una integration test probó contra una API
      viva. Un caller NO DEBE tratar ``capabilities.caching == True`` como
      garantía — es una declaración de intención. La validación runtime /
      capability override vive en el slice de capabilities (SPEC_14 §6.4).

@ai-directive: NO añadir lógica de instanciación. Solo DATA + dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Capabilities declaradas por un provider Agno.

    Attributes:
        multimodal: modalidades soportadas (subset de ``("image","audio",
            "video","pdf")``); tupla vacía = text-only.
        structured_output: modos soportados de ``("json_mode","strict",
            "response_model")``; tupla vacía = no soporta output estructurado.
        tool_use: ``"native"`` (function-calling first-class), ``"partial"``
            (soporte limitado/model-dependent), ``"none"`` (no tool use).
        streaming: ``True`` si el provider soporta streaming token-a-token.
        caching: ``True`` si acepta ``cache_response`` (Agno base.py).
        reasoning: ``True`` si acepta ``reasoning_effort`` / ``thinking``.

    Note:
        DECLARED, NOT RUNTIME-VERIFIED — ver docstring del módulo.
    """

    multimodal: tuple[str, ...] = ()
    structured_output: tuple[str, ...] = ()
    tool_use: Literal["native", "partial", "none"] = "none"
    streaming: bool = False
    caching: bool = False
    reasoning: bool = False


@dataclass(frozen=True, slots=True)
class ProviderRegistryEntry:
    """Entrada de catálogo por provider.

    Attributes:
        module_path: ruta importable (DEBE estar bajo ``AGNO_ALLOWLIST_PREFIXES``).
        class_name: nombre de la clase Agno exportada por ``module_path``.
        packages: extras pip sugeridos para usar este provider (metadata,
            NO enforced por yaml-agno).
        api_key_env: variable de entorno default para la API key, o ``None``
            para providers locales (ollama, llamacpp, lm_studio, vllm).
        capabilities: instancia de ``ProviderCapabilities``.
    """

    module_path: str
    class_name: str
    packages: tuple[str, ...]
    api_key_env: str | None
    capabilities: ProviderCapabilities


# --- Capabilities constantes reusadas (multimodal total / parcial) ---
_FULL_MM: Final[tuple[str, ...]] = ("image", "audio")
_IMG_MM: Final[tuple[str, ...]] = ("image",)
_FULL_STRUCT: Final[tuple[str, ...]] = ("json_mode", "strict", "response_model")
_NO_STRUCT: Final[tuple[str, ...]] = ()
_RM_STRUCT: Final[tuple[str, ...]] = ("response_model",)


# 27 entradas (una por key de MODEL_REGISTRY, incluyendo el alias "openai" y el
# gateway "mistral_gateway"). api_key_env desde SPEC_14 §2.2, capabilities desde
# §2.2 columnas + §2.3 yaml. Los 4 providers locales llevan api_key_env=None.
PROVIDER_REGISTRY: Final[dict[str, ProviderRegistryEntry]] = {
    # --- Native ---
    "anthropic": ProviderRegistryEntry(
        module_path="agno.models.anthropic",
        class_name="Claude",
        packages=("anthropic>=0.40",),
        api_key_env="ANTHROPIC_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "openai": ProviderRegistryEntry(
        module_path="agno.models.openai",
        class_name="OpenAIChat",
        packages=("openai>=1.0",),
        api_key_env="OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "openai_chat": ProviderRegistryEntry(
        module_path="agno.models.openai",
        class_name="OpenAIChat",
        packages=("openai>=1.0",),
        api_key_env="OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "openai_responses": ProviderRegistryEntry(
        module_path="agno.models.openai",
        class_name="OpenAIResponses",
        packages=("openai>=1.0",),
        api_key_env="OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "google": ProviderRegistryEntry(
        module_path="agno.models.google",
        class_name="Gemini",
        packages=("google-genai>=1.0",),
        api_key_env="GOOGLE_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "mistral": ProviderRegistryEntry(
        module_path="agno.models.mistral",
        class_name="MistralChat",
        packages=("mistralai>=1.0",),
        api_key_env="MISTRAL_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "deepseek": ProviderRegistryEntry(
        module_path="agno.models.deepseek",
        class_name="DeepSeek",
        packages=("openai>=1.0",),
        api_key_env="DEEPSEEK_API_KEY",
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "native", True, False, True),
    ),
    "cohere": ProviderRegistryEntry(
        module_path="agno.models.cohere",
        class_name="Cohere",
        packages=("cohere>=5.0",),
        api_key_env="COHERE_API_KEY",
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "partial", True, False, False),
    ),
    "perplexity": ProviderRegistryEntry(
        module_path="agno.models.perplexity",
        class_name="Perplexity",
        packages=("openai>=1.0",),
        api_key_env="PERPLEXITY_API_KEY",
        capabilities=ProviderCapabilities((), _NO_STRUCT, "none", True, False, False),
    ),
    "xai": ProviderRegistryEntry(
        module_path="agno.models.xai",
        class_name="xAI",
        packages=("openai>=1.0",),
        api_key_env="XAI_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, True),
    ),
    "meta": ProviderRegistryEntry(
        module_path="agno.models.meta",
        class_name="Llama",
        packages=("openai>=1.0",),
        api_key_env="META_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "dashscope": ProviderRegistryEntry(
        module_path="agno.models.dashscope",
        class_name="DashScope",
        packages=("openai>=1.0",),
        api_key_env="DASHSCOPE_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "vercel": ProviderRegistryEntry(
        module_path="agno.models.vercel",
        class_name="V0",
        packages=("openai>=1.0",),
        api_key_env="VERCEL_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    # --- Local (api_key_env = None) ---
    "ollama": ProviderRegistryEntry(
        module_path="agno.models.ollama",
        class_name="Ollama",
        packages=("ollama>=0.3",),
        api_key_env=None,
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "llamacpp": ProviderRegistryEntry(
        module_path="agno.models.llama_cpp",
        class_name="LlamaCpp",
        packages=("llama-cpp-python>=0.3",),
        api_key_env=None,
        capabilities=ProviderCapabilities((), _RM_STRUCT, "partial", True, False, False),
    ),
    "lm_studio": ProviderRegistryEntry(
        module_path="agno.models.lmstudio",
        class_name="LMStudio",
        packages=("openai>=1.0",),
        api_key_env=None,
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "native", True, False, False),
    ),
    "vllm": ProviderRegistryEntry(
        module_path="agno.models.vllm",
        class_name="VLLM",
        packages=("vllm>=0.6",),
        api_key_env=None,
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    # --- Cloud ---
    "bedrock": ProviderRegistryEntry(
        module_path="agno.models.aws",
        class_name="AwsBedrock",
        packages=("boto3>=1.34",),
        api_key_env="AWS_ACCESS_KEY_ID",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "azure": ProviderRegistryEntry(
        module_path="agno.models.azure",
        class_name="OpenAIChat",
        packages=("openai>=1.0",),
        api_key_env="AZURE_OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "vertex": ProviderRegistryEntry(
        module_path="agno.models.vertexai.claude",
        class_name="Claude",
        packages=("anthropic>=0.40",),
        api_key_env="GOOGLE_APPLICATION_CREDENTIALS",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    # --- Gateway ---
    "openrouter": ProviderRegistryEntry(
        module_path="agno.models.openrouter",
        class_name="OpenRouter",
        packages=("openai>=1.0",),
        api_key_env="OPENROUTER_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "together": ProviderRegistryEntry(
        module_path="agno.models.together",
        class_name="Together",
        packages=("openai>=1.0",),
        api_key_env="TOGETHER_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "groq": ProviderRegistryEntry(
        module_path="agno.models.groq",
        class_name="Groq",
        packages=("groq>=0.11",),
        api_key_env="GROQ_API_KEY",
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "native", True, False, False),
    ),
    "fireworks": ProviderRegistryEntry(
        module_path="agno.models.fireworks",
        class_name="Fireworks",
        packages=("openai>=1.0",),
        api_key_env="FIREWORKS_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "langdb": ProviderRegistryEntry(
        module_path="agno.models.langdb",
        class_name="LangDB",
        packages=("openai>=1.0",),
        api_key_env="LANGDB_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "nebius": ProviderRegistryEntry(
        module_path="agno.models.nebius",
        class_name="Nebius",
        packages=("openai>=1.0",),
        api_key_env="NEBIUS_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "mistral_gateway": ProviderRegistryEntry(
        module_path="agno.models.mistral",
        class_name="MistralChat",
        packages=("mistralai>=1.0",),
        api_key_env="MISTRAL_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
}


# Derivado: único lugar que enumera los provider_ids canónicos. SPEC_14 §3.4
# ModelStringSpec valida contra este frozenset.
SUPPORTED_PROVIDERS: Final[frozenset[str]] = frozenset(PROVIDER_REGISTRY.keys())


# Convenience: lista de provider_ids locales (sin api_key_env). Útil para
# diagnosticar configs que piden api_key en un provider local.
LOCAL_PROVIDERS: Final[frozenset[str]] = frozenset(
    pid for pid, entry in PROVIDER_REGISTRY.items() if entry.api_key_env is None
)


__all__ = [
    "LOCAL_PROVIDERS",
    "PROVIDER_REGISTRY",
    "SUPPORTED_PROVIDERS",
    "ProviderCapabilities",
    "ProviderRegistryEntry",
]
