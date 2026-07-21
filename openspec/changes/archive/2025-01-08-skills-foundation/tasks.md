---
change: skills-foundation
spec: SPEC_30
artifact: tasks
status: tasked
artifact_store: hybrid
depends_on: [proposal, spec, design]
strict_tdd: true
test_command: "python -m pytest"
---

# Tasks: Skills Foundation — Schema + Factory (SPEC_30, Slice A)

> SPEC_30 slice A. Adapter puro: `SkillsConfig` (Pydantic V2) +
> `SkillsFactory.build` (delegación a `agno.skills`). **Cero lógica de
> skills reimplementada.** Wiring de `AgentFactory` DEFERRED a slice B (A4).
> Strict TDD: RED → GREEN → REFACTOR por tarea conductual.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~200 (schema.py ~45, factory.py ~55, __init__.py ~7, tests ~90) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (3 files src + 1 file tests; well under budget) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | SkillsConfig + SkillsFactory + re-exports + tests (slice A completo) | PR único | base = trunk; 2 NEW src + 1 MODIFY src + 1 NEW test file |

## Open Items

- **Naming deviation intencional**: SPEC_30 §4.4 nombra la factoría
  `SkillsConfigFactory`; este slice usa `SkillsFactory` (convención bare-noun
  de `ToolFactory`/`AgentFactory`). Documentado en design A3 — no requiere
  resolución, es decisión baked.
- **Spec habla de `entries` (multi-loader); design A5 + código literal usan
  single-loader (`path` + `validate` → un `LocalSkills`)**. El design es la
  decisión final (A5: una sola entrada por `SkillsConfig`). Si slice B
  requiere multi-directorio, el schema cambia ahí. No bloquea slice A.

## Phase 1: Baseline

- [x]1.1 Verificar baseline limpio: `git status` sin cambios sin commitear;
  `src/yaml_agno/skills/__init__.py` existe como stub vacío (0 bytes).
  **Req: Rollback Plan (baseline obligatorio).**

## Phase 2: RED — tests de schema y factory (fallback GREEN estructural primero)

> Orden: primero crear los archivos vacíos para que los imports de los tests
> resuelvan (skeleton), luego escribir los tests (RED conductual). Strict TDD:
> los tests se escriben ANTES de la implementación.

- [x]2.1 Crear `tests/unit/skills/__init__.py` (vacío) y
  `tests/unit/skills/test_skills_factory.py` con los **6 tests** del design
  §Testing (literal): `test_build_none_returns_none`,
  `test_build_missing_path_rejected`, `test_build_extra_keys_rejected`,
  `test_build_dict_returns_skills_with_localskills`,
  `test_build_invalid_skill_raises_when_validate_true`,
  `test_build_invalid_skill_skipped_when_validate_false`. Helper
  `_write_valid_skill(skill_dir, name)`. Todos con `@pytest.mark.unit`.
  **Req: SkillsFactory.build contrato (R2, R7). Scenario: golden build / None on empty / validate=True / validate=False.**
- [x]2.2 Añadir tests de schema pura (validación Pydantic sin tocar Agno):
  `test_skillsconfig_valid_entry` (`path` + `validate=True` aceptados),
  `test_skillsconfig_rejects_unknown_keys` (`extra="forbid"` →
  `ValidationError`), `test_skillsconfig_validate_defaults_true`,
  `test_skillsconfig_path_min_length_1`. **Req: SkillsConfig schema (R1). Scenario: entrada válida / rechaza claves desconocidas.**
- [x]2.3 Confirmar RED: `python -m pytest tests/unit/skills/ -v` — todos
  FALLAN (ImportError: no existe `yaml_agno.skills.schema` ni `.factory`, ni
  re-exports en `__init__.py`). **GATE RED: cero tests pasan sin implementación.**

## Phase 3: GREEN — implementación (código literal del design)

> Una tarea por archivo, en orden de dependencia: schema → factory →
> re-exports. Tras cada tarea, los tests correspondientes pasan de RED a GREEN.

- [x]3.1 Crear `src/yaml_agno/skills/schema.py` con `SkillsConfig(BaseModel)`
  (código literal design §schema.py): `model_config = ConfigDict(extra="forbid")`,
  `path: str = Field(..., min_length=1, ...)`, `validate: bool = Field(default=True, ...)`.
  `__all__ = ["SkillsConfig"]`. **Req: SkillsConfig schema (R1).**
  **GREEN parcial:** tests 2.2 pasan.
- [x]3.2 Crear `src/yaml_agno/skills/factory.py` con `SkillsFactory.build(cls,
  config: SkillsConfig | dict[str, Any] | None) -> Skills | None` (código
  literal design §factory.py): `_CONFIG_ADAPTER = TypeAdapter(SkillsConfig)`,
  early-return `None` si `config is None`, `TypeAdapter.validate_python` si
  `dict`, `LocalSkills(path=cfg.path, validate=cfg.validate)` →
  `Skills(loaders=[local_skills])`. **Req: SkillsFactory.build contrato (R2) / construye LocalSkills (R3) / envuelve en Skills (R4) / None on empty (R7).**
  **GREEN parcial:** tests 2.1 excepto los que requieren re-export.
- [x]3.3 Modificar `src/yaml_agno/skills/__init__.py`: re-exportar
  `SkillsConfig` (de `.schema`) y `SkillsFactory` (de `.factory`);
  `__all__ = ["SkillsConfig", "SkillsFactory"]` (código literal design
  §__init__.py). **Req: API pública re-exportada (proposal Success Criteria).**
  **GREEN total:** tests 2.1 + 2.2 todos pasan.

## Phase 4: Verificación (GREEN conductual + GATES de contrato)

- [x]4.1 `python -m pytest tests/unit/skills/ -v` — **6 + 4 = 10 tests**
  verde (0 failed, 0 errors). **Scenario: golden build / validate=True / validate=False / None on empty.**
- [x]4.2 `ruff check src/yaml_agno/skills/` limpio (F401 ok en `__init__.py`
  por `per-file-ignores`; E501 ignorado por line-length=120 + formatter).
  **Req implícito (lint).**
- [x]4.3 `mypy src/yaml_agno/skills/` limpio (strict, python 3.12;
  `agno.*` tiene `ignore_missing_imports`). **Req implícito (types).**
- [x]4.4 Cold import smoke:
  `python -c "from yaml_agno.skills import SkillsConfig, SkillsFactory; print('ok')"`
  imprime `ok`. **Req: API pública importable.**
- [x]4.5 **GATE Option B**: `src/yaml_agno/models/config/agent_config.py`
  sin cambios — `AgentConfig.skills` permanece `dict[str, Any] | None` opaco,
  sin referencia a `SkillsConfig`. **Req: AgentConfig.skills opaco (R8). Scenario: invariante opaco.**
- [x]4.6 **GATE no-regresión**: `python -m pytest` (suite completa) verde —
  los tests existentes (`test_agent_factory`, `test_tool_factory`, etc.) no
  se rompen por la adición del sub-paquete skills.
- [x]4.7 **GATE thin adapter**: grep confirma que ni `schema.py` ni
  `factory.py` contienen lógica de parsing/validación de `SKILL.md` propia
  (solo `TypeAdapter`, `LocalSkills(...)`, `Skills(...)`).

## Phase 5: Commit granular (conventional commits)

- [x]5.1 Commits atómicos en orden:
  `test: add skills-foundation RED tests (schema + factory)` (Phase 2) →
  `feat: add SkillsConfig schema for SPEC_30 slice A` (3.1) →
  `feat: add SkillsFactory thin adapter for SPEC_30 slice A` (3.2) →
  `feat: re-export SkillsConfig and SkillsFactory from skills package` (3.3).
  **No commitear cambios en `agent_config.py`** (no debe haberlos).

## TDD Compliance Matrix

| Req | RED (test) | GREEN (impl) | Scenario |
|-----|-----------|--------------|----------|
| R1 SkillsConfig schema | 2.2 (4 tests) | 3.1 schema.py | entrada válida / rechaza unknown keys / validate default / min_length |
| R2 SkillsFactory.build contrato | 2.1 (6 tests) | 3.2 factory.py | golden build / None on empty |
| R3 construye LocalSkills loaders | 2.1 (test_build_dict_returns_skills_with_localskills) | 3.2 factory.py | Skills instance tiene skills cargadas |
| R4 envuelve loaders en Skills | 2.1 (test_build_dict_returns_skills_with_localskills) | 3.2 factory.py | Skills(loaders=...) construido |
| R5 SkillValidationError propaga (validate=True) | 2.1 (test_build_invalid_skill_raises_when_validate_true) | 3.2 factory.py | validate=True rechaza skill inválida |
| R6 validate=False omite validación | 2.1 (test_build_invalid_skill_skipped_when_validate_false) | 3.2 factory.py | validate=False omite validación |
| R7 retorna None en None/vacío | 2.1 (test_build_none_returns_none) | 3.2 factory.py | None on empty config |
| R8 AgentConfig.skills opaco (Option B) | 4.5 GATE (no-test: diff invariant) | n/a (no se toca) | invariante opaco de AgentConfig |

## Implementation Order

**Estrictamente secuencial** — cada paso depende del anterior:

1. **Baseline** (1.1) — confirmar punto de partida limpio.
2. **RED** (2.1 → 2.2 → 2.3) — escribir los 10 tests; confirmar que TODOS
   fallan (no hay implementación todavía). Skeleton vacío solo para que los
   imports resuelvan.
3. **GREEN** (3.1 → 3.2 → 3.3) — implementar en orden de dependencia:
   `schema.py` primero (sin dependencias), `factory.py` después (importa
   `schema`), `__init__.py` al final (re-exporta ambos). Tras 3.3, todos los
   tests pasan.
4. **Verificación** (4.1–4.7) — suite completa + lint + types + cold import
   + GATE Option B + GATE no-regresión + GATE thin adapter.
5. **Commit** (5.1) — commits atómicos por archivo lógico.

No hay paralelismo: es una cadena lineal de 3 archivos con dependencias
unidireccionales (`schema ← factory ← __init__`).
