# Tasks: model-resilience-runtime (SPEC_14 slice #4 — DOMAIN)

> Tres componentes puros bajo `src/yaml_agno/models/` cierran la capa DOMINIO
> de resiliencia: `build_fallback_chain`, `CacheKeyBuilder`,
> `FallbackErrorClassifier`. Strict TDD RED→GREEN por comportamiento. Sin
> runtime, sin async, sin red — cableado es SPEC_09.

---

```yaml
change: model-resilience-runtime
spec: SPEC_14
slice: "SPEC_14 #4 (DOMAIN-only)"
status: tasked
artifact: tasks
artifact_store: hybrid
depends_on:
  - openspec/changes/model-resilience-runtime/proposal.md
  - openspec/changes/model-resilience-runtime/specs/model-resilience-runtime/spec.md
  - openspec/changes/model-resilience-runtime/design.md
  - engram://doc.reca/sdd/model-resilience-runtime/proposal
  - engram://doc.reca/sdd/model-resilience-runtime/spec
  - engram://doc.reca/sdd/model-resilience-runtime/design
strict_tdd: true
test_command: python -m pytest tests/unit/models/ -m unit
```

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~305 (3 src ~155 + 3 tests ~150) |
| 400-line budget risk | Low-Medium |
| Chained PRs recommended | No |
| Suggested split | single PR (well under 400 budget) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low-Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | 3 domain modules + 3 RED/GREEN test files + `__init__` re-export | PR único | base = tracker branch; net-new additive, cero SPEC_05/09 refs |

## Open Items (CRÍTICO — leer antes de apply)

- **DISCREPANCIA `max_fallback_hops` vs spec scenario**: el spec scenario
  "truncado a max_fallback_hops" con `max_fallback_hops=2` espera `2+1=3`
  entradas (primario más 2 hops). El design literal usa
  `chain[:max_fallback_hops]` → con `max_hops=2` produce **2** entradas
  (longitud 2, no 3). El Requirement text dice "truncarse a
  `max_fallback_hops + 1` entradas". **Resolver en apply**: muy probablemente
  `chain[:max_hops + 1]` (primario + N hops). El test RED debe fijar la
  expectativa correcta ANTES de escribir GREEN — que el test decida, no el
  copy-paste del design.
- **Verificación runtime Agno** (Task 2.1): `from agno.exceptions import
  ModelRateLimitError, ContextWindowExceededError, ModelProviderError` Y
  `hasattr(ModelProviderError, "classify")` — ya verificado por orquestador,
  pero el primer test classifier debe re-confirmar (risk R1/R5). Si falla,
  STOP apply.
- **`ModelProviderError.classify` return type**: design asume devuelve una
  instancia de excepción (subclass); el classifier `isinstance`-checa el
  resultado. Si devuelve string/enum, ajustar 1 línea en el branch de
  delegación (R5).

---

## Phase 1: Baseline (ROJO falso —-setup, no TDD conductual)

- [x] 1.1 Verificar baseline limpio: `git status` sin cambios sin commitear;
  HEAD en el branch tracker. Confirmar `src/yaml_agno/models/__init__.py`
  existe con sus 6 re-exports actuales. **Req: Rollback Plan (baseline).**
- [x] 1.2 Confirmar que `ProviderFactory.build` (slice #3) YA está shipped en
  `src/yaml_agno/di/provider_factory.py` y exporta `ProviderFactory`.
  Confirmar `parse_model_spec`, `ProviderResolver`, `FallbackConfig`,
  `ModelExpandedSpec` en `src/yaml_agno/models/model_spec.py`. **Req deps:
  build_fallback_chain devuelve instancias (Req 1, Req 2).**
- [x] 1.3 Sanity runtime: `python -c "from agno.exceptions import
  ModelRateLimitError, ContextWindowExceededError, ModelProviderError;
  print(hasattr(ModelProviderError, 'classify'))"` → `True`. **Req:
  FallbackErrorClassifier adaptador Agno (Req 6, Req 7).**

## Phase 2: RED — tests fallando primero (strict TDD)

> Un test file por componente. Marker `@pytest.mark.unit` en cada test.
> Estilo: `tests/unit/models/test_model_spec.py` (pure Pydantic, sin network).

- [x] 2.1 `tests/unit/models/test_fallback_classifier.py` — imports Agno +
  `hasattr(ModelProviderError, "classify")` guard (si missing → SKIP con
  razón, no xfail). RED: `ModuleNotFoundError` (módulo no existe).
  **Req 6/7 — Scenarios: classify rate_limit, classify context_overflow,
  classify error genérico, ModelProviderError delega.**
- [x] 2.2 `tests/unit/models/test_fallback_classifier.py` — 4 tests: (a)
  `ModelRateLimitError(...)` → `"rate_limit"`; (b)
  `ContextWindowExceededError(...)` → `"context_overflow"`; (c) `ValueError`
  → `"error"`; (d) mock subclass de `ModelProviderError` cuyo `.classify`
  retorna `ModelRateLimitError` → `"rate_limit"` (delegación). RED: símbolo
  `FallbackErrorClassifier` no importable.
- [x] 2.3 `tests/unit/models/test_cache_key.py` — 4 tests: (a) mismo input →
  mismo digest (64 hex, prefix `ya:ck:v1:`); (b) `temperature=0.7` vs `0.9` →
  keys distintos; (c) `messages_hash` distinto → key distinto; (d) misma
  `model_dump` reordenada (vía dict rebuild) → key estable (sort_keys).
  **Req 4/5 — Scenarios: determinismo, temperatura, messages stable.**
- [x] 2.4 `tests/unit/models/test_fallback_chain.py` — stub `ProviderFactory`
  (dataclass que registra `spec.provider` y devuelve
  `{"provider": spec.provider, "id": spec.id}` tagged dict, sin red). Tests:
  (a) `fallback is None` → lista de 1 entrada (primaria); (b) golden
  `["openai:gpt-4o"]` → 2 entradas, índice 0 = primaria; (c) truncación con
  `max_fallback_hops=2` y 4 fallbacks → **resolver longitud esperada según
  Open Item** (3 si `chain[:max_hops+1]`, 2 si `chain[:max_hops]`); (d)
  `{"alias": "fb-openai"}` → `NotImplementedError` con mensaje mencionando
  definitions registry/TASK_013; (e) str ref canonicaliza alias
  `"openai"`→`"openai_chat"` (factory recibe provider canónico); (f) dict
  ref `{"provider":"google","id":"gemini-2.5-pro"}` sin aliasing.
  **Req 1/2/3 — Scenarios: cadena dorada, sin fallback, truncado, str-ref,
  dict-ref, alias rechazado.**
- [x] 2.5 Invariante (Req 8): test en `test_fallback_chain.py` que usa
  `pkgutil`/importlib para afirmar que NINGÚN módulo bajo
  `src/yaml_agno/{models}` introduce `CircuitBreaker`, `call_with_fallback`,
  `RetryPolicy`, `compute_delay`, `dispatch_fallback_callback`,
  `probe_models_health` (grep sobre source de los 3 módulos nuevos).
  **Req 8 — Scenario: no-circuit-breaker invariant.**

## Phase 3: GREEN — implementación mínima (código literal del design)

> Copiar del design.md literal. NO improvisar signatures. Ajustar
> `max_fallback_hops` según lo fijado por el test RED (Open Item).

- [x] 3.1 `src/yaml_agno/models/fallback_classifier.py` — clase
  `FallbackErrorClassifier` con `@staticmethod classify(exc) -> Literal[...]`
  exactamente como design §fallback_classifier.py. **Req 6, Req 7.**
- [x] 3.2 `src/yaml_agno/models/cache_key.py` — clase `CacheKeyBuilder` con
  `@staticmethod build(spec, *, messages_hash, tool_defs_hash="",
  response_model_hash="") -> str`, `_PREFIX = "ya:ck:v1:"`,
  `ErrorCategory`/payload via `json.dumps(sort_keys=True,
  separators=(",",":"))` + `sha256().hexdigest()`. **Req 4, Req 5.**
- [x] 3.3 `src/yaml_agno/models/fallback_chain.py` — función
  `build_fallback_chain(primary, factory, *, resolver=None) -> list[Any]`
  literal del design. **Ajustar** el slice de truncación
  (`chain[:max_hops]` vs `chain[:max_hops+1]`) según lo que el test RED 2.4
  haya fijado como expectativa correcta. **Req 1, Req 2, Req 3.**
- [x] 3.4 `src/yaml_agno/models/__init__.py` — añadir 3 re-exports
  (`build_fallback_chain`, `CacheKeyBuilder`, `FallbackErrorClassifier`) y
  extender `__all__` (orden alfabético, F401 cubierto por per-file-ignores).
  **Req: re-export público (Success Criteria).**

## Phase 4: Verificación (GREEN conductual + invariantes)

- [x] 4.1 `python -m pytest tests/unit/models/ -m unit` verde al 100% sobre
  los 3 módulos nuevos. **Scenario: cobertura total 3 módulos.**
- [x] 4.2 `ruff check .` sin findings (F401 ok en `__init__.py`). **Scenario:
  Ruff limpio.**
- [x] 4.3 `mypy src/yaml_agno` sin errores (`ignore_missing_imports` ya
  cubre `agno.*`). **Scenario: Mypy limpio.**
- [x] 4.4 Smoke import: `python -c "from yaml_agno.models import
  build_fallback_chain, CacheKeyBuilder, FallbackErrorClassifier"` sin error.
  **Scenario: re-export público.**
- [x] 4.5 Runtime: `FallbackErrorClassifier.classify(ModelRateLimitError())`
  → `"rate_limit"`. **Scenario: classify rate_limit runtime.**
- [x] 4.6 Runtime: `CacheKeyBuilder.build(spec, messages_hash="x")` estable
  entre dos llamadas y distinto al cambiar `temperature`. **Scenario:
  determinismo runtime.**
- [x] 4.7 Runtime: `build_fallback_chain` con factory stub trunca a
  `max_fallback_hops` según definición final (ver Open Item). **Scenario:
  truncación runtime.**
- [x] 4.8 `git diff --name-only specs/` y
  `git diff --name-only src/yaml_agno/di/provider_factory.py
  src/yaml_agno/models/model_spec.py` vacíos (sólo `models/__init__.py` +
  3 archivos nuevos modificados). **Req 8 (no tocar dependencias
  shipped).**
- [x] 4.9 Invariante DEFER (Req 8): grep confirma cero referencias a
  `CircuitBreaker`, `call_with_fallback`, `RetryPolicy`, `compute_delay`,
  `dispatch_fallback_callback`, `probe_models_health` en los 3 módulos
  nuevos. **Scenario: no-circuit-breaker invariant.**

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 Commits atómicos en orden:
  `test: add fallback_classifier RED tests` (2.1+2.2) →
  `feat: add FallbackErrorClassifier thin Agno adapter` (3.1) →
  `test: add cache_key RED tests` (2.3) →
  `feat: add CacheKeyBuilder deterministic sha256 key` (3.2) →
  `test: add fallback_chain RED tests` (2.4+2.5) →
  `feat: add build_fallback_chain instance assembler` (3.3) →
  `feat: re-export resilience domain symbols from models __init__` (3.4).
  **No commitear specs/ ni design.md cambios.**

---

## TDD Compliance Matrix (9 Reqs × RED→GREEN × Scenario)

| Req | RED Task | GREEN Task | Scenario cubierto |
|-----|----------|------------|-------------------|
| 1 — chain retorna instancias ordenadas, primary idx 0, truncada | 2.4 | 3.3 | cadena dorada; sin fallback; truncado |
| 2 — parsea str/dict via parse_model_spec + ProviderResolver | 2.4 | 3.3 | str-ref canonicaliza; dict-ref expandido |
| 3 — rechaza `{"alias": name}` con NotImplementedError | 2.4 | 3.3 | alias-ref rechazado |
| 4 — CacheKeyBuilder hex sha256 determinista 64 chars | 2.3 | 3.2 | mismo input→mismo key; temperatura distinta |
| 5 — stable-sort messages antes de hashear | 2.3 | 3.2 | messages reordenados→mismo key |
| 6 — classify mapea a Literal routing | 2.2 | 3.1 | classify rate_limit; context_overflow; error genérico |
| 7 — adaptador delgado (delega a `ModelProviderError.classify`) | 2.2 | 3.1 | ModelProviderError genérico delega |
| 8 — sin CircuitBreaker/RetryPolicy/call_with_fallback | 2.5 | (invariante) | no-circuit-breaker invariant |
| 9 — no cache store (dedup key only) | 2.3 | 3.2 | (implícito — sin get/set/invalidate en la API) |

## Implementation Order

1. **Phase 1** (baseline + sanity Agno) — prereq de todo.
2. **classifier primero** (2.1-2.2 → 3.1): es el más aislado, depende sólo de
   `agno.exceptions`. Valida el supuesto runtime (R1/R5) cuanto antes.
3. **cache_key segundo** (2.3 → 3.2): puro, sin dependencias más allá de
   `ModelExpandedSpec`.
4. **fallback_chain último** (2.4-2.5 → 3.3): integra `ProviderFactory` +
   `parse_model_spec` + `ProviderResolver` — el más acoplado; resolver el
   Open Item `max_fallback_hops` en su test RED antes de GREEN.
5. **`__init__` re-export** (3.4) al cierre, cuando los 3 símbolos ya existen.
6. **Phase 4** verificación + **Phase 5** commits granulares.

Razón: el orden va de menor a mayor acoplamiento y de mayor a menor riesgo de
supuesto runtime. Si Agno cambió una firma, lo descubrimos en el primer GREEN
del classifier, no al final.
