# Delta for TeamFactory

> **Origen**: SPEC_01 §2 (Specialized Teams Contracts), §5.1 escenarios 2/3/4.
> **Contrato shipped**: `src/yaml_agno/models/config/team_config.py` (`TeamConfig`,
> `TeamMemberConfig`). `TeamConfig` **NO** tiene campo `model`.
> **Agno verificado**: `agno/team/team.py:437` — `Team.__init__(members, ..., mode=None,
> name=None, instructions=None, ...)`; `model` es opcional (`= None`).
> **Alcance**: SPEC_01 slice #3. Workflows están **deferred** (slot opaco, no se procesa).

## ADDED Requirements

### Requirement: TeamFactory construye un agno.Team válido

`TeamFactory.build(cfg, agents)` DEBE retornar un objeto `isinstance(agno.Team)`.
La fábrica NO DEBE reenviar parámetros que no existen en `TeamConfig`
(en particular, NO existe resolución de `model`).

- **Entrada**: `cfg: TeamConfig` (ya validado por Pydantic), `agents: dict[str, Agent]`
  (instancia ya construidas por `AgentFactory`).
- **Salida**: instancia de `agno.team.team.Team`.
- **Postcondición**: `team.mode == cfg.mode` y `team.name == cfg.name`.

#### Scenario: Golden path — equipo de 2 miembros resueltos

- GIVEN un `TeamConfig` con `name="t"`, `mode=TeamMode.coordinate` y `members=[{member:"m1", agent:"a1"}, {member:"m2", agent:"a2"}]`
- AND `agents={"a1": agentA, "a2": agentB}` (dos `agno.Agent` ya construidos)
- WHEN se llama `TeamFactory.build(cfg, agents)`
- THEN el retorno es `isinstance(agno.Team)`
- AND `team.members` contiene exactamente `[agentA, agentB]` en ese orden
- AND `team.mode == TeamMode.coordinate`
- AND `team.name == "t"`

#### Scenario: Golden path con instructions pasadas por completo

- GIVEN un `TeamConfig` con `instructions="You orchestrate invoices."`
- WHEN se llama `build(cfg, agents)`
- THEN `team.instructions == "You orchestrate invoices."`
- AND ningún otro campo de identidad se altera

### Requirement: Resolución de miembros por nombre

Para cada `TeamMemberConfig` en `cfg.members`, la fábrica DEBE buscar
`member.agent` (string de nombre) en el dict `agents` y ensamblar la lista
`members=[...]` en el **mismo orden** que aparece en el YAML. El `TeamMemberConfig.role`
y `TeamMemberConfig.member` (id local) NO son pasados a `agno.Team`
(`Team` no acepta metadata por miembro en su constructor de slice #3);
se ignoran silenciosamente en este slice.

- **MUST**: la correspondencia es **por nombre de agente** (`member.agent`), no por `member.member`.
- **MUST NOT**: la fábrica NO DEBE instanciar agentes; recibe el dict ya construido.

#### Scenario: Orden de miembros preservado

- GIVEN `members=[{agent:"z"}, {agent:"a"}, {agent:"m"}]` y `agents` con los tres
- WHEN se llama `build(cfg, agents)`
- THEN `team.members == [agents["z"], agents["a"], agents["m"]]` (mismo orden)

### Requirement: Referencia de agente faltante — error claro

Si un `TeamMemberConfig.agent` referencia un nombre **ausente** del dict `agents`,
la fábrica DEBE elevar `ValueError` con un mensaje que incluya el nombre faltante,
**antes** de invocar al constructor de `agno.Team`.

- **MUST**: el mensaje contiene el nombre del agente no encontrado.
- **SHOULD**: el mensaje sugiere verificación de la sección `agents:` del YAML.

#### Scenario: RED — referencia de agente inexistente

- GIVEN `cfg.members=[{member:"x", agent:"no_existe"}]` y `agents={}` (vacío)
- WHEN se llama `build(cfg, agents)`
- THEN se eleva `ValueError`
- AND `str(exc)` contiene `"no_existe"`
- AND `agno.Team` NUNCA es instanciado (no se construye un Team parcial)

### Requirement: Mapeo directo de TeamMode

`cfg.mode` ya es un `agno.team.mode.TeamMode` (Pydantic lo coerciona desde
el string lowercase del YAML). La fábrica DEBE pasarlo sin transformación:
`Team(mode=cfg.mode)`. **MUST NOT** re-validar el modo contra un set literal
en la fábrica — eso duplica la validación que ya hace el type `TeamMode`.

#### Scenario: Passthrough de mode

- GIVEN `cfg.mode == TeamMode.route`
- WHEN se llama `build(cfg, agents)`
- THEN `team.mode is TeamMode.route` (misma instancia, sin conversión)

### Requirement: Identidad y comportamiento pasados por completo

La fábrica DEBE mapear `cfg.name` → `Team(name=)` y `cfg.instructions` →
`Team(instructions=)`. Si `cfg.instructions is None`, se OMITE el kwarg
(dejar el default `None` de Agno). **MUST NOT** inyectar `description`,
`tags`, ni `metadata` en este slice (slots no cableados aún).

#### Scenario: Instructions None no rompe

- GIVEN `cfg.instructions is None`
- WHEN se llama `build(cfg, agents)`
- THEN se construye el Team sin pasar `instructions=`
- AND `team.instructions is None`

### Requirement: NO resolución de model

`TeamConfig` **NO posee** campo `model`. La fábrica **MUST NOT** inventar,
derivar ni pasar un `model=` a `agno.Team`. `Team(model=None)` es el default
de Agno (`team.py:441`) y es válido: el team delega el modelo a sus miembros.

- **MUST NOT**: pasar `model=` explícitamente.
- **MUST NOT**: lanzar error por ausencia de model.

#### Scenario: Sin model — Team se construye igual

- GIVEN un `TeamConfig` sin ningún campo de model (no existe)
- WHEN se llama `build(cfg, agents)`
- THEN `team.model is None`
- AND no se pasa `model=` al constructor de `agno.Team`

### Requirement: Slot opaco `workflows` ignorado sin error

`cfg.workflows` existe en `TeamConfig` como `list[dict[str, Any]]` (slot opaco,
SPEC_01 §4). En este slice la fábrica **MUST NOT** procesarlo, validarlo, ni
pasarlo a `agno.Team`. Su presencia NO DEBE causar error; su contenido se
preserva solo en `cfg` (no se pierde, pero no se cablea).

- **MUST**: `build` ignora `cfg.workflows` completamente.
- **MUST NOT**: elevar error por workflows no vacíos.

#### Scenario: Workflows presentes, sin error

- GIVEN `cfg.workflows=[{"workflow": "x", "steps": [...]}]`
- WHEN se llama `build(cfg, agents)`
- THEN no se eleva error
- AND `agno.Team` no recibe ningún argumento derivado de workflows

### Requirement: Sin re-validación de invariantes de TeamConfig

`TeamConfig` ya valida en su boundary (Pydantic): unicidad de `member.member`,
no-vacío de `name`, counts mínimos por modo (`route`/`broadcast` ≥ 2).
La fábrica **MUST NOT** re-ejecutar esas validaciones — son responsabilidad
del schema, no de la fábrica de runtime. Si el contrato del schema cambia,
la fábrica no se acopla.

- **MUST NOT**: re-validar unicidad de miembros.
- **MUST NOT**: re-validar counts mínimos por modo.
- **MUST NOT**: re-validar `name` no-vacío.

#### Scenario: Modo route con 1 miembro — error viene del schema, no de la fábrica

- GIVEN un intento de `TeamConfig(name="t", mode=TeamMode.route, members=[único])`
- WHEN Pydantic valida el cfg (ANTES de llegar a la fábrica)
- THEN se eleva `ValueError` desde `TeamConfig.validate_mode_requirements`
- AND la fábrica nunca es invocada

### Requirement: Los 4 modos construyen correctamente

Para cada uno de los 4 valores de `TeamMode` (`coordinate`, `route`,
`broadcast`, `tasks`), con un `members` válido para ese modo, `build` DEBE
producir un `agno.Team` cuyo `team.mode` coincide.

#### Scenario: coordinate construye

- GIVEN `cfg.mode=TeamMode.coordinate`, `members` con 1+ agente(s)
- WHEN `build(cfg, agents)`
- THEN `team.mode is TeamMode.coordinate`

#### Scenario: route construye (≥2 miembros)

- GIVEN `cfg.mode=TeamMode.route`, `members` con 2 agentes (schema exige ≥2)
- WHEN `build(cfg, agents)`
- THEN `team.mode is TeamMode.route`

#### Scenario: broadcast construye (≥2 miembros)

- GIVEN `cfg.mode=TeamMode.broadcast`, `members` con 2 agentes
- WHEN `build(cfg, agents)`
- THEN `team.mode is TeamMode.broadcast`

#### Scenario: tasks construye

- GIVEN `cfg.mode=TeamMode.tasks`, `members` con 1+ agente(s)
- WHEN `build(cfg, agents)`
- THEN `team.mode is TeamMode.tasks`
