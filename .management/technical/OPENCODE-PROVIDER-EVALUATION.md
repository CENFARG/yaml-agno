# OPENCODE-PROVIDER-EVALUATION — Provider OpenCode en Agno

- **Fecha**: 2026-08-09
- **Autor**: Code Architect (development-team, CENF)
- **Contexto**: Correcciones Gonzalo (2026-08-09): burn rate $134/mes bajando por modelos
  free; interés en probar equipos yaml-agno con modelos free de OpenCode. Este documento
  evalúa si Agno tiene (o debe tener) un provider para OpenCode.
- **Método**: git grep en repo agno local + WebSearch (docs opencode.ai, docs.agno.com,
  OpenRouter cookbook, DeepWiki).

---

## 1. ¿Existe un provider OpenCode en Agno? — NO

- `git grep -il "opencode"` en `libs/agno/agno/` → **0 resultados**.
- Directorios de providers en `libs/agno/agno/models/` (50+): aimlapi, anthropic, aws,
  azure, cerebras, cloudflare, cohere, cometapi, dashscope, deepinfra, **deepseek**, fireworks,
  google, groq, huggingface, ibm, inception, internlm, langdb, litellm, llama_cpp, lmstudio,
  meta, minimax, mistral, moonshot, n1n, nebius, neosantara, nexus, nvidia, ollama, openai,
  **openrouter**, perplexity, portkey, requesty, sambanova, siliconflow, together, tokenlab,
  trustedrouter, tuning_engines, vercel, vertexai, vllm, xai, xiaomi. **No hay `opencode`**.
- WebSearch: no existe documentación de "agno opencode provider" (los resultados relevantes
  son del lado de OpenCode consumiendo providers, no al revés).

## 2. ¿Qué es OpenCode realmente? (verificado con WebSearch)

OpenCode (opencode.ai, GitHub `anomalyco/opencode`) es un **cliente de agentes de código**:
TUI de terminal, app desktop (macOS/Windows/Linux) y extensión IDE. Consume **75+ providers**
de LLM (OpenRouter, Anthropic, OpenAI, Gemini, DeepSeek, GitHub Copilot, GitLab Duo, Ollama,
LM Studio, etc.) vía el Vercel **AI SDK** (`@ai-sdk/openai-compatible`, `@ai-sdk/openai`, …).

- **OpenCode NO es un proveedor de modelos**: no sirve inferencia propia ni expone una API
  pública tipo `api.opencode.ai/v1/chat/completions` para terceros.
- **No verificado/inexistente**: endpoint `https://api.opencode.ai` como API de chat — no
  aparece en ninguna doc oficial. El único "bridge" que expone los 75+ providers de OpenCode
  como API OpenAI-compatible es un proyecto **de terceros, no oficial**
  (`crazyboy24/opencode-bridge`, DeepWiki: "translates OpenAI-standard chat requests into
  OpenCode-specific sessions"; sin respaldo de anomalía/anomalyco).
- Conclusión conceptual: **un "provider OpenCode" para Agno no tiene sentido directo**,
  porque no hay backend de modelos al cual conectarse. OpenCode es el análogo-cliente de
  agno/opencode, no un upstream.

## 3. Qué se necesitaría para "probar equipos yaml-agno con modelos free"

El objetivo real (bajar burn rate con modelos free) se logra **sin OpenCode**:

| Necesidad | Solución en Agno (ya disponible) |
|---|---|
| Modelos free/baratos | `agno.models.openrouter.OpenRouter` (modelos free: `:free`), `agno.models.deepseek`, `agno.models.groq`, `agno.models.google` (Gemini free tier), `agno.models.openai.like.OpenAILike` para cualquier endpoint OpenAI-compatible |
| Fallback entre providers | yaml-agno ya tiene `models/fallback_chain.py` + `di/provider_factory.py` (SPEC_14, hecha) |
| Config de API keys | `di/secret_resolver.py` (ConfigSecretResolver lee OPENROUTER_API_KEY etc., ya en uso) |
| Contexto CENF | el fork `agno-docs-agent` ya probó este camino: commit `8a57169` "feat: add OpenRouter + DeepSeek V4 config, .env loading" (verificado en `C:\Dropbox\DOC.RECA\06-Software\agno-docs-agent`) |

**Si en el futuro OpenCode expusiera una API oficial de chat**, el camino sería un provider
`OpenAILike` con `base_url` apuntando a ese endpoint — no un provider nuevo completo.

## 4. Cuánto costaría crear un provider nuevo (referencia, no recomendado)

Referencia de estructura real en el repo agno (patrón estándar):
- `libs/agno/agno/models/deepseek/deepseek.py` — un archivo Python que subclasea `Model`
  (base en `models/base.py`) o `OpenAIChat`/`OpenAILike`; export en `__init__.py`.
- `libs/agno/agno/models/openrouter/openrouter.py` + `responses.py` (soporte Responses API).

Un provider nuevo típico: **~200-600 líneas** (subclase de Model, `invoke`/`ainvoke`,
`response`/`aresponse`, params de chat, mapeo de errores) + `__init__.py` (export) + tests
unit (~100-300 líneas) + entrada en docs de provider. Esfuerzo: **~1-3 días-agente**,
más el mantenimiento ante cambios de API del upstream.

**Recomendación**: NO crear provider. La capa `OpenAILike` cubre cualquier endpoint
OpenAI-compatible y yaml-agno ya abstrae providers vía `di/provider_factory.py`
(formato `"openrouter:openai/gpt-4o"`, `"openai:gpt-4o"` — AGENTS.md yaml-agno "Model
format"). Agregar un provider nuevo a Agno solo tiene sentido si el upstream expone API
propia (como hace OpenRouter), y OpenCode no la expone.

## 5. Conclusión

1. **No existe** provider OpenCode en Agno (git grep vacío).
2. **No corresponde crearlo**: OpenCode es cliente, no proveedor de modelos; no hay endpoint
   oficial de chat al cual conectarse (los bridges son de terceros, no recomendados).
3. **Para el objetivo (modelos free + equipos yaml-agno)**: usar los providers ya
   disponibles (OpenRouter free, DeepSeek, Gemini, Groq) vía `di/provider_factory.py` +
   `fallback_chain.py` (SPEC_14). El fork `agno-docs-agent` ya validó OpenRouter + DeepSeek V4.
4. **Esfuerzo real si igualmente se quisiera**: ~1-3 días-agente + mantenimiento continuo —
   no justificado hoy.
