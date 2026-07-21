---
change: provider-factory-adapter
spec: SPEC_14
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/provider-catalog-expansion
  - openspec/specs/model-config-schema
---

# Proposal: ProviderFactory + AgnoModelAdapter (SPEC_14 slice #3)

## Intent

Cerrar el gap entre la **declaración** de modelos (`ModelExpandedSpec`, slice #2)
y la **instanciación** real de un `Model` Agno. Hoy no existe un componente que
parta de un `ModelExpandedSpec` validado y produzca una instancia `Model` viva con
los kwargs correctos y el `api_key` resuelto. Sin esta pieza, los slices #4
(fallback/Circuit Breaker) y el bootstrap de agentes no tienen nada que invocar.

## Why Now

- Slice #1 (`provider_capabilities.py`) entrega `PROVIDER_REGISTRY` + capabilities.
- Slice #2 (`model_spec.py`) entrega `ModelExpandedSpec` con campos Agno-native.
- Slice #3 es el **punto de convergencia**: toma ambos y materializa la instancia.
- Postergarlo bloquea todo el runtime de modelos (fallback, cache, agent bootstrap).

## Scope

### In Scope

- `ProviderFactory(resolver, secret_resolver).build(ModelExpandedSpec) -> Model`:
  delega `resolve_class` al `AgnoResolver` inyectado, compone kwargs filtrados por
  los `dataclass_fields` de la clase resuelta, resuelve `api_key` vía
  `SecretResolver`, instancia.
- `_compose_kwargs` dinámico: inspecciona `dataclasses.fields(resolved_class)` y
  sólo reenvía kwargs que la clase destino realmente declara (Model es
  `@dataclass`, NO Pydantic; `temperature`/`top_p` son provider-specific).
  Escape hatch: `provider_kwargs` (dict) forwarded as-is para `thinking`,
  `stop`, `top_k`, `frequency_penalty`.
- `AgnoModelAdapter`: cache de **instancias** por clave
  `spec.alias or f"{spec.provider}:{spec.id}"`. Dict de proceso (sin TTL).
  Hook `invalidate(alias=None)` para el futuro path de rotación (SPEC_23 §2.9).
- `SecretResolver` Protocol **sync** (`Callable[[str], str | None]`) + default
  `ConfigSecretResolver(config)` leyendo `config.get_string(f"secrets.{key}")`.
  NO es el `SecretManager` async de core-cenf.
- `ModelCapabilitiesValidator`: validador pure-data config-time contra
  `PROVIDER_REGISTRY[provider].capabilities`. Devuelve `list[str]` errores.
- Tests con `InMemoryDependencyAdapter`/`InMemoryConfigAdapter` (doubles core-cenf)
  y `OpenAIChat` real donde sea viable (sin red en construct).

### Out of Scope

- Runtime de fallback / Circuit Breaker (slice #4).
- `FallbackConfig` wiring a SPEC_09.
- Resolución del `fallback_callback` dotted-ref (se deja stub / raise NotImplemented;
  es invocado por slice #4).
- Rotación/auditoría de secretos, TTL de cache (SPEC_23 §2.9, slice posterior).
- Async-to-sync adapter del bootstrap (decision #10 TaskGroup) — este slice sólo
  define el contrato sync que el bootstrap consumirá.
- `AgentConfig.model` swap (cambio coordinado SPEC_02 posterior).
- Re-litigar nombres de campos retry (slice #2 ya define Agno-native; SPEC_14
  §3.4/§11.2 text es STALE — el código shipped es SSOT).

## Capabilities

### New Capabilities

- `model-instantiation`: factory sync que convierte un `ModelExpandedSpec`
  validado en una instancia `Model` Agno, delegando resolución de clase, filtrando
  kwargs por introspección dataclass, resolviendo secretos vía callable inyectado,
  y cacheando instancias por alias.

### Modified Capabilities

- `model-config-schema`: la capacidad existente (slice #2) **no cambia requisitos
  de spec** — slice #3 la consume read-only. Sin delta.

## Approach

**COMPOSE around `AgnoResolver` (no parallel/replace).**
`ProviderFactory.__init__(self, resolver: AgnoResolver, secret_resolver: SecretResolver)`.
`build(spec)`:

1. Lookup `PROVIDER_REGISTRY[spec.provider]` → `(agno_module, agno_class, api_key_env)`.
2. `cls = self._resolver.resolve_class(agno_module, agno_class)` — reutiliza
   allowlist + `InMemoryDependencyAdapter` test path (público, `agno_resolver.py:184`).
   NO se duplica importlib. NO se toca `resolve_model` (sigue siendo el path
   minimal string→instance del que dependen slices 1-2).
3. `kwargs = _compose_kwargs(spec, cls)` — ver abajo.
4. `api_key = self._secret_resolver(api_key_env)` si `api_key_env` no es `None`;
   inyectar en kwargs sólo si la clase destino declara `api_key`.
5. `return cls(**kwargs)`. Fallos → `ModelConstructionError`.

**`_compose_kwargs` dinámico (anti-TypeError).** Model es `@dataclass` (base.py).
`temperature`/`top_p`/`seed`/`stop`/`reasoning_effort` viven en `OpenAIChat`, NO en
base; `top_k`/`thinking`/`stop_sequences` en Claude. Pasar `top_k` a OpenAIChat →
`TypeError`. Por eso `_compose_kwargs` inspecciona `dataclasses.fields(cls)` y sólo
reenvía los campos que la clase destino declara. Los campos retry
(`retries`/`delay_between_retries`/`exponential_backoff`/`retry_with_guidance`/
`retry_with_guidance_limit`) van 1:1 (ya Agno-native en slice #2, sin capa de
traducción). `provider_kwargs` dict se forward as-is como escape hatch.

**SecretResolver SYNC + async boundary en bootstrap.** Agno constructores son sync
`@dataclass`; los providers resuelven `api_key` lazy en el primer request, pero el
constructor acepta `api_key=None`. Para encajar con el patrón asyncio.TaskGroup de
yaml-agno + decision #7 (no `os.environ`), la factory es sync y recibe los secretos
ya resueltos vía un `SecretResolver = Callable[[str], str | None]` sync. El bootstrap
async (decision #10) hace `await secret_manager.get_secret(env)` una vez por
provider-family, arma `{env: value}` y le pasa a la factory un
`lambda env: cache[env]`. La factory NUNCA llama al `SecretManager` async de
core-cenf. Default MVP: `ConfigSecretResolver(config)` →
`config.get_string(f"secrets.{key}")`.

**Cache de instancias.** `AgnoModelAdapter` envuelve `ProviderFactory`; cache dict
de proceso, clave `spec.alias or f"{provider}:{id}"`. `invalidate(alias=None)`
limpia una o todas las entradas (hook para rotación futura). Sin TTL en slice #3.

**Capabilities validator config-time.** Pure-data, sin tocar clases Agno. Lee
`PROVIDER_REGISTRY[provider].capabilities` (`provider_capabilities.py:26-50`) y
valida intent declarado en `ModelExpandedSpec` (e.g. `reasoning_effort`/`thinking`
requiere `capabilities.reasoning`; structured strict requiere `"strict"` en
`structured_output`). Devuelve `list[str]` (vacío = OK). Se invoca en
`factory.build()` pre-instantiation (fail-fast) — confirmar en spec si también
corre a config-load.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/models/factory.py` | New | `ProviderFactory` + `_compose_kwargs` + `ModelConstructionError`. |
| `src/yaml_agno/models/adapter.py` | New | `AgnoModelAdapter` (cache + invalidate). |
| `src/yaml_agno/models/secret_resolver.py` | New | `SecretResolver` Protocol (sync) + `ConfigSecretResolver`. |
| `src/yaml_agno/models/capabilities_validator.py` | New | `ModelCapabilitiesValidator` (pure-data). |
| `src/yaml_agno/di/agno_resolver.py` | None (read) | Se consume `resolve_class` público (línea 184); sin cambios. |
| `src/yaml_agno/di/provider_capabilities.py` | None (read) | Se consume `PROVIDER_REGISTRY` + `ProviderCapabilities`. |
| `src/yaml_agno/models/model_spec.py` | None (read) | Se consume `ModelExpandedSpec`; sin cambios de schema. |
| `tests/models/` | New | Tests de factory/adapter/secret/capabilities. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `thinking` es `Dict[str,Any]` en Claude pero `bool` en `ModelExpandedSpec` → TypeError si se forward directo | High | `_compose_kwargs` NO forward `thinking` directo; documentar `provider_kwargs` como escape hatch (`{"type":"enabled","budget_tokens":N}`). |
| `stop_sequences` (Claude) vs `stop` (OpenAI) naming mismatch | High | `_compose_kwargs` renombra per-provider O lo deja caer si la clase no declara el campo exacto; explicit test por provider. |
| SPEC_14 §3.4/§11.2 text diverge del código shipped (retry names, ausencia de `provider_kwargs`/`timeout`/`base_url`) | Medium | El código shipped (slice #2) es SSOT; spec/citacion debe apuntar a `model_spec.py`, no a SPEC text. |
| Pre-resolución eager de `api_key` en bootstrap → secret faltante falla en boot, no en primer request | Low | Aceptable (fail-fast); documentar en spec. |
| `resolve_class` podría dejar de ser público (refactor futuro de AgnoResolver) | Low | Ya es API pública con tests; citar `agno_resolver.py:184` como contrato. |
| Diferencia de campos dataclass entre versiones Agno | Medium | `_compose_kwargs` es introspectivo, no hardcoded; una nueva versión sólo cambia el set filtrado. |

## Rollback Plan

Slice #3 es **additivo puro**: nuevos módulos `factory.py`, `adapter.py`,
`secret_resolver.py`, `capabilities_validator.py`. Ningún módulo existente los
importa todavía (el wiring a `AgentConfig.model` es un cambio coordinado posterior).
Rollback = eliminar los 4 módulos nuevos + sus tests. Sin migración de datos, sin
cambios en schemas existentes, sin impacto en slices #1/##2 shipped.

## Dependencies

- `openspec/specs/provider-catalog-expansion` (slice #1) — `PROVIDER_REGISTRY`,
  `ProviderCapabilities`, `SUPPORTED_PROVIDERS`. Shipped.
- `openspec/specs/model-config-schema` (slice #2) — `ModelExpandedSpec`,
  `ProviderResolver`, `parse_model_spec`. Shipped.
- `agno_resolver.resolve_class` público (`agno_resolver.py:184`). Verified.
- Agno 2.6.22 (`Model` `@dataclass`, `OpenAIChat`, `Claude`). Verified.

## Success Criteria

- [ ] `ProviderFactory.build(ModelExpandedSpec(provider="openai", id="gpt-4o"))`
      devuelve una instancia `OpenAIChat` con `id="gpt-4o"` y `api_key` resuelto.
- [ ] Pasar `top_k` a un spec openai NO levanta TypeError (filtrado dinámico).
- [ ] `provider_kwargs={"thinking": {...}}` se forward as-is a Claude.
- [ ] `AgnoModelAdapter` retorna la MISMA instancia para la misma clave (cache hit).
- [ ] `invalidate(alias)` limpia sólo esa entrada; `invalidate()` limpia todas.
- [ ] `ConfigSecretResolver` lee `secrets.{key}` desde `ConfigManager` sin `os.environ`.
- [ ] `ModelCapabilitiesValidator` reporta error si `reasoning_effort` se declara
      sobre un provider con `capabilities.reasoning == False`.
- [ ] Cero cambios en `agno_resolver.py`, `provider_capabilities.py`, `model_spec.py`.
- [ ] Cobertura de tests ≥ umbral del proyecto; sin red en construct.
