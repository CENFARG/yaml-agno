---
change: agent-factory-basic
spec: agent-factory-basic
artifact: spec
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/changes/agent-factory-basic/proposal.md
  - engram://doc.reca/1925  # sdd/agent-factory-basic/proposal
  - openspec/specs/agent-config-schema/spec.md  # SPEC_02 (shipped, read-only)
---

# Delta Spec: agent-factory-basic

> Primer slice de SPEC_01. Construye `agno.Agent` desde `AgentConfig` (SPEC_02)
> mapeando identidad + modelo, **sin** resolución de dependencias ni
> side-effects en red. Función pura: `AgentFactory.build(cfg) -> agno.Agent`.

## ADDED Requirements

### Requirement: La fábrica construye un `agno.Agent` real desde `AgentConfig`

`AgentFactory.build(cfg: AgentConfig)` MUST retornar una instancia cuyo tipo
es `agno.Agent` (verificable con `isinstance`). La función MUST ser pura:
acepta solo el `AgentConfig` y SHALL NO aceptar los 9 slots opacos, `tags` ni
`metadata` como argumentos en este slice (sus owner SPECs los resolverán). El
sistema SHALL NO llamar al LLM ni crear el cliente HTTP en tiempo de
construcción. (Nota: Agno SÍ resuelve el string `model` a una instancia de
`Model` en el constructor — eso es comportamiento nativo de Agno, no una
llamada al LLM; la fábrica solo pasa el string y deja que Agno resuelva.)

#### Scenario: GREEN — Instancia válida retornada desde config mínima

- GIVEN un `AgentConfig(name="agent-01", model="openai:gpt-4o")` válido
- WHEN se ejecuta `AgentFactory.build(cfg)`
- THEN el retorno es `isinstance(result, agno.Agent)`
- AND la llamada no realiza I/O de red ni invoca al LLM

#### Scenario: GREEN — El retorno mapea los cuatro campos de identidad

- GIVEN un `AgentConfig` con `name`, `model`, `instructions`, `description`
- WHEN se ejecuta `build(cfg)`
- THEN `result.name == cfg.name`
- AND `result.instructions == cfg.instructions`
- AND `result.description == cfg.description`
- AND `result.model` es una instancia de `Model` resuelta por Agno (ver Requirement de passthrough para el contrato exacto)

### Requirement: Mapeo directo de identidad sin traducción de nombres

La fábrica MUST mapear cuatro campos de `AgentConfig` a kwargs homónimos de
`agno.Agent()`: `name → name`, `instructions → instructions`,
`description → description`, `model → model`. La fábrica MUST NO renombrar,
prefijar ni traducir ninguno de estos cuatro campos. El campo `model` MUST
pasarse como **passthrough directo**: el string nativo `provider:id` de SPEC_02
va sin transformación a `Agent(model=...)`.

#### Scenario: GREEN — Config mínima mapea name y model

- GIVEN `AgentConfig(name="my-agent", model="openai:gpt-4o")`
- WHEN se ejecuta `build(cfg)`
- THEN `result.name == "my-agent"`
- AND `result.model` es una instancia de `Model` con `result.model.id == "gpt-4o"`

#### Scenario: GREEN — Identidad completa mapea los cuatro campos

- GIVEN `AgentConfig(name="a", model="openai:gpt-4o", instructions="Sé útil", description="d")`
- WHEN se ejecuta `build(cfg)`
- THEN `result.name`, `result.instructions`, `result.description`, `result.model`
- AND cada uno coincide con el valor de `cfg` sin transformación

### Requirement: Passthrough de `model` en formato nativo `:` (sin traducción)

El campo `model` MUST pasarse al `Agent()` tal cual lo provee SPEC_02 (formato
`provider:id`, p. ej. `"openai:gpt-4o"`). La fábrica MUST NO implementar
traducción de sintaxis (`/` → `:`), splitting, ni reconstrucción del string.

**Comportamiento verificado de Agno** (Agno v2.6.22, confirmado empíricamente):
`Agent(model="openai:gpt-4o")` **resuelve el string a una instancia de `Model`
en el constructor** (`agno.models.utils.get_model` → p. ej. `OpenAIResponses` con
`.id="gpt-4o"`, `.provider="OpenAI"`). Por lo tanto `result.model` NO es el
string de entrada sino un objeto `Model`. La fábrica hace passthrough del
string; Agno es quien resuelve. La creación del cliente HTTP sí es perezosa
(en `run()`/`arun()`), pero la resolución `str → Model` ocurre en `__init__`.

#### Scenario: GREEN — `agent.model` es una instancia de `Model` resuelta por Agno

- GIVEN `AgentConfig(name="x", model="openai:gpt-4o")`
- WHEN se ejecuta `build(cfg)`
- THEN `result.model` es una instancia de `agno.models.base.Model`
- AND `result.model.id == "gpt-4o"`
- AND `result.model.provider == "OpenAI"`

### Requirement: Los slots opacos, `tags` y `metadata` se ignoran sin error

La fábrica MUST aceptar un `AgentConfig` que contenga cualquiera de los 9 slots
opacos (`tools`, `knowledge`, `memory`, `session`, `reasoning`, `skills`,
`human_review`, `culture`, `persistence`), `tags` o `metadata` poblados, sin
lanzar error. La fábrica MUST NO reenviar ninguno de estos campos al
constructor `agno.Agent()` en este slice — su resolución es responsabilidad de
los owner SPECs. El `Agent` resultante se construye con éxito, pero sin
tools/knowledge/memory/etc. asignados.

#### Scenario: GREEN — Slots opacos presentes no rompen la construcción

- GIVEN un `AgentConfig` con `memory={"driver": "sqlite"}` y `tools=[{"name": "t"}]`
- WHEN se ejecuta `build(cfg)`
- THEN la llamada retorna un `agno.Agent` válido sin error
- AND los slots opacos NO se pasaron a `Agent(...)` (no están en el agent construido)

#### Scenario: EDGE — Todos los slots opacos poblados simultáneamente

- GIVEN un `AgentConfig` con los 9 slots + `tags` + `metadata` poblados
- WHEN se ejecuta `build(cfg)`
- THEN la fábrica ignora los 11 campos y retorna un `agno.Agent` válido

### Requirement: Ausencia de side-effects y de red en la construcción

La fábrica SHALL NO ejecutar `agent.run()`, `agent.arun()` ni ningún método que
dispare I/O de red, telemetría activa o invocación al LLM. La construcción
SHALL consistir únicamente en mapeo de campos e invocación de `Agent(...)`.
Esto garantiza que los tests de este slice corren offline y son deterministes.

#### Scenario: GREEN — `build()` no invoca `run()` ni `arun()`

- GIVEN un espía/mock sobre `agno.Agent.run` y `arun`
- WHEN se ejecuta `build(cfg)` con un `AgentConfig` válido
- THEN ni `run` ni `arun` fueron llamados
- AND no hay intento de conexión de red durante la construcción

### Requirement: Idempotencia de `build()` sobre configs iguales

Dos invocaciones de `build()` sobre `AgentConfig` instancias estructuralmente
iguales SHOULD retornar dos `agno.Agent` independientes cuyos campos mapeados
son iguales entre sí. Cada llamada MUST producir una instancia nueva (no cacheada
ni compartida), pero ambas SHOULD ser equivalentes en sus atributos de identidad.

#### Scenario: GREEN — Dos llamadas producen agents equivalentes

- GIVEN dos `AgentConfig` instancias con campos idénticos
- WHEN se ejecuta `build(cfg_a)` y `build(cfg_b)` por separado
- THEN `agent_a is not agent_b` (instancias distintas)
- AND `agent_a.name == agent_b.name`
- AND `type(agent_a.model) is type(agent_b.model)` (mismo tipo de `Model` resuelto)
- AND `agent_a.model.id == agent_b.model.id`

### Requirement: `instructions=None` produce un Agent válido

Cuando `AgentConfig.instructions` es `None` (el default de SPEC_02), la fábrica
MUST pasarlo a `Agent(instructions=None)` y retornar un `agno.Agent` válido. El
default nativo de Agno para `instructions` es `None` (verificado
`agent.py:456`), por lo que la construcción no depende de instrucciones
obligatorias.

#### Scenario: GREEN — Config con `instructions=None`

- GIVEN `AgentConfig(name="x", model="openai:gpt-4o", instructions=None)`
- WHEN se ejecuta `build(cfg)`
- THEN retorna un `agno.Agent` válido
- AND `result.instructions is None`

### Requirement: La validación del `AgentConfig` es responsabilidad de SPEC_02, no de la fábrica

La fábrica MUST asumir que el `AgentConfig` recibido ya pasó la validación de
SPEC_02 (Pydantic V2, `extra="forbid"`, validadores de `name` y `model`). La
fábrica SHOULD NO reimplementar validación de sintaxis (`name`, formato de
`model`) — eso es trabajo de SPEC_02. Si se pasa un `AgentConfig` inválido, la
fábrica MAY propagar la excepción de Pydantic sin interceptarla.

#### Scenario: RED — La fábrica delega validación a SPEC_02 (no reimplementa)

- GIVEN un intento de `AgentConfig(name="", model="bad")`
- WHEN se construye el `AgentConfig` (antes de `build`)
- THEN Pydantic lanza `ValidationError` (name vacío o model sin `:`)
- AND la fábrica nunca se alcanza; no duplica la validación

### Requirement: Re-export de `AgentFactory` desde `factories/__init__.py`

`src/yaml_agno/factories/__init__.py` MUST re-exportar `AgentFactory` de modo
que `from yaml_agno.factories import AgentFactory` funcione. Hoy el módulo está
vacío; este cambio lo poblar con el re-export.

#### Scenario: GREEN — Import desde el paquete raíz

- GIVEN el paquete instalado
- WHEN se ejecuta `from yaml_agno.factories import AgentFactory`
- THEN la importación finaliza sin `ImportError`
- AND `AgentFactory.build` es invocable

### Requirement: Tests unitarios con marker `@pytest.mark.unit`

Los tests de `AgentFactory` MUST llevar el marker `@pytest.mark.unit` y MUST
vivir en `tests/unit/factories/test_agent_factory.py`. Deben cubrir
construcción, mapeo de campos, passthrough de `model`, ignorado de slots
opacos, idempotencia e `instructions=None`, sin red ni LLM.

#### Scenario: GREEN — Colección de tests con marker unit

- GIVEN la suite de tests de fábrica
- WHEN se ejecuta `python -m pytest -m unit tests/unit/factories/`
- THEN todos los tests del change se seleccionan y pasan verde, offline
