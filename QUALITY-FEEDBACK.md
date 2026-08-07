# yaml-agno — Feedback técnico (2026-08-07)

**Fuente**: CODE-QUALITY_REPORT_6REPOS.md §2.1 + datos crudos (radon/mypy/coverage/git/codegraph) en `Temp\opencode\qa\` | **Analista**: code-quality-analyst (quality-team)
**Score**: 79.5/100 | **Rol**: librería pública pip (YAML → Pydantic → Agno)
**Período medido**: 2026-05-01 → 2026-08-31

---

## Resumen del estado

Estructuralmente sano: McCabe A (2.75), MI 83.8, cobertura 96%, ruff 0, rework 8.8% 🟢. Los 3 problemas reales son: (1) `_build_step` CC=24 (D) — el dispatcher central de toda la librería; (2) 22 errores mypy, de los cuales **14 son por core-cenf-py sin `py.typed`** (no es deuda de este repo, es deuda del paquete core); (3) comment ratio 5.3% (target ≥10%). Ya existe `.openspec/SDD-HOTSPOTS-REFACTOR.md` con el plan de refactor — **ejecutarlo**.

---

## Hotspots P0 (prioridad alta)

### 1. `factories/workflow_factory.py:222 _build_step` — CC 24 (D), 27 callers vía `build`
- **Problema**: 231 líneas, 8 dispatches de `StepType` inline + validaciones. Fan-in crítico: `StepConfig` (models/config/workflow_config.py:12) tiene **54 callers** y `WorkflowConfig` (línea 104) 12. Es el lugar donde cualquier cambio rompe la construcción de workflows.
- **Por qué importa**: es el contrato público `WorkflowFactory.build()` → cualquier bug aquí afecta a todos los consumidores de la librería. Es exactamente el tipo de hotspot donde en un proyecto SouthMap nacerían los bugs de dominio.
- **Cómo corregirlo**: ejecutar TASK 1 del SDD-HOTSPOTS-REFACTOR.md — extraer cada dispatch a un método privado:
  - `_build_steps_group()` (líneas 298-310)
  - `_build_parallel_group()` (313-325)
  - `_build_condition_group()` (328-368)
  - `_build_router_group()` (371-406)
  - `_build_loop_group()` (409-435)
  - `_build_step` queda como dispatcher puro (<30 líneas, CC ≤8). Ya existe `_build_step_executor()` (455) ✅.
- **Tests**: los existentes en `tests/unit/factories/test_workflow_factory.py` deben pasar sin cambios. Añadir los casos de test de §Cobertura antes de tocar nada.

### 2. 14 errores mypy `import-untyped` de `core_infrastructure.*` — deuda raíz en core-cenf-py
- **Problema**: mypy strict no puede tipar los imports porque core-cenf-py no publica marcador `py.typed`.
- **Archivos afectados**: `di/secret_resolver.py:27,28,82`, `di/agno_resolver.py:22,23,24,28-33,255`, `di/value_resolver.py:18`, `workflows/retry_policy.py:18`, `workflows/step_executor.py:17`, `db/repositories/agent_config_repository.py:25`.
- **Cómo corregirlo (en core-cenf-py, no acá)**: agregar `py.typed` a `core_infrastructure` (archivo vacío en el paquete + declararlo en `pyproject.toml` `[tool.setuptools.package-data]`). *Mientras tanto, no silenciar con `# type: ignore`* — coordinar con el team de core-cenf-py (ver QUALITY-FEEDBACK de core-cenf-py, P1).
- **Fallback temporal** (si se quiere desbloquear ya): `[[tool.mypy.overrides]] module = "core_infrastructure.*", ignore_missing_imports = true` — pero registrarlo como deuda y revertirlo al publicar `py.typed`.

### 3. `agentos/a2a_interface.py:105` — `import-not-found: a2a`
- **Problema**: import del paquete `a2a` no resuelto por mypy.
- **Cómo corregirlo**: verificar si `a2a` es dependencia declarada en `pyproject.toml`; si es opcional (protocolo A2A de Agno), usar `import a2a  # type: ignore[import-not-found]` **con comentario explicando por qué** (dependencia opcional) o import diferido con TYPE_CHECKING.

---

## Hotspots P1

### 4. `models/config/workflow_config.py:12 StepConfig` — CC 13 (C), **54 callers** (fan-in crítico)
- **Problema**: el modelo con mayor fan-in de la librería. Cualquier cambio de schema rompe 54 usos.
- **Cómo corregirlo**: NO refactorizar el modelo (es un Pydantic schema, su complejidad es legítima). En cambio: (a) añadir tests de contrato que congelen el schema (ver §Cobertura), (b) asegurar que todo cambio pase por openspec change con revisión de blast-radius (54 callers).

### 5. `api/agentos_factory.py:171 build` — CC 16 (C)
- **Problema**: 5 responsabilidades mezcladas (validación, deps, middlewares, ensamblado, lifecycle).
- **Cómo corregirlo**: ejecutar TASK 2 del SDD-HOTSPOTS-REFACTOR.md — pipeline `_validate_config` → `_build_dependencies` → `_wire_middlewares` → `_assemble_app` → `_register_lifecycle` (CC ≤5 cada uno).

### 6. `factories/workflow_factory.py` — MI 38.2 (único archivo MI<40 del repo)
- **Problema**: bajo el umbral 40 por volumen + baja densidad de docstrings.
- **Cómo corregirlo**: TASK 3 del SDD-HOTSPOTS-REFACTOR.md — tras el refactor de TASK 1, medir MI target >55. No aplicar docstrings hasta refactorizar (evitar comentar código que se va a mover).

### 7. mypy restantes (5 errores no-core)
- `resilience/circuit_breaker.py:140`, `models/model_spec.py:69,78`, `factories/workflow_factory.py:393` — **`Unused "type: ignore"`**: mypy 1.20 ya no necesita esos ignores. Eliminar los comentarios.
- Comando de verificación: `mypy src/yaml_agno --strict` → target: 0 errores.

---

## Mejoras P2

### 8. Comment ratio 5.3% → 10% (docstrings faltantes)
Archivos con mayor SLOC sin docstrings proporcionales (medir con `radon raw` post-refactor):
- `factories/agentos_factory.py` — `build()` y métodos internos sin docstring de contrato
- `di/provider_factory.py` (82% cobertura, 9 líneas sin cubrir) — documentar el ciclo de vida del provider
- `tools/tool_factory.py` (89.5%) — docstring de `BUILTIN_REGISTRY` y convenciones de resolución
- `workflows/condition_evaluator.py` (55.6% — el peor cubierto) — ver §Cobertura
- Regla CENF: docstring público (Args/Returns/Raises) para toda función pública en `src/yaml_agno/`. Target: ratio ≥10%.

### 9. 9 tests fallados (pass rate 98.7%)
- `tests/unit/tools/test_mcp_resolver.py` — 6 fails (resolve_single_stdio, resolve_multi_*, deprecation_warning, refresh_connection): investigar si es cambio de contrato del MCPResolver o tests desactualizados. Cualquiera de los dos, es bug abierto.
- `tests/integration/api/test_runtime_server.py` y `test_yaml_agent_os_app.py` — 3 fails de app end-to-end (liveness/readiness): probablemente dependencia de entorno (config path). Verificar en CI limpio.

### 10. Proceso
- Días activos 22.8% (28/123) 🟡 — bajo el umbral 30% pero el mejor del grupo. Mantener cadencia.
- Bulk commits: el log muestra +113K LOC con rework 8.8% — sin anomalías. Bien.

---

## Cobertura de tests faltante

Cobertura global 96% — excelente. Faltan casos en los hotspots de alto fan-in (los tests existen pero no cubren los caminos del refactor):

### `tests/unit/factories/test_workflow_factory.py` — casos a añadir ANTES del refactor
1. `_build_step` con `execute=False` → warning logueado + step construido (no dropeado)
2. `_build_step` con `finally_=True` → warning + step construido
3. `Steps` anidado con `steps: []` vacío → `Steps(name=...)` con lista vacía
4. `Parallel` con 2 steps → `Parallel(*built, name=...)` con ambos
5. `Condition` con `if_true` inexistente en step_index → `if_steps` vacío, sin crash
6. `Condition` con `if_false` inexistente → `else_steps=None`
7. `Router` con `cases` apuntando a step_id inexistente → `continue` (defensivo), sin crash
8. `Router` con selector CEL vs callable simple → ambos resueltos vía `_resolve_callable_or_cel`
9. `Loop` sin `max_iterations` → default 3; con valor → respeta el valor
10. `StepType.WORKFLOW` → `NotImplementedError` con mensaje

### `tests/unit/models/test_workflow_config.py` — congelar schema de `StepConfig`
1. `StepConfig(**raw)` mínimo (solo `step` + `type`) → defaults correctos
2. Round-trip `model_dump()` → `StepConfig(**dump)` idéntico (contrato de serialización YAML)
3. Discriminador `type` con los 8 StepType → instancia correcta

### `src/yaml_agno/workflows/condition_evaluator.py` (55.6%) — cubrir
1. Evaluación con condition truthy/falsy
2. Condición ausente → default
3. Callable vs CEL expression
4. Excepciones del evaluador → manejo definido (no propagar)

### `src/yaml_agno/di/provider_factory.py` (82%, 9 líneas faltantes)
1. Provider con API key presente vs ausente
2. Formato "openrouter:openai/gpt-4o" vs "openai:gpt-4o" vs inválido
3. Error de resolución → excepción tipada

---

## Trazabilidad

| Dato | Comando | Fuente | Timestamp |
|------|---------|--------|-----------|
| CC `_build_step`=24, `build`=16, `StepConfig`=13 | `radon cc src -s --json` | yaml-agno_cc.json | 2026-08-07 |
| 22 errores mypy | `mypy --strict src --no-error-summary` | mypy_yaml-agno.txt | 2026-08-07 |
| Cobertura 96% / 9 fails | `pytest --cov --cov-report=json` | cov_yaml-agno.json, pytest_yaml-agno.txt | 2026-08-07 |
| Fan-in 54/27 callers | `codegraph explore "StepConfig"` | blast radius | 2026-08-07 |
| Comment ratio 5.3% | `radon raw src -s --json` | radon_summary.json | 2026-08-07 |

**Nota**: Halstead = DATO FALTANTE (bug radon en Py 3.12, ya documentado). Sin impacto en las acciones de este feedback.
