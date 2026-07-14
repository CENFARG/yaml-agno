# Delta for skills-wiring (SPEC_30 slice B)

> Cierra SPEC_30. Slice A (`skills-foundation`) entregó `SkillsConfig` +
> `SkillsFactory.build`. Este delta describe el cableado en `AgentFactory.build`:
> el agente con skills recibe `Agent(skills=...)`, el bloque de system prompt
> de skills, las 3 access tools, y el hot-reload sobre el atributo público.
> La nariz de validación permanece en `SkillsFactory` (Option B, invariante de
> slice A). `AgentConfig.skills` SIGUE siendo opaco (`dict | None`).

## ADDED Requirements

### Requirement: AgentFactory.build cablea cfg.skills hacia SkillsFactory.build

`AgentFactory.build` DEBE invocar `SkillsFactory.build(cfg.skills)` y reenviar
el resultado a `agno.Agent(skills=...)`. Cuando `cfg.skills` es `None`, la
fábrica DEBE devolver `None` y `Agent` DEBE recibir `skills=None`.

El cableado NO debe interpretar, validar nuevamente, ni transformar el dict
opaco — `SkillsFactory` es el único punto de validación (Option B, slice A).
La firma pública de `AgentFactory.build` NO debe cambiar para los callers
existentes.

#### Scenario: Agente dorado con skills — reenvío de SkillsFactory a Agent

- GIVEN un `AgentConfig` cuyo slot `skills` es un dict opaco `{"path": "<dir con SKILL.md>", "validate": true}`
- WHEN `AgentFactory.build(cfg)` se ejecuta
- THEN `SkillsFactory.build(cfg.skills)` es invocado exactamente una vez
- AND el `Agent` resultante tiene `agent.skills` igual a la instancia `Skills` devuelta por la fábrica
- AND `agent.skills` NO es `None`

#### Scenario: None forwarding — cfg.skills None produce Agent(skills=None)

- GIVEN un `AgentConfig` cuyo slot `skills` es `None`
- WHEN `AgentFactory.build(cfg)` se ejecuta
- THEN `SkillsFactory.build(None)` devuelve `None`
- AND el `Agent` resultante se construye con `skills=None`
- AND `agent.skills is None`

### Requirement: Agente con skills recibe el bloque de system prompt de skills

Cuando `AgentFactory.build` cablea un `Skills` no nulo, Agno DEBE inyectar la
salida de `skills.get_system_prompt_snippet()` en el system prompt del agente.
yaml-agno NO genera ni modifica el snippet — solo garantiza que la instancia
`Skills` llega al constructor de `Agent` para que Agno haga la inyección.

#### Scenario: System prompt contiene el bloque skills_system

- GIVEN un `AgentConfig` con un slot `skills` apuntando a un directorio con un `SKILL.md` válido
- WHEN `AgentFactory.build(cfg)` construye el `Agent`
- AND se arma el system prompt del agente
- THEN el system prompt contiene el marcador `<skills_system>`
- AND el snippet lista la skill con su nombre y descripción
- AND el snippet indica que los nombres de skills NO son funciones invocables

### Requirement: Agente sin skills (cfg.skills None) NO tiene bloque de skills (backward compat)

Cuando `cfg.skills` es `None`, el `Agent` resultante NO DEBE contener el bloque
`<skills_system>` en su system prompt. Esta es la garantía de compatibilidad
hacia atrás: los agentes existentes sin skills son idénticos a los de slice #1
(behavior cero-rotura).

#### Scenario: Agente sin skills — sin bloque en system prompt

- GIVEN un `AgentConfig` cuyo slot `skills` es `None`
- WHEN `AgentFactory.build(cfg)` construye el `Agent`
- AND se arma el system prompt del agente
- THEN el system prompt NO contiene el marcador `<skills_system>`
- AND el system prompt es equivalente al de un agente construido sin el parámetro `skills`

### Requirement: Agente con skills expone las 3 access tools

Cuando `AgentFactory.build` cablea un `Skills` no nulo, el set de tools del
agente DEBE contener exactamente tres `Function` de Agno nombradas
`get_skill_instructions`, `get_skill_reference`, y `get_skill_script`.
yaml-agno NO genera estas tools — las provee Agno a través de
`skills.get_tools()`.

#### Scenario: Tres access tools presentes en el agente con skills

- GIVEN un `AgentConfig` con un slot `skills` apuntando a un `SKILL.md` válido
- WHEN `AgentFactory.build(cfg)` construye el `Agent`
- THEN el tool set del agente contiene una `Function` llamada `get_skill_instructions`
- AND contiene una `Function` llamada `get_skill_reference`
- AND contiene una `Function` llamada `get_skill_script`

#### Scenario: Agente sin skills — sin access tools

- GIVEN un `AgentConfig` cuyo slot `skills` es `None`
- WHEN `AgentFactory.build(cfg)` construye el `Agent`
- THEN el tool set del agente NO contiene ninguna `Function` llamada `get_skill_instructions`, `get_skill_reference`, ni `get_skill_script`

### Requirement: Hot-reload opera sobre el atributo público agent.skills

El hot-reload DEBE invocar `agent.skills.reload()` directamente sobre el
atributo público `agent.skills` (agent.py:588). yaml-agno NO DEBE acceder a
atributos privados (`_skills`) ni reimplementar la recarga. Cuando
`agent.skills is None`, el hook de reload DEBE ser un no-op (no levantar
excepción).

#### Scenario: Hot-reload recarga skills editadas en disco

- GIVEN un `Agent` construido con skills que cargaron la skill `brand-audit` en t0
- WHEN el archivo `SKILL.md` de `brand-audit` se edita en disco
- AND se invoca `agent.skills.reload()`
- THEN el diccionario interno de skills se limpia y reconstruye
- AND `get_skill_instructions("brand-audit")` devuelve el cuerpo actualizado

#### Scenario: Hot-reload sobre agente sin skills es no-op

- GIVEN un `Agent` construido con `skills=None`
- WHEN el hook de hot-reload evalúa `agent.skills`
- THEN no se invoca `reload()` sobre `None`
- AND no se levanta ninguna excepción

### Requirement: SkillsFactory.build devuelve None cuando cfg.skills es None

`SkillsFactory.build(None)` DEBE devolver `None` sin construir ningún objeto
Agno. Esto es la raíz del short-circuit de backward-compat: `AgentFactory`
confía en que `None` se propaga sin construir un `Skills` vacío.

#### Scenario: SkillsFactory.build(None) devuelve None sin tocar Agno

- GIVEN el slot `cfg.skills` es `None`
- WHEN `SkillsFactory.build(None)` se invoca
- THEN el valor de retorno es `None`
- AND no se construye ninguna instancia de `LocalSkills` ni `Skills`

## MODIFIED Requirements

### Requirement: AgentFactory.build mapea AgentConfig a agno.Agent

`AgentFactory.build(cfg, resolver=None)` mapea los campos de identidad
(`name`, `instructions`, `description`, `model`), los tools vía `ToolFactory`
cuando se provee `resolver`, y ahora TAMBIÉN cablea `cfg.skills` vía
`SkillsFactory.build` hacia `Agent(skills=...)`. La construcción sigue siendo
asignación pura + dispatch de fábricas: sin red, sin LLM, sin resolución de
provider.

(Previously: AgentFactory.build solo cableaba identidad + tools; el slot
`skills` era aceptado silenciosamente y se perdía. Ahora se reenvía a
`SkillsFactory.build` y llega a `Agent(skills=...)`.)

#### Scenario: Agente con identidad, tools y skills cableados juntos

- GIVEN un `AgentConfig` con `name`, `model`, `tools` no vacío y `skills` no nulo
- WHEN `AgentFactory.build(cfg, resolver)` se ejecuta
- THEN el `Agent` resulta con `name`, `instructions`, `description`, `model` directos
- AND `tools` resueltos vía `ToolFactory`
- AND `skills` cableado vía `SkillsFactory.build`
- AND `agent.skills` NO es `None`

#### Scenario: Agente con identidad y sin tools ni skills (slice #1 intacto)

- GIVEN un `AgentConfig` con `tools=None`, `skills=None`, `resolver=None`
- WHEN `AgentFactory.build(cfg)` se ejecuta
- THEN el `Agent` se construye con `tools=None` y `skills=None`
- AND el comportamiento es idéntico al de slice #1 (cero rotura)

#### Scenario: ValidationError de SkillsFactory se propaga sin tragar

- GIVEN un `AgentConfig` cuyo slot `skills` falla la validación de `SkillsConfig`
- WHEN `AgentFactory.build(cfg)` se ejecuta
- THEN `SkillsFactory.build` levanta `ValidationError` (re-emitido por `TypeAdapter`)
- AND `AgentFactory.build` propaga la excepción sin interceptarla
- AND no se construye ningún `Agent`

## Cobertura

- Happy paths: cubiertos (agente con skills, agente sin skills, identidad+tools+skills juntos)
- Edge cases: cubiertos (None forwarding, hot-reload no-op sobre None, backward compat slice #1)
- Error states: cubiertos (propagación de ValidationError sin tragar)
