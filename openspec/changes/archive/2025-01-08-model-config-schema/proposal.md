---
change: model-config-schema
spec: SPEC_14
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/provider-catalog-expansion   # SUPPORTED_PROVIDERS + PROVIDER_ALIASES (shipped slice #1)
---

# Proposal: Model Config Schema (SPEC_14 slice #2)

## Intent

SPEC_14 §3/§4/§6 exigen un set de schemas Pydantic que representen la
configuración de modelo en YAML: forma compacta (`"openai:gpt-4o"`), forma
expandida (provider + id + params + fallback), y un resolver que normalice
cualquier referencia a un `ModelExpandedSpec`. Hoy no existen — `AgentConfig.model`
es un `str` opaco que `AgentFactory` pasa verbatim a `agno.Agent`, sin validar
provider, sin params, sin fallback.

Este slice (slice #2, **puramente schemas + resolver**) introduce los 5 schemas
en un único módulo `src/yaml_agno/models/model_spec.py` consumiendo el catálogo
del slice #1 (`SUPPORTED_PROVIDERS`, `PROVIDER_ALIASES`). Nada los importa todavía
— son la base sobre la que los slices 3-4 construirán el wiring de
`AgentConfig.model` y el runtime de fallback.

## Why

- **Sin schemas, no hay capa de modelo**: el parser YAML no puede distinguir
  `model: "openai:gpt-4o"` de `model: { provider: openai, id: gpt-4o, ... }`;
  AgentFactory recibe un string crudo y Agno hace parsing nativo opaco a
  yaml-agno.
- **Validación de provider SSOT**: hoy un YAML con `provider: banana` pasa
  `AgentConfig` sin error y revienta en `agno.Agent`. `ModelStringSpec` debe
  validar contra `SUPPORTED_PROVIDERS` (frozenset derivado de `PROVIDER_REGISTRY`,
  slice #1) para fallar temprano con un mensaje accionable.
- **Retry/fallback boundary**: SPEC_14 §1.3 separa model-level retry (campos
  nativos de Agno `Model.*`) de step-level retry (`RetryPolicy`, SPEC_05). El
  slice #2 debe FORWARDAR a los campos nativos de Agno — NO inventar un
  `RetryPolicy` a nivel modelo (coherence-audit #2, directiva TOP-3).
- **Spec drift corregido**: SPEC_14 §3.4 (líneas 255-262) enumera campos
  inventados `retry_delay`, `wait_on_rate_limit`, `retry_jitter` que **no
  existen** en Agno `Model` (verificado en `agno/models/base.py`). Este slice
  los reemplaza por los 5 campos nativos reales: `retries`,
  `delay_between_retries`, `exponential_backoff`, `retry_with_guidance`,
  `retry_with_guidance_limit`.

## Scope

### In Scope

- **`ModelStringSpec`**: forma compacta `"provider:id"` o `"provider:id:alias"`.
  `field_validator` parte por `:`, valida `len(parts) in (2,3)` y valida
  `provider in SUPPORTED_PROVIDERS`.
- **`FallbackConfig`**: schema self-contained. `fallback_models: list[str|dict]`,
  enums `on_rate_limit`/`on_context_overflow`/`on_error` (`Literal["retry_only",
  "route_fallback", "retry_then_fallback", "fail"]`), `fallback_callback: str|None`,
  `max_fallback_hops: int = Field(3, ge=1)`, `propagate_session: bool = True`.
  **Sin** dependencia de SPEC_09 (CircuitBreaker se referencia, no se duplica).
- **`ModelExpandedSpec`**: `provider` (validado contra `SUPPORTED_PROVIDERS` vía
  `field_validator`, **no** `Literal[26]`), `id`, `alias`. Generation params
  (§4.1): `temperature` (0.0-2.0), `max_tokens` (>=1), `top_p` (0.0-1.0),
  `top_k` (>=0), `stop_sequences`, `seed`. Reasoning: `reasoning_effort`
  (`Literal["minimal","low","medium","high"]`), `thinking`. Caching:
  `cache_response: bool = False`. **Retry block forwarding a Agno native**:
  `retries` (0-10), `delay_between_retries` (>=0.0), `exponential_backoff`
  (default True), `retry_with_guidance` (bool), `retry_with_guidance_limit`
  (int>=0). `fallback: FallbackConfig|None`. `provider_kwargs: dict`,
  `timeout: float|None`, `base_url: str|None`.
- **`ModelSpec` union**: `Annotated[Union[ModelStringSpec, ModelExpandedSpec]]`
  con discriminación por tipo (str vs dict), no por campo.
- **`ProviderResolver`**: `resolve(ref: str|dict|ModelExpandedSpec)` aplica
  `PROVIDER_ALIASES` antes del lookup (corrige gap SPEC_14 §12.1 línea 896),
  devuelve `ModelExpandedSpec` normalizado. `resolve_alias(alias)` indexa por
  `spec.alias`.
- **Tests**: pure Pydantic, mock-free. Cobertura: grammar válida/inválida,
  provider desconocido rechazado, rangos de params (temperature fuera de rango,
  retries >10), alias aplicado, FallbackConfig enums aceptados/rechazados,
  round-trip str → ModelExpandedSpec.

### Out of Scope

- **`AgentConfig.model` NO se toca** (decisión crítica): permanece `str`
  (`ModelReference` alias). Cambiarlo a `ModelSpec` union rompe ~8 tests de
  `test_agent_config.py` y ~6 de `test_agent_factory.py`, y requiere actualizar
  `agent_factory.py:82` (`model=cfg.model` pasa un Pydantic object, no str).
  Eso es evolución de schema coordinada → slice #3 o #4. **Este slice sólo
  entrega los schemas standalone; nada los importa aún.**
- **Runtime de fallback**: `build_fallback_chain`, `call_with_fallback`,
  integración con CircuitBreaker (SPEC_09) → slice #4.
- **`ModelBuilder`**: traducción `ModelExpandedSpec → instancia agno.Model` →
  slice #3 (wiring factory).
- **CapabilityValidator** (SPEC_14 §6.4): validación runtime contra
  `ProviderCapabilities` → slice #3.
- **Wiring de `AgentConfig.model` como union** → slice #3.
- **Campos inventados por SPEC_14 (`retry_delay`, `wait_on_rate_limit`,
  `retry_jitter`)**: NO se implementan. SPEC_14 §3.4 líneas 255-262 está
  desactualizado; la directiva de coherence-audit TOP-3 #2 y la verificación
  de `agno/models/base.py` confirman que Agno no los tiene.

## Capabilities

### New Capabilities

- `model-config-schema`: schemas Pydantic (`ModelStringSpec`,
  `ModelExpandedSpec`, `FallbackConfig`, `ModelSpec`) + `ProviderResolver` para
  representar y normalizar la configuración de modelo declarada en YAML.

### Modified Capabilities

Ninguna. `AgentConfig.model` no cambia en este slice; no hay delta spec-level
sobre `agent-config-schema`. El wiring es un cambio posterior coordinado.

## Approach

**Un módulo, cinco exports.** Todo vive en `src/yaml_agno/models/model_spec.py`
(~450 LOC). Orden de definición respeta dependencia forward:

1. `ModelStringSpec` (sin deps internas).
2. `FallbackConfig` (sin deps internas — self-contained, sin SPEC_09).
3. `ModelExpandedSpec` (referencia `FallbackConfig` en `fallback`).
4. `ModelSpec = Annotated[Union[ModelStringSpec, ModelExpandedSpec], ...]`.
5. `ProviderResolver` (consume `ModelStringSpec`, `ModelExpandedSpec`,
   `PROVIDER_ALIASES`, `SUPPORTED_PROVIDERS`).

**SSOT enforcement.** `ModelExpandedSpec.provider` es `str` validado por
`field_validator` contra `SUPPORTED_PROVIDERS` (frozenset importado de
`yaml_agno.di.provider_capabilities`), **no** un `Literal[26]` hardcoded.
Cuando se agregue un provider al catálogo (slice #1 edit), el schema lo acepta
automáticamente — sin drift (explore risk #5).

**Alias resolution simétrica con AgnoResolver.** `ProviderResolver._resolve_string`
aplica `PROVIDER_ALIASES` (de `yaml_agno.di.registries`) **antes** del lookup,
espejando `AgnoResolver.resolve_model` (explore risk #6 / SPEC_14 §12.1 gap).
Así `"openai:gpt-4o"` se canonicaliza a `provider="openai_chat"` en el
`ModelExpandedSpec` retornado.

**Retry = forward nativo, no invención.** `ModelExpandedSpec` expone los 5
campos nativos de Agno `Model`: `retries`, `delay_between_retries`,
`exponential_backoff`, `retry_with_guidance`, `retry_with_guidance_limit`. NO
hay `retry_delay` (nombre yaml-agno-only), NO `wait_on_rate_limit`, NO
`retry_jitter`. La traducción yaml→Agno es 1:1 porque los nombres coinciden
con el base. CircuitBreaker y Retry-After son runtime del slice #4, no schema.

**Tests mock-free.** Todos los tests son Pydantic puro: instanciar schema con
dict válido/inválido, assert `ValidationError` con mensaje esperado,
`ProviderResolver.resolve("openai:gpt-4o")` assert
`result.provider == "openai_chat"`. Sin mock de Agno ni de dependencias.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/models/model_spec.py` | New | 5 schemas + ProviderResolver (~450 LOC). Módulo standalone; nada lo importa aún. |
| `tests/unit/models/test_model_spec.py` | New | Tests Pydantic mock-free (~25 casos). |
| `src/yaml_agno/models/config/agent_config.py` | Untouched | `AgentConfig.model` permanece `str`. |
| `src/yaml_agno/factories/agent_factory.py` | Untouched | `model=cfg.model` passthru no cambia. |
| `specs/SPEC_14_*.md` | Deferred | §3.4 líneas 255-262 (campos inventados) queda obsoleto; corrección se documenta en este proposal y en el design. No se edita el SPEC en este slice. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SPEC_14 §3.4 (líneas 255-262) lista `retry_delay`/`wait_on_rate_limit`/`retry_jitter` que NO existen en Agno | Confirmed | Schema forwardarea sólo a los 5 campos nativos verificados (`retries`, `delay_between_retries`, `exponential_backoff`, `retry_with_guidance`, `retry_with_guidance_limit`). Design doc citará `agno/models/base.py`. SPEC queda marcado obsoleto en este punto. |
| Drift entre `Literal[26]` (SPEC_14 §3.4 línea 221) y `SUPPORTED_PROVIDERS` real | Medium | `ModelExpandedSpec.provider` usa `field_validator` contra `SUPPORTED_PROVIDERS`, no `Literal`. Una sola fuente de verdad. |
| `openai` es clave en `SUPPORTED_PROVIDERS` pero alias canónico es `openai_chat` | Medium | `ProviderResolver._resolve_string` aplica `PROVIDER_ALIASES` antes de construir el `ModelExpandedSpec`, igual que `AgnoResolver`. Test explícito: `resolve("openai:gpt-4o").provider == "openai_chat"`. |
| `AgentConfig.model` queda como `str` — alguien podría asumir que ya es union | Low | Docstring del módulo + proposal explícito "Out of Scope". Wiring es slice #3. |
| `FallbackConfig` definido antes que `ModelExpandedSpec` para evitar forward refs | Low | Orden de declaración en el módulo respeta la dependencia. Pydantic V2 no necesita `model_rebuild()` si el orden es correcto. |
| `ModelSpec` union discriminada por tipo (str vs dict) — Pydantic V2 behaviour | Low | `Field(discriminator=None)` + tests explícitos de round-trip `parse_model("openai:x")` y `parse_model({...})`. |

## Rollback Plan

El slice es **aditivo puro**: un módulo nuevo + su test. Ningún archivo
existente se modifica. Rollback = `git revert` del commit del slice (borra
`src/yaml_agno/models/model_spec.py` + `tests/unit/models/test_model_spec.py`).
No hay migración, no hay cambio de `AgentConfig`, no hay wiring que deshacer.
Como nada importa el módulo todavía, el revert no tiene efecto colateral sobre
los 163 tests existentes.

## Dependencies

- **`yaml_agno.di.provider_capabilities.SUPPORTED_PROVIDERS`** (slice #1,
  shipped, read-only) — frozenset de 27 claves, fuente única para validación
  de provider.
- **`yaml_agno.di.registries.PROVIDER_ALIASES`** (slice #1, shipped) — dict
  `{"openai": "openai_chat"}` para canonicalización en `ProviderResolver`.
- **Pydantic V2** (`pydantic>=2.0`, ya en `pyproject.toml`) — `BaseModel`,
  `field_validator`, `Field(ge=, le=)`, `ConfigDict`.
- **Agno 2.6.22** (`agno==2.6.22`, ya pinneado) — referencia read-only de los
  campos nativos de `Model` base (no se importa nada de Agno en este slice;
  los nombres se verifican contra `agno/models/base.py`).

## Success Criteria

- [ ] `from yaml_agno.models.model_spec import ModelStringSpec, ModelExpandedSpec, FallbackConfig, ModelSpec, ProviderResolver` funciona sin error.
- [ ] `ModelStringSpec(raw="openai:gpt-4o")` valida OK; `ModelStringSpec(raw="banana:x")` lanza `ValidationError` con `SUPPORTED_PROVIDERS` como fuente.
- [ ] `ModelExpandedSpec(provider="banana", id="x")` lanza `ValidationError` (mismo SSOT que `ModelStringSpec`).
- [ ] `ModelExpandedSpec(provider="anthropic", id="x", temperature=2.5)` lanza `ValidationError` (rango 0.0-2.0 de §4.1).
- [ ] `ModelExpandedSpec(provider="anthropic", id="x", retries=11)` lanza `ValidationError` (rango 0-10).
- [ ] `ModelExpandedSpec` expone `retries`, `delay_between_retries`, `exponential_backoff`, `retry_with_guidance`, `retry_with_guidance_limit` y **NO** expone `retry_delay`/`wait_on_rate_limit`/`retry_jitter`.
- [ ] `FallbackConfig(fallback_models=[], on_rate_limit="banana")` lanza `ValidationError`; los 4 valores del `Literal` enum aceptan.
- [ ] `ProviderResolver({}).resolve("openai:gpt-4o").provider == "openai_chat"` (alias aplicado).
- [ ] `ProviderResolver({}).resolve("anthropic:claude-sonnet-4-5:main").alias == "main"`.
- [ ] Los 163 tests existentes siguen pasando sin modificación (slice aditivo, `AgentConfig` intacto).
- [ ] `pytest tests/unit/models/test_model_spec.py` pasa en verde (≥25 casos).
