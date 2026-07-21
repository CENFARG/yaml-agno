# Memory Identity Leaf Specification

## Purpose

Definir el comportamiento requerido del slice **LEAF** de SPEC_04 (Memory
Architecture): el resolver único `resolve_user_id()` y el schema tipado
`MemoryConfig` (Pydantic V2 puro). Este slice rompe el ciclo de dependencia
mutua SPEC_04 <-> SPEC_06 entregando el contrato del que dependen SPEC_03
(persistencia), SPEC_06 (tenant middleware) y SPEC_15 (context compression) **sin
ningún llamador cableado todavía** (Option B opaco).

El slice existe además para cerrar un **footgun verificado en Agno v2.6.18**:
`MemoryManager` coacciona `user_id=None` al string literal `"default"` en todos
sus métodos (`agno/memory/manager.py:177,191,205,239`), causando cross-talk
entre runs anónimas de todos los agentes del proceso. `resolve_user_id()` hace
ese fall-through imposible: nunca retorna `None`, nunca retorna un principal sin
tenant, y falla rápido cuando la identidad no resuelve.

## Scope

### In Scope

- `src/yaml_agno/memory/user_identity.py` — `UserIdentityResolutionError` +
  `resolve_user_id(memory_cfg, principal_id, tenant_id, context=None) -> str`.
- `src/yaml_agno/models/config/memory_config.py` — `MemoryConfig` Pydantic V2 +
  sub-schemas anidados, `ConfigDict(extra="forbid")`.
- `src/yaml_agno/memory/__init__.py` — re-export del resolver y la excepción.

### Out of Scope (DEFER)

- `TenantContextMiddleware` (SPEC_06) — el llamador HTTP del resolver.
- `build_memory_config()` / `build_learning_config()` factories.
- `recall_on_start()` y `AutosaveManager`.
- `map_scope_to_namespace()`.
- Wiring `AgentConfig.memory` de `dict[str, Any] | None` a `MemoryConfig`
  (cambio coordinado posterior; `AgentConfig.memory` permanece opaco).
- `ContextCompressor` (SPEC_15), sanitización PII/secretos (SPEC_16),
  retention purge job (post-MVP).

## Requirements

### Requirement: Resolución de user_id compuesto ({tenant_id}:{principal_id})

`resolve_user_id(memory_cfg, principal_id, tenant_id, context=None)` MUST
retornar el string compuesto `"{tenant_id}:{principal_id}"`, donde el principal
seleccionado es `principal_id` cuando está presente, o
`memory_cfg.system_user_id` (literal o expandido) en caso contrario. La función
MUST NEVER retornar `None`, MUST NEVER retornar un principal sin tenant, y MUST
NEVER aplicar un fallback silencioso al bucket compartido `"default"` de Agno.
La firma del resolver MUST ser autocontenida: `memory_cfg` es duck-typed
(`Any`) y el campo `system_user_id` se lee vía `getattr(memory_cfg,
"system_user_id", None)`, de modo que el módulo MUST NOT importar
`MemoryConfig`, Agno, ni ningún otro módulo yaml-agno.

#### Scenario: Golden path — principal humano

- GIVEN `memory_cfg` con `system_user_id` cualquiera, `principal_id="alice"`,
  `tenant_id="acme"`
- WHEN se llama `resolve_user_id(memory_cfg, "alice", "acme")`
- THEN el retorno es exactamente `"acme:alice"`
- AND el valor de `system_user_id` es ignorado (el principal humano gana)

#### Scenario: Golden path — principal del sistema (literal)

- GIVEN `memory_cfg.system_user_id="agent:facturacion"`,
  `principal_id=None`, `tenant_id="acme"`
- WHEN se llama `resolve_user_id(memory_cfg, None, "acme")`
- THEN el retorno es exactamente `"acme:agent:facturacion"`
- AND no se aplica expansión de template (el literal no contiene `{` y `}`)

### Requirement: Fail-fast cuando falta tenant_id

Si `tenant_id` es `None`, vacío o falsy, `resolve_user_id` MUST raises
`UserIdentityResolutionError` ANTES de intentar resolver el principal. El
mensaje de error MUST mencionar que `tenant_id` es requerido y debe romper el
aislamiento de tenant.

#### Scenario: RED — tenant ausente

- GIVEN `tenant_id=None`, cualquier `principal_id` y `memory_cfg`
- WHEN se llama `resolve_user_id(memory_cfg, "alice", None)`
- THEN se levanta `UserIdentityResolutionError`
- AND el mensaje menciona `tenant_id` y aislamiento de tenant

### Requirement: Fail-fast cuando ni principal ni system_user_id resuelven

Si `principal_id` es `None`/vacío y `getattr(memory_cfg, "system_user_id",
None)` también es `None`/vacío, `resolve_user_id` MUST raises
`UserIdentityResolutionError`. El mensaje MUST mencionar que se rehusa caer al
bucket compartido `"default"` de Agno.

#### Scenario: RED — sin principal humano ni system_user_id

- GIVEN `memory_cfg` sin atributo `system_user_id` (o con valor `None`),
  `principal_id=None`, `tenant_id="acme"`
- WHEN se llama `resolve_user_id(memory_cfg, None, "acme")`
- THEN se levanta `UserIdentityResolutionError`
- AND el mensaje menciona `default` y la negativa a usarlo

### Requirement: Expansión de template en system_user_id

Cuando `principal_id` no está presente y `memory_cfg.system_user_id` contiene
tanto `{` como `}`, ese valor MUST ser tratado como un template Python
`str.format`-compatible y expandido contra el kwarg `context`. Un template que
referencie una llave ausente en `context` MUST raises
`UserIdentityResolutionError` (encadenado desde el `KeyError` subyacente). Un
template con `{`/`}` presente pero `context=None` MUST raises
`UserIdentityResolutionError`. Un `system_user_id` sin `{`/`}` MUST usarse como
string literal sin intento de expansión.

#### Scenario: Golden path — template expandido correctamente

- GIVEN `memory_cfg.system_user_id="workflow:{workflow_id}"`,
  `principal_id=None`, `tenant_id="acme"`,
  `context={"workflow_id": "wf-42"}`
- WHEN se llama `resolve_user_id(memory_cfg, None, "acme", context)`
- THEN el retorno es exactamente `"acme:workflow:wf-42"`

#### Scenario: RED — template sin context dict

- GIVEN `memory_cfg.system_user_id="workflow:{workflow_id}"`,
  `principal_id=None`, `tenant_id="acme"`, `context=None`
- WHEN se llama `resolve_user_id(memory_cfg, None, "acme", None)`
- THEN se levanta `UserIdentityResolutionError`
- AND el mensaje menciona que el template requiere un context dict

#### Scenario: RED — template con llave faltante en context

- GIVEN `memory_cfg.system_user_id="workflow:{workflow_id}"`,
  `principal_id=None`, `tenant_id="acme"`,
  `context={"agent_id": "a"}` (sin `workflow_id`)
- WHEN se llama `resolve_user_id(memory_cfg, None, "acme", context)`
- THEN se levanta `UserIdentityResolutionError`
- AND la excepción original (`KeyError`) se preserva como `__cause__`

### Requirement: MemoryConfig es schema Pydantic V2 puro con extra=forbid

`MemoryConfig` (en `src/yaml_agno/models/config/memory_config.py`) MUST ser un
`BaseModel` de Pydantic V2 con `model_config = ConfigDict(extra="forbid")`. El
módulo MUST NOT importar nada del paquete `agno` (zero imports de Agno). El
schema MUST declarar estos 6 campos escalares requeridos (sin defaults):
`enable_agentic_memory: bool`, `update_memory_on_run: bool`,
`add_memories_to_context: bool`, `num_history_runs: int` (con `ge=0`),
`num_history_messages: int` (con `ge=0`), y `system_user_id: str` (con
`min_length=1`). Además MUST declarar 4 bloques anidados opcionales (default
`None`): `session: SessionMemoryConfig | None`, `working: WorkingMemoryConfig |
None`, `learning: LearningMemoryConfig | None`, `retention: RetentionConfig |
None`. Cada sub-modelo MUST también usar `ConfigDict(extra="forbid")`.

#### Scenario: Golden path — parseo del bloque YAML canónico

- GIVEN un dict con los 6 campos escalares requeridos con valores válidos
  (e.g. `enable_agentic_memory=True`, `update_memory_on_run=True`,
  `add_memories_to_context=True`, `num_history_runs=5`,
  `num_history_messages=50`, `system_user_id="agent:my_agent"`)
- WHEN se ejecuta `MemoryConfig.model_validate({...})`
- THEN la validación pasa sin errores
- AND los 4 bloques anidados (`session`, `working`, `learning`, `retention`)
  son `None` por defecto

#### Scenario: RED — clave desconocida rechazada (extra=forbid)

- GIVEN un dict válido para los 6 escalares más una clave spurious
  `"unknown_field": 123`
- WHEN se ejecuta `MemoryConfig.model_validate({...})`
- THEN la validación falla con un `ValidationError`
- AND el error menciona `extra_forbidden` o `Unexpected keyword argument`

#### Scenario: RED — campo escalar requerido omitido

- GIVEN un dict que omite `enable_agentic_memory` (y los demás escalares
  presentes)
- WHEN se ejecuta `MemoryConfig.model_validate({...})`
- THEN la validación falla con `ValidationError`
- AND el error cita `enable_agentic_memory` como faltante

### Requirement: Sub-schemas anidados con validación propia

Los sub-modelos `SessionMemoryConfig`, `WorkingMemoryConfig`,
`LearningMemoryConfig` (con sus `LearnedKnowledgeScopeConfig` y
`EntityMemoryScopeConfig` anidados), `RetentionConfig` (con
`RetentionMaxAgeConfig`) MUST ser `BaseModel` Pydantic V2 con
`ConfigDict(extra="forbid")`. `SessionMemoryConfig.storage_type` MUST ser un
`Literal["sqlite", "postgres", "memory"]` (rechaza otros valores). Los campos
numéricos con cota inferior (`max_messages`, `max_context_tokens`,
`compression_threshold`, `max_age_days.*`, `num_history_*`) MUST declarar `ge=0`
o `ge=1` según SPEC_04 §1.3.

#### Scenario: RED — storage_type fuera del Literal

- GIVEN un dict con `session={"storage_type": "redis", "max_messages": 10}`
- WHEN se ejecuta `MemoryConfig.model_validate({...con session...})`
- THEN la validación falla con `ValidationError`
- AND el error menciona `storage_type`

### Requirement: AgentConfig.memory permanece opaco (Option B)

Este slice MUST NOT modificar el slot `memory: dict[str, Any] | None` en
`src/yaml_agno/models/config/agent_config.py`. El schema `MemoryConfig` MUST
enviarse como módulo standalone sin callers cableados. El wiring del slot a
`MemoryConfig` es un cambio coordinado posterior fuera del alcance de este
slice.

#### Scenario: agent_config.py sin cambios

- GIVEN el estado del repo tras aplicar el change
- WHEN se ejecuta `git diff --name-only src/yaml_agno/models/config/agent_config.py`
- THEN la salida es vacía (el archivo no fue modificado)

### Requirement: Re-export público desde yaml_agno.memory

`src/yaml_agno/memory/__init__.py` MUST re-exportar `resolve_user_id` y
`UserIdentityResolutionError` con `__all__` explícito, de modo que
`from yaml_agno.memory import resolve_user_id, UserIdentityResolutionError`
funcione. `MemoryConfig` MUST ser importable únicamente desde
`yaml_agno.models.config.memory_config` (no se re-exporta desde `yaml_agno.memory`).

#### Scenario: Import del resolver desde el package público

- GIVEN el paquete instalado
- WHEN se ejecuta
  `python -c "from yaml_agno.memory import resolve_user_id, UserIdentityResolutionError"`
- THEN la importación tiene éxito (código de salida 0)

#### Scenario: MemoryConfig accesible vía su ruta canónica

- GIVEN el paquete instalado
- WHEN se ejecuta
  `python -c "from yaml_agno.models.config.memory_config import MemoryConfig"`
- THEN la importación tiene éxito

### Requirement: Cero imports de Agno en los módulos nuevos

Los archivos `src/yaml_agno/memory/user_identity.py` y
`src/yaml_agno/models/config/memory_config.py` MUST NOT contener ninguna
instrucción `import` (directa o `from`) que referencie el paquete `agno`. La
memoria es 100% Agno-native; yaml-agno solo la configura.

#### Scenario: Sin imports de agno en los módulos nuevos

- GIVEN el contenido de `user_identity.py` y `memory_config.py`
- WHEN se busca la cadena `agno` en sus sentencias de import
- THEN no aparece ninguna sentencia `import agno` ni `from agno...`

### Requirement: Suite de tests en verde

`tests/yaml_agno/memory/test_user_identity.py` y
`tests/yaml_agno/models/config/test_memory_config.py` MUST existir y cubrir los
escenarios listados arriba. `python -m pytest <estos dos archivos>` MUST pasar
todos los casos.

#### Scenario: Pytest verde sobre los dos módulos nuevos

- GIVEN el entorno con el paquete instalado y `pytest` disponible
- WHEN se ejecuta
  `python -m pytest tests/yaml_agno/memory/test_user_identity.py tests/yaml_agno/models/config/test_memory_config.py`
- THEN el resultado es N passed, 0 failed
