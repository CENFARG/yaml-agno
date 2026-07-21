# Design: bootstrap-pip-package

> Diseño técnico del **primer change** de yaml-agno: convertir el repo de
> SPEC-only (34 SPECs + DECISIONES.md) en un **paquete pip instalable vacío,
> verde y con CI pasando**. Sin lógica de negocio.

## Technical Approach

Esqueleto de paquete Python **src-layout + hatchling + PEP 621**, clonando el
patrón de referencia `core-cenf-py/pyproject.toml` (misma configuración de
build, ruff, mypy, pytest). El paquete `yaml_agno` se crea con los **21
sub-paquetes canónicos** (DECISIONES §4bis) cada uno con `__init__.py` vacío;
el `__init__.py` raíz expone `__version__` vía `importlib.metadata` (SSOT =
`pyproject.toml`). Un único smoke test ancla el GREEN day-1. CI en GitHub
Actions valida el paquete en matrix Python 3.12/3.13 (`ruff check` + `pytest`).

El approach mapea 1:1 con la propuesta aprobada: crea la capability
`package-skeleton`, no toca behavior de negocio y deja los 21 namespaces
listos para que cada SPEC aterrice sin churn estructural.

## Architecture Decisions

### Decision: build backend = hatchling + src-layout

- **Choice**: `[build-system] requires=["hatchling"]`, build-backend=`hatchling.build`, con `[tool.hatch.build.targets.wheel] packages=["src/yaml_agno"]`.
- **Alternatives considered**:
  - `setuptools` (lo que usa el repo local `agno/libs/agno/pyproject.toml`) — más verboso, configuration legacy.
  - `flit-core` — válido pero no se usa en el ecosistema CENF.
  - Flat layout (`yaml_agno/` en raíz en vez de `src/yaml_agno/`) — permite imports accidentales desde el cwd, rompe el aislamiento del install.
- **Rationale**: `core-cenf-py` (referencia explícita del usuario y dependencia directa) usa hatchling + src-layout + wheel packages; replicarlo da uniformidad de tooling, PEP 621 nativa, aislamiento real (un `pip install -e .` fallido se detecta en el smoke test, no en producción), y wheel target explícito que evita el bug "wheel vacío" (riesgo documentado en proposal).

### Decision: sub-packages vacíos con `__init__.py` (NO `.gitkeep`)

- **Choice**: cada uno de los 21 sub-paquetes canónicos recibe un `__init__.py` **vacío** (0 bytes); el root recibe uno con el bloque `__version__`.
- **Alternatives considered**:
  - `.gitkeep` — no crea namespace Python; al aterrizar el primer SPEC hay que crear el `__init__.py` igual (churn innecesario).
  - Solo crear la carpeta cuando su SPEC correspondiente se implemente — deja un árbol parcial, rompe la promesa "21 namespaces canónicos listos" de DECISIONES §4bis.
- **Rationale**: (a) `__init__.py` es el sentinel idiomático de Python para namespace regular; git solo trackea dirs con un archivo dentro. (b) Los 21 namespaces quedan **importables desde el day-1** (`from yaml_agno import models` funciona tras `pip install -e .`) → cero churn cuando un SPEC aterriza. (c) `core-cenf-py` sigue el mismo patrón (sus packages se definen en wheel target, sus `__init__.py` existen). (d) Costo trivial: 21 archivos vacíos, cero runtime cost, cero conflictos de merge.

### Decision: `__version__` vía `importlib.metadata` (SSOT en `pyproject.toml`)

- **Choice**: `src/yaml_agno/__init__.py` resuelve la versión con `importlib.metadata.version("yaml-agno")`; el literal `"0.1.0"` vive **solo** en `pyproject.toml`.
- **Alternatives considered**:
  - Hardcodear `__version__ = "0.1.0"` — duplica la fuente de verdad; en un bump se olvida una de las dos (drift clásico).
  - Leer de un `_version.py` generado por `setuptools-scm` — sobrecarga para un bootstrap sin tags git todavía.
- **Rationale**: PEP 396 deprecated el patrón hardcoded; `importlib.metadata` es la API estándar desde Python 3.8 y lee los metadatos que el build backend instaló desde `pyproject.toml`. El smoke test afirma `yaml_agno.__version__ == "0.1.0"` y con eso valida end-to-end que el wheel target, el nombre del paquete (`yaml-agno`) y el `__init__.py` están coherentes. Si el wheel queda vacío o el nombre difiere, el test falla con `PackageNotFoundError`.

### Decision: dep `core-cenf-py` vía git+https pinneado a tag `v0.1.0`

- **Choice**: `core-cenf-py @ git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0` (PEP 508 direct reference, tag fijo).
- **Alternatives considered**:
  - **Local editable path** `core-cenf-py @ file:///C:/Dropbox/DOC.RECA/06-Software/core-cenf-py` (recomendado en la exploración obs 1865) — rompe portabilidad: `pip install` solo funciona en esta máquina; inviable para CI GitHub Actions y para cualquier otro contributor.
  - Esperar a que `core-cenf-py` se publique en PyPI — bloquea el bootstrap; deuda técnica abierta explícita en el proposal.
  - `git+ssh` — requiere claves SSH configuradas; `https` es más portable para CI con `GITHUB_TOKEN`.
- **Rationale**: `core-cenf-py` está verificado como Pre-Alpha, no está en PyPI, pero el tag `v0.1.0` es público/accesible en github.com/CENFARG/core-cenf-py (exploración obs 1865 lo confirma). Pin a tag = builds reproducibles, sin dependencia de máquina, sin "path mágico". CI puede clonar con credenciales default. Cuando `core-cenf-py` publique en PyPI, el cambio es un one-liner (tracked como Open Item #4 del proposal).

### Decision: pin exacto `agno==2.6.22`

- **Choice**: `"agno==2.6.22"` en `dependencies` (pin exacto, no `~=`, no `>=`).
- **Alternatives considered**:
  - `agno==2.6.18` (baseline SPEC) — exploración obs 1865 lo recomendaba como opción conservadora.
  - `agno~=2.6.18` (allow patches) — daría cabida a 2.6.19+ cuya superficie API no estaba verificada en el momento de la exploración.
- **Rationale**: La verificación adversarial de drift (obs 1866, topic_key `yaml-agno/agno-2.6.22-drift-verify`) confirmó **SAFE TO PIN `agno==2.6.22`**: cero breaking changes vs el baseline 2.6.18 en las 12 APIs MVP-críticas (AgentOS, TeamMode=4, StepType=8, A2A nativa, MemoryManager, Agent reasoning params, MCP, Workflow primitives, JWT_VERIFICATION_KEY, Databases, Agent() flags). El único feature post-2.6.18 que toca el constructor de Agent (`fork`/`resume-run`, añadido en 2.6.19) es **puramente aditivo** y no interactúa con ningún path MVP. Pin exacto = fidelidad de SPEC garantizada + builds reproducibles; un bump futuro requiere (y debe trigger) una nueva pasada de re-verificación. Único residuo cosmético: SPEC_06 tiene citas `file:line` desfazadas +1/+13 líneas (tracked como Open Item #1 del proposal, **fuera de scope** de este bootstrap).

### Decision: `requires-python = ">=3.12,<3.14"`

- **Choice**: piso 3.12, techo `<3.14`.
- **Alternatives considered**: `>=3.12` sin techo (estilo `agno`); `<4` (estilo agno/liberal); `<3.13` (ultra conservador).
- **Rationale**: piso `>=3.12` es vinculante — lo imponen `core-cenf-py` (PEP 695 type params), SPEC_00 §7.1 y `openspec/config.yaml`. Techo `<3.14` es conservador hasta que 3.14 (Oct 2025) se valide contra agno + core-cenf-py; evita roturas silenciosas si 3.14 cambia una API que agno usa. CI corre matrix 3.12+3.13 exactamente.

## Data Flow

El bootstrap no tiene data flow de negocio. El flujo relevante es el de **instalación y validación**:

```
pyproject.toml ─┐
                ├─ pip install -e . ─→ wheel (src/yaml_agno) ─┐
src/yaml_agno/ ─┤                                              ├─ import yaml_agno ─→ __version__ via importlib.metadata ─→ "0.1.0"
                │                                              │
tests/test_smoke.py ── pytest ─────────────────────────────────┘
                                                                 │
.github/workflows/ci.yml ─ matrix 3.12/3.13 ─→ ruff check + pytest ─→ green
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Create | Metadata PEP 621, hatchling, deps pinneadas, ruff/mypy/pytest config (contenido modelo en §pyproject.toml model). |
| `src/yaml_agno/__init__.py` | Create | Package root con bloque `__version__` vía `importlib.metadata`. |
| `src/yaml_agno/{api,factories,models,di,persistence,memory,workflows,tools,knowledge,media,hitl,guardrails,skills,culture,reasoning,evals,scheduler,config,tracing,templates,runtime}/__init__.py` | Create | 21 archivos vacíos (0 bytes). |
| `tests/test_smoke.py` | Create | 1 test: `import yaml_agno` + `assert yaml_agno.__version__ == "0.1.0"`. |
| `.github/workflows/ci.yml` | Create | Matrix Python 3.12/3.13, `setup-python` con cache, `ruff check`, `pytest`. |
| `.gitignore` | Modify | Append `*.egg-info`/build artifacts faltantes si diff vs core-cenf-py lo requiere (ver §.gitignore additions). |
| `README.md` | Create | 1 párrafo descriptivo + `pip install -e .`. |

## Interfaces / Contracts

### pyproject.toml model (artefacto central)

Espejo exacto del patrón `core-cenf-py/pyproject.toml`. Contenido objetivo:

```toml
[project]
name = "yaml-agno"
version = "0.1.0"
description = "yaml-agno — Declarative YAML-driven agent orchestration on top of Agno"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.12,<3.14"
authors = [
    {name = "CENF", email = "gonzalo@cenf.tech"},
]
keywords = ["agno", "yaml", "agents", "orchestration", "clean-architecture", "sdd", "tdd"]
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
]

dependencies = [
    "agno==2.6.22",
    "core-cenf-py @ git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=7.0",
    "ruff>=0.15",
    "mypy>=1.20",
    "types-pyyaml>=6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/yaml_agno"]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "SIM", # flake8-simplify
    "ASYNC", # flake8-async
    "RUF", # ruff-specific
]
ignore = [
    "E501", # line-too-long (handled by formatter)
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]
"**/__init__.py" = ["F401"]  # allow unused imports in __init__.py (future re-exports)

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false

[tool.mypy]
python_version = "3.12"
strict = true
enable_error_code = ["ignore-without-code", "redundant-expr", "truthy-bool"]
warn_unreachable = true
warn_unused_ignores = false
show_error_codes = true

[[tool.mypy.overrides]]
module = [
    "agno",
    "agno.*",
    "core_infrastructure",
    "core_infrastructure.*",
]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "9.0"
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = [
    "--strict-markers",
    "--tb=short",
    "-v",
]
markers = [
    "unit: Unit tests (no external I/O)",
    "integration: Integration tests (requires external services)",
    "e2e: End-to-end tests (full lifecycle)",
    "slow: Tests that take longer than 2 seconds",
]
```

Notas de desviación intencional vs `core-cenf-py`:
- `--cov` **no** se activa en `addopts` (bootstrap sin lógica que cubrir; coverage se agrega en changes posteriores). `[tool.coverage.*]` se omite por la misma razón.
- `mypy.overrides` agrega `agno`/`core_infrastructure` al ignore-list: ambos exponen superficie sin stubs tipados completos; sin esto, `strict=true` grita en cualquier `import`.

### src/yaml_agno tree

```
src/yaml_agno/
├── __init__.py              # root: bloque __version__ (ver abajo)
├── api/__init__.py          # vacío
├── factories/__init__.py    # vacío
├── models/__init__.py       # vacío
├── di/__init__.py           # vacío
├── persistence/__init__.py  # vacío
├── memory/__init__.py       # vacío
├── workflows/__init__.py    # vacío
├── tools/__init__.py        # vacío
├── knowledge/__init__.py    # vacío
├── media/__init__.py        # vacío
├── hitl/__init__.py         # vacío
├── guardrails/__init__.py   # vacío
├── skills/__init__.py       # vacío
├── culture/__init__.py      # vacío
├── reasoning/__init__.py    # vacío
├── evals/__init__.py        # vacío
├── scheduler/__init__.py    # vacío
├── config/__init__.py       # vacío
├── tracing/__init__.py      # vacío
├── templates/__init__.py    # vacío
└── runtime/__init__.py      # vacío
```

Contenido exacto de `src/yaml_agno/__init__.py`:

```python
"""yaml-agno: declarative YAML-driven agent orchestration on top of Agno."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yaml-agno")
except PackageNotFoundError:  # pragma: no cover - editable install fallback
    __version__ = "0.0.0"

__all__ = ["__version__"]
```

Los 21 sub-packages son archivos **vacíos** (0 bytes), sin docstring.

### CI workflow model (`.github/workflows/ci.yml`)

```yaml
name: CI

on:
  push:
    branches: [main, "feature/**"]
  pull_request:
    branches: [main]

jobs:
  lint-test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"

      - name: Install package (editable, with dev extras)
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint with ruff
        run: ruff check .

      - name: Type-check with mypy
        run: mypy src/yaml_agno

      - name: Run tests
        run: pytest
```

Notas:
- `cache: "pip"` aprovecha `actions/setup-python@v5` para cachear wheels (agno trae transitivas pesadas; mitigación directa del riesgo "CI lento" del proposal).
- `fail-fast: false` para ver los resultados de ambas versiones de Python aunque una falle.
- El step `mypy` se incluye en CI pese a que el bootstrap no tiene lógica: valida que `strict=true` no grite sobre los `__init__.py` vacíos y mantiene la disciplina desde el día 1.
- `git+https` para `core-cenf-py` funciona en GitHub Actions con el `GITHUB_TOKEN` default mientras el repo sea público/accesible por tag.

### Smoke test model (`tests/test_smoke.py`)

```python
"""Smoke test: package is importable and version metadata is wired correctly."""

import yaml_agno


def test_package_version_matches_pyproject() -> None:
    """yaml_agno.__version__ MUST resolve to the version declared in pyproject.toml."""
    assert yaml_agno.__version__ == "0.1.0"


def test_package_is_importable() -> None:
    """The package namespace MUST be importable after pip install -e ."""
    assert hasattr(yaml_agno, "__version__")
    assert isinstance(yaml_agno.__version__, str)
    assert yaml_agno.__version__  # non-empty
```

### .gitignore additions

El `.gitignore` actual **ya cubre** todos los artifacts relevantes (`build/`, `dist/`, `*.egg-info/`, `.eggs/`, `*.egg`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `htmlcov/`, `.coverage`, `coverage.xml`, `venv/`, `__pycache__/`). Solo se agrega:

```gitignore
# Build artifacts (hatchling)
*.whl
src/*.egg-info/
src/yaml_agno.egg-info/
```

(Sin duplicar lo ya presente. `sdd-apply` debe hacer un diff contra el actual antes de añadir — si ya existen, no tocar.)

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Smoke (única layer en este change) | `import yaml_agno` funciona; `__version__` resuelve a `"0.1.0"` desde metadatos del paquete instalado | `tests/test_smoke.py`: 2 tests (`test_package_version_matches_pyproject`, `test_package_is_importable`). Ejecutan con `python -m pytest`. |
| Unit / Integration / E2E | N/A | No hay lógica de negocio. Estos layers arrancan en el change #2 (AgentConfig schema). |

### TDD approach — honesto

Este change **NO es un RED-GREEN-REFACTOR clásico**, y hay que decirlo explícitamente:

- **No hay RED significativo** porque no hay comportamiento de negocio que falle primero. El "RED" aquí sería `pip install -e .` fallando (no existe `pyproject.toml`), pero ese estado no es un test que falle — es "el repo no es un paquete todavía".
- **El smoke test es el GREEN anchor**: valida end-to-end que el esqueleto está bien armado (wheel target correcto, nombre de paquete coherente, `__init__.py` raíz correcto, `importlib.metadata` resuelve).
- **REFACTOR**: ninguno; es greenfield puro.

Strict TDD Mode está activo (`openspec/config.yaml`), y este cambio lo honra de la única forma posible para un skeleton: el test existe **antes** de declarar done, y si se rompe cualquier pieza del esqueleto (wheel vacío, `__init__.py` perdido, nombre mal pinchado), el test falla. No es TDD de comportamiento porque no hay comportamiento — es TDD de **estructura**.

## Verification Strategy

`sdd-apply` confirmará éxito ejecutando, en orden:

1. **Instalación**: `pip install -e ".[dev]"` termina sin error (Python 3.12 y 3.13).
2. **Importabilidad**: `python -c "import yaml_agno; print(yaml_agno.__version__)"` imprime `0.1.0`.
3. **Sub-packages importables**: `python -c "import yaml_agno.api, yaml_agno.factories, yaml_agno.models, yaml_agno.di, yaml_agno.persistence, yaml_agno.memory, yaml_agno.workflows, yaml_agno.tools, yaml_agno.knowledge, yaml_agno.media, yaml_agno.hitl, yaml_agno.guardrails, yaml_agno.skills, yaml_agno.culture, yaml_agno.reasoning, yaml_agno.evals, yaml_agno.scheduler, yaml_agno.config, yaml_agno.tracing, yaml_agno.templates, yaml_agno.runtime"` sin error (los 21 namespaces existen).
4. **Tests**: `python -m pytest` verde (2/2 smoke tests), con `pytest-asyncio` cargando (`asyncio_mode=auto`).
5. **Lint**: `ruff check .` sin findings (F401 permitido en `__init__.py`).
6. **Types**: `mypy src/yaml_agno` sin errores sobre los `__init__.py`.
7. **SPECs intactos**: `git diff --name-only specs/` vacío (ningún SPEC editado).
8. **Conteo de archivos**: 22 archivos `__init__.py` (1 root + 21 sub) + `pyproject.toml` + `tests/test_smoke.py` + `.github/workflows/ci.yml` + `README.md`.

CI en GitHub Actions queda listo para validar 1-6 automáticamente en matrix 3.12/3.13 una vez creado el remote (Open Item #3 del proposal, fuera de scope técnico).

## Migration / Rollout

No migration required (net-new greenfield). Rollback = `git revert` del commit del change (proposal §Rollback Plan). Baseline commit obligatorio antes de aplicar (regla DECISIONES §4).

## Open Questions

- [ ] **`core-cenf-py` accesibilidad para CI**: ¿el tag `v0.1.0` en github.com/CENFARG/core-cenf-py es público o requiere token en GitHub Actions? Verificar en `sdd-apply` o al crear el remote. Si es privado, configurar secret `GIT_AUTH_TOKEN` y pasar credenciales en la URL del dep.
- [ ] **`mypy` strict sobre `__init__.py` vacíos**: teóricamente limpio, pero `sdd-apply` debe confirmar que no grita. Si lo hace, revisar si hace falta `# type: ignore` en el root `__init__.py` (no se anticipa, pero es el único punto de fricción mypy plausible).
- [ ] **README contenido**: el proposal pide "1 párrafo"; el wording exacto queda a criterio de `sdd-apply` alineado con VISION.md/SPEC.md. No es bloqueante para el diseño.
