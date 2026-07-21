---
change: agent-config-schema
spec: SPEC_02
artifact: design
status: designed
artifact_store: hybrid
depends_on:
  - proposal: openspec/changes/agent-config-schema/proposal.md (engram #1877)
  - exploration: engram #1876
  - source_spec: specs/SPEC_02_DOMAIN_MODEL.md (read-only SSOT)
  - agno_source: agno/agent/agent.py:384-503, agno/team/mode.py, agno/workflow/types.py
---

# Design: Domain Model — YAML Configuration Schemas (Pydantic V2)

> **@ai-directive**: Este documento es el **HOW técnico**. El SSOT normativo es
> `specs/SPEC_02_DOMAIN_MODEL.md` (read-only). Toda discrepancia se resuelve a
> favor de SPEC_02. El código mostrado aquí es **documentación viva** — el cambio
> crea los archivos `.py`, este `design.md` los especifica y razona.

## Technical Approach

yaml-agno define **6 modelos Pydantic V2** que validan la forma del YAML de
configuración en la frontera (antes de pasar a los factories SPEC_01). La
estrategia: `model_config = ConfigDict(extra="forbid")` en los 5 `*Config` +
`ConfigDict(frozen=True)` en `DIReference`; los enums `TeamMode`/`StepType` se
**importan** de Agno (DRY/SSOT), nunca se redefinen; los 9 sub-bloques nativos
de Agno (`tools`, `knowledge`, `memory`, `session`, `reasoning`, `skills`,
`human_review`, `culture`, `persistence`) se exponen como **slots opacos
nombrados** (`dict[str, Any] | None`) cuya validación interna delega al SPEC
dueño (10/04/03+13/28/30/29/31/03).

Esto llena el namespace `src/yaml_agno/models/` dejado vacío por el bootstrap
(change #1). NO construye objetos Agno, NO carga YAML, NO define runtime — solo
forma del YAML + validación sintáctica propia.

### Flujo de datos (boundary validation)

```
YAML string ──► yaml.safe_load ──► dict
                                      │
                                      ▼
                          AgentConfig / TeamConfig
                          WorkflowConfig / StepConfig
                          (Pydantic V2 validation)
                                      │
                           [REJECT si inválido]
                                      │
                                      ▼
                          *Config (Python objects)
                                      │
                                      ▼
                          Factories (SPEC_01) ──► Agno objects

DIReference (inline en cualquier str del YAML):
  "${provider.key}" ──► field_validator ──► tokens + resolve()
```

## Architecture Decisions

### Decision A1: `extra="forbid"` + slots explícitos (no `extra="allow"`)

**Choice**: `model_config = ConfigDict(extra="forbid")` en los 5 `*Config`. Cada
feature de Agno que yaml-agno quiera exponer en YAML tiene un **slot nombrado
explícito** (`tools`, `knowledge`, ...). `tools` se tipa `list[ToolConfig]`
(`= list[dict[str, Any]]`); los otros 8 slots son `dict[str, Any] | None`.

**Alternatives considered**:
- `extra="allow"`: dejar pasar campos desconocidos al dict interno. Rechazado
  porque rompe el SSOT — silenciosamente aceptaría typos, features futuras sin
  documentar, y desincronizaría YAML ↔ factories.

**Rationale**: `extra="forbid"` fuerza a que cada feature nueva se agregue como
slot explícito en SPEC_02 (visible en PR review). Esto es **contraintuitivo pero
correcto**: cuando Agno agregue un campo (ej. `learning`), el PR que lo soporte
DEBE tocar AgentConfig — no puede colarse por `extra`. El validador Pydantic se
convierte en la primera línea de defensa contra YAML malformado. VERIFICADO
contra `agent.py:384-503`: los 9 slots nombrados tienen contraparte nativa en
`Agent()` (`model`, `name`, `instructions`, `tools`, `knowledge`,
`memory_manager`, `skills`, `reasoning`, `metadata`, `culture_manager`, `db`).
`human_review` NO es param de Agent (es workflow-level) — confirmado.

### Decision A2: Enums importados de Agno, no redefinidos (DRY/SSOT)

**Choice**: `from agno.team.mode import TeamMode` y
`from agno.workflow.types import StepType`. Pydantic V2 valida automáticamente
el string del YAML contra los miembros del enum (porque ambos heredan
`str, Enum`).

**Alternatives considered**:
- Redefinir los enums en yaml-agno. Rechazado: si Agno agrega/renombra un valor
  (ej. un nuevo `TeamMode.collaborate`), yaml-agno se desincroniza silenciosamente.

**Rationale**: Principio "Build ON TOP" de SPEC_00. Importar es cero-cost y da
herencia gratis. **Importante (asimetría de casing)**: los miembros de
`TeamMode` son **lowercase** (`"coordinate"`, `"route"`, `"broadcast"`,
`"tasks"` — verificado en `agno/team/mode.py`), mientras que los de `StepType`
son **Capitalized** (`"Step"`, `"Parallel"`, `"Condition"`, `"Router"`,
`"Loop"`, `"Function"`, `"Steps"`, `"Workflow"` — verificado en
`agno/workflow/types.py`). El YAML debe respetar esos casings exactos. Esto se
documenta en tests.

### Decision A3: Opaque slots `dict[str, Any] | None` con validación diferida

**Choice**: Los 9 sub-bloques (excepto `tools` que es `list[...]`) son
`dict[str, Any] | None`. AgentConfig **nombra** los slots pero NO valida sus
internas.

**Alternatives considered**:
- Modelar sub-configs completas (MemoryConfig, KnowledgeConfig...) en este
  cambio. Rechazado: viola DRY (cada SPEC dueño define su schema propio) e
  infla el scope.

**Rationale**: SSOT por feature. MemoryConfig lo define SPEC_04, KnowledgeConfig
lo define SPEC_10, etc. AgentConfig es el **agregado** que referencia estos
slots; el factory (SPEC_01) los despacha al schema dueño antes de construir el
objeto Agno. Esto mantiene el cambio cohesivo y desacoplado.

### Decision A4: `DIReference` frozen, valor-resuelto diferido

**Choice**: `model_config = ConfigDict(frozen=True)`. `template: str` con
`field_validator`. Propiedad `tokens` lee los `${provider.key}` tokens. Método
`resolve(resolved_values: dict[str, Any]) -> str` hace el reemplazo.

**Alternatives considered**:
- Hacer `resolve()` dependiente del DI infra de SPEC_00 (que no existe aún).
- Eliminar `resolve()` y delegar todo al DIFactory.

**Rationale**: La **sintaxis** `${provider.key}` es propia de yaml-agno (no
existe en Agno) — por eso es el único value object. `resolve()` es un método
**self-contained** que recibe el dict ya resuelto (la resolución real contra
providers —DB/env/api/file— es trabajo del DIFactory en SPEC_00).
**`resolve()` SÍ se implementa completo en este cambio** (no es stub): su lógica
es puramente string-replacement sobre `tokens`, sin tocar DI infra. Si SPEC_00
cambia la firma del resolvedor, `resolve()` de DIReference no cambia — solo
cambia quién lo invoca. Esto preserva el contrato del value object.

### Decision A5: Path layout — `models/config/` vs `config/`

**Choice**:
- Schemas: `src/yaml_agno/models/config/{agent_config,team_config,workflow_config}.py`
- Value object: `src/yaml_agno/models/value_objects/di_reference.py`
- Loader (SPEC_23, existente): `src/yaml_agno/config/` (vacío, solo `__init__.py`)

**Alternatives considered**:
- Poner los schemas en `src/yaml_agno/config/` directamente. Rechazado: colisiona
  con el namespace del loader SPEC_23 y mezcla responsabilidades (validación de
  forma vs carga/parseo).

**Rationale**: Son **paths distintos, sin colisión**, ambos válidos per
DECISIONES §4bis del proyecto. `models/` aloja el modelo de datos propio
(schemas + value objects); `config/` aloja el loader (cómo leer YAML de
filesystem/URLs). Verificado en el repo: `src/yaml_agno/config/__init__.py`
existe (vacío) y `src/yaml_agno/models/__init__.py` existe (vacío) — el cambio
crea los subdirs `models/config/` y `models/value_objects/`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/yaml_agno/models/config/__init__.py` | Create | Package marker (vacío). |
| `src/yaml_agno/models/config/agent_config.py` | Create | AgentConfig (13 fields + 9 opaque slots + 2 validators). |
| `src/yaml_agno/models/config/team_config.py` | Create | TeamConfig + TeamMemberConfig + 2 validators. |
| `src/yaml_agno/models/config/workflow_config.py` | Create | WorkflowConfig + StepConfig + 2 validators. |
| `src/yaml_agno/models/value_objects/__init__.py` | Create | Package marker (vacío). |
| `src/yaml_agno/models/value_objects/di_reference.py` | Create | DIReference frozen + tokens + resolve. |
| `src/yaml_agno/models/__init__.py` | Modify | Re-export de las 6 clases públicas (estaba vacío). |
| `tests/unit/__init__.py` | Create | Package marker. |
| `tests/unit/models/__init__.py` | Create | Package marker. |
| `tests/unit/models/test_agent_config.py` | Create | Tests RED→GREEN AgentConfig. |
| `tests/unit/models/test_team_config.py` | Create | Tests RED→GREEN TeamConfig. |
| `tests/unit/models/test_workflow_config.py` | Create | Tests RED→GREEN WorkflowConfig + StepConfig. |
| `tests/unit/value_objects/__init__.py` | Create | Package marker. |
| `tests/unit/value_objects/test_di_reference.py` | Create | Tests RED→GREEN DIReference. |
| `tests/unit/test_enums_import.py` | Create | Runtime import test: `TeamMode` y `StepType` desde Agno. |

**Total**: 11 archivos nuevos + 1 modificado = 12 files. Todos nuevos salvo
`models/__init__.py` (que estaba vacío del bootstrap).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Cada *Config y DIReference con input válido (golden path) | `@pytest.mark.unit` — pytest directo. |
| Unit | Cada validador rechazando input inválido (error path) | `pytest.raises(ValidationError)` + assert message. |
| Unit | `extra="forbid"` rechaza campos desconocidos | `pytest.raises(ValidationError)` con field name desconocido. |
| Unit | Enums importados de Agno (TeamMode, StepType) | Runtime import test (no mypy — mypy stubs tienen `ignore_missing_imports=true`). |
| Unit | `finally_` alias funciona por nombre Python y por alias YAML | Constructor dual test. |
| Unit | `cases.values()` (no keys) valida refs | Edge case: keys colisionando con step-ids válidos. |

## Verification Strategy

1. **`python -m pytest`** — verde con marker `unit`. Cobertura: 100% de los
   validadores (cada rama RED y GREEN testada).
2. **`ruff check .`** — limpio. Reglas del proyecto (line-length, import sort).
3. **`mypy src/yaml_agno`** — limpio. **Caveat**: Agno mypy stubs usan
   `ignore_missing_imports=true`, así que un import path erróneo NO falla en
   type-check. La verificación REAL es el runtime import test
   (`test_enums_import.py`).
4. **Runtime import test** — `from agno.team.mode import TeamMode` y
   `from agno.workflow.types import StepType` deben funcionar en runtime (no
   solo type-check). Este test es el contrato real contra Agno.
5. **Smoke runtime** — `python -c "from yaml_agno.models import AgentConfig,
   TeamConfig, WorkflowConfig, StepConfig, TeamMemberConfig, DIReference"` debe
   funcionar sin error.

## Migration / Rollout

**No migration required.** Todo el cambio vive en archivos nuevos bajo
`src/yaml_agno/models/{config,value_objects}/`. Rollback = `git revert` del PR
+ restaurar `models/__init__.py` a su estado vacío. Sin mutación de datos, sin
feature flags, sin dependientes (factories SPEC_01 aún no existen).

## Open Questions

- [ ] **TeamMemberConfig strictness**: SPEC_02 no le pone `extra="forbid"` a
      `TeamMemberConfig` (hereda default `extra="ignore"`). Esto permite que
      entries de miembros tengan campos extra silenciosamente ignorados. ¿Es esto
      intencional para soportar per-mode hints futuros? **Decisión**: seguir
      SPEC_02 literalmente (NO agregar `extra="forbid"` aquí). Si se quiere
      strictness, se cambia en otro cambio con SPEC update.
- [ ] **`mode="tasks"` minimum**: SPEC_02 solo exige mínimo para route/broadcast.
      `tasks` (autonomous task-based) podría necesitar >= 2 también (leader
      delega a members). **Decisión**: seguir SPEC_02 literalmente (no agregar
      restricción a `tasks`). Si Agno lo requiere en runtime, se descubre en
      SPEC_01 factories.
