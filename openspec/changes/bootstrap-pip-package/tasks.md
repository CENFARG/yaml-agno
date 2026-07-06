# Tasks: bootstrap-pip-package

> Change #1 de yaml-agno. Convierte el repo SPEC-only en un paquete pip
> instalable vacío, verde y con CI. **Sin lógica de negocio.** TDD honesto:
> skeleton sin RED conductual — el smoke test es ancla GREEN estructural.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~140-180 (pyproject ~95, CI ~35, smoke ~15, init root ~9, README/gitignore ~15) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (size well under budget) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Paquete instalable + smoke + CI (change completo) | PR único | base = `feature/specs-agno-coverage-10-25`; net-new, cero SPECs tocados |

## Open Items (CRÍTICO — leer antes de apply)

- **`core-cenf-py` es PRIVADO** (gh repo view → isPrivate:true). El CI local
  funciona por credenciales cacheadas; **CI en GitHub Actions FALLARÁ** hasta
  que el repo `CENFARG/yaml-agno` tenga el secret `GIT_AUTH_TOKEN` (PAT con
  read access a `CENFARG/core-cenf-py`). El workflow debe inyectar credenciales
  git antes de `pip install -e .` (Task 3.3). La primera corrida CI puede ser
  RED hasta que el secret se añada — **esperado**, no blocker del apply.
- **Decisión de producto abierta** (fuera de este task list): mantener
  `core-cenf-py` privado (usar PAT) vs publicarlo en PyPI (eliminar el
  requisito del secret). No lo resuelve este bootstrap.

## Phase 1: Foundation — metadata y raíz del paquete

- [ ] 1.1 Verificar baseline limpio: `git status` sin cambios sin commitear,
  HEAD en `cf5bd31` (branch `feature/specs-agno-coverage-10-25`). **Req: Rollback Plan (baseline obligatorio).**
- [ ] 1.2 Crear `pyproject.toml` con el contenido modelo del design §pyproject.toml model (hatchling, src-layout, deps `agno==2.6.22`, `core-cenf-py @ git+...@v0.1.0`, `pydantic>=2.0`, `pyyaml>=6.0`, extras `dev`, ruff/mypy/pytest config). **Req: Dependencias pinneadas / Instalabilidad editable / Versión SSOT / Lint / Types.**
- [ ] 1.3 Crear `src/yaml_agno/__init__.py` con el bloque `__version__` vía `importlib.metadata.version("yaml-agno")` (design §src/yaml_agno tree). **Req: Versión SSOT.**

## Phase 2: Namespaces canónicos vacíos

- [ ] 2.1 Crear los **21** `src/yaml_agno/{sub}/__init__.py` vacíos (0 bytes):
  `api, factories, models, di, persistence, memory, workflows, tools,
  knowledge, media, hitl, guardrails, skills, culture, reasoning, evals,
  scheduler, config, tracing, templates, runtime`. **Req: Namespaces canónicos vacíos e importables.**

## Phase 3: TDD estructural — smoke test + infraestructura

> Honesto: NO hay RED conductual. El smoke test es el ancla GREEN que valida
> end-to-end que wheel target, nombre de paquete e `__init__.py` están
> coherentes. Se escribe ANTES de declarar done (TDD de estructura).

- [ ] 3.1 Escribir `tests/test_smoke.py` (2 tests del design: `test_package_version_matches_pyproject`, `test_package_is_importable`). **Req: Smoke test day-1 green.**
- [ ] 3.2 Extender `.gitignore`: tras diff contra el actual, añadir SOLO `*.whl`, `src/*.egg-info/`, `src/yaml_agno.egg-info/` (sin duplicar lo ya presente). **Req implícito (higiene build artifacts).**
- [ ] 3.3 Crear `.github/workflows/ci.yml`: matrix `[3.12, 3.13]`, `cache: pip`, pasos `ruff check` + `mypy src/yaml_agno` + `pytest`. **INCLUIR** el paso de inyección de credenciales para el dep privado: `git config --global url."https://x-access-token:${{ secrets.GIT_AUTH_TOKEN }}@github.com/".insteadOf "https://github.com/"` ANTES de `pip install -e ".[dev]"`. Documentar en comentario del YAML que sin el secret el job falla. **Req: CI workflow válido y matriz.**
- [ ] 3.4 Crear `README.md` mínimo (1 párrafo: qué es yaml-agno + cómo `pip install -e ".[dev]"`). **Req implícito (readme = PEP 621 field).**

## Phase 4: Verificación (GREEN estructural)

- [ ] 4.1 `pip install -e ".[dev]"` verde (Python 3.12 y 3.13). **Scenario: Instalación editable 3.12 / 3.13.**
- [ ] 4.2 `python -c "import yaml_agno; print(yaml_agno.__version__)"` imprime `0.1.0`. **Scenario: Versión leída desde metadata.**
- [ ] 4.3 Import de los 21 sub-paquetes sin error. **Scenario: Todos los sub-paquetes son importables.**
- [ ] 4.4 `python -m pytest` verde (2/2), `pytest-asyncio` cargando. **Scenario: Pytest verde.**
- [ ] 4.5 `ruff check .` sin findings (F401 ok en `__init__.py`). **Scenario: Ruff sin findings.**
- [ ] 4.6 `mypy src/yaml_agno` sin errores. **Scenario: Mypy sin errores.**
- [ ] 4.7 `git diff --name-only specs/` vacío (ningún SPEC editado). **Scenario: specs/ sin cambios.**

## Phase 5: Commit granular (conventional commits)

- [ ] 5.1 Commits atómicos en orden: `chore: add pyproject.toml and package root` (1.2+1.3) → `chore: add 21 canonical empty namespaces` (2.1) → `test: add package smoke test` (3.1) → `chore: extend gitignore for build artifacts` (3.2) → `ci: add github actions workflow with private dep auth` (3.3) → `docs: add minimal README` (3.4). **No commitear specs/.**
