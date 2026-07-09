# Delta for Provider Catalog Expansion

> Progenitor: `openspec/specs/dependency-facade/spec.md` (gobierna `MODEL_REGISTRY`
> y `resolve_model`). Este delta expande el catálogo de 6 a 26 providers, corrige
> dos bugs de mapping verificados contra Agno 2.6.22, preserva el alias
> back-compat `openai`, e introduce un `PROVIDER_REGISTRY` enriquecido con
> capacidades declarativas. Source of truth: SPEC_14 §2.2 + §2.3 y exploración
> `sdd/model-resilience/explore` (Agno 2.6.22 re-verificado).

## ADDED Requirements

### Requirement: PROVIDER_REGISTRY enriquecido con capacidades

El módulo `yaml_agno.di.registries` DEBE exponer un `PROVIDER_REGISTRY`
(`Final[dict[str, ProviderRegistryEntry]]`) donde cada `provider_id` del
catálogo de 26 entradas tiene una entrada con los campos `agno_module: str`,
`agno_class: str`, `packages: list[str]`, `api_key_env: str | None` y
`capabilities: ProviderCapabilities`. Los providers locales (`ollama`,
`llamacpp`, `lm_studio`, `vllm`) DEBEN tener `api_key_env = None`. Cada entrada
DEBE ser inmutable tras construcción. El struct `ProviderCapabilities` DEBE
exponer los booleanos `multimodal`, `structured`, `tool_use`, `streaming`,
`caching` y `reasoning`.

#### Scenario: cada provider del catálogo tiene entrada completa

- GIVEN el `PROVIDER_REGISTRY` cargado
- WHEN se itera sobre las 26 claves esperadas
- THEN cada entrada tiene `agno_module`, `agno_class`, `packages`, `api_key_env` y `capabilities` no nulos (salvo `api_key_env=None` para locales)

#### Scenario: ProviderCapabilities es un struct de booleanos bien formado

- GIVEN una entrada cualquiera de `PROVIDER_REGISTRY`
- WHEN se inspecciona `entry.capabilities`
- THEN posee los seis campos booleanos `multimodal`, `structured`, `tool_use`, `streaming`, `caching`, `reasoning`
- AND cada uno es estrictamente `bool` (no `None` ni `int`)

### Requirement: providers locales sin API key

Los providers locales (`ollama`, `llamacpp`, `lm_studio`, `vllm`) DEBEN declarar
`api_key_env = None` en `PROVIDER_REGISTRY`. Cualquier otro provider DEBE
declarar un nombre de variable de entorno no vacío (ej. `ANTHROPIC_API_KEY`).

#### Scenario: provider local no requiere API key

- GIVEN `PROVIDER_REGISTRY["ollama"]`
- WHEN se lee `entry.api_key_env`
- THEN el valor es `None`

#### Scenario: provider cloud declara env var

- GIVEN `PROVIDER_REGISTRY["anthropic"]`
- WHEN se lee `entry.api_key_env`
- THEN el valor es la cadena no vacía `"ANTHROPIC_API_KEY"`

## MODIFIED Requirements

### Requirement: resolve_model con sintaxis provider:id

(Previously: `resolve_model(spec)` resolvía 6 providers (`openai`, `anthropic`,
`google`, `groq`, `mistral`, `cohere`) contra `MODEL_REGISTRY` con tuplas
`(module, class, packages)`. El alias `openai` apuntaba directamente a
`OpenAIChat`; `mistral` apuntaba a una clase inexistente `Mistral`.)

`resolve_model(spec)` DEBE aceptar el formato `"provider:id"`, partir en
`(provider, model_id)`, buscar el target en `MODEL_REGISTRY`, resolver la clase
vía el adapter e instanciarla con `id=model_id`. El `MODEL_REGISTRY` expandido
DEBE contener exactamente las 26 claves listadas en SPEC_14 §2.2:
`anthropic`, `openai`, `openai_chat`, `openai_responses`, `google`, `mistral`,
`deepseek`, `cohere`, `perplexity`, `xai`, `meta`, `dashscope`, `vercel`,
`ollama`, `llamacpp`, `lm_studio`, `vllm`, `bedrock`, `azure`, `vertex`,
`openrouter`, `together`, `groq`, `fireworks`, `langdb`, `nebius`. Un provider
ausente DEBE lanzar `KeyError` con mensaje accionable.

#### Scenario: las 26 claves del catálogo están presentes

- GIVEN el `MODEL_REGISTRY` cargado
- WHEN se compara `set(MODEL_REGISTRY.keys())` contra el conjunto esperado de 26 claves
- THEN los conjuntos son iguales (ni claves faltantes ni sobrantes)

#### Scenario: provider desconocido rechazado

- GIVEN un provider no presente en `MODEL_REGISTRY`
- WHEN `resolve_model("desconocido:foo")`
- THEN lanza `KeyError` con el nombre del provider en el mensaje

### Requirement: mapping de mistral apunta a MistralChat

El `MODEL_REGISTRY["mistral"]` y `PROVIDER_REGISTRY["mistral"]` DEBEN mapear a
`("agno.models.mistral", "MistralChat")`. El mapping anterior `("agno.models.mistral", "Mistral")`
es un BUG: el paquete Agno 2.6.22 exporta `MistralChat` (verificado
`agno/models/mistral/__init__.py`), no `Mistral`; `getattr(module, "Mistral")`
lanzaría `AttributeError` en runtime.

#### Scenario: resolve_model("mistral:mistral-large") instancia MistralChat

- GIVEN el adapter con `agno.models.` allowlisted y la dependencia `mistralai` instalada
- WHEN `resolve_model("mistral:mistral-large-latest")`
- THEN retorna una instancia de `MistralChat` con `id == "mistral-large-latest"`

#### Scenario: la clase Mistral (sin Chat) NO existe en el mapping

- GIVEN el `MODEL_REGISTRY["mistral"]`
- WHEN se inspecciona la tupla
- THEN el `class_name` es `"MistralChat"` y NO `"Mistral"`

### Requirement: mapping de vertex usa el submodule claude

El `MODEL_REGISTRY["vertex"]` y `PROVIDER_REGISTRY["vertex"]` DEBEN mapear a
`("agno.models.vertexai.claude", "Claude")`. El path previo
`("agno.models.vertexai", "Claude")` es un BUG: `agno/models/vertexai/__init__.py`
está VACÍO en Agno 2.6.22 (verificado), por lo que `importlib` sí importa el
paquete pero `getattr(module, "Claude")` fallaría. La subclase `Claude` vive en
`agno/models/vertexai/claude.py` (extends `AnthropicClaude`, provider
`"VertexAI"`).

#### Scenario: resolve_model("vertex:claude-sonnet-4") instancia Claude vertex

- GIVEN el adapter con `agno.models.` allowlisted y `anthropic` instalada
- WHEN `resolve_model("vertex:claude-sonnet-4@20250514")`
- THEN retorna una instancia de `Claude` cuyo `provider == "VertexAI"`

#### Scenario: el module_path incluye el submodule claude

- GIVEN el `MODEL_REGISTRY["vertex"]`
- WHEN se inspecciona la tupla
- THEN el `module_path` es `"agno.models.vertexai.claude"` (NO `"agno.models.vertexai"`)

### Requirement: openai es alias de back-compat de openai_chat

`MODEL_REGISTRY["openai"]` DEBE ser un alias semántico de
`MODEL_REGISTRY["openai_chat"]` apuntando a
`("agno.models.openai", "OpenAIChat")`, para preservar back-compat con configs
existentes que usan `resolve_model("openai:gpt-4o")`. `openai_chat` y
`openai_responses` DEBEN existir como claves distintas (OpenAIChat vs
OpenAIResponses respectivamente).

#### Scenario: openai alias resuelve idéntico a openai_chat

- GIVEN el `MODEL_REGISTRY` con `openai` y `openai_chat`
- WHEN se comparan ambas tuplas
- THEN son iguales (`("agno.models.openai", "OpenAIChat", [...])`)

#### Scenario: resolve_model("openai:gpt-4o") sigue funcionando

- GIVEN el adapter con `agno.models.` allowlisted y `openai` instalada
- WHEN `resolve_model("openai:gpt-4o")`
- THEN retorna una instancia de `OpenAIChat` con `id == "gpt-4o"`

### Requirement: toda entrada importable cuando su dependencia está instalada

Cada tupla `(module_path, class_name)` declarada en `MODEL_REGISTRY` y
`PROVIDER_REGISTRY` DEBE ser importable vía `importlib` cuando el paquete
proveedor nativo esté instalado (ej. `mistralai`, `anthropic`, `openai`).
Cuando la dependencia NO esté instalada, el adapter DEBE propagar
`ModuleNotFoundError`/`ImportError` sin crash del proceso de registro — el
catálogo se declara estáticamente como DATA, independiente de si las deps
opcionales están presentes.

#### Scenario: provider con dependencia instalada importa la clase

- GIVEN el entorno con `openai` instalado (dep nativa real en CI)
- WHEN `resolve_model("openai_chat:gpt-4o")`
- THEN retorna `OpenAIChat(id="gpt-4o")` sin `ImportError`

#### Scenario: provider con dependencia opcional ausente se salta con graceful skip

- GIVEN un provider opcional (ej. `mistral`) cuya dep `mistralai` NO está instalada
- WHEN se carga el módulo `yaml_agno.di.registries`
- THEN el módulo se importa sin lanzar (el catálogo es DATA estática)
- AND al invocar `resolve_model("mistral:x")` se propaga `ImportError`/`ModuleNotFoundError` al caller
