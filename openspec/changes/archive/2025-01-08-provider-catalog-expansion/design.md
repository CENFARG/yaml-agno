---
change: provider-catalog-expansion
slice: SPEC_14 #1
artifact: design
status: ready
depends_on:
  - sdd/model-resilience/explore (engram project=doc.reca)
  - src/yaml_agno/di/registries.py (shipped)
---

# Design: provider-catalog-expansion

> Technical design for SPEC_14 slice #1 — expand the Agno provider catalog from
> 6 to 26 providers and add a capability map, **as pure DATA**. No resolution
> logic, no instance construction. Slice #2 (ModelConfig schema) consumes this.

## Technical Approach

Two parallel declarative catalogs in the DI layer, both `Final`-typed module
constants matching the style of the shipped `registries.py`:

1. **`MODEL_REGISTRY` (expand, 6 → 26 + 1 alias)** — the existing
   `Final[dict[str, tuple[str, str, list[str]]]]` keyed by logical provider id
   (SPEC_14 §2.2 `provider_id`). It stays a 3-tuple `(module_path, class_name,
   packages)` because `AgnoResolver` / `ImportlibDependencyAdapter` already
   consume that shape — changing it would break the resolver contract. Two bugs
   baked in: `mistral` → `MistralChat` (was `Mistral`) and `vertex` →
   `agno.models.vertexai.claude.Claude` (parent `__init__.py` is empty). The
   legacy `openai` key becomes an alias resolved via a separate resolution map
   (Decision A2) instead of duplicating the tuple.

2. **`PROVIDER_REGISTRY` (new)** — a richer `Final[dict[str,
   ProviderRegistryEntry]]` keyed by the same 26 ids. This carries the
   per-provider metadata SPEC_14 §2.2/§2.3 needs but the 3-tuple cannot hold:
   `module_path`, `class_name`, `packages` (mirrors `MODEL_REGISTRY` for
   single-source access), `api_key_env` (or `None` for local providers), and a
   frozen `ProviderCapabilities` value object. Downstream slices (capabilities
   validator, ModelConfig schema, ProviderResolver) read THIS map, not the
   tuple dict.

Both maps are **declared, not runtime-verified**: cells reflect what Agno 2.6.22
claims to support (class exists + import is wired), not what an integration test
proved against a live API (explore risk; flagged in the `ProviderCapabilities`
docstring). A future "runtime verification" slice can promote a cell to
"verified" by adding a field — not by editing the dict.

```text
  yaml model              SPEC_14 slices #2/#3
     │                           │
     ▼                           ▼
  ModelConfig ──► ProviderResolver ──► SUPPORTED_PROVIDERS ──┐
                            │                                │
                            ├──► MODEL_REGISTRY (3-tuple) ───┤  AgnoResolver
                            │      consumed by Importlib-     │  (already shipped)
                            │      DependencyAdapter          │
                            │                                │
                            └──► PROVIDER_REGISTRY ──────────┤
                                  (rich entry: api_key_env,  │
                                   ProviderCapabilities)     │
                                  consumed by validator,     │
                                   ModelFactory (slice #3)   ▼
```

## Architecture Decisions

### Decision A1 — `MODEL_REGISTRY` stays a 3-tuple dict (do not break the resolver contract)

| Option | Tradeoff | Decision |
|---|---|---|
| Keep `Final[dict[str, tuple[str,str,list[str]]]]`, only add rows | Backward-compatible, `AgnoResolver`/`ImportlibDependencyAdapter` unchanged, zero risk | **CHOSEN** |
| Replace 3-tuple with `ProviderRegistryEntry` everywhere | Forces `agno_resolver.py` + `importlib_dependency_adapter` changes + cascading test churn in a slice labelled "pure DATA" | Rejected — out of slice scope |
| Add a parallel richer map + keep the 3-tuple | Two sources of truth for (module, class, packages) | Accepted with rule: see A3 |

**Rationale**: slice #1 is explicitly "pure DATA, no logic" (~150 lines). The
`MODEL_REGISTRY` 3-tuple is consumed today by
`ImportlibDependencyAdapter.resolve_class` (verified
`importlib_dependency_adapter.py:88` + `AGNO_ALLOWLIST_PREFIXES` prefix-match).
Changing its shape would drag resolver + adapter + their tests into this slice,
blowing the 400-line review budget and breaking the slice boundary. We keep the
tuple, add 20 rows, fix the 2 known bugs.

### Decision A2 — `openai` back-compat via duplicate tuple + alias dict (REVISED during apply)

> **Revision (verify W2)**: the original design chose alias-only. During apply
> this was changed to **duplicate the tuple AND keep the alias dict** — simpler
> back-compat (raw `MODEL_REGISTRY["openai"]` lookups keep working without every
> consumer being alias-aware) at the cost of a drift risk mitigated by a test
> that asserts `MODEL_REGISTRY["openai"] == MODEL_REGISTRY["openai_chat"]`.

| Option | Tradeoff | Decision |
|---|---|---|
| Duplicate the tuple: `"openai": (...)` AND `"openai_chat": ...` + `PROVIDER_ALIASES = {"openai": "openai_chat"}` | Two rows, drift risk (mitigated by equality test); but raw lookups + alias-aware resolution both work; zero consumer breakage | **CHOSEN (revised)** |
| Separate alias dict only (no direct key) | Single canonical id, alias explicit; but breaks any raw `MODEL_REGISTRY["openai"]` lookup unless every consumer is alias-aware | Original design, superseded |
| Make `openai` the canonical id and rename `openai_chat` | Breaks SPEC_14 which uses `openai_chat`/`openai_responses` as the two real ids | Rejected |

**Rationale**: SPEC_14 §2.2 lists `openai_chat` and `openai_responses` as the
two real ids (two distinct Agno classes, `OpenAIChat` vs `OpenAIResponses`).
The legacy `"openai"` key in the shipped registry is a shorthand users typed
before SPEC_14 landed. Keeping it as a resolution alias — `"openai" →
"openai_chat"` — preserves back-compat without duplicating a tuple and without
inventing a fake third class. The alias dict lives in `registries.py` next to
`MODEL_REGISTRY` so a future `ProviderResolver` (slice #2) resolves aliases
before touching either catalog.

### Decision A3 — `ProviderRegistryEntry` is a frozen dataclass (not TypedDict)

| Option | Tradeoff | Decision |
|---|---|---|
| `TypedDict` | Cheap, structural, JSON-friendly | Rejected |
| Frozen `@dataclass(frozen=True, slots=True)` | Immutable at runtime (hashable, safe to share), lets us attach `@property`/methods later without API break, slots gives lower memory for 26 instances | **CHOSEN** |
| Plain `class` with `__init__` | Verbose, no `frozen` guarantee | Rejected |

**Rationale**: SPEC_14 §6.4 (line 1131-1132) already asserts `entry.api_key_env
is None or isinstance(entry.api_key_env, str)` and `hasattr(entry.capabilities,
"structured_output")` — i.e. the design expects attribute access on a typed
object, not dict indexing. A frozen dataclass gives immutability (these are
`Final` module constants; nothing should mutate them), `slots=True` keeps the
26 instances lean, and dataclass semantics leave the door open to add
`@property` helpers (`is_local`, `requires_api_key`) in slice #2 without
breaking the constructor signature. `TypedDict` would lock us into dict shape
and force a rewrite later.

### Decision A4 — Capabilities fields + "declared, not verified" flagging

Fields on `ProviderCapabilities` (frozen dataclass), populated from SPEC_14
§2.2 + §2.3:

| Field | Type | Meaning | Source |
|---|---|---|---|
| `multimodal` | `tuple[str, ...]` | Modalities declared (e.g. `("image","audio")`); empty tuple = text-only | §2.2 "Multimodal" col (yes/partial/no → `("image",)` / `()` for no) |
| `structured_output` | `tuple[str, ...]` | Modes supported from `{"json_mode","strict","response_model"}`; empty = none (Perplexity) | §2.3 yaml + §2.2 "Structured" col |
| `tool_use` | `Literal["native","partial","none"]` | Native / partial / no tool calling | §2.2 "Native tool use" col |
| `streaming` | `bool` | Provider streams tokens | §2.3 yaml (default True for all native/cloud/gateway) |
| `caching` | `bool` | Supports Agno `cache_response` | §2.3 yaml + explore #4 (base.py cache fields confirmed) |
| `reasoning` | `bool` | Supports `reasoning_effort`/`thinking` | §2.3 yaml |

**Flagging "declared, not runtime-verified"**: a single docstring note on
`ProviderCapabilities`, NOT a per-cell boolean. The explore explicitly flagged
this risk: cells are "declared by Agno 2.6.22 class API surface", not "an
integration test hit the live API and proved it". Adding a verified/unverified
bit per cell would multiply the data 6x for zero downstream value in this
slice — the capabilities validator (slice #4) reads booleans/tuples, not
provenance. If a provider misbehaves at runtime, that's slice #4's problem
(runtime probe / capability override in YAML), not this catalog's. The
docstring makes the contract loud: callers MUST NOT treat these as guarantees.

### Decision A5 — Package versions match Agno's own pinning, not invented

The `packages` list in each entry mirrors what `agno==2.6.22`'s own
`pyproject.toml` declares as optional extras (best-effort lower bound). Where
Agno does not pin a version (e.g. `mistralai`, `groq`), we use `>=X.0` with the
lowest major the SDK requires. yaml-agno's `pyproject.toml` does NOT add these
to its own `dependencies` — they remain optional, installed by the user who
wants that provider. Tests use `pytest.importorskip` so a missing optional dep
skips the test rather than fails the suite (see Testing Strategy).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/di/registries.py` | Modify | Expand `MODEL_REGISTRY` 6→26 entries; fix `mistral`→`MistralChat` and `vertex`→`agno.models.vertexai.claude.Claude`; add `PROVIDER_ALIASES = {"openai": "openai_chat"}`; export it. No signature/shape change. |
| `src/yaml_agno/di/provider_capabilities.py` | Create | `ProviderCapabilities` + `ProviderRegistryEntry` frozen dataclasses; `PROVIDER_REGISTRY: Final[dict[str, ProviderRegistryEntry]]` (26 entries); `SUPPORTED_PROVIDERS: Final[frozenset[str]]` derived from `PROVIDER_REGISTRY`. |
| `tests/unit/di/test_registries.py` | Create | RED→GREEN: 26 keys present, mistral/vertex bug-fixes, alias resolves, every module_path under `AGNO_ALLOWLIST_PREFIXES`. |
| `tests/unit/di/test_provider_capabilities.py` | Create | RED→GREEN: `ProviderRegistryEntry` frozen+slots, 26 entries keyed identically to `MODEL_REGISTRY`, api_key_env for each local provider is `None`, `SUPPORTED_PROVIDERS` length 26. |

## Interfaces / Contracts

### `src/yaml_agno/di/registries.py` — expanded `MODEL_REGISTRY` + alias

```python
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
# 26 providers verificados contra Agno 2.6.22 (cada __init__.py confirmado).
# NOTA: "openai" es una entrada directa DUPLICADA de "openai_chat" (back-compat,
# ver Decision A2 revisada) Y un alias en PROVIDER_ALIASES. "openai_chat" y
# "openai_responses" son los
# dos ids canónicos de SPEC_14 §2.2.
MODEL_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    # --- Native ---
    "anthropic":        ("agno.models.anthropic",      "Claude",         ["anthropic>=0.40"]),
    "openai_chat":      ("agno.models.openai",         "OpenAIChat",     ["openai>=1.0"]),
    "openai_responses": ("agno.models.openai",         "OpenAIResponses", ["openai>=1.0"]),
    "google":           ("agno.models.google",         "Gemini",         ["google-genai>=1.0"]),
    "mistral":          ("agno.models.mistral",        "MistralChat",    ["mistralai>=1.0"]),  # FIX: era "Mistral" (no existe)
    "deepseek":         ("agno.models.deepseek",       "DeepSeek",       ["openai>=1.0"]),
    "cohere":           ("agno.models.cohere",         "Cohere",         ["cohere>=5.0"]),
    "perplexity":       ("agno.models.perplexity",     "Perplexity",     ["openai>=1.0"]),
    "xai":              ("agno.models.xai",            "xAI",            ["openai>=1.0"]),
    "meta":             ("agno.models.meta",           "Llama",          ["openai>=1.0"]),
    "dashscope":        ("agno.models.dashscope",      "DashScope",      ["openai>=1.0"]),
    "vercel":           ("agno.models.vercel",         "V0",             ["openai>=1.0"]),
    # --- Local (sin api_key_env) ---
    "ollama":           ("agno.models.ollama",         "Ollama",         ["ollama>=0.3"]),
    "llamacpp":         ("agno.models.llama_cpp",      "LlamaCpp",       ["llama-cpp-python>=0.3"]),
    "lm_studio":        ("agno.models.lmstudio",       "LMStudio",       ["openai>=1.0"]),
    "vllm":             ("agno.models.vllm",           "VLLM",           ["vllm>=0.6"]),
    # --- Cloud ---
    "bedrock":          ("agno.models.aws",            "AwsBedrock",     ["boto3>=1.34"]),
    "azure":            ("agno.models.azure",          "OpenAIChat",     ["openai>=1.0"]),  # azure/openai_chat.py exporta OpenAIChat (AzureOpenAI deprecated)
    "vertex":           ("agno.models.vertexai.claude", "Claude",        ["anthropic>=0.40"]),  # FIX: vertexai/__init__.py es vacío
    # --- Gateway ---
    "openrouter":       ("agno.models.openrouter",     "OpenRouter",     ["openai>=1.0"]),
    "together":         ("agno.models.together",       "Together",       ["openai>=1.0"]),
    "groq":             ("agno.models.groq",           "Groq",           ["groq>=0.11"]),
    "fireworks":        ("agno.models.fireworks",      "Fireworks",      ["openai>=1.0"]),
    "langdb":           ("agno.models.langdb",         "LangDB",         ["openai>=1.0"]),
    "nebius":           ("agno.models.nebius",         "Nebius",         ["openai>=1.0"]),
    "mistral_gateway":  ("agno.models.mistral",        "MistralChat",    ["mistralai>=1.0"]),  # alias vía gateway
}

# Alias de compatibilidad: "openai" (legacy) → "openai_chat" (canonical SPEC_14).
# ProviderResolver (slice #2) aplica esto ANTES de indexar MODEL_REGISTRY /
# PROVIDER_REGISTRY. Mantiene back-compat con configs que usan provider: "openai".
PROVIDER_ALIASES: Final[dict[str, str]] = {
    "openai": "openai_chat",
}

# Storage providers. (sin cambios en este slice)
STORAGE_REGISTRY: Final[dict[str, tuple[str, str, list[str]]]] = {
    "memory": ("agno.db.in_memory", "InMemoryDb", []),
    "sqlite": ("agno.db.sqlite", "SqliteDb", ["sqlalchemy>=2.0"]),
    "postgres": ("agno.db.postgres", "PostgresDb", ["sqlalchemy>=2.0", "psycopg[binary]>=3.0"]),
    "redis": ("agno.db.redis", "RedisDb", ["redis>=5.0"]),
}

WORKFLOW_REGISTRY: Final[dict[str, tuple[str, str]]] = {
    "Step": ("agno.workflow", "Step"),
    "Parallel": ("agno.workflow", "Parallel"),
    "Condition": ("agno.workflow", "Condition"),
    "Router": ("agno.workflow", "Router"),
    "Loop": ("agno.workflow", "Loop"),
    "Workflow": ("agno.workflow", "Workflow"),
}

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
```

> `azure` mapping note: `agno/models/azure/openai_chat.py` exports `OpenAIChat`
> (verified dir listing) — `AzureOpenAI` was removed from Agno's public surface.
> `deepseek`/`perplexity`/`xai`/`meta`/`dashscope`/`vercel`/`openrouter`/
> `together`/`fireworks`/`langdb`/`nebius` all subclass `OpenAILike` /
> `OpenAIChat` internally, so `openai>=1.0` is their only hard runtime dep
> (Agno pins the same).

### `src/yaml_agno/di/provider_capabilities.py` — NEW

```python
"""Catálogo de capabilities por provider — DATA pura.

Extiende ``registries.py`` con metadata que el 3-tuple no puede llevar:
``api_key_env`` (None para providers locales) y ``ProviderCapabilities``.

Contrato (SPEC_14 §2.2 / §2.3):
    - Cada entrada está indexada por el mismo ``provider_id`` que
      ``MODEL_REGISTRY`` (26 claves idénticas).
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

from dataclasses import dataclass, field
from typing import Final, Literal

from yaml_agno.di.registries import MODEL_REGISTRY, PROVIDER_ALIASES


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
        caching: ``True`` si acepta ``cache_response`` (Agno base.py:168).
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


# 26 entradas, una por key de MODEL_REGISTRY. api_key_env desde SPEC_14 §2.2,
# capabilities desde §2.2 columnas + §2.3 yaml.
PROVIDER_REGISTRY: Final[dict[str, ProviderRegistryEntry]] = {
    # --- Native ---
    "anthropic": ProviderRegistryEntry(
        module_path="agno.models.anthropic", class_name="Claude",
        packages=("anthropic>=0.40",), api_key_env="ANTHROPIC_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "openai_chat": ProviderRegistryEntry(
        module_path="agno.models.openai", class_name="OpenAIChat",
        packages=("openai>=1.0",), api_key_env="OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "openai_responses": ProviderRegistryEntry(
        module_path="agno.models.openai", class_name="OpenAIResponses",
        packages=("openai>=1.0",), api_key_env="OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "google": ProviderRegistryEntry(
        module_path="agno.models.google", class_name="Gemini",
        packages=("google-genai>=1.0",), api_key_env="GOOGLE_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "mistral": ProviderRegistryEntry(
        module_path="agno.models.mistral", class_name="MistralChat",
        packages=("mistralai>=1.0",), api_key_env="MISTRAL_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "deepseek": ProviderRegistryEntry(
        module_path="agno.models.deepseek", class_name="DeepSeek",
        packages=("openai>=1.0",), api_key_env="DEEPSEEK_API_KEY",
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "native", True, False, True),
    ),
    "cohere": ProviderRegistryEntry(
        module_path="agno.models.cohere", class_name="Cohere",
        packages=("cohere>=5.0",), api_key_env="COHERE_API_KEY",
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "partial", True, False, False),
    ),
    "perplexity": ProviderRegistryEntry(
        module_path="agno.models.perplexity", class_name="Perplexity",
        packages=("openai>=1.0",), api_key_env="PERPLEXITY_API_KEY",
        capabilities=ProviderCapabilities((), _NO_STRUCT, "none", True, False, False),
    ),
    "xai": ProviderRegistryEntry(
        module_path="agno.models.xai", class_name="xAI",
        packages=("openai>=1.0",), api_key_env="XAI_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, True),
    ),
    "meta": ProviderRegistryEntry(
        module_path="agno.models.meta", class_name="Llama",
        packages=("openai>=1.0",), api_key_env="META_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "dashscope": ProviderRegistryEntry(
        module_path="agno.models.dashscope", class_name="DashScope",
        packages=("openai>=1.0",), api_key_env="DASHSCOPE_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "vercel": ProviderRegistryEntry(
        module_path="agno.models.vercel", class_name="V0",
        packages=("openai>=1.0",), api_key_env="VERCEL_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    # --- Local (api_key_env = None) ---
    "ollama": ProviderRegistryEntry(
        module_path="agno.models.ollama", class_name="Ollama",
        packages=("ollama>=0.3",), api_key_env=None,
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "llamacpp": ProviderRegistryEntry(
        module_path="agno.models.llama_cpp", class_name="LlamaCpp",
        packages=("llama-cpp-python>=0.3",), api_key_env=None,
        capabilities=ProviderCapabilities((), _RM_STRUCT, "partial", True, False, False),
    ),
    "lm_studio": ProviderRegistryEntry(
        module_path="agno.models.lmstudio", class_name="LMStudio",
        packages=("openai>=1.0",), api_key_env=None,
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "native", True, False, False),
    ),
    "vllm": ProviderRegistryEntry(
        module_path="agno.models.vllm", class_name="VLLM",
        packages=("vllm>=0.6",), api_key_env=None,
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    # --- Cloud ---
    "bedrock": ProviderRegistryEntry(
        module_path="agno.models.aws", class_name="AwsBedrock",
        packages=("boto3>=1.34",), api_key_env="AWS_ACCESS_KEY_ID",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "azure": ProviderRegistryEntry(
        module_path="agno.models.azure", class_name="OpenAIChat",
        packages=("openai>=1.0",), api_key_env="AZURE_OPENAI_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    "vertex": ProviderRegistryEntry(
        module_path="agno.models.vertexai.claude", class_name="Claude",
        packages=("anthropic>=0.40",), api_key_env="GOOGLE_APPLICATION_CREDENTIALS",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, True, True),
    ),
    # --- Gateway ---
    "openrouter": ProviderRegistryEntry(
        module_path="agno.models.openrouter", class_name="OpenRouter",
        packages=("openai>=1.0",), api_key_env="OPENROUTER_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "together": ProviderRegistryEntry(
        module_path="agno.models.together", class_name="Together",
        packages=("openai>=1.0",), api_key_env="TOGETHER_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "groq": ProviderRegistryEntry(
        module_path="agno.models.groq", class_name="Groq",
        packages=("groq>=0.11",), api_key_env="GROQ_API_KEY",
        capabilities=ProviderCapabilities((), _FULL_STRUCT, "native", True, False, False),
    ),
    "fireworks": ProviderRegistryEntry(
        module_path="agno.models.fireworks", class_name="Fireworks",
        packages=("openai>=1.0",), api_key_env="FIREWORKS_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "langdb": ProviderRegistryEntry(
        module_path="agno.models.langdb", class_name="LangDB",
        packages=("openai>=1.0",), api_key_env="LANGDB_API_KEY",
        capabilities=ProviderCapabilities(_FULL_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "nebius": ProviderRegistryEntry(
        module_path="agno.models.nebius", class_name="Nebius",
        packages=("openai>=1.0",), api_key_env="NEBIUS_API_KEY",
        capabilities=ProviderCapabilities(_IMG_MM, _FULL_STRUCT, "native", True, False, False),
    ),
    "mistral_gateway": ProviderRegistryEntry(
        module_path="agno.models.mistral", class_name="MistralChat",
        packages=("mistralai>=1.0",), api_key_env="MISTRAL_API_KEY",
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
    "PROVIDER_ALIASES",  # re-exported para conveniencia del consumidor
    "PROVIDER_REGISTRY",
    "ProviderCapabilities",
    "ProviderRegistryEntry",
    "SUPPORTED_PROVIDERS",
]
```

## Data Flow

```text
  YAML "model: openai:gpt-4o"        (legacy shorthand)
          │
          ▼
  ProviderResolver (slice #2)
          │  1. PROVIDER_ALIASES["openai"]  →  "openai_chat"
          │  2. assert "openai_chat" in SUPPORTED_PROVIDERS     ✓
          │  3. MODEL_REGISTRY["openai_chat"]  → ("agno.models.openai",
          │                                       "OpenAIChat", [...])
          │  4. PROVIDER_REGISTRY["openai_chat"].api_key_env   → "OPENAI_API_KEY"
          │  5. PROVIDER_REGISTRY["openai_chat"].capabilities   → ProviderCapabilities(
          │                                                          multimodal=("image","audio"), ...)
          ▼
  AgnoResolver.resolve_class("agno.models.openai", "OpenAIChat")
          │  ImportlibDependencyAdapter._is_allowlisted("agno.models.openai")
          │    → "agno.models." in AGNO_ALLOWLIST_PREFIXES   ✓
          ▼
  OpenAIChat instance (via ModelFactory slice #3)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `MODEL_REGISTRY` has exactly 26 keys; mistral maps to `MistralChat`; vertex module_path is `agno.models.vertexai.claude`; every module_path starts with a prefix in `AGNO_ALLOWLIST_PREFIXES` (prefix-match guard); `PROVIDER_ALIASES["openai"] == "openai_chat"`; alias target is a real key in `MODEL_REGISTRY`. | Plain assertions on the dict literal. No Agno import needed (just the module constants). Tag `@pytest.mark.unit`. |
| Unit | `ProviderRegistryEntry` is frozen (`frozen=True`) — `dataclasses.replace` works but attribute assignment raises `FrozenInstanceError`; has `slots=True` — `__dict__` attr absent. `PROVIDER_REGISTRY` has the same 26 keys as `MODEL_REGISTRY` (`set(PROVIDER_REGISTRY) == set(MODEL_REGISTRY)`). Every local provider (`ollama, llamacpp, lm_studio, vllm`) has `api_key_env is None`; every other provider has a non-empty `api_key_env`. `SUPPORTED_PROVIDERS == frozenset(PROVIDER_REGISTRY)`. `LOCAL_PROVIDERS == {"ollama","llamacpp","lm_studio","vllm"}`. | `@pytest.mark.unit`, no network. |
| Unit (optional-dep aware) | For 2-3 representative providers (anthropic, google, mistral), the declared Agno class IS importable when its optional dep is present. | `pytest.importorskip("anthropic")` then `importlib.import_module(entry.module_path)` + `getattr(mod, entry.class_name)`. Skips cleanly if the dep is missing — never fails the suite on optional deps. |
| Integration | Deferred to slice #3 (ProviderFactory). This slice ships NO instance construction. | N/A in this slice. |

### TDD Approach (Strict TDD Mode — config.yaml `tdd: true`)

Each behavior task in `tasks.md` starts with a RED test that fails for a
concrete, named reason:

1. **RED**: `test_model_registry_has_26_providers` → `assert len(MODEL_REGISTRY) == 26` fails (today 6). **GREEN**: add the 20 missing entries. **REFACTOR**: group by family with comments.
2. **RED**: `test_mistral_maps_to_mistral_chat_not_mistral` → `assert MODEL_REGISTRY["mistral"][1] == "MistralChat"` fails (today "Mistral"). **GREEN**: fix the entry.
3. **RED**: `test_vertex_uses_submodule_not_empty_parent` → `assert MODEL_REGISTRY["vertex"][0] == "agno.models.vertexai.claude"` fails (not present). **GREEN**: add entry with the submodule path.
4. **RED**: `test_all_module_paths_under_allowlist` → iterate every `module_path`, assert `any(module_path.startswith(p) for p in AGNO_ALLOWLIST_PREFIXES)`. Already true today, but locks the invariant for the 20 new entries.
5. **RED**: `test_openai_alias_resolves_to_openai_chat` → `assert PROVIDER_ALIASES["openai"] == "openai_chat"` fails (no such symbol). **GREEN**: add the alias dict + export.
6. **RED**: `test_provider_registry_entry_is_frozen` → `entry.capabilities = ...` must raise `FrozenInstanceError`. **GREEN**: `@dataclass(frozen=True, slots=True)`.
7. **RED**: `test_provider_registry_keys_match_model_registry` → `assert set(PROVIDER_REGISTRY) == set(MODEL_REGISTRY)`. **GREEN**: populate 26 entries.
8. **RED**: `test_local_providers_have_no_api_key_env` → ollama/llamacpp/lm_studio/vllm `api_key_env is None`. **GREEN**: populate correctly.
9. **RED**: `test_supported_providers_derived_from_registry` → `assert SUPPORTED_PROVIDERS == frozenset(PROVIDER_REGISTRY)`. **GREEN**: derive, don't hardcode.
10. **RED** (optional-dep guarded): `test_anthropic_class_importable_when_dep_present` → `pytest.importorskip("anthropic")` then import + getattr. **GREEN**: nothing to do if entry is correct; if RED, fix `module_path`/`class_name`.

Test command: `python -m pytest tests/unit/di/ -m unit` (Strict TDD; coverage
target 100% on the two new/modified modules).

## Verification

- `python -m pytest tests/unit/di/test_registries.py tests/unit/di/test_provider_capabilities.py -v` → all GREEN.
- `python -m pytest tests/` → full suite still GREEN (no regressions; the 6 existing keys are unchanged in shape, only `mistral` got a class-name fix and `openai` moved from a direct key to an alias — this MAY break a test that does `MODEL_REGISTRY["openai"]` directly; grep first).
- `ruff check src/yaml_agno/di/` and `mypy src/yaml_agno/di/` clean.
- Manual: `python -c "from yaml_agno.di.provider_capabilities import SUPPORTED_PROVIDERS; assert len(SUPPORTED_PROVIDERS) == 26; print(sorted(SUPPORTED_PROVIDERS))"`.

## Rollback

Revert is mechanical — this slice adds DATA, no logic. Two commits make rollback
clean:

1. **Commit A** (`registries.py`): expand `MODEL_REGISTRY` + add
   `PROVIDER_ALIASES`. Revert = `git revert <sha>`; the 6 old keys are
   untouched (except `mistral` class-name fix and removal of direct `openai`
   key, which the alias restores at resolution time). If any consumer breaks on
   `MODEL_REGISTRY["openai"]` direct access, hot-patch: keep the old `"openai"`
   tuple entry too (costs one duplicate row) and remove the alias.
2. **Commit B** (`provider_capabilities.py` + tests): new module, zero imports
   into existing code in this slice. Revert = `git rm` the file + its tests.

No data migration, no feature flag, no DB change. Pure additive.

## Open Questions

- [ ] `mistral_gateway` vs `mistral`: SPEC_14 §2.2 lists both as separate rows
      with the same `MISTAL_API_KEY`. Today we model them as two distinct
      `provider_id`s pointing at the same `(module, class)`. If slice #2's
      `ProviderResolver` needs to distinguish "via gateway" from "native" at
      resolution time (e.g. different base URL), that's a slice #2 concern —
      this catalog only carries the id + class.
- [ ] `vertex` `api_key_env`: SPEC_14 §2.2 says "GCP service account JSON". We
      use `GOOGLE_APPLICATION_CREDENTIALS` (the gcloud SDK default). If the
      team prefers a custom `VERTEX_SA_JSON` env var, swap one literal.
- [ ] Capabilities provenance: today every cell is "declared". If slice #4
      (capabilities validator) needs "verified vs declared" granularity, we add
      a `verified: bool` field to `ProviderCapabilities` later — backward
      compatible (frozen dataclass + default `False`).
