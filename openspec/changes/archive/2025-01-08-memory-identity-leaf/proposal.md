---
change: memory-identity-leaf
spec: SPEC_04
status: proposed
artifact_store: hybrid
depends_on: []
---

# Proposal: Memory Identity Leaf (resolve_user_id + MemoryConfig)

## Intent / Por qué

SPEC_04 y SPEC_06 se citan mutuamente como dependencias (ciclo). `decisions.yaml`
(roadmap MVP-13) pone SPEC_04 fase 1a como **hoja** — `resolve_user_id()` +
`MemoryConfig` — para romper el ciclo sin tocar SPEC_06. Existe además un
**footgun verificado en Agno v2.6.18**: `user_id=None` se coacciona al string
literal `"default"` en todo `MemoryManager` (`agno/memory/manager.py:177,191,205,239`),
provocando cross-talk entre runs anónimas de TODOS los agentes del proceso.
Esta hoja entrega el único resolver de `user_id` y el schema tipado que reemplaza
el slot opaco `memory: dict[str, Any] | None` (`agent_config.py:63`).

**Éxito**: existe un único `resolve_user_id()` que NUNCA retorna `None`, NUNCA un
principal sin tenant, y falla rápido si falta tenant o principal; y un
`MemoryConfig` Pydantic V2 puro (sin imports de Agno) que tipa el bloque YAML.

## Scope

### In Scope
- `src/yaml_agno/memory/user_identity.py` — `UserIdentityResolutionError(RuntimeError)`
  + `resolve_user_id(memory_cfg, principal_id, tenant_id, context=None) -> str`.
  Retorna composite `"{tenant_id}:{principal_id}"`. Template expansion
  (`"workflow:{workflow_id}"`) vía `str.format(**context)`. Fail-fast.
- `src/yaml_agno/models/config/memory_config.py` — `MemoryConfig` Pydantic V2
  con `ConfigDict(extra="forbid")`. Campos Agno-constructor (`enable_agentic_memory`,
  `update_memory_on_run`, `add_memories_to_context`, `num_history_runs`,
  `num_history_messages`), `system_user_id: str | None`, y bloques anidados
  `session` / `working` / `learning` / `retention`. Patrón = `model_spec.py`
  (standalone, AgentConfig sin tocar).
- `src/yaml_agno/memory/__init__.py` — re-export de `resolve_user_id` y la excepción.
- Tests: `test_user_identity.py` (5 casos RED de SPEC_04 §6.1 TASK_005),
  `test_memory_config.py` (parseo, defaults, `extra="forbid"`).

### Out of Scope (DEFER)
- **TenantContextMiddleware** (SPEC_06) — el llamador HTTP de `resolve_user_id`.
- **`build_memory_config()` factory** (TASK_001) y `build_learning_config()` (TASK_002).
- **`recall_on_start()`** (TASK_003) y **`AutosaveManager`** (TASK_004).
- **Scope/namespace mapping** `map_scope_to_namespace()` (TASK_006).
- Wiring `AgentConfig.memory` de `dict` a `MemoryConfig` (cambio coordinado SPEC_02).
- **ContextCompressor** (SPEC_15), **PII/secret sanitization** (SPEC_16),
  **retention purge job** (post-MVP).

## Capabilities

### New Capabilities
- `memory-identity`: Resolución de identidad de usuario compuesta
  (`{tenant_id}:{principal_id}`) y schema tipado del bloque `memory:` YAML.
  Cubre `resolve_user_id()` + `MemoryConfig`. Es hoja: sin imports de Agno,
  sin wiring a `AgentConfig`.

### Modified Capabilities
- Ninguna. `AgentConfig.memory` permanece opaco (`dict[str, Any] | None`); el
  wiring es un cambio coordinado posterior (Option B standalone, como `model_spec.py`).

## Approach

Dos entregables autónomos, sin dependencia entre sí ni con Agno:

1. **`resolve_user_id()`** replica literalmente SPEC_04 §1.4 (líneas 183-258).
   Lógica: tenant faltante → raise; principal = `principal_id` OR
   `memory_cfg.system_user_id` (con expansión de template si contiene `{}`);
   sin fallback a `"default"`. `memory_cfg` es `Any` (duck-typed por
   `getattr(..., "system_user_id", None)`) → compatible con `MemoryConfig` y
   con dicts sueltos en tests.

2. **`MemoryConfig`** es Pydantic V2 puro (`ConfigDict(extra="forbid")`), archivo
   separado bajo `models/config/` siguiendo el precedent `model_spec.py`.
   Mapea 1:1 los flags del constructor Agno + `system_user_id` + 4 sub-modelos
   anidados (`SessionMemoryConfig`, `WorkingMemoryConfig`, `LearningMemoryConfig`,
   `RetentionConfig`). No importa Agno; solo valida forma YAML.

## Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `src/yaml_agno/memory/user_identity.py` | New | Resolver + excepción. |
| `src/yaml_agno/models/config/memory_config.py` | New | Schema Pydantic V2 standalone. |
| `src/yaml_agno/memory/__init__.py` | Modified | Re-export (hoy vacío). |
| `src/yaml_agno/models/config/agent_config.py` | Unchanged | `memory: dict[str,Any]|None` intacto (Option B). |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `MemoryConfig` se desfase del YAML real de SPEC_04 §1.3 | Med | Campos derivados literalmente de §1.3 (líneas 86-153); `extra="forbid"` fuerza fallar en drift. |
| `resolve_user_id` rompa si `memory_cfg` es `None` (caso sin bloque `memory:`) | Med | `getattr(memory_cfg, "system_user_id", None)` maneja `None`/dict/objeto; spec exige raise si no hay principal — comportamiento correcto, no bug. |
| Drift entre el `system_user_id` de `MemoryConfig` y el esperado por el resolver | Baja | Ambos en este slice; tests cruzan los dos (fixture `memory_cfg` usa `MemoryConfig`). |
| Over-build: tentación de wiring prematuro a `AgentConfig.memory` | Med | Proposal explícito Option B standalone; `agent_config.py` marcado Unchanged. |

## Rollback Plan

Todo el slice son 2 archivos nuevos + 1 `__init__.py` con re-exports. Rollback =
`git revert` del commit del slice. `AgentConfig.memory` nunca se tocó, así que no
hay migración ni estado que recuperar. Los tests viven en `tests/unit/memory/` y
se borran junto.

## Dependencies

- Ninguna externa nueva. Pydantic V2 ya está en el proyecto (Agno + model_spec.py).
- Agno NO se importa (footgun documentado; este slice es Agno-agnostic).

## Success Criteria

- [ ] `resolve_user_id` pasa los 5 casos RED de SPEC_04 TASK_005 (composite humano,
  composite sistema, template expandido, raise sin tenant, raise sin principal).
- [ ] `MemoryConfig.model_validate(...)` parsea el bloque YAML canónico de §1.3.
- [ ] `MemoryConfig` rechaza claves desconocidas (`extra="forbid"`).
- [ ] `python -m pytest tests/unit/memory/test_user_identity.py tests/unit/memory/test_memory_config.py` en verde.
- [ ] Cero imports de `agno` en los dos archivos nuevos.

## Proposal question round

Propuestas para refinar el PRD antes de `sdd-spec` (responder, saltar o
re-enmarcar):

1. **`num_history_*` defaults**: SPEC_04 §1.3 muestra `num_history_runs: 5` y
   `num_history_messages: 50` como valores de ejemplo. ¿Son estos los defaults
   del schema, o debe `MemoryConfig` exigirlos explícitos (`...`) para forzar
   decisión consciente? Asumo defaults del ejemplo.

2. **`system_user_id` validación de template**: si `system_user_id` contiene
   `{` pero el template queda con placeholders sin expandir tras `format()`
   (e.g. formato parcial), ¿se valida en `MemoryConfig` (tiempo de parseo) o
   solo en `resolve_user_id` (tiempo de resolve)? Asumo solo en resolve — el
   schema acepta cualquier string válido.

3. **Sub-modelos de `MemoryConfig` requeridos vs opcionales**: los bloques
   `session`/`working`/`learning`/`retention` — ¿todos opcionales con defaults
   sensatos, o alguno requerido? Asumo todos `None` por defecto (opcional),
   coherente con Option B standalone.

4. **`__all__` de `memory/__init__.py`**: además de `resolve_user_id` y
   `UserIdentityResolutionError`, ¿re-exportar también `MemoryConfig` desde
   `memory/` (atajo) o dejarlo accesible solo vía `models.config.memory_config`?
   Asumo solo lo del resolver (cohesión del módulo `memory/`).
