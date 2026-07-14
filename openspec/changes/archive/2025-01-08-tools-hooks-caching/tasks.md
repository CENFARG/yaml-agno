---
change: tools-hooks-caching
spec: SPEC_11
artifact: tasks
status: tasked
artifact_store: hybrid
slice: D (final)
depends_on:
  - openspec/changes/tools-hooks-caching/proposal.md
  - openspec/changes/tools-hooks-caching/specs/tools-hooks-caching/spec.md
  - openspec/changes/tools-hooks-caching/design.md
strict_tdd: true
test_command: python -m pytest
---

# Tasks: Tools Hooks + Caching + tool_call_limit (SPEC_11 Slice D — final)

> Cierra SPEC_11. TDD estricto RED→GREEN. 4 archivos modificados, 0 creados.
> Hooks ahora, caching invariante, concurrencia nunca, registry separado,
> tool_call_limit ahora.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 (schema ~40, tool_factory ~30, agent_config ~10, agent_factory ~5, tests ~80-100, docstrings ~15) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (well under budget) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (no split needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Hooks schema + resolution + tool_call_limit + caching invariant | PR único | base = feature branch; 4 files modified, 0 created; all orthogonal concerns |

## Open Items

- **Allowlist de hooks**: los módulos de hook del usuario (ej. `myapp.hooks.`)
  deben añadirse al allowlist en bootstrap (SPEC_11 §10.3). Es concern de
  bootstrap-config, NO de código slice-D. `_resolve_dotted` lee el allowlist
  tal cual. Documentado como paso de despliegue.
- **@tool(pre_hook=) acceptance**: verificado por orchestrator en Agno 2.6.22.
  Apply debe re-verificar con test de integración (Phase 4).

## TDD Compliance Matrix

| Req | RED task | GREEN task | Scenarios |
|-----|----------|------------|-----------|
| R1: Hook fields en CustomToolConfig | 2.1 | 3.1 | Configuración válida; tool_hooks default []; tool_hooks multi-ref; dotted-path inválido |
| R2: Resolución+forwarding en _wrap_tool | 2.2 | 3.2 | Reenvío dorado pre_hook; reenvío dorado tool_hooks; hooks omitidos ausentes |
| R3: Rechazo módulo no-allowlisted | 2.3 | 3.2 (inmediato) | Hook no-allowlisted (RED); transacción parcial |
| R4: tool_call_limit en AgentConfig | 2.4 | 3.3 | Válido 5; default None; inválido 0 |
| R5: AgentFactory forwarding | 2.5 | 3.4 | Reenvío dorado 10; None omitido |
| R6: Caching invariante | 2.6 | 3.2 (inmediato) | Caching+hooks coexisten; caching sin hooks sin regresión |
| R7: REMOVED (concurrencia/registry/cache_callables) | — | — | N/A — nunca/separado/deferido |

## Implementation Order

**Schema primero** (R1) → **Factory hooks** (R2+R3+R6, mismo archivo) →
**AgentConfig** (R4) → **AgentFactory** (R5). Los cuatro cambios son
ortogonales (tools-layer vs agent-layer no comparten codepath), pero el orden
maximiza coherencia: el schema habilita los tests de factory, y el
agent_config habilita los tests de agent_factory.

## Phase 1: Baseline

- [x] 1.1 Verificar baseline limpio: `git status` sin cambios, HEAD en la
  rama del slice C. **Req: Rollback (baseline obligatorio).**
- [x] 1.2 Confirmar verde inicial: `python -m pytest` pasa sin modificaciones.
  **Req: Sin regresión slice A/B/C.**

## Phase 2: RED — tests que fallan primero

- [x] 2.1 **R1** — Escribir `test_custom_tool_config_accepts_hook_fields` en
  `tests/unit/tools/test_schema.py`: parse con `pre_hook`, `post_hook`,
  `tool_hooks=["a.b","c.d"]`. Escribir `test_tool_hooks_defaults_empty`.
  Escribir `test_pre_hook_invalid_no_dot` (espera ValidationError).
  Run → FAILS (`extra="forbid"` rechaza los campos).
- [x] 2.2 **R2** — Escribir `test_wrap_tool_resolves_pre_hook` en
  `tests/unit/tools/test_tool_factory.py`: assert `_resolve_dotted` llamado
  Y `Function.pre_hook` es el stub. Escribir
  `test_wrap_tool_resolves_tool_hooks_list`: assert `Function.tool_hooks`
  tiene 2 callables en orden. Escribir
  `test_wrap_tool_omits_hooks_when_absent`: assert `@tool` sin keys de hook.
  Run → FAILS (`_wrap_tool` no resuelve hooks).
- [x] 2.3 **R3** — Escribir `test_wrap_tool_rejects_non_allowlisted_hook`:
  `pre_hook="evil_pkg.spy"` espera `SecurityError`. Escribir
  `test_wrap_tool_partial_hooks_transaction`: `tool_hooks=["ok.good","evil.bad"]`
  espera `SecurityError` (todo-o-nada). Run → FALLA si wiring de 3.2 incorrecto
  (el guardia vive en `_resolve_dotted`, ya testeado).
- [x] 2.4 **R4** — Escribir `test_agent_config_accepts_tool_call_limit` en
  `tests/unit/models/test_agent_config.py`: valor `5` aceptado. Escribir
  `test_agent_config_tool_call_limit_defaults_none`. Escribir
  `test_agent_config_rejects_zero_tool_call_limit`: `0` → ValidationError.
  Run → FAILS (`extra="forbid"` en AgentConfig rechaza el campo).
- [x] 2.5 **R5** — Escribir `test_agent_factory_forwards_tool_call_limit` en
  `tests/unit/factories/test_agent_factory.py`: `Agent.tool_call_limit == 10`.
  Escribir `test_agent_factory_tool_call_limit_none_omitted`:
  `Agent.tool_call_limit is None`. Run → FAILS (`build()` no forwardea).
- [x] 2.6 **R6** — Escribir `test_caching_plus_hooks_coexist` en
  `test_tool_factory.py`: config con `cache_results=True, cache_ttl=300,
  pre_hook="..."` → `Function` tiene ambas (cache y hook). Escribir
  `test_caching_without_hooks_no_regression`. Run → FALLA hasta que 3.2
  aplique (las flags de cache ya existen; el test valida invariante).

## Phase 3: GREEN — implementación mínima

- [x] 3.1 **R1 GREEN** — Añadir `pre_hook: str|None`, `post_hook: str|None`,
  `tool_hooks: list[str]` a `CustomToolConfig` en
  `src/yaml_agno/tools/schema.py` (insert after caching block, before
  `@model_validator`). Quitar NOTE "INTENTIONALLY ABSENT" del docstring.
  Run tests 2.1 → verdes.
- [x] 3.2 **R2+R3+R6 GREEN** — En `_wrap_tool` (`tool_factory.py`): añadir
  bloque de resolución (`pre_hook_callable`, `post_hook_callable`,
  `tool_hooks_callables` vía `self._loader._resolve_dotted`) + tres keys en
  el dict `flags` (`tool_hooks_callables or None`). El None-drop existente
  maneja omisión. Actualizar docstrings módulo + clase. Run tests
  2.2+2.3+2.6 → verdes.
- [x] 3.3 **R4 GREEN** — Añadir `tool_call_limit: int|None = Field(default=None,
  ge=1)` a `AgentConfig` en `src/yaml_agno/models/config/agent_config.py`
  (Behavior section, after `description`). Actualizar comment field-count
  (13→14). Run tests 2.4 → verdes.
- [x] 3.4 **R5 GREEN** — Añadir `tool_call_limit=cfg.tool_call_limit` al
  `Agent(...)` call en `src/yaml_agno/factories/agent_factory.py`. Quitar
  comment "DEFER to slice D". Actualizar scope table del docstring. Run
  tests 2.5 → verdes. Re-run TODO `test_agent_factory.py` → todo verde.

## Phase 4: Verification

- [x] 4.1 `python -m pytest` — suite completa verde (0 fail).
- [x] 4.2 `ruff check .` — sin findings.
- [x] 4.3 `mypy src/yaml_agno` — sin errores.
- [x] 4.4 Cold imports: `python -c "from yaml_agno.tools.schema import
  CustomToolConfig; from yaml_agno.tools.tool_factory import ToolFactory;
  from yaml_agno.models.config.agent_config import AgentConfig; from
  yaml_agno.factories.agent_factory import AgentFactory"` sin error.
- [x] 4.5 **GATE decisions.yaml VQ** — verificar que el spec delta está
  alineado con `specs/SPEC_11_TOOLS_AND_MCP.md` (§3.1 hooks, §5.4
  tool_call_limit, §10.3 allowlist). Sin contradicciones.
- [x] 4.6 **@tool(pre_hook=) integration** — test de integración: construir
  un `Function` real vía `ToolFactory._wrap_tool` con `pre_hook` y leer
  `Function.pre_hook` → es el callable resuelto (re-verifica Agno 2.6.22).
- [x] 4.7 Caching invariante: confirmar que `cache_results`/`cache_dir`/
  `cache_ttl` siguen en el dict `flags` tras edits slice-D (sin regresión).
- [x] 4.8 `extra="forbid"` preservado en ambos modelos (CustomToolConfig +
  AgentConfig): test que campo desconocido sigue rechazado.

## Phase 5: Commit granular (conventional commits)

- [x] 5.1 `feat(tools): add hook fields to CustomToolConfig` (3.1).
- [x] 5.2 `feat(tools): resolve and forward hooks in _wrap_tool` (3.2).
- [x] 5.3 `feat(agent): add tool_call_limit to AgentConfig` (3.3).
- [x] 5.4 `feat(agent): forward tool_call_limit in AgentFactory.build` (3.4).
- [x] 5.5 `test: add hook resolution, tool_call_limit, caching invariant tests`
  (Phase 2 — si se prefirió commit separado de tests). **No commitear specs/.**
