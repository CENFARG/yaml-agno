---
change: team-factory
spec: SPEC_01
artifact: design
status: designed
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/team-factory/proposal.md (engram #1956)
  - spec: openspec/changes/team-factory/specs/team-factory/spec.md (BDD SSOT for behavior)
  - source_spec: specs/SPEC_01_AGENT_FACTORY.md (read-only SSOT, slice #3 of 4)
  - shipped_pattern: src/yaml_agno/factories/agent_factory.py (AgentFactory.build @staticmethod — style template)
  - consumed_contract: src/yaml_agno/models/config/team_config.py (SPEC_02, TeamConfig + TeamMemberConfig)
  - agno_source: agno/team/team.py:437-468 (Team.__init__ signature), :446 (mode: Optional[TeamMode] = None), :444 (name: Optional[str] = None), :468 (instructions: Optional[Union[str, List[str], Callable]] = None)
  - agno_source_enum: agno/team/mode.py:6-23 (TeamMode: 4 lowercase str-enum members)
---

# Design: TeamFactory — SPEC_01 slice #3 (TeamConfig + agents dict → agno.Team)

> **@ai-directive**: Este documento es el **HOW técnico**. El SSOT normativo de
> comportamiento es `openspec/changes/team-factory/specs/team-factory/spec.md`;
> el SSOT normativo de arquitectura es `specs/SPEC_01_AGENT_FACTORY.md` (read-only).
> Este cambio entrega el **slice #3 de 4**. Toda discrepancia se resuelve a favor
> de ambos specs. El código mostrado aquí es **documentación viva** — el cambio
> `sdd-apply` crea los archivos `.py` literalmente como se especifican aquí.

## Technical Approach

**Composición por lookup de nombre + mapeo directo de 3 campos.**
`TeamFactory.build(cfg: TeamConfig, agents: dict[str, Agent])` construye un
`agno.Team` en dos fases: (1) resuelve la lista de miembros iterando
`cfg.members` y buscando cada `member.agent` (string de nombre) en el dict
`agents` ya construido; (2) invoca `agno.Team(members=[...], mode=cfg.mode,
name=cfg.name, instructions=cfg.instructions)` con esos 4 kwargs nativos.

La estrategia se apoya en cuatro hechos verificados del contrato Agno 2.6.22:

1. **`Team.__init__` acepta `members` como primer argumento posicional-after-self
   y los otros tres como kwargs nativos**
   (`agno/team/team.py:437-468`). La firma exacta verificada:
   ```python
   def __init__(
       self,
       members: Union[List[Union[Agent, "Team"]], Callable[..., List]],
       id: Optional[str] = None,
       model: Optional[Union[Model, str]] = None,
       ...
       name: Optional[str] = None,
       ...
       mode: Optional[TeamMode] = None,
       ...
       instructions: Optional[Union[str, List[str], Callable]] = None,
       ...
   )
   ```
   No hay renombrado: `members`, `mode`, `name`, `instructions` se llaman igual
   en ambos lados del boundary.
2. **`members` acepta instancias `agno.Agent` ya construidas directamente**
   (`team.py:439`: `Union[List[Union[Agent, "Team"]], Callable[..., List]]`).
   No requiere wrappers ni adaptadores — el dict `agents` producido por
   `AgentFactory.build()` (slice #1) alimenta este slot sin traducción.
3. **`mode` es `Optional[TeamMode]` y acepta el enum nativo** (`team.py:446`).
   `cfg.mode` ya es una instancia `TeamMode` (Pydantic lo coerciona desde el
   string lowercase del YAML en el boundary de `TeamConfig`). Passthrough
   directo: cero conversión, cero re-validación.
4. **`instructions` acepta `None` sin error** (`team.py:468`,
   `Optional[Union[str, List[str], Callable]] = None`). Pasar
   `instructions=cfg.instructions` cuando `cfg.instructions is None` produce
   `team.instructions is None` — idéntico a omitir el kwarg.

Los **slots opacos** (`workflows`, `description`, `tags`, `metadata`) **NO se
envían a `Team(...)`** en este slice. La firma `build()` solo lee `cfg.name`,
`cfg.mode`, `cfg.instructions` y `cfg.members` (este último solo para extraer
los nombres `member.agent`). Los slots opacos son ignorados explícitamente
(deferred: `workflows` → WorkflowFactory slice #4 / SPEC_01 §4; `description`,
`tags`, `metadata` → SPEC_05). El factory debe aceptar un `TeamConfig` con
slots opacos populados sin error y simplemente no reenviarlos.

### Flujo de datos (boundary construction)

```
TeamConfig (SPEC_02, validado por Pydantic)         agents: dict[str, Agent]
  cfg.members: list[TeamMemberConfig]                 (ya construidos por
    each has .agent: str  ──────────────────► lookup   AgentFactory.build,
                                                key=member.agent       slice #1)
        │                                                      │
        │  for m in cfg.members:                               │
        │     if m.agent not in agents:                        │
        │        raise ValueError(f"Agent not found: {m.agent}")  (before Team())
        │     resolved.append(agents[m.agent])                 │
        ▼                                                      ▼
TeamFactory.build(cfg, agents)
        │
        │  agno.Team(members=resolved, mode=cfg.mode,
        │           name=cfg.name, instructions=cfg.instructions)
        │
        │  workflows, description, tags, metadata  ──► IGNORED (deferred)
        │  member.role, member.member (local id)   ──► IGNORED (Team has no per-member metadata in slice #3)
        ▼
agno.Team  (isinstance ✓, sin network, sin LLM, sin model resolution)

Tests:  assert isinstance(result, agno.Team)
        assert result.members == [agents["a1"], agents["a2"]]   # orden preservado
        assert result.mode is cfg.mode                           # misma instancia TeamMode
        assert result.name == cfg.name
        assert result.instructions == cfg.instructions           # None o str
        assert result.model is None                              # TeamConfig no tiene model
```

## Architecture Decisions

### Decision A1: Método estático `TeamFactory.build()` — consistencia con AgentFactory

**Choice**: `TeamFactory` expone `build(cfg: TeamConfig, agents: dict[str, Agent])
-> Team` como `@staticmethod`. No se instancia la factory; no guarda estado.

**Alternatives considered**:
- Clase con `__init__(deps: DependencyManager)` y método de instancia
  `async def create()` (pseudo-código de SPEC_01 §2). **Rechazado**: ese patrón
  referencia `self.deps.resolve_team_symbols()` que **NO EXISTE** en el código
  shipped y mezcla resolución de dependencias (change #2 DependencyManager) con
  construcción (este slice). Duplica responsabilidades y rompe el paralelismo
  con `AgentFactory.build()` ya shipped.
- Función libre `build_team(cfg, agents)` en el módulo. **Rechazado**: pierde el
  namespace `TeamFactory.` que SPEC_01 nombra explícitamente, rompe simetría con
  `AgentFactory.`, y dificulta el mock/spy en tests futuros de WorkflowFactory
  (slice #4) que consumirá teams ya construidos.

**Rationale**: Slice #3 no tiene estado ni colaboradores runtime (el dict
`agents` es un parámetro, no una dependencia inyectada). Un `@staticmethod` es
el contrato mínimo que (a) cumple el nombre `TeamFactory` de SPEC_01, (b)
**replica exactamente** el patrón shipped de `AgentFactory.build()` (slice #1),
(c) deja crecer limpiamente: cuando #2 añada `DependencyManager`, el cambio es
`build(cfg, agents, *, deps: DependencyManager | None = None)` manteniendo
compat hacia atrás. Static method ahora = cero boilerplate de instanciación en
los callers futuros (WorkflowFactory, runtime loader).

### Decision A2: Member resolution por lookup directo en dict — `agents[member.agent]`

**Choice**: Un loop `for m in cfg.members:` que busca `m.agent` (string) en el
dict `agents` y acumula las instancias `Agent` resueltas en una lista. Si
`m.agent not in agents`, se eleva `ValueError` con el nombre ofensor **antes**
de invocar `agno.Team(...)`.

**Alternatives considered**:
- Usar `agents.get(m.agent)` y filtrar `None`. **Rechazado**: enmascara el
  error — un `None` en la lista de members produce un `Team` parcialmente
  roto que falla tarde (en `run()`) con un mensaje criptico de Agno. Fail-fast
  con mensaje claro es el contrato del spec (BDD scenario "RED — referencia de
  agente inexistente").
- Resolver via `DependencyManager` (lazy load de agentes por nombre).
  **Rechazado para este slice**: el `DependencyManager` es el cambio #2. Este
  slice recibe el dict ya construido — el contrato del caller (runtime loader)
  es construir los agentes primero vía `AgentFactory.build()` y pasarlos como
  dict. Mezclar lazy-load ahora infla scope y duplica #2.
- Indexar por `member.member` (id local) en vez de `member.agent` (nombre).
  **Rechazado**: viola el BDD spec ("la correspondencia es **por nombre de
  agente** (`member.agent`)"). `member.member` es el id local del miembro
  dentro del team (puede diferir del nombre del agente referenciado);
  `member.agent` es el nombre canónico del `AgentConfig` — esa es la clave del
  dict.

**Rationale**: El contrato del BDD spec exige (a) correspondencia por
`member.agent`, (b) orden preservado, (c) error claro con el nombre ofensor,
(d) `agno.Team` nunca instanciado parcialmente. El loop con lookup + raise
pre-construcción cumple los cuatro. El `ValueError` (no `KeyError`) se elige
porque (i) el BDD spec exige `ValueError`, (ii) `KeyError` expone internals del
dict ( Mensaje `"'<name>'"`) mientras `ValueError` permite un mensaje accionable
que sugiere verificar la sección `agents:` del YAML.

**Message format**:
`f"Agent not found: {m.agent!r}. Check the 'agents:' section of your YAML."`.
Usa `!r` para que nombres con espacios o caracteres especiales se delimiten
claramente (`'my agent'` vs `my agent`).

### Decision A3: `mode` passthrough — sin `TeamMode(cfg.mode)`, sin re-validación

**Choice**: `Team(mode=cfg.mode)`. El enum se pasa sin transformación.

**Alternatives considered**:
- `TeamMode(cfg.mode)` para "ser explícito". **Rechazado**: `cfg.mode` ya es
  una instancia `TeamMode` (Pydantic coerciona en el boundary de `TeamConfig`:
  `mode: TeamMode = Field(default=TeamMode.coordinate)`). `TeamMode(cfg.mode)`
  es idempotente pero **ruidoso** — sugiere al lector que hay una conversión
  happening cuando no la hay. El BDD spec scenario "Passthrough de mode"
  exige `team.mode is TeamMode.route` (misma instancia, sin conversión); el
  passthrough directo preserva identidad.
- Re-validar `cfg.mode` contra un set literal (`{"coordinate", "route", ...}`).
  **Rechazado**: viola el BDD spec ("**MUST NOT** re-validar el modo contra un
  set literal — duplica la validación que ya hace el type `TeamMode`").
  Duplicación = deuda: si Agno añade un quinto modo, yaml-agno lo rechazaría
  silenciosamente.

**Rationale**: Principio SSOT. `TeamMode` es el único dueño del set de modos
válidos. `TeamConfig.mode: TeamMode` ya garantiza tipo en el boundary.
Re-verificar en la factory es acoplamiento innecesario al enum. Passthrough =
cero código de conversión = cero bugs de conversión.

### Decision A4: `instructions=cfg.instructions` incondicional (incluso cuando es `None`)

**Choice**: `Team(..., instructions=cfg.instructions)`. Se pasa siempre, aún
cuando `cfg.instructions is None`.

**Alternatives considered**:
- Omitir condicionalmente el kwarg cuando es `None` (patrón
  `kwargs = {...}; if cfg.instructions is not None: kwargs["instructions"] = ...`).
  **Rechazado**: el BDD spec menciona "se OMITE el kwarg", pero la
  **postcondición verificable** es `team.instructions is None` — que se cumple
  idénticamente pasando `instructions=None` (Agno default `team.py:468`).
  La omisión condicional rompe simetría con `AgentFactory.build()` shipped
  (que pasa `instructions=cfg.instructions` unconditional, línea 80 de
  `agent_factory.py`), añade 3 líneas de complejidad sin valor observable, y
  hace el código menos declarativo. El spec describe comportamiento
  (outcome `team.instructions is None`), no implementación literal; esta ADR
  fija la implementación en passthrough para consistencia.

**Rationale**: Consistencia con el patrón shipped (`AgentFactory.build()` pasa
sus 4 campos unconditionalmente, incluyendo `instructions` y `description`
cuando son `None`). Agno 2.6.22 acepta `instructions=None` sin error
(verificado `team.py:468`). El BDD scenario "Instructions None no rompe"
pasa con esta implementación: `team.instructions is None` se cumple porque
Agno asigna `self.instructions = None` literalmente.

### Decision A5: Import directo `from agno.team.team import Team` (no lazy importlib)

**Choice**: `from agno.team.team import Team` y
`from agno.agent import Agent` (solo para type hint del dict) al tope del
módulo, fuera de cualquier función. Sin `importlib.import_module`, sin
`lru_cache`.

**Alternatives considered**:
- Lazy import vía `importlib` dentro de `build()` (patrón DependencyManager).
  **Rechazado para este slice**: el `DependencyManager` es el cambio #2.
  Mezclar lazy import ahora infla scope y duplica la responsabilidad de #2.
- Import condicional (`TYPE_CHECKING` guard para `Agent`). **Parcialmente
  adoptado**: `Agent` se usa solo como type hint en la firma
  (`agents: dict[str, Agent]`), pero también se necesita en runtime para que
  `isinstance` checks en tests funcionen — en este slice se importa en
  runtime para mantener la firma simple y consistente con `agent_factory.py`
  (que importa `Agent` en runtime).

**Rationale**: Matchea exactamente el patrón shipped de `agent_factory.py:23`
(`from agno.agent import Agent`). Separación de concerns entre slices: #3 =
mapeo + member resolution; #2 = resolución de dependencias + lazy loading.
Import directo ahora mantiene #3 cohesivo.

### Decision A6: `workflows` y metadata slots ignorados explícitamente (SSOT delegation)

**Choice**: `build()` lee SOLO `cfg.name`, `cfg.mode`, `cfg.instructions`,
`cfg.members`. Los slots `workflows`, `description`, `tags`, `metadata`, y los
campos `member.role` / `member.member` (id local) de cada `TeamMemberConfig`
no se leen ni se reenvían a `Team(...)`. El factory NO falla si un slot opaco
está populado.

**Alternatives considered**:
- Forwardear `description=cfg.description`, `tags=cfg.tags`,
  `metadata=cfg.metadata` a `Team(...)`. **Rechazado**: rompe SSOT — aunque
  `Team()` acepta `description` (`team.py:467`) y se podría cablear, los
  `tags` y `metadata` de `TeamConfig` son `list[str]` y `dict[str, Any]`
  opacos cuya resolución a objetos Agno nativos es trabajo de SPEC_05.
  Cablear `description` solo (dejando `tags`/`metadata` fuera) crea
  inconsistencia. Mejor postergar los tres a SPEC_05 como bloque coherente.
- Fallar (`raise NotImplementedError`) si `cfg.workflows` está populado.
  **Rechazado**: hace el factory inutilizable para configs reales que ya
  tienen workflows válidos en YAML. Pierde la capacidad de probar construcción
  end-to-end con configs completos.

**Rationale**: Cada sub-sistema tiene su SPEC dueño. Este slice
declarativamente **no opina** sobre workflows ni metadata: los acepta (son
parte del aggregate `TeamConfig`), los nombra en docstring como "deferred" y
deja que los owner SPECs provean los resolvedores. Preserva cohesión del slice
y no genera deuda técnica (el camino queda abierto, no cerrado).

## Class-by-Class Model (literal target code)

> El código siguiente es **literal** — `sdd-apply` crea los archivos `.py`
> byte-for-byte con este contenido. No añadir ni quitar líneas.

### `src/yaml_agno/factories/team_factory.py`

```python
"""TeamFactory — builds a native ``agno.Team`` from a ``TeamConfig`` and a
dict of pre-built agents.

This is slice #3 of SPEC_01 (4-slice factory chain). It composes an
``agno.Team`` by (1) resolving each ``TeamMemberConfig.agent`` (string name)
against the supplied ``agents`` dict of already-constructed ``agno.Agent``
instances, and (2) mapping the 3 identity/behavior fields of ``TeamConfig``
(SPEC_02) — ``name``, ``mode``, ``instructions`` — plus the resolved
``members`` list to the corresponding ``agno.Team`` constructor kwargs.

The opaque ``workflows`` slot, plus ``description``, ``tags``, and
``metadata``, are intentionally NOT forwarded in this slice. ``workflows``
resolution is owned by WorkflowFactory (slice #4) and SPEC_01 §4;
``description``/``tags``/``metadata`` forwarding is owned by SPEC_05. The
per-member fields ``TeamMemberConfig.role`` and ``TeamMemberConfig.member``
(local id) are not consumed: ``agno.Team`` has no per-member metadata slot in
its slice-#3 constructor surface.

Contract:
    - ``TeamConfig`` is already Pydantic-validated (member uniqueness, mode
      minimum counts, non-empty name). This factory performs NO re-validation.
    - ``agents`` is supplied pre-built by the caller (runtime loader). The
      factory does NOT instantiate agents — that is ``AgentFactory.build()``
      (slice #1).
    - ``TeamConfig`` has NO ``model`` field. ``agno.Team(model=None)`` is the
      Agno default (``agno/team/team.py:441``); the team delegates the model to
      its members at ``run()`` time. This factory MUST NOT pass ``model=``.
    - Construction is pure assignment; no network, no LLM instantiation, no
      provider resolution occurs until ``run()`` or ``arun()`` is invoked.

@ai-directive: Behavioral SSOT is
openspec/changes/team-factory/specs/team-factory/spec.md; architectural SSOT is
specs/SPEC_01_AGENT_FACTORY.md. Discrepancies resolve in their favor. This
module consumes SPEC_02 (TeamConfig) read-only.
"""

from __future__ import annotations

from agno.agent import Agent
from agno.team.team import Team

from yaml_agno.models.config.team_config import TeamConfig

__all__ = ["TeamFactory"]


class TeamFactory:
    """Builds ``agno.Team`` instances from a validated ``TeamConfig`` and a
    dict of pre-built ``agno.Agent`` instances.

    Slice #3 scope (composition + 3 identity fields):

        +--------------------------+--------------------------+-----------+
        | TeamConfig field         | agno.Team kwarg          | Mapping   |
        +--------------------------+--------------------------+-----------+
        | name: str                | name                     | direct    |
        | mode: TeamMode           | mode                     | passthru  |
        | instructions: str | None | instructions             | direct    |
        | members: list[MemberCfg] | members                  | resolve   |
        +--------------------------+--------------------------+-----------+
        | workflows                | (not forwarded)          | deferred  |
        | description, tags,       | (not forwarded)          | deferred  |
        | metadata                 |                          |           |
        +--------------------------+--------------------------+-----------+

    ``members`` resolution: for each ``TeamMemberConfig`` in ``cfg.members``,
    the factory looks up ``member.agent`` (the referenced AgentConfig name) in
    the ``agents`` dict and collects the resulting ``Agent`` instances in YAML
    order. A missing reference raises ``ValueError`` with the offending name
    **before** ``agno.Team`` is constructed (no partial Team is ever built).

    Deferred slots are accepted silently (they are valid members of
    ``TeamConfig``) and will be resolved by their owner SPECs.

    This class exposes a static ``build()`` method; it holds no state and is
    not instantiated.
    """

    @staticmethod
    def build(cfg: TeamConfig, agents: dict[str, Agent]) -> Team:
        """Build a native ``agno.Team`` from a ``TeamConfig`` and pre-built agents.

        Member resolution iterates ``cfg.members`` in order and looks up each
        ``member.agent`` (string name) in ``agents``. The resolved ``Agent``
        instances are passed to ``agno.Team(members=...)`` preserving YAML
        order. Only ``name``, ``mode``, ``instructions``, and the resolved
        ``members`` are mapped; ``workflows``, ``description``, ``tags``, and
        ``metadata`` are intentionally ignored in this slice (see class
        docstring).

        Args:
            cfg: A validated ``TeamConfig`` (SPEC_02). Its ``mode`` field is
                already a ``agno.team.mode.TeamMode`` enum instance (Pydantic
                coerces it at the schema boundary) and is forwarded verbatim.
                Its ``members`` is a list of ``TeamMemberConfig``, each
                carrying an ``agent`` field naming an ``AgentConfig``.
            agents: A mapping from AgentConfig name to a pre-built
                ``agno.Agent`` instance (produced by ``AgentFactory.build()``,
                slice #1). The factory does NOT instantiate agents; the caller
                is responsible for building every agent referenced by
                ``cfg.members``.

        Returns:
            A constructed ``agno.Team``. Per ``agno/team/team.py:437-468``,
            construction is pure assignment — no network call, no LLM
            instantiation, no provider resolution occurs until ``run()`` or
            ``arun()`` is invoked. The returned team has ``model=None`` (Agno
            default) because ``TeamConfig`` has no ``model`` field; the team
            delegates the model to its members at run time.

        Raises:
            ValueError: If any ``TeamMemberConfig.agent`` references a name
                absent from ``agents``. The message includes the offending
                name and a hint to check the YAML ``agents:`` section. Raised
                before ``agno.Team`` is constructed, so no partial Team is
                ever produced.
        """
        resolved_members: list[Agent] = []
        for member in cfg.members:
            agent_name = member.agent
            if agent_name not in agents:
                raise ValueError(
                    f"Agent not found: {agent_name!r}. "
                    "Check the 'agents:' section of your YAML."
                )
            resolved_members.append(agents[agent_name])

        return Team(
            members=resolved_members,
            mode=cfg.mode,
            name=cfg.name,
            instructions=cfg.instructions,
        )
```

### `src/yaml_agno/factories/__init__.py`

```python
"""Factories package — builds native Agno objects from validated configs.

Re-exports the public factory classes so callers can do
``from yaml_agno.factories import AgentFactory`` or
``from yaml_agno.factories import TeamFactory``.
"""

from yaml_agno.factories.agent_factory import AgentFactory
from yaml_agno.factories.team_factory import TeamFactory

__all__ = ["AgentFactory", "TeamFactory"]
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/team_factory.py` | Create | `TeamFactory.build(cfg, agents) -> agno.Team`. Static method, member-resolution loop with `ValueError` on miss, 3 identity fields mapped + `members` resolved. |
| `src/yaml_agno/factories/__init__.py` | Modify | Add `from yaml_agno.factories.team_factory import TeamFactory` and append `"TeamFactory"` to `__all__`. Existing `AgentFactory` re-export unchanged. |
| `tests/unit/factories/test_team_factory.py` | Create | BDD scenarios RED→GREEN: golden-path 2-member resolution + 3 identity fields, member-order preservation, missing-agent `ValueError`, `instructions=None` OK, all 4 `TeamMode` values construct, opaque-slot tolerance (`workflows` populated). Offline, no LLM, no network. |

**Total**: 2 archivos nuevos + 1 modificado = 3 files. Solo
`factories/__init__.py` preexiste (ya shipping con `AgentFactory` re-export).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `isinstance(result, agno.Team)` tras `build(cfg, agents)` | `@pytest.mark.unit` — construcción directa, sin `.run()`. |
| Unit | Member resolution: `result.members == [agents["a1"], agents["a2"]]` en orden | Golden path 2 miembros, assert de igualdad de lista. |
| Unit | Member order preservation: `[m1.agent="z", m2.agent="a", m3.agent="m"]` → `[agents["z"], agents["a"], agents["m"]]` | 3 miembros en orden no-alfabético. |
| Unit | Missing agent: `cfg.members=[{agent:"no_existe"}]`, `agents={}` → `ValueError` con `"no_existe"` en `str(exc)` | `pytest.raises(ValueError)` + `match`. Assert Team nunca construido (no hay forma directa; el raise pre-construcción lo garantiza estructuralmente). |
| Unit | `instructions=None` construye OK y `result.instructions is None` | Caso minimal: `cfg` sin `instructions`. |
| Unit | `instructions="You orchestrate invoices."` → `result.instructions == "You orchestrate invoices."` | String completa pasada. |
| Unit | `result.mode is cfg.mode` (misma instancia, sin conversión) | Un escenario por cada uno de los 4 `TeamMode`: `coordinate`, `route` (≥2 miembros), `broadcast` (≥2 miembros), `tasks`. |
| Unit | `result.name == cfg.name` | Assert de igualdad estricta. |
| Unit | `result.model is None` (no se pasa `model=`, default de Agno) | Assert explícito — confirma Decision A6. |
| Unit | Tolerancia a slots opacos: `build()` NO falla cuando `cfg.workflows=[{...}]`, `cfg.description="..."`, `cfg.tags=["x"]`, `cfg.metadata={"k":"v"}` están populados. | Construir cfg con todos los opacos llenos y verificar `isinstance(result, Team)`. |
| Unit | `member.role` y `member.member` (id local) se ignoran sin error | Cfg con `members=[{member:"local_id", agent:"a1", role="leader"}]` construye OK. |
| Contract | Smoke import: `from yaml_agno.factories import TeamFactory` funciona en runtime. | Test separado o `python -c`. |

**Sin tests de**: `.run()`, `.arun()`, network, provider resolution, lazy
agent loading (todo deferred). Sin mocks de Agno — se usa el `Team` real
porque la construcción es pura asignación. Los `Agent` del dict se construyen
vía `AgentFactory.build()` real (slice #1 shipped) o directamente vía
`agno.agent.Agent(name=..., model=...)` con un model string trivial como
`"openai:gpt-4o"` (no se invoca al provider — solo asignación).

## TDD Approach

Strict TDD Mode está ACTIVO (verificado en `sdd-init/doc.reca` engram #531:
`strict_tdd: true`, test runner `python -m pytest`). Por tarea (ver `tasks.md`
futuro):

1. **RED**: escribir `tests/unit/factories/test_team_factory.py` con todos los
   escenarios BDD del spec referenciando
   `from yaml_agno.factories import TeamFactory` — falla con `ImportError`
   (módulo no existe).
2. **GREEN**: crear `team_factory.py` + actualizar `__init__.py` con el código
   literal de este design — todos los tests pasan.
3. **REFACTOR**: no se anticipa. El código es un loop + 4 kwargs. Si emerge
   duplicación con `AgentFactory` (p.ej. un helper de "passthrough kwargs"),
   extraer — pero en este slice la forma más simple es la actual.

Ciclo RED→GREEN→REFACTOR por tarea atómica, no bulk. Cada escenario BDD del
spec es una tarea con su propio ciclo.

## Verification Strategy

1. **`python -m pytest -m unit tests/unit/factories/test_team_factory.py`** —
   verde. Cobertura: golden path, member order, missing-agent error,
   `instructions=None`, 4 modos, opaque-slot tolerance, smoke import.
2. **`python -m pytest -m unit tests/unit/factories/`** — verde integral
   (agent_factory + team_factory; la adición de `TeamFactory` al `__init__.py`
   no rompe el re-export de `AgentFactory`).
3. **`ruff check src/yaml_agno/factories tests/unit/factories`** — limpio
   (line-length 120, import sort, etc.).
4. **`mypy src/yaml_agno/factories`** — limpio. **Caveat**: Agno mypy stubs
   usan `ignore_missing_imports=true`, así que un import path erróneo NO falla
   type-check. La verificación REAL es el runtime import en los tests.
5. **Smoke runtime**:
   ```bash
   python -c "from yaml_agno.factories import TeamFactory; print(TeamFactory)"
   ```
   debe funcionar sin error.
6. **Team() signature re-confirm** (apply-time, defensive):
   ```bash
   python -c "import inspect; from agno.team.team import Team; print(inspect.signature(Team.__init__))"
   ```
   Debe mostrar `members`, `mode`, `name`, `instructions` como params. Si Agno
   upstream cambia la firma (p.ej. renombra `instructions`), los tests
   capturarán el break — pero el design asume Agno 2.6.22 pinneado.
7. **Construct end-to-end smoke** (apply-time):
   ```bash
   python -c "
   from agno.agent import Agent
   from agno.team.team import Team
   from agno.team.mode import TeamMode
   a = Agent(name='x', model='openai:gpt-4o')
   t = Team(members=[a], mode=TeamMode.coordinate, name='t')
   print(type(t).__name__, t.name, t.mode, len(t.members))
   "
   ```
   Debe imprimir `Team t TeamMode.coordinate 1`.
8. **SSOT intocado**: `git diff --exit-code src/yaml_agno/models/ specs/
   openspec/specs/` — vacío (SPEC_02 + specs no mutados; este slice solo
   añade factory code + tests).

## Migration / Rollback

**No migration required.** Todo el cambio vive en archivos nuevos bajo
`src/yaml_agno/factories/team_factory.py` y `tests/unit/factories/`, salvo
`factories/__init__.py` que pasa de re-exportar 1 símbolo a re-exportar 2.

Rollback = `git revert` del commit. Esto restaura `factories/__init__.py` a su
estado de 1 símbolo (`AgentFactory` only) y elimina los 2 archivos nuevos. Sin
mutación de datos, sin feature flags, sin dependientes rotos:
`WorkflowFactory` (slice #4) aún no existe; el runtime loader que orquestará
los 4 factories tampoco. `AgentFactory` shipped sigue funcionando
independientemente.

## Open Questions

- [ ] **Confirmación apply-time de `Team(members=[Agent], ...)` sin
      instanciación parcial**: el design asume que `Team.__init__` con un
      `Agent` ya construido en `members` no valida tipos en runtime de forma
      que rechace instancias válidas. Verificado leyendo `team.py:437-468` +
      el tipo declarado `Union[List[Union[Agent, "Team"]], ...]`, pero
      **re-confirmar en `sdd-apply`** con el smoke test #7 de Verification. Si
      Agno hiciera validación estricta (p.ej. exigir `TeamMember` wrapper),
      el factory necesitaría un adaptador — pero eso rompería el contrato
      documentado del constructor, así que likelihood muy baja.
- [ ] **Costo de import de `agno.team.team` en tests**: aceptado como
      inherente al framework (ya pagado por `agent_factory.py`). Si ralentiza
      la suite, #2 (DependencyManager) puede introducir lazy import. No
      bloquea este slice.
