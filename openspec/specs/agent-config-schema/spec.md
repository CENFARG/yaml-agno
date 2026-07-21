# Agent Config Schema Specification

## Purpose

Definir el comportamiento requerido de los 6 schemas Pydantic V2 que constituyen
el **único modelo de datos propio** de yaml-agno: `AgentConfig`, `TeamConfig`,
`TeamMemberConfig`, `WorkflowConfig`, `StepConfig` y el value object `DIReference`.
Estos schemas validan la forma del YAML de configuración antes de que los
factories (SPEC_01) construyan objetos Agno nativos. Son el single source of
truth de la forma del YAML; ninguna otra parte del código los re define.

La sintaxis propia de yaml-agno (`${provider.key}`) y los slots opacos que
referencian sub-sistemas delegados a sus SPECs dueños también se formalizan aquí.

## Requirements

### Requirement: Seis clases Pydantic V2 con model_config correcto

El sistema MUST definir exactamente 6 clases Pydantic V2 en los paths
`src/yaml_agno/models/config/` (AgentConfig, TeamConfig, TeamMemberConfig,
WorkflowConfig, StepConfig) y `src/yaml_agno/models/value_objects/` (DIReference),
con los campos declarados en SPEC_02 §1.3-1.5 y §2. Los 5 schemas `*Config`
MUST declarar `model_config = ConfigDict(extra="forbid")`. `DIReference` MUST
declarar `model_config = ConfigDict(frozen=True)`.

#### Scenario: GREEN — Instanciación válida de cada schema

- GIVEN los módulos de schemas cargados
- WHEN se instancia cada clase con los campos requeridos de SPEC_02
- THEN cada instancia se crea sin error
- AND `AgentConfig.model_config["extra"]` es `"forbid"`
- AND `DIReference.model_config["frozen"]` es `True`

#### Scenario: RED — extra="forbid" rechaza campos desconocidos en cada *Config

- GIVEN cada uno de los 5 schemas `*Config`
- WHEN se intenta instanciar pasando un campo top-level desconocido (ej. `foo="bar"`)
- THEN se lanza `pydantic.ValidationError`
- AND el mensaje menciona el campo extra prohibido

### Requirement: Nueve slots opacos explícitos en AgentConfig

`AgentConfig` MUST exponer 9 slots opacos como `dict[str, Any] | None` (excepto
`tools` que es `list[dict[str, Any]]`): `tools`, `knowledge`, `memory`,
`session`, `reasoning`, `skills`, `human_review`, `culture`, `persistence`.
AgentConfig MUST NO enumerar las internals de estos slots; su validación interna
es responsabilidad del SPEC dueño (10/11/04/03+13/28/29/30/31).

#### Scenario: GREEN — Slots aceptan dicts opacos

- GIVEN un YAML de agente con un bloque `memory:` arbitrario
- WHEN se valida contra AgentConfig
- THEN `config.memory` contiene el dict intacto sin validación interna

#### Scenario: RED — Slot inválido rechazado por extra="forbid"

- GIVEN un YAML de agente con un campo top-level no declarado
- WHEN se valida contra AgentConfig
- THEN se lanza `ValidationError`

### Requirement: Enums TeamMode y StepType importados de Agno

El sistema MUST importar `TeamMode` desde `agno.team.mode` y `StepType` desde
`agno.workflow.types`. El sistema MUST NOT re definir estos enums. Un test de
import runtime MUST pasar verde (no confiar en stubs de mypy).

#### Scenario: GREEN — Import runtime de enums Agno

- GIVEN el paquete instalado con `agno==2.6.22`
- WHEN se ejecuta `from agno.team.mode import TeamMode` y `from agno.workflow.types import StepType`
- THEN la importación finaliza sin ImportError
- AND `TeamMode` tiene 4 miembros
- AND `StepType` tiene 8 miembros

#### Scenario: GREEN — Valor YAML mapea al enum Agno correcto

- GIVEN un YAML `team.mode: coordinate`
- WHEN se valida contra TeamConfig
- THEN `config.mode` es `TeamMode.coordinate` (no una copia local)

### Requirement: Ausencia de user_id en todos los *Config

Ningún schema `*Config` MUST NO declarar el campo `user_id`. El `user_id`
compuesto es un concern runtime de SPEC_04.

#### Scenario: RED — user_id rechazado si aparece en YAML

- GIVEN un YAML de agente con un campo `user_id: "u1"`
- WHEN se valida contra AgentConfig
- THEN se lanza `ValidationError` (campo no declarado, atrapado por extra="forbid")

### Requirement: Validador de caracteres de name

`AgentConfig` y `TeamConfig` y `WorkflowConfig` MUST validar que `name` solo
contenga caracteres `[A-Za-z0-9_-]` y sea no-vacío.

#### Scenario: GREEN — Nombre válido aceptado

- GIVEN un nombre `"my_agent-01"`
- WHEN se valida el schema correspondiente
- THEN el nombre se acepta sin error

#### Scenario: RED — Nombre con caracteres ilegales rechazado

- GIVEN un nombre `"bad name!"`
- WHEN se valida AgentConfig
- THEN se lanza `ValidationError`
- AND el mensaje menciona "Invalid agent name"

### Requirement: Validador de formato de model (provider:id)

`AgentConfig` MUST validar que `model` siga el formato `provider:id` con ambos
segmentos no-vacíos (sintaxis solamente; la resolución del provider es del
DependencyManager, SPEC_01). El formato `provider:id` es el formato nativo que
exige `_parse_model_string` de Agno (`agno.models.utils`): cualquier string sin
`:` lanza `ValueError`. yaml-agno NO implementa capa de traducción (`/`→`:`);
el YAML usa el formato nativo `:` directamente.

#### Scenario: GREEN — Formato provider:id aceptado

- GIVEN `model="openai:gpt-4o"`
- WHEN se valida AgentConfig
- THEN el modelo se acepta sin error

#### Scenario: RED — Formato sin colon rechazado

- GIVEN `model="invalid-format"`
- WHEN se valida AgentConfig
- THEN se lanza `ValidationError`
- AND el mensaje menciona "Invalid model format" y "Expected 'provider:id'"

#### Scenario: RED — Provider o id vacío rechazado

- GIVEN `model=":gpt-4o"` o `model="openai:"`
- WHEN se valida AgentConfig
- THEN se lanza `ValidationError`

### Requirement: Validador de members únicos en TeamConfig

`TeamConfig` MUST rechazar configuraciones donde dos `TeamMemberConfig` tengan
el mismo `member` id.

#### Scenario: GREEN — Members únicos aceptados

- GIVEN dos miembros con ids distintos
- WHEN se valida TeamConfig
- THEN se aceptan sin error

#### Scenario: RED — Members duplicados rechazados

- GIVEN dos miembros con `member="m1"`
- WHEN se valida TeamConfig
- THEN se lanza `ValidationError`
- AND el mensaje menciona "Duplicate member ids"

### Requirement: Validador de requisitos por mode en TeamConfig

`TeamConfig` MUST rechazar equipos con `mode=route` o `mode=broadcast` que tengan
menos de 2 miembros.

#### Scenario: GREEN — route con 2+ miembros aceptado

- GIVEN `mode="route"` y 2 miembros
- WHEN se valida TeamConfig
- THEN se acepta sin error

#### Scenario: RED — route con 1 miembro rechazado

- GIVEN `mode="route"` y 1 miembro
- WHEN se valida TeamConfig
- THEN se lanza `ValidationError`
- AND el mensaje menciona "requires at least 2 members"

### Requirement: Validador de campos type-specific de StepConfig

`StepConfig` MUST rechazar que campos type-specific aparezcan en tipos
incompatibles: `steps` solo en Parallel/Steps/Condition; `condition`/`if_true`/
`if_false` solo en Condition; `expression`/`cases` solo en Router;
`end_condition`/`max_iterations` solo en Loop.

#### Scenario: GREEN — Campos correctos para cada tipo aceptados

- GIVEN un StepConfig con `type=Condition` y `condition`/`if_true`/`if_false`
- WHEN se valida
- THEN se acepta sin error

#### Scenario: RED — expression en Loop rechazado

- GIVEN un StepConfig con `type=Loop` y `expression="x"`
- WHEN se valida
- THEN se lanza `ValidationError`
- AND el mensaje menciona "only allowed for Router type"

### Requirement: Validador de integridad de step-ids en WorkflowConfig

`WorkflowConfig` MUST rechazar `steps` con ids duplicados. `validate_steps_integrity`
MUST caminar las referencias `if_true`, `if_false` Y los `values()` de `cases`
(no las keys) validando que cada referencia apunte a un step-id existente.

#### Scenario: GREEN — Referencias válidas a step-ids existentes

- GIVEN steps con `if_true`/`if_false`/`cases` apuntando a ids existentes
- WHEN se valida WorkflowConfig
- THEN se acepta sin error

#### Scenario: RED — Step-ids duplicados rechazados

- GIVEN dos steps con `step="s1"`
- WHEN se valida WorkflowConfig
- THEN se lanza `ValidationError`
- AND el mensaje menciona "Duplicate step ids"

#### Scenario: RED — Referencia colgante en if_true rechazada

- GIVEN un Condition con `if_true="missing"` donde `"missing"` no existe
- WHEN se valida WorkflowConfig
- THEN se lanza `ValidationError`
- AND el mensaje menciona "non-existent step"

#### Scenario: EDGE — Referencia en cases.values() (no keys) detectada

- GIVEN un Router con `cases={"legal_key": "missing_step"}` donde `"missing_step"`
  no existe pero `"legal_key"` sí podría colisionar con un step-id
- WHEN se valida WorkflowConfig
- THEN se lanza `ValidationError` porque el validador camina values, no keys

### Requirement: Alias `finally` para el campo finally_

`StepConfig.finally_` MUST usar `Field(alias="finally")` de modo que la clave
YAML `finally` poblar el campo. Esto permite usar la palabra reservada Python
como clave YAML sin romper el populate.

#### Scenario: GREEN — YAML key `finally` pobla el campo

- GIVEN un StepConfig construido vía input con la clave `finally=True` (alias)
- WHEN se valida
- THEN `config.finally_` es `True`
- AND el populate por alias funciona sin warning silencioso

### Requirement: Validador de formato de template de DIReference

`DIReference` MUST rechazar templates que no contengan al menos un token
well-formed `${provider.key}` (regex `\$\{[a-z_]+(\.[a-z0-9_]+)*\}`).

#### Scenario: GREEN — Template con token válido aceptado

- GIVEN `template="Hello ${user_db.name}"`
- WHEN se construye DIReference
- THEN `ref.tokens` es `[("user_db", "name")]`
- AND `ref.resolve({"user_db.name": "Alice"})` retorna `"Hello Alice"`

#### Scenario: RED — Template sin token rechazado

- GIVEN `template="no-token-here"`
- WHEN se construye DIReference
- THEN se lanza `ValidationError`
- AND el mensaje menciona "Invalid DI reference format"

### Requirement: Inmutabilidad de DIReference

`DIReference` MUST ser inmutable (`frozen=True`); la mutación de `template`
después de la construcción MUST lanzar `ValidationError`.

#### Scenario: RED — Mutación de template rechazada

- GIVEN un DIReference construido
- WHEN se asigna `ref.template = "other"`
- THEN se lanza `ValidationError`

### Requirement: Re-export de las 6 clases en models/__init__.py

`src/yaml_agno/models/__init__.py` MUST re-exportar las 6 clases: AgentConfig,
TeamConfig, TeamMemberConfig, WorkflowConfig, StepConfig, DIReference.

#### Scenario: GREEN — Import desde el paquete raíz funciona

- GIVEN el paquete instalado
- WHEN se ejecuta `from yaml_agno.models import AgentConfig, TeamConfig, TeamMemberConfig, WorkflowConfig, StepConfig, DIReference`
- THEN la importación finaliza sin ImportError

### Requirement: Tests unitarios con marker @pytest.mark.unit

Todos los tests de schemas y value objects MUST llevar el marker
`@pytest.mark.unit` y MUST vivir en `tests/unit/{models,value_objects}/`.

#### Scenario: GREEN — Colección de tests con marker unit

- GIVEN la suite de tests de schemas
- WHEN se ejecuta `python -m pytest -m unit`
- THEN todos los tests de este change se seleccionan y pasan verde

### Requirement: Exclusión explícita de factories, persistencia y API

Este change MUST NOT introducir factories (SPEC_01), persistencia (SPEC_03) ni
API (SPEC_06). Solo se definen los schemas que validan la forma del YAML; la
construcción de objetos Agno, el guardado y la exposición HTTP son
responsabilidad de cambios posteriores.

#### Scenario: RED — Sin factories ni código Agno runtime

- GIVEN el diff del change
- WHEN se inspeccionan los archivos bajo `src/yaml_agno/models/`
- THEN no existe ningún factory ni import de constructores Agno (`agno.Agent`,
  `agno.Team`, `agno.Workflow`) más allá de los enums referenciados
