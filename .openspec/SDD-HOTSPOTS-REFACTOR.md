# SDD Tasks — Refactor hotspots yaml-agno

**Origen**: CODE-QUALITY_REPORT.md (radon McCabe analysis)
**Prioridad**: MEDIA (promedio general A, estos 3 hotspots bajan el promedio)

---

## TASK 1: Refactor `WorkflowFactory._build_step` — Complejidad D (24)

**Archivo**: `src/yaml_agno/factories/workflow_factory.py:222-453`
**Problema**: Método de 231 líneas con 24 caminos independientes (8 dispatches de StepType × 3 validaciones). Cada dispatch es autocontenido pero está inline.

**Solución propuesta**: Extraer cada dispatch a su propio método privado:
- `_build_step_executor()` → ya existe ✅
- `_build_steps_group()` → Steps
- `_build_parallel_group()` → Parallel
- `_build_condition_group()` → Condition
- `_build_router_group()` → Router
- `_build_loop_group()` → Loop

**Resultado esperado**: `_build_step` queda como dispatcher puro (<30 líneas, CC ≤ 8). Cada sub-método CC ≤ 10.

**Tests**: Los tests existentes en `tests/unit/factories/test_workflow_factory.py` deben seguir pasando. No cambia comportamiento.

---

## TASK 2: Refactor `AgentOSFactory.build` — Complejidad C (16)

**Archivo**: `src/yaml_agno/api/agentos_factory.py`
**Problema**: `build()` mezcla 5 responsabilidades: validación de config, construcción de dependencias, wiring de middlewares, ensamblado de app, y registro de lifecycle hooks.

**Solución propuesta**: Descomponer en pipeline de métodos:
1. `_validate_config(cfg) → AgentOSConfig`
2. `_build_dependencies(cfg) → Dependencies`
3. `_wire_middlewares(deps) → list[Middleware]`
4. `_assemble_app(deps, middlewares) → FastAPI`
5. `_register_lifecycle(app, deps) → FastAPI`

**Resultado esperado**: Cada método CC ≤ 5. `build()` queda como orquestador de 5 llamadas.

---

## TASK 3: Mejorar Maintainability Index de `workflow_factory.py` (MI 38)

**Archivo**: `src/yaml_agno/factories/workflow_factory.py`
**Problema**: MI 38 por debajo del umbral 40. Causado por alto volumen de código en un solo archivo + baja densidad de comentarios.

**Solución propuesta**:
1. Ejecutar TASK 1 (reducir tamaño del archivo extrayendo sub-métodos)
2. Agregar docstrings a cada método nuevo (target: docstring/LOC > 10%)
3. Medir MI post-refactor: target >55

---

**Sub-agente recomendado**: @team-development → `code-architect.md` o `backend-developer.md`
**SDD flow**: sdd-explore → sdd-spec → sdd-design → sdd-tasks → sdd-apply → sdd-verify
