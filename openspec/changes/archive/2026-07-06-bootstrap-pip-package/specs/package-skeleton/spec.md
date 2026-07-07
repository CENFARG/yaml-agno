# Package Skeleton Specification

## Purpose

Definir el comportamiento requerido del esqueleto de paquete pip `yaml_agno`:
un paquete vacío, instalable, verde e importable que sirve de contenedor sobre
el que se insertarán las capabilities definidas en los 34 SPECs del proyecto.
**No define lógica de negocio** — solo metadata, namespaces vacíos, smoke test
y CI. Es el change #1 del proyecto (el repo hoy es SPEC-only).

## Requirements

### Requirement: Instalabilidad editable multi-Python

El paquete `yaml_agno` MUST ser instalable en modo editable (`pip install -e .`)
en Python 3.12 y 3.13, con `requires-python` declarado `>=3.12,<3.14`.

#### Scenario: Instalación editable en Python 3.12

- GIVEN un entorno Python 3.12 limpio con acceso a PyPI y github.com/CENFARG
- WHEN se ejecuta `pip install -e .` desde la raíz del repo
- THEN el comando finaliza con código de salida 0
- AND `import yaml_agno` funciona en un intérprete nuevo

#### Scenario: Instalación editable en Python 3.13

- GIVEN un entorno Python 3.13 limpio con acceso a PyPI y github.com/CENFARG
- WHEN se ejecuta `pip install -e .`
- THEN el comando finaliza con código de salida 0
- AND `import yaml_agno` funciona en un intérprete nuevo

### Requirement: Versión única fuente de verdad (SSOT)

El valor de `yaml_agno.__version__` MUST ser `"0.1.0"` y MUST obtenerse vía
`importlib.metadata.version("yaml-agno")`, siendo `pyproject.toml` la única
fuente de la versión.

#### Scenario: Versión leída desde metadata del paquete

- GIVEN el paquete instalado editable
- WHEN se ejecuta `python -c "import yaml_agno; print(yaml_agno.__version__)"`
- THEN la salida stdout es exactamente `0.1.0`
- AND el valor proviene de `importlib.metadata`, no de un literal hardcoded

### Requirement: Namespaces canónicos vacíos e importables

El paquete MUST contener exactamente 21 sub-paquetes canónicos, cada uno con un
`__init__.py` **vacío** (sin lógica, sin re-exports): `api`, `factories`,
`models`, `di`, `persistence`, `memory`, `workflows`, `tools`, `knowledge`,
`media`, `hitl`, `guardrails`, `skills`, `culture`, `reasoning`, `evals`,
`scheduler`, `config`, `tracing`, `templates`, `runtime`. Cada sub-paquete
MUST ser importable.

#### Scenario: Todos los sub-paquetes son importables

- GIVEN el paquete instalado
- WHEN se ejecuta `python -c "import yaml_agno.api, yaml_agno.factories, yaml_agno.models, yaml_agno.di, yaml_agno.persistence, yaml_agno.memory, yaml_agno.workflows, yaml_agno.tools, yaml_agno.knowledge, yaml_agno.media, yaml_agno.hitl, yaml_agno.guardrails, yaml_agno.skills, yaml_agno.culture, yaml_agno.reasoning, yaml_agno.evals, yaml_agno.scheduler, yaml_agno.config, yaml_agno.tracing, yaml_agno.templates, yaml_agno.runtime"`
- THEN el comando finaliza con código de salida 0

#### Scenario: Ausencia de lógica de negocio

- GIVEN los 22 archivos `__init__.py` (1 root + 21 sub-paquetes)
- WHEN se inspecciona su contenido
- THEN los 21 sub-paquetes están vacíos
- AND solo el `__init__.py` raíz contiene código (el bloque `__version__`)

### Requirement: Dependencias pinneadas

`pyproject.toml` MUST declarar las dependencias runtime con estos pines exactos:
`agno==2.6.22`, `core-cenf-py @ git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0`,
`pydantic>=2`, `pyyaml>=6`.

#### Scenario: Pines de runtime respetados

- GIVEN el `pyproject.toml` resultante
- WHEN se parsean las dependencias `[project.dependencies]`
- THEN `agno` está pinneado exacto a `2.6.22`
- AND `core-cenf-py` apunta a `git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0`
- AND `pydantic` permite `>=2`
- AND `pyyaml` permite `>=6`

### Requirement: Smoke test day-1 green

`tests/test_smoke.py` MUST existir y validar `import yaml_agno` +
`yaml_agno.__version__ == "0.1.0"`. `python -m pytest` MUST pasar 2/2.

#### Scenario: Pytest verde

- GIVEN el entorno con el paquete instalado y `pytest`/`pytest-asyncio` disponibles
- WHEN se ejecuta `python -m pytest`
- THEN el resultado es 2 passed, 0 failed

### Requirement: Lint limpio (ruff)

`ruff check .` MUST producir cero findings. La config MUST permitir `F401` en
`**/__init__.py` (vía `per-file-ignores`) para soportar re-exports futuros.

#### Scenario: Ruff sin findings

- GIVEN la configuración de ruff aplicada
- WHEN se ejecuta `ruff check .`
- THEN la salida es "All checks passed" con código de salida 0

### Requirement: Type-check limpio (mypy)

`mypy src/yaml_agno` MUST producir cero errores sobre los `__init__.py` vacíos.

#### Scenario: Mypy sin errores

- GIVEN los archivos del paquete
- WHEN se ejecuta `mypy src/yaml_agno`
- THEN el comando reporta "Success" con código de salida 0

### Requirement: CI workflow válido y matriz

`.github/workflows/ci.yml` MUST ser YAML válido y MUST ejecutar `ruff check` +
`pytest` sobre una matriz Python `[3.12, 3.13]`.

#### Scenario: CI matrix cubre ambas versiones

- GIVEN el workflow `.github/workflows/ci.yml`
- WHEN se parsea el YAML
- THEN la matriz `python-version` contiene `3.12` y `3.13`
- AND los steps incluyen `ruff check .` y `pytest` (o equivalente)

#### Scenario: YAML válido sintácticamente

- GIVEN el archivo `.github/workflows/ci.yml`
- WHEN se valida como YAML
- THEN el parseo no produce errores de sintaxis

### Requirement: No-modificación de SPECs

Este change MUST NOT modificar ningún archivo bajo `specs/` del proyecto.

#### Scenario: specs/ sin cambios

- GIVEN el estado del repo tras aplicar el change
- WHEN se ejecuta `git diff --name-only specs/`
- THEN la salida es vacía
