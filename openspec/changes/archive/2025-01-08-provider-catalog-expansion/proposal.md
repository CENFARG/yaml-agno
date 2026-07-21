---
change: provider-catalog-expansion
spec: SPEC_14
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/dependency-facade        # MODEL_REGISTRY source (shipped, read-only)
---

# Proposal: Provider Catalog Expansion (SPEC_14 slice #1)

## Intent

`MODEL_REGISTRY` (en `src/yaml_agno/di/registries.py`) hoy solo declara 6
providers y arrastra un **bug en producción**: la entrada `mistral` apunta a la
clase `Mistral`, que **no existe** en Agno 2.6.22 (el paquete exporta
`MistralChat`). Cualquier YAML que use `provider: mistral` revienta en runtime
con `AttributeError` al primer `getattr`.

SPEC_14 exige un catálogo de 26 providers con matriz de capabilities
declarativa. Este slice (slice #1, **puramente DATA**) cierra ambas deudas de
una vez: corrige el bug de mistral, arregla el path de vertex (también roto en
el SPEC), expande el registry a los 26 providers verificados contra Agno 2.6.22,
e introduce un `provider_capabilities.py` con la matriz declarativa de §2.2/§2.3
que los slices 2-4 consumirán.

Es **foundacional**: los slices 2 (ModelConfig/Pydantic schema),
3 (ProviderFactory/AgnoModelAdapter) y 4 (Fallback/Capabilities validators)
referencian todos este catálogo. Sin él, no hay `provider_id` contra el cual
validar, enrutar fallbacks, ni construir instancias.

## Why now

- **Bug live en mistral**: no es teórico — está merged en `registries.py:23` y
  fallaría en cualquier despliegue que toque el provider.
- **Vertex path roto en SPEC_14**: `agno.models.vertexai.Claude` no resuelve
  porque `vertexai/__init__.py` está vacío. Hay que usar el submodule
  `agno.models.vertexai.claude.Claude`.
- **Bloquea 3 slices downstream**: el catálogo es el dato compartido. Empezar
  por aquí maximiza paralelismo posterior.

## Scope

### In scope

1. **Expandir `MODEL_REGISTRY`** (en `src/yaml_agno/di/registries.py`) de 6 → 26
   providers. Estructura del tuple sin cambios: `(module_path, class_name, packages)`.
   - Fix `mistral`: `("agno.models.mistral", "MistralChat", ["mistralai>=1.0"])`
     (era `"Mistral"` — **bug**).
   - Fix `vertex`: `("agno.models.vertexai.claude", "Claude", ["anthropic>=0.40"])`
     (SPEC_14 decía `agno.models.vertexai` — `__init__.py` vacío, no resuelve).
   - Agregar los 19 faltantes con paths y nombres de clase verificados:
     `deepseek→DeepSeek`, `perplexity→Perplexity`, `xai→xAI`, `meta→Llama`,
     `dashscope→DashScope`, `vercel→V0`, `ollama→Ollama`, `llamacpp→LlamaCpp`,
     `lm_studio→LMStudio`, `vllm→VLLM`, `bedrock→AwsBedrock` (módulo `agno.models.aws`),
     `azure→AzureOpenAI`, `openrouter→OpenRouter`, `together→Together`,
     `fireworks→Fireworks`, `langdb→LangDB`, `nebius→Nebius`.
   - **Split OpenAI**: agregar `openai_chat` (`OpenAIChat`) y `openai_responses`
     (`OpenAIResponses`). **Mantener `openai` como alias de `openai_chat`** para
     no romper tests YAML existentes (back-compat).
2. **Nuevo archivo** `src/yaml_agno/di/provider_capabilities.py`:
   - `ProviderRegistryEntry` — frozen dataclass con campos:
     `agno_module: str`, `agno_class: str`, `packages: tuple[str, ...]`,
     `api_key_env: str | None`, `capabilities: ProviderCapabilities`.
   - `ProviderCapabilities` — frozen dataclass con `multimodal: bool|list[str]`,
     `structured_output: list[str]`, `tool_use: Literal["native","partial","none"]`,
     `streaming: bool`, `caching: bool`, `reasoning: bool`, `local: bool`.
   - `PROVIDER_REGISTRY: dict[str, ProviderRegistryEntry]` — las 26 entradas
     según SPEC_14 §2.2 (matriz maestra) + §2.3 (capabilities). Los valores de
     capabilities se toman literal de la tabla de §2.2; no se inventan.
3. **Tests** (TDD, en `tests/di/`):
   - Assert que las 26 keys esperadas están presentes (sin `mistral_gateway`,
     que es alias — ver Risks).
   - Assert que cada `(module_path, class_name)` está bien formado
     (regex `^agno\.models\.` + identificador PascalCase no vacío).
   - Assert específico: `mistral` → `MistralChat` (regresión del bug).
   - Assert específico: `vertex` → module path termina en `.claude` (submodule).
   - Assert back-compat: `openai` y `openai_chat` resuelven al mismo `(module, class)`.
   - **Import real** con `importlib.import_module` + `getattr` solo para providers
     cuyas deps estén instaladas en el entorno de test (usar `pytest.importorskip`
     o `skip`). No se exigen las 26 SDKs instaladas. Una minoría (típicamente
     `openai`, más lo que esté en el venv de CI) recibe import real; el resto se
     skipcea con mensaje claro.

### Out of scope

- **Cualquier lógica de resolución**: `AgnoResolver`, `ImportlibDependencyAdapter`,
  allowlist — intactos. Este slice es DATA pura.
- **`ProviderFactory.build`**, `_compose_kwargs`, instanciación de modelos —
  slice #3.
- **`ModelExpandedSpec`**, `ModelStringSpec`, parser `provider:id` — slice #2.
- **`FallbackConfig`**, chain builder, Circuit Breaker, `RetryPolicy`,
  `compute_delay` — slice #4.
- **`CacheManager`, `ModelCapabilitiesValidator` runtime** — slice #4 (este
  slice solo declara los datos de capabilities; no implementa el validador).
- **Cambios en `STORAGE_REGISTRY` ni `WORKFLOW_REGISTRY`** — fuera de SPEC_14.
- **Cualquier cambio en YAML schemas, parsers, ni config loading.**

## Approach

### 1. `MODEL_REGISTRY` — corrección + expansión (DATA)

El dict existente mantiene su tipo (`Final[dict[str, tuple[str, str, list[str]]]]`).
No se cambia la forma del value — solo se corrige `mistral`, se reescribe
`vertex`, y se agregan 19 entradas + 2 (`openai_chat`, `openai_responses`) + se
preserva `openai` como alias.

El alias `openai` se implementa como entrada duplicada apuntando al mismo tuple
que `openai_chat`. Es la opción más simple y la única que no requiere tocar
`AgnoResolver` (que solo hace lookup por key). Alternativa considerada:
normalización post-lookup en el resolver — se descarta porque cruza la frontera
DATA/lógica y metería lógica en un slice puramente DATA.

### 2. `provider_capabilities.py` — nueva DATA declarativa

Archivo hermano de `registries.py` en `src/yaml_agno/di/`. Define dos
dataclasses frozen + el dict `PROVIDER_REGISTRY`. Los datos provienen **únicamente**
de SPEC_14 §2.2 (matriz maestra) y §2.3 (capabilities). No se infiere nada del
código ni se inventan capabilities: si la tabla de §2.2 dice `Perplexity:
structured_output=no`, la entrada lleva `structured_output=[]`.

Esto deja el camino pavimentado para que slice #4 implemente
`ModelCapabilitiesValidator` consultando `PROVIDER_REGISTRY[provider].capabilities`.

### 3. Tests — estrategía de import condicional

El header del archivo de tests declara el set esperado de 26 keys. Luego:

```python
REAL_IMPORT_PROVIDERS = ["openai"]  # ampliar en CI si hay más deps instaladas

@pytest.mark.parametrize("provider", sorted(MODEL_REGISTRY))
def test_module_class_well_formed(provider):
    module, cls, _ = MODEL_REGISTRY[provider]
    assert module.startswith("agno.models.")
    assert cls and cls[0].isupper()

def test_mistral_uses_mistralchat():  # regresión bug
    assert MODEL_REGISTRY["mistral"][1] == "MistralChat"

def test_vertex_uses_submodule():  # regresión path roto
    assert MODEL_REGISTRY["vertex"][0] == "agno.models.vertexai.claude"

def test_openai_alias_backcompat():
    assert MODEL_REGISTRY["openai"] == MODEL_REGISTRY["openai_chat"]

@pytest.mark.parametrize("provider", REAL_IMPORT_PROVIDERS)
def test_real_import_resolves(provider):
    module, cls, _ = MODEL_REGISTRY[provider]
    mod = importlib.import_module(module)
    assert hasattr(mod, cls), f"{cls} not exported by {module}"
```

Los providers con deps opcionales (anthropic, mistral, groq, etc.) **no** se
testeaban con import real en este slice — eso vive en CI con su matrix de deps.

### 4. Convenciones

- **Strict TDD**: RED (test falla porque faltan keys / mistral sigue mal) → GREEN
  (expansión del dict) → REFACTOR (extracción de `provider_capabilities.py`).
- Commit por tarea micro (registries expansion, capabilities module, tests).
- No se añade lógica de resolución. `@ai-directive` del módulo se mantiene.

## Risks

1. **`mistral_gateway` (alias de mistral vía gateway, §2.2 fila 27)**: SPEC_14
   lo lista como fila separada pero es semánticamente un alias de `mistral`. Este
   slice NO lo incluye como key propia en `MODEL_REGISTRY` — `mistral_gateway`
   sería un caso de dispatch de `ProviderFactory` (slice #3) que reutiliza la
   entrada `mistral` con `base_url` override. Si se requiere como key explícita,
   se añade en slice #2 o #3 al definir el parser. **Decisión pendiente**, no
   bloqueante para este slice.
2. **Capabilities son declarativas, no verificadas contra Agno runtime**: si
   Agno 2.6.22 cambió el soporte real de, p.ej., `perplexity.structured_output`,
   la matriz de §2.2 puede estar desactualizada. Este slice confía en SPEC_14
   iter4. Validación empírica de capabilities queda para slice #4 o un audit futuro.
3. **`bedrock` module es `agno.models.aws`** (no `agno.models.bedrock`) — confirmado
   contra `aws/__init__.py:1` que exporta `AwsBedrock`. Riesgo de confusión con
   el nombre lógico del provider. Mitigado por test de well-formedness.
4. **`vertex` requiere `anthropic` package** (no un SDK propio de Vertex) porque
   `vertexai/claude.py:8` importa `Claude as AnthropicClaude` desde
   `agno.models.anthropic`. El campo `packages` lo refleja. Documentado en el
   comentario del dict.
5. **Back-compat del alias `openai`**: si existe código que itera
   `MODEL_REGISTRY.items()` esperando exactamente N providers, ahora verá N+1
   (el alias duplica una entrada). Búsqueda preliminar no encontró dichos
   consumidores; `AgnoResolver` solo hace lookup por key. A confirmar en review.

## Rollback

Revert del commit/PR. Al ser DATA pura (un dict expandido + un archivo nuevo
sin consumers vivos aún), el rollback es limpio y sin migración: los slices 2-4
no existen todavía, nada referencia `PROVIDER_REGISTRY`. El bug de mistral
volvería a estar presente tras rollback — documentar en el PR que rollback
reabre el bug.

## Verification evidence (Agno 2.6.22)

Todas las rutas y nombres de clase fueron verificados leyendo
`agno/models/<provider>/__init__.py` directamente en el source tree
(`C:/Dropbox/DOC.RECA/06-Software/agno/libs/agno/agno/models/`):

- `mistral/__init__.py:1` → `from agno.models.mistral.mistral import MistralChat`
  (exporta `MistralChat`, **NO** `Mistral`).
- `vertexai/__init__.py` → **vacío** (0 exports). Submodule `vertexai/claude.py`
  define `Claude` heredando de `agno.models.anthropic.Claude`.
- `deepseek/__init__.py:1` → `DeepSeek`.
- `xai/__init__.py:1` → `xAI`.
- `aws/__init__.py:1` → `AwsBedrock` (módulo `agno.models.aws`, no `bedrock`).
- `vercel/__init__.py:1` → `V0`.
- `vllm/__init__.py:1` → `VLLM`.
- `lmstudio/__init__.py:1` → `LMStudio`.
- `llama_cpp/__init__.py:1` → `LlamaCpp`.
- `meta/__init__.py:1` → `Llama`.
- `openai/__init__.py:1-4` → exporta `OpenAIChat` y `OpenAIResponses` del mismo
  paquete (split válido).
