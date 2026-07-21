# Proposal: bootstrap-pip-package

> **Cambio #1 del proyecto yaml-agno.** Es el FIRST change: el repo hoy es
> SPEC-only (34 SPECs + DECISIONES.md, sin `pyproject.toml`, sin `src/`, sin
> `tests/`). Este cambio crea el esqueleto del paquete pip **vacío, verde,
> instalable y con CI pasando**. Sin lógica de negocio.

## Intent

El proyecto yaml-agno tiene 34 SPECs verificados (gate 34/34) pero **no existe
como paquete Python instalable**. Sin `pyproject.toml`, `src/` y `tests/`, ningún
SPEC puede aplicarse (no hay `import yaml_agno`, no hay runner de tests, no hay
lint). Este cambio crea el esqueleto mínimo para que la máquina SDD/TDD arranque:
un paquete `yaml_agno` pip-installable con las 21 carpetas canónicas **vacías**,
un smoke test que valide `import` + `__version__`, y CI en GitHub Actions.

**Éxito**: `pip install -e .` verde, `import yaml_agno` funciona, `pytest` verde
(1 test), `ruff check` limpio, CI verde en Python 3.12 y 3.13.

## Scope

### In Scope
- `pyproject.toml` (PEP 621, hatchling, requires-python `>=3.12,<3.14`).
- `src/yaml_agno/__init__.py` con `__version__` vía `importlib.metadata.version("yaml-agno")`.
- 21 sub-paquetes canónicos (§DECISIONES 4bis) cada uno con `__init__.py` **vacío**.
- `tests/test_smoke.py` (assert `yaml_agno.__version__ == "0.1.0"`).
- `.github/workflows/ci.yml` (matrix Python 3.12+3.13, `ruff check` + `pytest`).
- Extensión mínima de `.gitignore` (build artifacts de hatchling).
- `README.md` minimal (1 párrafo: qué es yaml-agno + cómo `pip install -e .`).

### Out of Scope (cambios posteriores — explícitos)
- **CUALQUIER lógica de negocio**: AgentConfig schema (change #2), factories,
  persistence, memory, workflows, DI, tools, knowledge, media, hitl, guardrails,
  skills, culture, reasoning, evals, scheduler, config loader, tracing,
  templates, runtime/server.
- **Edición de SPECs** (incluida la corrección cosmética de SPEC_06 — ver
  *Open Items*; es un task separado del orquestador, no de este bootstrap).
- **Creación del repo GitHub remoto** (paso inmediato siguiente, fuera del
  bootstrap; el CI workflow queda listo para cuando el remote exista).
- Migración de `core-cenf-py` a git+https/PyPI (hoy editable local path).

## Capabilities

### New Capabilities
- `package-skeleton`: estructura de paquete pip instalable con layout src,
  21 namespaces vacíos canónicos, metadata PEP 621, y CI que valida
  importabilidad + lint + smoke test. No define comportamiento de negocio; es
  el contenedor vacío sobre el que se insertarán las capabilities de cada SPEC.

### Modified Capabilities
- *None*. El repo no tiene capabilities previas (no hay código).

## Approach

**Layout src (PEP 621)** idéntico al de `core-cenf-py`: `src/yaml_agno/` como
package root (underscore = nombre pip `yaml-agno` → `import yaml_agno`).
Build backend **hatchling** con `[tool.hatch.build.targets.wheel]
packages = ["src/yaml_agno"]`. Las 21 sub-carpetas canónicas (DECISIONES §4bis)
reciben cada una un `__init__.py` **vacío** — no `.gitkeep` — porque (a) son
namespaces Python canónicos, (b) quedan importables de inmediato (cero churn
cuando un SPEC aterrice), (c) git solo trackea dirs con un sentinel y
`__init__.py` es el sentinel idiomático.

**`__version__` SSOT** vía `importlib.metadata.version("yaml-agno")`; el valor
`"0.1.0"` vive en `pyproject.toml` (única fuente). El smoke test importa el
paquete y asserts igualdad — estricto TDD day-1 green.

**Dependencias pinneadas y verificadas** (ver *Dependencies*). Regla: pin exacto
en agno (fidelidad a SPECs verificados), heredar versiones de agno donde sea
posible (pydantic, pyyaml) para no duplicar constraints.

**CI**: GitHub Actions matrix `[3.12, 3.13]`, pasos `ruff check` + `pytest`,
cache de pip wheels (agno trae transitivas pesadas). El workflow se commitea
ahora aunque el remote GitHub se cree en el paso siguiente — queda listo.

**Reglas de oro respetadas**: *build ON TOP, never frankenstein* (solo esqueleto,
cero reimplementación); código/identifiers en inglés, narrativa SPEC/proposal en
español; nada escrito fuera de `C:\Dropbox\DOC.RECA\06-Software\yaml-agno`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | New | Metadata PEP 621, hatchling, deps pinneadas, ruff/mypy/pytest config. |
| `src/yaml_agno/__init__.py` | New | `__version__` vía importlib.metadata. Package root. |
| `src/yaml_agno/{21 subdirs}/__init__.py` | New | 21 archivos vacíos (api, factories, models, di, persistence, memory, workflows, tools, knowledge, media, hitl, guardrails, skills, culture, reasoning, evals, scheduler, config, tracing, templates, runtime). |
| `tests/test_smoke.py` | New | 1 test: `import yaml_agno` + `__version__ == "0.1.0"`. |
| `.github/workflows/ci.yml` | New | Matrix Python 3.12/3.13, ruff + pytest. |
| `.gitignore` | Modified | Append build artifacts (dist/, build/, *.egg-info, .ruff_cache/, .mypy_cache/, .pytest_cache/). |
| `README.md` | New | 1 párrafo descriptivo + `pip install -e .`. |

## Dependencies

| Dep | Pin | Mecanismo | Justificación / verificación |
|-----|-----|-----------|------------------------------|
| `agno` | `==2.6.22` | PyPI | **VERIFICADO SEGURO** por adversarial drift check (Engram obs 1866, topic_key `yaml-agno/agno-2.6.22-drift-verify`): cero breaking changes vs el baseline 2.6.18 de los SPECs. Las 12 APIs MVP-críticas (Agent/Team/AgentOS/Memory/Workflow/etc.) se mantienen. `fork/resume-run` añadido en 2.6.19 es puramente aditivo. |
| `core-cenf-py` | `@ git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0` | git+https pinneado a tag | **VERIFICADO**: repo está en github.com/CENFARG/core-cenf-py, el tag `v0.1.0` existe, importa como `core_infrastructure`. Pre-alpha, NO está en PyPI → git+https con tag fijo es el mecanismo correcto (repoducible, sin requerir path local). |
| `pydantic` | `>=2` | PyPI (inherit) | Runtime; heredado transitivamente por agno. No re-pin (SPEC_00 §7.1). |
| `pyyaml` | `>=6` | PyPI (inherit) | Runtime; heredado. |
| `pytest` | latest | PyPI | dev. |
| `pytest-asyncio` | latest | PyPI | dev (agno es async). |
| `pytest-cov` | latest | PyPI | dev (coverage target 100%). |
| `ruff` | latest | PyPI | dev (lint+format). |
| `mypy` | latest | PyPI | dev (type check). |

**Patrón copiado de `core-cenf-py/pyproject.toml`**: ruff con
`per-file-ignores` `"**/__init__.py" = ["F401"]` (permite re-exports futuros en
`__init__.py` sin ruido), `target-version = "py312"`, `line-length = 120`.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| **SPEC drift Agno 2.6.18 → 2.6.22**: los 34 SPECs citan APIs verificadas contra 2.6.18; ahora pinchamos 2.6.22. | Baja (ya mitigado) | Adversarial re-verification (obs 1866) confirma cero breaking en las 12 APIs MVP-críticas. Único residuo: SPEC_06 tiene citas `file:line` v2.6.18-era (drift +1 a +13 líneas). **Cosmético, tracked como task separado #5 del orquestador — este bootstrap NO toca SPECs.** |
| **`core-cenf-py` git dep portabilidad**: requiere acceso de red a github.com/CENFARG + credenciales para clones privados (si el repo es privado). | Media | El tag `v0.1.0` está verificado como público/accesible. Para open-source futuro de yaml-agno, evaluar publicación de core-cenf-py en PyPI o documentar el requisito de acceso. Hoy es aceptable: el dev loop local ya tiene credenciales. |
| **Hatchling wheel target olvidado**: sin `[tool.hatch.build.targets.wheel] packages = ["src/yaml_agno"]`, el wheel queda vacío y `import yaml_agno` falla tras install. | Baja | Copiar literalmente el patrón de `core-cenf-py`. Smoke test lo caza inmediatamente. |
| **Agno transitive deps pesadas**: agno arrastra muchas dependencias (LLM clients, etc.); CI lento. | Media | Cache pip wheels en CI (`actions/setup-python` cache). Aceptar costo; es inherente al framework. |
| **`pydantic>=2` / `pyyaml>=6` sin pin superior**: una versión mayor futura podría romper. | Baja | Heredan constraint superior de agno implícitamente. Vigilar en cada bump de agno. |

## Rollback Plan

Este cambio es **net-new** (crea archivos, no modifica código existente salvo
`.gitignore`). Rollback = `git revert` del commit del cambio. Antes de aplicar:

1. **Baseline commit obligatorio** (regla de trabajo del usuario — DECISIONES §4).
   Estado actual: branch `feature/specs-agno-coverage-10-25` HEAD `cf5bd31`.
2. Si la instalación falla por `core-cenf-py` git inaccesible: caer temporalmente
   a editable local path `core-cenf-py @ file:///../core-cenf-py` (opción del
   explore obs 1865) y abrir issue para restaurar git+https.
3. Si `agno==2.6.22` rompe algo no cubierto por obs 1866: caer a `agno==2.6.18`
  (baseline SPEC) y re-abrir el drift como blocker.

## Success Criteria

- [ ] `pip install -e .` finaliza sin error (Python 3.12 y 3.13).
- [ ] `python -c "import yaml_agno; print(yaml_agno.__version__)"` imprime `0.1.0`.
- [ ] `python -m pytest` verde (1/1 smoke test) con `pytest-asyncio` cargando.
- [ ] `ruff check .` sin findings (F401 permitido en `__init__.py`).
- [ ] `mypy src/yaml_agno` sin errores (sobre los `__init__.py` vacíos).
- [ ] Los 22 archivos `__init__.py` (1 root + 21 sub-paquetes) existen y están vacíos salvo el root (que tiene el `__version__` block).
- [ ] `.github/workflows/ci.yml` existe y es YAML válido.
- [ ] CI verde en push (post-creación del remote GitHub — paso siguiente).
- [ ] Ningún SPEC editado (verificar `git diff specs/` vacío).

## Open Items / Follow-up Changes

1. **SPEC_06 cosmetic file:line refresh** (task separado del orquestador, NO de
   este bootstrap): actualizar citas `agno/agno/os/router.py:XXX` al esquema
   2.6.22. No impacta comportamiento — solo trazabilidad documental.
2. **AgentConfig schema = change #2** (siguiente SDD change): SPEC_02 es el SSOT
   de schemas; este bootstrap solo deja el namespace `models/` vacío listo.
3. **GitHub remote creation**: paso inmediato siguiente al aplicar este change.
   Crear repo `CENFARG/yaml-agno`, pushear `main`, verificar que el CI workflow
   corra verde. Fuera del scope técnico del bootstrap (decisión + acción del
   orquestador/usuario).
4. **core-cenf-py publish a PyPI**: deuda técnica abierta hasta que yaml-agno
   vaya a open-source. Mientras tanto git+https pinneado a tag es aceptable.
