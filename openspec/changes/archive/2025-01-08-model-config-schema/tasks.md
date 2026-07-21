---
change: model-config-schema
slice: SPEC_14 #2
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on:
  - openspec/changes/model-config-schema/proposal.md      # obs 1979
  - openspec/changes/model-config-schema/specs/model-config-schema/spec.md  # obs 1980 (9 reqs, 28 scenarios)
  - openspec/changes/model-config-schema/design.md         # obs 1981 (literal code, 6 ADRs)
  - src/yaml_agno/di/provider_capabilities.py              # SUPPORTED_PROVIDERS (shipped slice 1)
  - src/yaml_agno/di/registries.py                         # PROVIDER_ALIASES (shipped slice 1)
strict_tdd: true
test_command: pytest tests/unit/models/test_model_spec.py -m unit
---

# Tasks: model-config-schema (SPEC_14 slice #2)

> Slice #2 de SPEC_14. Schemas Pydantic V2 standalone + resolver para la
> configuración de modelo declarada en YAML. **Puro dato + un resolver
> stateless** — no instancia Agno, no toca `AgentConfig.model` (queda `str`).
> TDD estricto: RED (28 escenarios + test de override del union) → GREEN
> (código literal del design, sin desviaciones).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450 (model_spec.py ~300 + test_model_spec.py ~150) |
| 400-line budget risk | Medium (approaches budget with tests; source alone is ~300) |
| Chained PRs recommended | No |
| Suggested split | single PR (additive slice, one module + one test file + 5-line re-export) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | RED tests + GREEN schemas + re-export + verification (change completo) | PR único | base = current branch; net-new module `models/model_spec.py`, no touch a `AgentConfig` |

## CRITICAL — design risk baked into tasks

`ModelStringSpec.model_validate` is OVERRIDDEN (design.md:217-222) to accept a
bare `"provider:id"` string. Pydantic V2 default expects a dict payload, so the
union `ModelSpec = ModelStringSpec | ModelExpandedSpec` must still resolve
correctly when fed a bare string (it should land on `ModelStringSpec`, not
throw `ValidationError`). Tasks MUST include an explicit test that `ModelSpec`
union resolves from BOTH a bare string AND a dict (the override composes
correctly with union resolution). **This is the load-bearing test of the slice**
— flagged in Task 2.7 below. If it goes RED, the override is broken; do NOT
ship GREEN without it.

## Open Items

- **None blocking**. The union swap (`AgentConfig.model: ModelSpec`) and
  `AgentFactory.build()` integration are explicitly deferred to a later slice
  (ADR A1). The 5 schemas ship standalone; nothing imports them yet.
- **Spec drift documented, NOT edited**: SPEC_14 §3.4 (líneas 255-262) lista
  `retry_delay`/`wait_on_rate_limit`/`retry_jitter` que no existen en Agno. La
  corrección vive en proposal.md + design.md (ADR A3). SPEC queda marcado
  obsoleto en ese punto — no se edita el SPEC en este slice.
- **FallbackConfig vs spec wording**: design.md literal ships
  `fallback_models: list[Union[str, dict]]` + `strategy: Literal["ordered","random"]`,
  while spec.md §"FallbackConfig — schema autocontenido" mentions
  `on_rate_limit`/`on_context_overflow`/`on_error` enums and `max_fallback_hops`.
  The design literal is the CONTRACT (design > spec when they diverge, per
  design.md frontmatter `status: ready-for-tasks`). Tests follow the design
  literal verbatim — see Task 2.9 and the TDD Compliance Matrix note.

## Phase 1: Baseline — confirmar cimientos antes de RED

> Objetivo: verificar que slice #1 está importable y que `models/` existe con
> su `__init__.py`. Sin esto, los imports del nuevo módulo fallan antes de
> validar nada.

- [ ] 1.1 Verificar baseline limpio: `git status` sin cambios sin commitear
  (slice aditivo puro; cualquier ruido previo se resuelve antes de empezar).
  **Req: ADR A1 (zero blast radius) + Rollback Plan.**
- [ ] 1.2 Confirmar `from yaml_agno.di.provider_capabilities import SUPPORTED_PROVIDERS`
  funciona y `isinstance(SUPPORTED_PROVIDERS, frozenset) is True` y
  `"anthropic" in SUPPORTED_PROVIDERS` y `"openai_chat" in SUPPORTED_PROVIDERS`.
  **Scenario: Importabilidad del catálogo. Req: SSOT — catálogo único.**
- [ ] 1.3 Confirmar `from yaml_agno.di.registries import PROVIDER_ALIASES`
  funciona y `PROVIDER_ALIASES.get("openai") == "openai_chat"`.
  **Req: ProviderResolver — resolución y canonicalización (precondición).**
- [ ] 1.4 Confirmar `src/yaml_agno/models/__init__.py` existe y re-exporta
  `AgentConfig, TeamConfig, TeamMemberConfig, WorkflowConfig, StepConfig,
  DIReference` (la convención que el Task 3.5 extenderá).
  **Req implícito (convención de re-export).**

## Phase 2: RED — `tests/unit/models/test_model_spec.py`

> Objetivo: escribir el test file ANTES de que el módulo exista. Cada test
> mapea a un escenario del spec (28 scenarios) + el test load-bearing del
> override del union (Task 2.7). `pytestmark = pytest.mark.unit` arriba del
> archivo (convención de `test_agent_config.py:17`). Header docstring estilo
> `test_agent_config.py:1-10` ("RED tests for ...").

- [ ] 2.1 **Header + marker + imports.** Crear
  `tests/unit/models/test_model_spec.py` con docstring explicando que cubre
  los 9 requisitos del spec + el override del union; `pytestmark = pytest.mark.unit`;
  imports `pytest`, `ValidationError` de pydantic, los 5 símbolos de
  `yaml_agno.models.model_spec` (RED: el import falla — esperado). **Req implícito (setup TDD).**
- [ ] 2.2 **`TestModelStringSpecGoldenPaths`** — cubre los 2 escenarios golden
  path del spec:
  - `ModelStringSpec.model_validate("anthropic:claude-sonnet-4-5")` → sin error,
    `.provider == "anthropic"`, `.id == "claude-sonnet-4-5"` (golden path).
  - `ModelStringSpec.model_validate("openai_responses:gpt-4o:fb-openai")` →
    sin error, `.raw.count(":") == 2` si existe `.raw`, o assert que el alias
    3er segmento se preserva (design literal no expone `.raw`; usar `.id`
    según contrato literal — confirmar contra design.md:184-250 antes de
    escribir; si el contrato no expone `raw`, ajustar el assert a los campos
    que sí existen).
  **Scenario: ModelStringSpec golden path / ModelStringSpec con alias (3 segmentos).
  Req: ModelStringSpec valida formato `provider:id`.**
- [ ] 2.3 **`TestModelStringSpecRejects`** — cubre los 3 escenarios RED del spec:
  - `acme:gpt-x` → `ValidationError` cuyo mensaje menciona `"acme"`.
  - `no_colon` → `ValidationError` exigiendo formato `provider:id`.
  - `a:b:c:d` → `ValidationError` por exceso de segmentos (regex no matchea 4
    segmentos; confirmar que el mensaje sea accionable).
  **Scenario: RED — provider desconocido / formato inválido (sin dos puntos) /
  formato inválido (4 segmentos). Req: ModelStringSpec valida formato `provider:id`.**
- [ ] 2.4 **`TestModelStringSpecAlias`** — cubre el escenario de alias a nivel
  schema (sin canonicalización):
  - `ModelStringSpec.model_validate("openai:gpt-4o")` → sin error (porque
    `"openai"` es clave directa de `SUPPORTED_PROVIDERS`), `.provider ==
    "openai"` (sin canonicalizar — la canonicalización es del resolver).
  **Scenario: Alias `openai` aceptado a nivel de schema.
  Req: ModelStringSpec acepta providers vía alias.**
- [ ] 2.5 **`TestModelExpandedSpecGoldenPath`** — cubre el escenario golden +
  default `provider_kwargs`-equivalente (design literal no expone
  `provider_kwargs`; expone los campos listados en design.md:334-373 —
  ajustar el assert a esos campos). Casos:
  - `ModelExpandedSpec(provider="anthropic", id="claude-sonnet-4-5",
    temperature=...)` — NOTA: design literal NO modela `temperature`/
    `max_tokens`/`top_p`/`top_k`/`stop_sequences`/`seed` (design.md:334-373
    no los lista). Cubrir SOLO los campos que el design literal expone
    (`name`, `retries`, `cache_response`, etc.). Documentar en el test que
    los generation params del spec §4.1 están deferred al wiring slice (3).
  - Default: `ModelExpandedSpec(provider="anthropic", id="x")` → sin
    overrides, los opcionales son `None`.
  **Scenario: ModelExpandedSpec golden path / `provider_kwargs` default
  (adaptado a los campos reales del design literal). Req: ModelExpandedSpec
  — forma expandida con parámetros.**
- [ ] 2.6 **`TestModelExpandedSpecRejects`** — cubre los escenarios RED del spec
  adaptados al design literal:
  - `provider="nonexistent"` → `ValidationError` mencionando el provider.
  - `retries=11` → `ValidationError` por exceder `le=10`.
  - clave desconocida `{"provider":"openai","id":"x","bogus":1}` →
    `ValidationError` por `extra="forbid"`.
  NOTA: el design literal NO modela `temperature`/`top_p` (no escribir
  asserts sobre ellos — rompería GREEN contra el contrato literal). Si se
  quieren, son un slice posterior.
  **Scenario: RED — provider ausente / retries excede el tope.
  Req: ModelExpandedSpec + Retry boundary.**
- [ ] 2.7 **⚠️ LOAD-BEARING — `TestModelSpecUnionOverride`**. Este es EL test
  crítico del slice. Cubre la composición entre el override de
  `ModelStringSpec.model_validate` y la resolución del union Pydantic V2.
  - `ModelSpec.__getitem__`/`TypeAdapter(ModelSpec).validate_python("anthropic:claude-sonnet-4-5")`
    → instancia `ModelStringSpec`, `.provider == "anthropic"`.
  - `TypeAdapter(ModelSpec).validate_python({"provider":"anthropic","id":"x"})`
    → instancia `ModelExpandedSpec`, `.provider == "anthropic"`.
  **Si este test va RED después del GREEN, el override está roto y el slice
  NO puede mergear.** Cubre los 2 escenarios del spec sobre el union.
  **Scenario: ModelSpec path str → ModelStringSpec / path dict →
  ModelExpandedSpec. Req: ModelSpec — unión discriminada str | dict.**
- [ ] 2.8 **`TestModelExpandedSpecRetryFields`** — cubre los 2 escenarios del
  "Retry boundary":
  - Defaults Agno-native: `ModelExpandedSpec(provider="anthropic", id="x")`
    sin overrides → los campos retry son `None` (design literal los modela
    como opcionales, no con defaults `0`/`True` — ajustar el assert al
    contrato literal: `assert spec.retries is None`, etc.).
  - Ausencia de knobs yaml-agno: `assert "retry_delay" not in
    ModelExpandedSpec.model_fields`, lo mismo con `wait_on_rate_limit` y
    `retry_jitter`.
  NOTA: spec.md §"Retry boundary" dice defaults (`retries==0`,
  `exponential_backoff is True`); el design literal los modela como
  `Optional` con default `None`. **Design > spec cuando divergen**
  (status: ready-for-tasks). Tests siguen el design literal.
  **Scenario: Defaults Agno-native / Ausencia de knobs yaml-agno.
  Req: Retry boundary — sólo campos Agno-native.**
- [ ] 2.9 **`TestFallbackConfig`** — cubre los 4 escenarios del "FallbackConfig"
  adaptados al design literal (design.md:253-296, NO spec.md §165-178):
  - Golden path: `FallbackConfig(fallback_models=["openai_responses:gpt-4o"])`
    → sin error.
  - RED enum: `FallbackConfig(fallback_models=["x"], strategy="banana")` →
    `ValidationError`.
  - RED `min_length=1`: `FallbackConfig(fallback_models=[])` →
    `ValidationError`.
  - Default `strategy="ordered"`.
  NOTA: el design literal expone `fallback_models` + `strategy`, NO
  `on_rate_limit`/`on_context_overflow`/`on_error`/`max_fallback_hops`/
  `propagate_session`/`fallback_callback`. Esos son del spec.md. **Design >
  spec**. Tests siguen el design literal verbatim.
  **Scenario: FallbackConfig golden path / RED enum / RED min_length /
  Defaults (adaptado). Req: FallbackConfig — schema autocontenido.**
- [ ] 2.10 **`TestProviderResolver`** — cubre los 4 escenarios del resolver +
  path dict + passthrough:
  - String con alias canonicalizado:
    `ProviderResolver().resolve(ModelStringSpec.model_validate("openai:gpt-4o"))`
    → `ModelExpandedSpec`-equivalente con `.provider == "openai_chat"`.
    NOTA: design.md:441-445 devuelve el MISMO tipo de spec (ModelStringSpec
    queda ModelStringSpec, no se convierte en ExpandedSpec). Ajustar el
    assert al contrato literal: la salida es `ModelStringSpec` con
    `.provider == "openai_chat"`. Documentar la divergencia spec vs design.
  - String con provider canónico: `resolve(spec_anthropic)` →
    `.provider == "anthropic"` (no-op).
  - RED provider desconocido post-alias: construir spec con alias inyectado
    custom (`ProviderResolver(aliases={"foo":"bar"})`, con spec `foo:x`) →
    `ValueError` nombrando el provider resuelto.
  - TypeError en tipo foráneo: `ProviderResolver().resolve(42)` → `TypeError`.
  **Scenario: Resolver — string con alias canonicalizado / string con
  provider canónico / RED rechaza provider desconocido / passthrough.
  Req: ProviderResolver — resolución y canonicalización.**
- [ ] 2.11 **`TestSSOT`** — cubre el escenario "Sin Literal hardcodeado":
  - `inspect.getsource(ModelExpandedSpec)` NO contiene un `Literal["anthropic",`
    pattern como anotación del campo `provider` (puede aparecer en otro
    contexto; el chequeo es sobre la anotación del campo).
  **Scenario: Sin Literal hardcodeado. Req: SSOT — catálogo único.**
- [ ] 2.12 **`TestAgentConfigModelUnchanged`** — regresión de la invariante
  ADR A1:
  - `from yaml_agno.models.config.agent_config import AgentConfig`;
    `AgentConfig.model_fields["model"].annotation is str` (no union, no
    ModelSpec).
  **Scenario: AgentConfig.model sigue siendo str (regresión).
  Req: AgentConfig.model permanece `str`.**
- [ ] 2.13 **`TestNoCrossImport`** — cubre el escenario "Ningún módulo
  importa las schemas nuevas":
  - Leer el source de `agent_config.py` y `agent_factory.py`; assert que ni
    `ModelStringSpec` ni `ModelExpandedSpec` ni `ModelSpec` ni
    `ProviderResolver` aparecen en los imports.
  **Scenario: Ningún módulo importa las schemas nuevas.
  Req: AgentConfig.model permanece `str`.**
- [ ] 2.14 **Correr la suite RED.** `pytest tests/unit/models/test_model_spec.py
  -m unit` → debe fallar colectivamente (ImportError o collection error por
  módulo inexistente). Confirmar que TODOS los tests fallan por la razón
  correcta (modulo no existe), no por errores de sintaxis del test.
  **Req implícito (TDD RED honesto).**

## Phase 3: GREEN — `src/yaml_agno/models/model_spec.py` (código LITERAL del design)

> Objetivo: implementar el módulo EXACTAMENTE como aparece en design.md:154-482.
> No desviarse, no "mejorar", no añadir campos que el spec menciona y el design
> no lista. Orden de declaración respeta la dependencia forward:
> `ModelStringSpec` → `FallbackConfig` → `ModelExpandedSpec` → `ModelSpec`
> union → `ProviderResolver`.

- [ ] 3.1 Crear `src/yaml_agno/models/model_spec.py` con el docstring del
  módulo (design.md:155-166), imports (`re`, `Any`, `Union`, pydantic pieces,
  `SUPPORTED_PROVIDERS` de `provider_capabilities`, `PROVIDER_ALIASES` de
  `registries`) y la regex `_PROVIDER_ID_RE` (design.md:181). **Req: SSOT (import del catálogo).**
- [ ] 3.2 Implementar `class ModelStringSpec(BaseModel)` LITERALMENTE como
  design.md:184-250. Esto incluye el `@classmethod model_validate` override
  que acepta bare string (design.md:217-222) — **el núcleo del test
  load-bearing 2.7**. **Req: ModelStringSpec valida formato `provider:id` +
  ModelStringSpec acepta providers vía alias.**
- [ ] 3.3 Implementar `class FallbackConfig(BaseModel)` LITERALMENTE como
  design.md:253-296 (`fallback_models` con `min_length=1, max_length=10`,
  `strategy` con field_validator restrictivo). Definir ANTES de
  `ModelExpandedSpec` (forward-ref avoidance, ADR A6). **Req: FallbackConfig
  — schema autocontenido.**
- [ ] 3.4 Implementar `class ModelExpandedSpec(BaseModel)` LITERALMENTE como
  design.md:299-388. Campos en orden: identity (`provider`, `id`) → Agno
  base passthrough (`name`, `model_type`) → structured outputs (2) →
  caching (3) → retry Agno-native (5) → `fallback: FallbackConfig | None`.
  `field_validator("provider")` contra `SUPPORTED_PROVIDERS` (NO `Literal`).
  **Req: ModelExpandedSpec + Retry boundary + SSOT.**
- [ ] 3.5 Definir `ModelSpec = Union[ModelStringSpec, ModelExpandedSpec]`
  (design.md:393) + `class ProviderResolver` (design.md:396-472) con
  `__init__(aliases)`, `resolve(spec)`, `_canonical_provider(provider)`.
  + `__all__` (design.md:475-481). **Req: ModelSpec unión + ProviderResolver.**
- [ ] 3.6 Modificar `src/yaml_agno/models/__init__.py`: añadir import de los
  5 símbolos desde `yaml_agno.models.model_spec` (design.md:489-496) y
  extender `__all__` en orden alfabético (design.md:498-500), + 2 líneas al
  docstring público (design.md:505-507). Mantener los imports existentes
  intactos. **Req implícito (convención de re-export).**

## Phase 4: Verification (GREEN conductual + zero blast radius)

> Objetivo: confirmar que los 28 escenarios + el test load-bearing pasan, que
> el lint/typecheck están limpios, y que NINGÚN archivo shipped fue mutado
> (invariante ADR A1).

- [ ] 4.1 `pytest tests/unit/models/test_model_spec.py -m unit` verde (≥14
  test functions cubriendo los 28 escenarios + override). Confirmar que
  **el Task 2.7 (override union test) está verde específicamente** — es la
  garantía de que el override compone con el union. **Scenario: colectivo de
  los 28 + override. Req: todos los 9.**
- [ ] 4.2 `python -c "from yaml_agno.models.model_spec import ModelSpec,
  ModelExpandedSpec, FallbackConfig, ProviderResolver, ModelStringSpec;
  print('ok')"` exit 0. **Smoke import (success criterion del proposal).**
- [ ] 4.3 `python -c "from yaml_agno.models import ModelSpec, ModelStringSpec,
  ModelExpandedSpec, FallbackConfig, ProviderResolver; print('ok')"` exit 0
  (re-export vía `__init__` sin circular import — el módulo nuevo sólo
  importa de `yaml_agno.di.*`). **Req implícito (convención re-export).**
- [ ] 4.4 `pytest` (suite completa) verde — los ~163 tests existentes siguen
  pasando sin modificación (slice aditivo, `AgentConfig` intacto). **Scenario:
  AgentConfig.model sigue siendo str (regresión). Req: AgentConfig.model
  permanece `str`.**
- [ ] 4.5 `ruff check src/yaml_agno/models/model_spec.py
  tests/unit/models/test_model_spec.py` sin findings. (F401 ok en
  `__init__.py` re-export, como en slice previo.) **Req implícito (lint).**
- [ ] 4.6 `mypy src/yaml_agno/models/model_spec.py` sin errores (si mypy está
  configurado en CI; design.md:550 lo lista como verificación opcional).
  **Req implícito (types).**
- [ ] 4.7 `git diff --name-only specs/ openspec/specs/` vacío (ningún SPEC
  editado — la corrección del drift §3.4 vive en proposal+design, no en
  specs/). **Scenario: spec/design no mutados por el apply.**
- [ ] 4.8 `git diff --name-only src/yaml_agno/models/config/agent_config.py
  src/yaml_agno/factories/agent_factory.py` vacío (zero blast radius, ADR A1).
  **Scenario: Ningún módulo importa las schemas nuevas.**
- [ ] 4.9 Confirmar que `proposal.md`, `spec.md`, y `design.md` no fueron
  modificados durante el apply (son inputs read-only del tasks→apply flujo).
  **Req implícito (artifact hygiene).**

## Phase 5: Commit granular (conventional commits)

> Objetivo: commits atómicos en orden lógico (RED primero, GREEN después,
  init y verify al final). No commitear `specs/` ni `openspec/specs/`.

- [ ] 5.1 `test: add RED tests for model_spec schemas (SPEC_14 slice #2)`
  (Phase 2 entera — el test file solo, todos los tests failing por módulo
  inexistente).
- [ ] 5.2 `feat(models): add model_spec schemas + ProviderResolver (SPEC_14
  slice #2)` (Phase 3.1-3.5 — el módulo nuevo completo).
- [ ] 5.3 `feat(models): re-export model_spec symbols from models/__init__`
  (Phase 3.6 — modificación de `__init__.py`).
- [ ] 5.4 (Opcional, sólo si la verificación 4.x descubrió algo) commit de
  ajustes puntuales. Si todo pasó limpio, omitir.

## TDD Compliance Matrix

> Mapeo de los 9 requisitos del spec → task RED → task GREEN → escenario(s)
> cubierto(s). Diseñado para que `sdd-verify` pueda auditar línea por línea.

| # | Requirement | RED (Task) | GREEN (Task) | Scenario(s) del spec |
|---|-------------|------------|--------------|----------------------|
| 1 | ModelStringSpec valida formato `provider:id` | 2.2, 2.3 | 3.2 | ModelStringSpec golden path / con alias (3 segmentos) / RED provider desconocido / RED formato inválido sin dos puntos / RED formato inválido 4 segmentos |
| 2 | ModelStringSpec acepta providers vía alias | 2.4 | 3.2 | Alias `openai` aceptado a nivel de schema |
| 3 | ModelExpandedSpec — forma expandida | 2.5, 2.6 | 3.4 | ModelExpandedSpec golden path / `provider_kwargs` default¹ / RED provider ausente² |
| 4 | Retry boundary — sólo Agno-native | 2.8 | 3.4 | Defaults Agno-native³ / Ausencia de knobs yaml-agno |
| 5 | FallbackConfig — schema autocontenido | 2.9 | 3.3 | FallbackConfig golden path⁴ / RED enum⁴ / RED min_length⁴ / Defaults⁴ |
| 6 | ModelSpec — unión discriminada str \| dict | **2.7 (load-bearing)** | 3.5 | ModelSpec path str → ModelStringSpec / path dict → ModelExpandedSpec |
| 7 | ProviderResolver — resolución y canonicalización | 2.10 | 3.5 | Resolver string con alias / string canónico / RED rechaza provider / path dict⁵ / passthrough⁵ |
| 8 | SSOT — catálogo único | 2.11 | 3.2, 3.4 | Sin Literal hardcodeado (+ Importabilidad del catálogo en Task 1.2) |
| 9 | AgentConfig.model permanece `str` | 2.12, 2.13 | (no GREEN — invariante) | AgentConfig.model sigue siendo str / Ningún módulo importa las schemas nuevas |

**Notas de divergencia spec vs design (design > spec, status: ready-for-tasks):**

¹ El design literal no modela `provider_kwargs` (design.md:334-373); el test
2.5 adapta el assert a los campos reales del design. Los generation params
(`temperature`/`max_tokens`/`top_p`/`top_k`/`stop_sequences`/`seed`) del spec
§4.1 NO están en el design literal → deferred al wiring slice.

² El spec lista `temperature=2.5`/`top_p=1.5` como RED scenarios; el design
literal no modela esos campos → tests 2.6 omiten esos casos (romperían GREEN
contra el contrato literal). Si se quieren, son slice posterior coordinado.

³ El spec dice defaults (`retries==0`, `exponential_backoff is True`); el
design literal los modela como `Optional` con default `None`. Tests 2.8
siguen el design literal: `assert spec.retries is None`.

⁴ El spec enumera `on_rate_limit`/`on_context_overflow`/`on_error`/
`max_fallback_hops`/`propagate_session`/`fallback_callback`; el design literal
expone `fallback_models` + `strategy` solamente. Tests 2.9 siguen el design
literal verbatim.

⁵ El spec Scenario "Resolver path dict" y "passthrough ModelExpandedSpec"
describen comportamientos que el design literal no implementa
(`ProviderResolver.resolve` recibe un `ModelSpec`, no un dict ni un
`ModelExpandedSpec` y devuelve el mismo tipo de spec sin reconstruir). Tests
2.10 se ajustan al contrato literal; los escenarios spec no cubiertos por el
design se documentan como divergencia — no se inventan.

## Implementation Order (critical)

> Respetar ESTE orden al escribir GREEN. Romperlo rompe la forward-ref
> invariant y fuerza `model_rebuild()` que el design explícitamente evita
> (ADR A6).

1. **Module header + imports + `_PROVIDER_ID_RE`** (Task 3.1).
2. **`ModelStringSpec`** (Task 3.2) — sin deps internas; incluye el
   `model_validate` override que el test 2.7 ejercita.
3. **`FallbackConfig`** (Task 3.3) — sin deps internas; ANTES de
   `ModelExpandedSpec` para que `fallback: FallbackConfig | None` resuelva
   sin forward ref.
4. **`ModelExpandedSpec`** (Task 3.4) — depende de `FallbackConfig`; el
   `field_validator("provider")` consulta `SUPPORTED_PROVIDERS` (SSOT, ADR A2).
5. **`ModelSpec` union + `ProviderResolver` + `__all__`** (Task 3.5) — el
   union al final, después de que ambos miembros existan; el resolver
   consume ambos + los registries del slice 1.
6. **`models/__init__.py` re-export** (Task 3.6) — al final, para no romper
   el smoke import mientras el módulo está a medio escribir.

**Early-write priority for the load-bearing test**: Task 2.7 debe estar en
el test file DESDE EL PRINCIPIO (no al final). Si se escribe al final, el
test colectivo puede pasar sin ejercitar el override, dejando el bug latente.
