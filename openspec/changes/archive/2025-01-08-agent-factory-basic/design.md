---
change: agent-factory-basic
spec: SPEC_01
artifact: design
status: designed
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/agent-factory-basic/proposal.md (engram #1925)
  - source_spec: specs/SPEC_01_AGENT_FACTORY.md (read-only SSOT, slice #1 of 4)
  - consumed_contract: src/yaml_agno/models/config/agent_config.py (SPEC_02, shipped)
  - agno_source: agno/agent/agent.py:384-503 (constructor signature), :504 (`self.model = model`), :456 (`instructions=None` default)
---

# Design: AgentFactory — primer slice (AgentConfig → agno.Agent)

> **@ai-directive**: Este documento es el **HOW técnico**. El SSOT normativo es
> `specs/SPEC_01_AGENT_FACTORY.md` (read-only); este cambio entrega el **slice #1
> de 4**. Toda discrepancia se resuelve a favor de SPEC_01. El código mostrado
> aquí es **documentación viva** — el cambio `sdd-apply` crea los archivos `.py`
> literalmente como se especifican aquí.

## Technical Approach

**Mapeo mínimo y directo de 4 campos.** `AgentFactory.build(cfg: AgentConfig)`
construye un `agno.Agent` pasando los 4 campos de identidad como kwargs nativos:
`name`, `instructions`, `description`, `model`. **Sin traducción de nombres**,
sin `partition()` del model, sin DependencyManager, sin side-effects en red.

La estrategia se apoya en tres hechos verificados del contrato Agno:

1. **`Agent.__init__` es keyword-only con ~120 params y defaults `None`**
   (`agno/agent/agent.py:384-503`). Los 4 campos que mapeamos son kwargs nativos;
   no hay renombrado (p.ej. `instructions` se llama `instructions`, no
   `system_message`).
2. **La construcción es asignación pura** (`agno/agent/agent.py:504`:
   `self.model = model`). No se instancia cliente HTTP ni se resuelve el string
   `provider:id` a un `Model` hasta `run()`/`arun()`. Esto hace viable el TDD por
   construcción (sin network).
3. **`model` acepta `str`** en el constructor. Agno parsea nativamente el formato
   `provider:id` (p.ej. `"openai:gpt-4o"`). yaml-agno **no** particiona ni
   traduce — passthrough directo. Esto preserva el contrato Agno-native y deja la
   resolución al framework.

Los **9 slots opacos** (`tools`, `knowledge`, `memory`, `session`, `reasoning`,
`skills`, `human_review`, `culture`, `persistence`) más `tags` y `metadata` **NO
se envían a `Agent(...)`** en este slice. La firma `build()` solo acepta el
`AgentConfig` aggregate y lee sus 4 campos de identidad; los slots opacos son
ignorados explícitamente (deferred a sus owner SPECs 03/04/10/11/13/28/29/30/31).
El factory debe aceptar un `AgentConfig` con slots opacos populados sin error
(son `dict | None` válidos) y simplemente no reenviarlos.

### Flujo de datos (boundary construction)

```
AgentConfig (SPEC_02, validado)
        │
        │  name, instructions, description, model   ──► forwarded
        │  tools, knowledge, memory, session, ...   ──► IGNORED (deferred)
        ▼
AgentFactory.build(cfg) ──► agno.Agent(name=..., instructions=...,
                                       description=..., model=...)
        │
        │  agent.py:504  self.model = model   (asignación pura, sin I/O)
        ▼
agno.Agent  (isinstance ✓, sin network, sin LLM)

Tests:  assert isinstance(result, agno.Agent)
        assert result.name == cfg.name
        assert result.model == cfg.model          # ver nota ADR-A4
        assert result.description == cfg.description
        assert result.instructions == cfg.instructions
```

## Architecture Decisions

### Decision A1: Método estático `AgentFactory.build()` (no instancia de factory)

**Choice**: `AgentFactory` expone `build(cfg: AgentConfig) -> Agent` como
`@staticmethod`. No se instancia la factory; no guarda estado.

**Alternatives considered**:
- Clase con `__init__` y método de instancia (inyectar `DependencyManager`
  después). Rechazado para este slice: no hay dependencias que inyectar todavía
  (#2 agrega `DependencyManager`).
- Función libre `build_agent(cfg)` en el módulo. Rechazado: pierde el namespace
  `AgentFactory.` que SPEC_01 nombra explícitamente y dificulta el mock/spy en
  tests futuros de TeamFactory (#3) que dependerán de esta factory.

**Rationale**: Slice #1 no tiene estado ni colaboradores. Un `@staticmethod` es
el contrato mínimo que (a) cumple el nombre `AgentFactory` de SPEC_01, (b) deja
crecer limpiamente: cuando #2 añada `DependencyManager`, el cambio es
`build(cfg, *, deps: DependencyManager | None = None)` manteniendo compat, o se
convierte en método de instancia — decisión de #2, no de este slice. Static
method ahora = cero boilerplate de instanciación en los 3 callers futuros
(TeamFactory, WorkflowFactory, loader).

### Decision A2: Import directo `from agno.agent import Agent` (no lazy importlib)

**Choice**: `from agno.agent import Agent` al tope del módulo, fuera de cualquier
función. Sin `importlib.import_module`, sin `lru_cache`.

**Alternatives considered**:
- Lazy import vía `importlib` dentro de `build()` (patrón DependencyManager de
  SPEC_01). Rechazado para este slice: el `DependencyManager` es el cambio #2.
  Mezclar lazy import ahora infla scope y duplica la responsabilidad de #2.
- Import condicional (`TYPE_CHECKING` guard). Rechazado: necesitamos el símbolo
  en runtime para instanciar; el guard solo sirve para type hints.

**Rationale**: Separación de concerns entre slices. #1 = mapeo; #2 = resolución
de dependencias + lazy loading + allowlist. Hacer el import directo ahora
mantiene #1 cohesivo y deja a #2 la introducción del mecanismo de carga
diferida como su entregable propio. El costo (import de `agno` en tests) es
inherente al framework y ya asumido por SPEC_02 (`tests/unit/test_enums_import.py`).

### Decision A3: Slots opacos ignorados explícitamente (SSOT delegation)

**Choice**: `build()` lee SOLO `cfg.name`, `cfg.model`, `cfg.instructions`,
`cfg.description`. Los 9 slots opacos + `tags` + `metadata` no se leen ni se
reenvían a `Agent(...)`. El factory NO falla si un slot opaco está populado.

**Alternatives considered**:
- Forwardear los 9 slots nativos tal cual (`tools=cfg.tools`,
  `knowledge=cfg.knowledge`, ...). Rechazado: rompe SSOT — los slots son
  `dict[str, Any]` opacos en SPEC_02; Agno espera **objetos tipados** (`Toolkit`,
  `KnowledgeBase`, `Memory`, `Db`, etc.). Forwardear dicts crudos provoca errores
  de tipo en runtime o (peor) aceptación silenciosa de shapes incorrectos. La
  resolución dict→objeto nativo es trabajo de los owner SPECs (10/04/03/...).
- Fallar (`raise NotImplementedError`) si algún slot opaco está populado.
  Rechazado: hace el factory inutilizable para configs reales que ya tienen
  slots opacos válidos en YAML. Perdería la capacidad de probar construcción
  end-to-end con configs completos.

**Rationale**: Cada sub-sistema (memory, knowledge, tools, ...) tiene su SPEC
dueño que define cómo se resuelve el dict a un objeto Agno nativo. Este slice
declarativamente **no opina** sobre esos sub-sistemas: los acepta (son parte del
aggregate AgentConfig), los nombra en docstring como "deferred" y deja que los
owner SPECs provean los resolvedores. Esto preserva la cohesión del slice y no
genera deuda técnica (el camino de resolución queda abierto, no cerrado).

### Decision A4: `model` passthrough — sin `partition()`, sin traducción

**Choice**: `Agent(..., model=cfg.model)`. El string `"openai:gpt-4o"` se pasa
íntegro. yaml-agno no toca el formato `provider:id`.

**Alternatives considered**:
- `provider, _, model_id = cfg.model.partition(":")` + construir
  `Model(provider=..., id=...)`. Rechazado: Agno ya parsea nativamente el string
  `provider:id` en su model factory (SPEC_14 delega a Agno). Repetir el parseo
  en yaml-agno es DRY violation y desincroniza contra futuros cambios de Agno.
- Validar el provider contra un allowlist antes de pasar. Rechazado: eso es
  trabajo del DependencyManager (#2) contra el registry de Agno, no de este
  slice. SPEC_02 ya valida la **sintaxis** (`provider:id` con ambos lados no
  vacíos).

**Rationale**: Principio "Build ON TOP" de SPEC_00. Agno expone el formato
`provider:id` como input válido de `model`; passthrough = cero código de
traducción = cero bugs de traducción. El test de `result.model == cfg.model`
asume que la construcción es asignación pura (`agent.py:504`). **Nota sobre el
tipo post-construcción**: si una versión futura de Agno resolviera `model` a un
objeto `Model` en el constructor, el assert de igualdad estricta fallaría — en
ese caso el test debe afirmar identidad por string (`str(result.model)` o el
atributo `.id`). Para Agno 2.6.22 (pinneado), la asignación pura mantiene el
string intacto.

## Class-by-Class Model (literal target code)

### `src/yaml_agno/factories/agent_factory.py`

```python
"""AgentFactory — builds a native ``agno.Agent`` from an ``AgentConfig``.

This is slice #1 of SPEC_01 (4-slice factory chain). It maps the 4 identity
fields of ``AgentConfig`` (SPEC_02) to the corresponding ``agno.Agent``
constructor kwargs. The 9 opaque sub-system slots (tools, knowledge, memory,
session, reasoning, skills, human_review, culture, persistence) plus tags and
metadata are intentionally NOT forwarded in this slice — their resolution
(dict -> native Agno object) is owned by dedicated SPECs (03/04/10/11/13/
28/29/30/31) and the DependencyManager (change #2).

Contract:
    - Construction is pure assignment (agno/agent/agent.py:504: ``self.model =
      model``); no network, no LLM instantiation, no provider resolution.
    - ``model`` is passed through as the raw ``provider:id`` string. Agno parses
      it natively; yaml-agno performs no translation.

@ai-directive: SSOT is specs/SPEC_01_AGENT_FACTORY.md. Discrepancies resolve in
its favor. This module consumes SPEC_02 (AgentConfig) read-only.
"""

from __future__ import annotations

from agno.agent import Agent

from yaml_agno.models.config.agent_config import AgentConfig

__all__ = ["AgentFactory"]


class AgentFactory:
    """Builds ``agno.Agent`` instances from validated ``AgentConfig`` objects.

    Slice #1 scope (identity + model only):

        +--------------------------+--------------------------+-----------+
        | AgentConfig field        | agno.Agent kwarg         | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | instructions: str | None | instructions             | direct    |
        | description: str | None  | description              | direct    |
        | model: str               | model                    | passthru  |
        +--------------------------+--------------------------+-----------+
        | tools, knowledge, ...    | (not forwarded)          | deferred  |
        | tags, metadata           | (not forwarded)          | deferred  |
        +--------------------------+--------------------------+-----------+

    Deferred slots are accepted silently (they are valid ``dict | None`` members
    of ``AgentConfig``) and will be resolved by their owner SPECs + the
    DependencyManager in change #2.

    This class exposes a static ``build()`` method; it holds no state and is not
    instantiated.
    """

    @staticmethod
    def build(cfg: AgentConfig) -> Agent:
        """Build a native ``agno.Agent`` from an ``AgentConfig``.

        Only the 4 identity/behavior fields are mapped. The 9 opaque sub-system
        slots, ``tags``, and ``metadata`` are intentionally ignored in this
        slice (see class docstring).

        Args:
            cfg: A validated ``AgentConfig`` (SPEC_02). Its ``model`` field is a
                ``provider:id`` string forwarded verbatim to Agno.

        Returns:
            A constructed ``agno.Agent``. Per ``agno/agent/agent.py:504``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked.

        Raises:
            (none directly) Any exception raised by ``agno.Agent.__init__`` on
                invalid input propagates unchanged. Per verified contract, the 4
                mapped fields are accepted as-is by Agno 2.6.22.
        """
        return Agent(
            name=cfg.name,
            instructions=cfg.instructions,
            description=cfg.description,
            model=cfg.model,
        )
```

### `src/yaml_agno/factories/__init__.py`

```python
"""Factories package — builds native Agno objects from validated configs.

Re-exports the public factory classes so callers can do
``from yaml_agno.factories import AgentFactory``.
"""

from yaml_agno.factories.agent_factory import AgentFactory

__all__ = ["AgentFactory"]
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/agent_factory.py` | Create | `AgentFactory.build(cfg) -> agno.Agent`. Static method, 4-field map, passthrough model. |
| `src/yaml_agno/factories/__init__.py` | Modify | Re-export `AgentFactory` (was empty after bootstrap). |
| `tests/unit/factories/__init__.py` | Create | Namespace package marker (vacío). |
| `tests/unit/factories/test_agent_factory.py` | Create | Tests RED→GREEN: construction + 4-field mapping + opaque-slot tolerance. |

**Total**: 3 archivos nuevos + 1 modificado = 4 files. Solo
`factories/__init__.py` preexiste (vacío del bootstrap).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `isinstance(result, agno.Agent)` tras `build(AgentConfig(...))` | `@pytest.mark.unit` — construcción directa, sin `.run()`. |
| Unit | Mapeo `result.name == cfg.name` | assert de igualdad estricta (str). |
| Unit | Mapeo `result.model == cfg.model` | assert de igualdad — **ver nota ADR-A4**: asume asignación pura (agent.py:504). Si Agno resuelve a `Model`, ajustar a `str(result.model)` o `result.model.id`. Re-confirmar en apply con Agno 2.6.22 instalado. |
| Unit | Mapeo `result.description == cfg.description` | assert de igualdad (ambos `str | None`). |
| Unit | Mapeo `result.instructions == cfg.instructions` | assert de igualdad (ambos `str | None`). |
| Unit | Tolerancia a slots opacos: `build()` NO falla cuando `AgentConfig` tiene `tools`, `memory`, etc. populados. | Construir cfg con los 9 slots llenos + tags + metadata y verificar `isinstance(result, Agent)`. |
| Unit | `instructions=None` y `description=None` construyen OK (defaults nativos de Agno). | Caso minimal: solo `name` + `model`. |
| Contract | Smoke import: `from yaml_agno.factories import AgentFactory` funciona en runtime. | Test separado o `python -c`. |

**Sin tests de**: `.run()`, `.arun()`, network, provider resolution (todo
deferred). Sin mocks de Agno — se usa el `Agent` real porque la construcción es
pura asignación.

## TDD Approach

Por tarea (ver `tasks.md` futuro):

1. **RED**: escribir `tests/unit/factories/test_agent_factory.py` referenciando
   `from yaml_agno.factories import AgentFactory` — falla con `ImportError`.
2. **GREEN**: crear `agent_factory.py` + actualizar `__init__.py` con el código
   literal de este design — tests pasan.
3. **REFACTOR**: si emerge duplicación (p.ej. helper de mapeo), extraer. En este
   slice no se anticipa refactor — el código es 4 kwargs.

## Verification Strategy

1. **`python -m pytest -m unit tests/unit/factories/`** — verde. Cobertura: 4
   campos mapeados + tolerancia a slots opacos + caso minimal.
2. **`ruff check src/yaml_agno/factories tests/unit/factories`** — limpio
   (line-length 120, import sort, etc.).
3. **`mypy src/yaml_agno/factories`** — limpio. **Caveat**: Agno mypy stubs
   usan `ignore_missing_imports=true`, así que un import path erróneo NO falla
   type-check. La verificación REAL es el runtime import en los tests.
4. **Smoke runtime**:
   `python -c "from yaml_agno.factories import AgentFactory; print(AgentFactory)"`
   debe funcionar sin error.
5. **SSOT intocado**:
   `git diff --exit-code src/yaml_agno/models/ specs/` — vacío (SPEC_02 + specs
   no mutados).

## Migration / Rollback

**No migration required.** Todo el cambio vive en archivos nuevos bajo
`src/yaml_agno/factories/` (y `tests/unit/factories/`), salvo
`factories/__init__.py` que pasa de vacío a re-export.

Rollback = `git revert` del commit. Esto restaura `factories/__init__.py` a su
estado vacío (bootstrap) y elimina los 3 archivos nuevos. Sin mutación de datos,
sin feature flags, sin dependientes (TeamFactory #3 y WorkflowFactory #4 aún no
existen; DependencyManager #2 tampoco).

## Open Questions

- [ ] **Tipo post-construcción de `result.model` en Agno 2.6.22**: el design
      asume asignación pura (`agent.py:504`) → `result.model == "openai:gpt-4o"`
      (str idéntico). **Re-confirmar en `sdd-apply`** ejecutando
      `python -c "from agno.agent import Agent; a=Agent(name='x', model='openai:gpt-4o'); print(type(a.model), repr(a.model))"`.
      Si Agno resolviera a un objeto `Model`, el test de igualdad debe cambiarse
      a `str(result.model)` o al atributo equivalente. El diseño del factory NO
      cambia (passthrough sigue siendo correcto); solo cambia el assert del test.
- [ ] **Costo de import de `agno` en tests**: aceptado como inherente al
      framework. Si ralentiza la suite, #2 (DependencyManager) puede introducir
      lazy import. No bloquea este slice.
