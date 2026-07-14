# skills-foundation Specification

> **Slice**: SPEC_30 slice A — SkillsConfig schema + SkillsFactory (adapter puro).
> **Opción**: B (opaque + resolve at factory). `AgentConfig.skills` permanece opaco; la
> resolución a `agno.skills.Skills` ocurre exclusivamente en `SkillsFactory.build`.
> **Aplazado (slice B)**: wiring de AgentFactory, contrato de system-prompt, hot-reload, e2e.

## Purpose

Exponer el sistema de Skills de Agno a yaml-agno como una capa fina de delegación. Slice A
introduce el schema `SkillsConfig` (fuente de verdad declarativa) y el adapter
`SkillsFactory.build(config) -> Skills | None`, que traduce entradas YAML en loaders
`LocalSkills` delegados a Agno. yaml-agno NO parsea `SKILL.md`, NO genera tools y NO
construye el snippet de system-prompt: todo eso lo posee Agno.

## Requirements

### Requirement: SkillsConfig — schema de configuración

El sistema SHALL proveer un `SkillsConfig` (modelo Pydantic) como SSOT del bloque
`agent.skills`. Cada entrada MUST exponer `path: str` (no vacío) y `validate: bool`
(default `True`). El modelo MUST rechazar claves desconocidas (`extra="forbid"`). `path`
MUST ser una cadena de 1–1024 caracteres; yaml-agno valida el string pero NO pre-stat
el directorio (la semántica de filesystem la posee `LocalSkills`).

#### Scenario: SkillsConfig con entrada válida

- GIVEN un dict `{"path": "./skills/brand-audit", "validate": True}`
- WHEN `SkillsConfig.model_validate({"entries": [dict]})` se ejecuta
- THEN `entries[0].path == "./skills/brand-audit"` y `entries[0].validate is True`

#### Scenario: SkillsConfig rechaza claves desconocidas

- GIVEN un dict `{"path": ".", "body": "inline no permitido"}`
- WHEN `SkillsConfig.model_validate({"entries": [dict]})` se ejecuta
- THEN se lanza `pydantic.ValidationError` (extra forbidden)

### Requirement: SkillsFactory.build — contrato del adapter

El sistema SHALL proveer `SkillsFactory.build(config) -> Skills | None`. `build` MUST
aceptar `config: SkillsConfig | None` y retornar una instancia de `agno.skills.Skills`
cuando `config` sea no-`None`, habilitado y con entradas; de lo contrario MUST retornar
`None` (Sección "None on empty"). `build` MUST delegar todo el cargado a Agno — no
parsea `SKILL.md`, no valida estructura de bundle, no genera access tools.

#### Scenario: golden SkillsFactory.build con temp dir y SKILL.md

- GIVEN un `tempfile.TemporaryDirectory()` que contiene un subfolder `my-skill/` con un
  `SKILL.md` válido (frontmatter `name: my-skill`, `description: test`, body markdown)
- AND un `SkillsConfig(entries=[LocalSkillEntry(path=<tempdir>, validate=True)])`
- WHEN `SkillsFactory.build(config)` se ejecuta
- THEN el valor retornado es una instancia de `agno.skills.Skills`
- AND `Skills.get_skill_names()` incluye `"my-skill"`

#### Scenario: Skills instance tiene skills cargadas

- GIVEN un `Skills` retornado por `build` con un bundle `my-skill`
- WHEN se invoca `get_all_skills()`
- THEN la lista contiene un `Skill` con `name == "my-skill"` y `description == "test"`

### Requirement: SkillsFactory construye LocalSkills loaders

`build` MUST construir un `LocalSkills(path=entry.path, validate=entry.validate)` por cada
entrada de `config.entries`. Los loaders MUST pasarse a `Skills(loaders=[...])`. El orden
de los loaders MUST preservar el orden de las entradas (last-write-wins en colisión de
nombres es comportamiento heredado de Agno).

#### Scenario: dos entradas producen dos loaders y skills mergeadas

- GIVEN un `tempfile` con dos subfolders `alpha` y `beta`, cada uno con `SKILL.md`
- AND un `SkillsConfig` con dos entradas apuntando a cada subfolder
- WHEN `build(config)` se ejecuta
- THEN `get_skill_names()` contiene `"alpha"` y `"beta"`

### Requirement: SkillsFactory envuelve loaders en Skills

`build` MUST construir exactamente un `Skills(loaders=loaders)` a partir de la lista de
`LocalSkills`. yaml-agno MUST NOT instanciar `Skill` directamente ni manipular el dict
interno de `Skills`.

#### Scenario: Skills(loaders=...) construido con la lista de LocalSkills

- GIVEN un `SkillsConfig` con una entrada válida
- WHEN `build(config)` se ejecuta
- THEN el retorno es `Skills` con `len(loaders) == len(entries)` conceptualmente

### Requirement: SkillValidationError propaga (validate=True)

Cuando `validate=True` y un bundle es inválido (ej. frontmatter ausente, nombre con
mayúsculas), `LocalSkills.load()` lanza `SkillValidationError`. `build` MUST propagar la
excepción sin capturarla ni enmascararla. El caller decide el manejo de errores.

#### Scenario: validate=True rechaza skill dir inválida

- GIVEN un `tempfile` con un subfolder `BadName` (mayúsculas) que contiene un `SKILL.md`
  sin frontmatter, y `validate=True`
- WHEN `build(config)` se ejecuta
- THEN se lanza `SkillValidationError` (propagado desde `LocalSkills`)

### Requirement: validate=False omite la validación

Cuando `validate=False`, `LocalSkills` omite `validate_skill_directory`. `build` MUST
completar sin lanzar `SkillValidationError` para el mismo bundle que fallaría con
`validate=True`.

#### Scenario: validate=False omite la validación estructural

- GIVEN el mismo bundle inválido del escenario anterior pero `validate=False`
- WHEN `build(config)` se ejecuta
- THEN no se lanza `SkillValidationError`
- AND `build` retorna una instancia `Skills` (el skill se carga lenientemente o se omite
  según comportamiento de Agno)

### Requirement: SkillsFactory retorna None cuando config es None o vacío

`build` MUST retornar `None` cuando: (a) `config is None`, (b) `config.entries` es una
lista vacía. Esto garantiza `Agent(skills=None)` como default seguro — sin snippet, sin
access tools.

#### Scenario: None on empty config

- GIVEN `config = SkillsConfig(entries=[])` y `config = None`
- WHEN `build(config)` se ejecuta en ambos casos
- THEN ambos retornan `None` (tipo `None`, no una `Skills` vacía)

### Requirement: AgentConfig.skills permanece opaco (invariante Opción B)

`AgentConfig.skills` MUST permanecer tipado como opaco (`dict[str, Any] | None` o slot
equivalente sin schema fuerte). yaml-agno MUST NOT agregar validación de skills en
`AgentConfig` ni reificar `SkillsConfig` dentro del aggregate del agente en slice A. La
resolución de opaco → `SkillsConfig` → `Skills` ocurre exclusivamente dentro de
`SkillsFactory.build` (o su caller de wiring en slice B). Slice A no toca `AgentConfig`.

#### Scenario: invariante opaco de AgentConfig

- GIVEN el estado actual de `AgentConfig.skills` (slot opaco)
- WHEN slice A (SkillsConfig + SkillsFactory) se aplica
- THEN `AgentConfig.skills` conserva su tipo opaco, sin referencia a `SkillsConfig`
- AND `SkillsFactory.build` es la única superficie que conoce `SkillsConfig` y `Skills`

## Out of Scope (DEFER a slice B)

Los siguientes elementos están FUERA de slice A y se abordarán en slice B o posterior:

- **AgentFactory wiring**: pasar `skills=SkillsFactory.build(...)` al constructor de
  `Agent` (TASK_005 de SPEC_30).
- **Contrato de system-prompt**: verificar que `<skills_system>` se inyecta
  (TASK_006).
- **Presence de access tools**: verificar `get_skill_instructions`,
  `get_skill_reference`, `get_skill_script` en el tool set del agente (TASK_007).
- **Hot-reload**: exponer `Skills.reload()` vía lifecycle hook (TASK_008).
- **Path traversal**: test de contrato sobre `safe_join_relative_path` (TASK_009).
- **Heuristic single-folder vs directory**: test de contrato sobre `LocalSkills`
  (TASK_010).
- **E2E integration**: agent que responde usando un skill (TASK_011).

## Assumptions

1. `from agno.skills import Skills, LocalSkills` es importable (Agno 2.6.22 verificado en
   exploración #2137: `agno/skills/__init__.py` expone ambos símbolos).
2. `LocalSkills(path: str, validate: bool = True)` y `Skills(loaders: List[SkillLoader])`
   son las firmas canónicas (exploración #2137, loaders/local.py:12, agent_skills.py:16).
3. `SkillValidationError` se importa de `agno.skills.errors` (exploración #2137).
4. `AgentConfig.skills` ya existe como slot opaco
   (`src/yaml_agno/models/config/agent_config.py:66`); slice A no lo modifica.
5. La factoría se nombra `SkillsFactory` (decisión del prompt de tarea; alinea con la
   convención `*_factory.py` del códigobase: `tool_factory.py`, `agent_factory.py`).
