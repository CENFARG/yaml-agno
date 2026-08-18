# AGNO-283-DIFF-ANALYSIS — Diff Agno 2.8.3 → 2.8.7 y compatibilidad con yaml-agno

- **Fecha**: 2026-08-09
- **Autor**: Code Architect (development-team, CENF)
- **Contexto**: Re-evaluación técnica de yaml-agno con datos corregidos por Gonzalo
  (2026-08-09). El repo local de agno ya estaba en `v2.8.3-16-g7c68873c1` (release 2.8.6);
  el `git pull` avanzó a `d28d58049` (post-release 2.8.7). Este análisis cubre
  **v2.8.3 → HEAD (d28d58049)**, que incluye las releases 2.8.4, 2.8.5, 2.8.6 y 2.8.7.
- **Propósito**: Determinar si subir el pin de yaml-agno de `agno==2.8.3` a `2.8.6` (o `2.8.7`)
  es seguro, e identificar qué tocar.

---

## 1. Estado del repositorio agno (verificado)

| Ítem | Valor |
|---|---|
| Rama | `main` |
| HEAD pre-pull | `7c68873c1` — `chore: release 2.8.6 (#9271)` |
| HEAD post-pull | `d28d58049` — `fix: preserve toolkit instructions on rehydration (#9395)` |
| `git describe` pre-pull | `v2.8.3-16-g7c68873c1` |
| Estado | Fast-forward limpio (`7c68873c1..d28d58049`), working tree solo con `.codegraph/` untracked |
| Red | `git pull origin main` **OK** (no falló; se documenta el resultado real) |

**Corrección de datos**: la consigna indicaba que el repo estaba en 2.8.6. Tras el pull,
el repo local quedó en **2.8.7 + 2 commits de fix** (`03d2bf051` release v2.8.7, luego
`e7f08bfb5` MCP entrypoint fix y `d28d58049` toolkit rehydration fix). El análisis se hace
contra este HEAD, con foco en lo que yaml-agno consume.

## 2. Alcance del diff

- **Rango**: `v2.8.3..HEAD` → **22 commits** (2.8.4 = `f2fdceeb7`, 2.8.5 = `52fa83b05`,
  2.8.6 = `7c68873c1`, 2.8.7 = `03d2bf051`).
- **Repo completo**: 195 archivos, **+24.750 / −4.097** líneas.
- **Solo `libs/agno/agno/`** (el paquete instalable): **78 archivos, +11.340 / −3.437** líneas.
- Áreas con más cambio: `learn/stores/entity_memory.py` (5.251 líneas, revamp de entity
  memory), `vectordb/opensearch/` (nuevo, 2.023), `tools/agentos.py` (nuevo, 991),
  `db/postgres/` (sync+async ≈ 763), `db/sqlite/` (≈ 687), `registry/registry.py` (253),
  `tools/studio.py` (302), `tools/function.py` (131).

## 3. Qué importa yaml-agno de agno (superficie de compatibilidad)

Los 42 imports encontrados en `src/yaml_agno/` (evidencia `git grep "from agno"`):

| Módulo agno | Uso en yaml-agno | ¿Tocado por el diff? |
|---|---|---|
| `agno.os` (AgentOS, config: AuthorizationConfig/MCPServerConfig/MCPBuiltinTag, interfaces: AGUI/Slack/Whatsapp/Telegram/A2A) | `factories/agentos_factory.py`, `agentos/*`, `api/app.py`, `ports/agentos_ports.py` | `client/os.py` +55 (aditivo); `os/routers/metrics` +158 (aditivo); `os/utils.py` +12 (aditivo) |
| `agno.agent` (Agent, AgentFactory, AgentProtocol, RemoteAgent) | `factories/`, `api/app.py` | `agent/agent.py` +9 (aditivo); `_storage.py`/`_tools.py`/`_messages.py` internos |
| `agno.team` (Team, TeamMode) | `factories/team_factory.py`, `models/config/team_config.py` | `team/team.py` +9 (aditivo); `_storage.py`/`_tools.py`/`_messages.py` internos. `team/mode.py` (TeamMode) **NO cambió** |
| `agno.workflow` (Step, Steps, Parallel, Condition, Router, Loop, Workflow, StepType, cel) | `factories/workflow_factory.py`, `workflows/*`, `models/config/workflow_config.py` | `workflow/types.py` +4 (fix serialización); `run/requirement.py` nuevo |
| `agno.tools.mcp` (MCPTools, MultiMCPTools, params) | `tools/mcp_resolver.py` | `utils/mcp.py` +9 (cambio de comportamiento MCP, ver §4) |
| `agno.tools.decorator` (`@tool`) | `tools/tool_factory.py` | `tools/function.py` +131 (aditivo, serialización) |
| `agno.skills` (LocalSkills, Skills) | `skills/factory.py` | `skills/agent_skills.py` +22 (aditivo) |
| `agno.remote` (BaseRemote) | `workflows/a2a_config.py` | `remote/base.py` +12 (aditivo) |
| `agno.exceptions` | `models/fallback_classifier.py` | sin cambios |
| `agno.os.interfaces.a2a` (A2A) | `agentos/a2a_interface.py` | **sin cambios** (el módulo no figura en el diff) |
| `agno.workflow.cel` | `workflows/condition_evaluator.py` | sin cambios |
| `agno.db`, `agno.learn`, `agno.session` | **NO se importan directamente** (la capa DB es propia, `yamlagno_*`; la memoria es Agno native vía kwargs de config) | los grandes cambios de `db/*` y `learn/*` no tocan la superficie de yaml-agno |

## 4. Cambios con potencial de impacto (análisis archivo por archivo)

### 4.1 `agent/agent.py` y `team/team.py` — ADITIVO, sin breaking
- Nuevo kwarg `input` en `get_system_message()`/`aget_system_message()` (agent.py:878-904,
  team.py:1448-1485). Parámetro nuevo opcional; llamadas existentes intactas.
- Nueva advertencia en docstring de `enable_agentic_memory` (agent.py:119-123,
  team.py:302-306): **no combinar con LearningMachine que tenga `user_memory` store** —
  colisión de tool name `update_user_memory` (el parser de tools conserva el primer nombre
  y descarta el del learning store, silenciosamente). Es un **gotcha de configuración**,
  no un breaking. yaml-agno debe evitar activar `enable_agentic_memory` + LearningMachine
  con store `user_memory` en la misma config.

### 4.2 `utils/mcp.py` — CAMBIO DE COMPORTAMIENTO (fix de seguridad, no de API)
- `get_entrypoint_for_tool()` (commit `e7f08bfb5`, #9379): ya no usa
  `partial(call_tool, tool_name=...)`; el tool_name queda **pinneado por closure** y ya no
  puede ser override en call-time. Un argumento `tool_name` que mande el modelo ahora se
  reenvía como argumento ordinario del tool al servidor MCP.
- Impacto en yaml-agno: **bajo** — `tools/mcp_resolver.py` usa `MCPTools`/`MultiMCPTools`
  (mcp_resolver.py:16-17), no construye entrypoints a mano. Comportamiento deseado
  (bloquea prompt injection por tool_name).
- Nota: `prepare_command`/`ALLOWED_COMMANDS` (utils/mcp.py:318,360-361) **ya existía
  idéntico en 2.8.3 instalado** (site-packages:315,357-358) — ver §5.

### 4.3 `agent/_storage.py` / `team/_storage.py` — API interna de rehydration
- `registry.rehydrate_function` (singular) → `registry.rehydrate_functions` (plural)
  (_storage.py:824, _storage.py:836). Serialización de tools ahora estampa el campo
  `toolkit` (toolkit owner) para re-binding (commits `94864b785`, `d28d58049`).
- Impacto: yaml-agno **no llama** a `Agent.from_dict`/`registry.rehydrate_function`
  directamente (sus factories construyen objetos nuevos desde YAML). Cambio interno de
  Agno, transparente.

### 4.4 `learn/*` — REVAMP de entity memory (el cambio más grande)
- `learn/stores/entity_memory.py`: 5.251 líneas cambiadas (commit `6aa13e8f8`,
  "revamp entity memory for the second brain") + `decision_log`, `user_memory`,
  `user_profile`, `machine.py`, `schemas.py`.
- Impacto: la **API pública** de LearningMachine/MemoryManager no cambió (yaml-agno no la
  importa; Decisión 4 la consume vía kwargs de config). Pero el **schema interno de
  almacenamiento** cambió: sesiones/memoria persistidas con 2.8.3 en el store de memoria
  **no son migrables por schema** → hay que **recrear/reindexar** los stores de memoria
  (incluido el `agno.db` local del repo yaml-agno, generado bajo 2.8.3).
- Acción al subir: borrar/regenerar `agno.db` y stores de memoria en entornos de dev.

### 4.5 `db/postgres/` y `db/sqlite/` — ADITIVO
- `db/postgres/postgres.py`: +`get_span_stats()`, +`search_learnings()` (métodos nuevos).
  Sin renombres de clase (PgVectorDb/PgAgentStorage intactos). Importante para SPEC_03:
  la clase que yaml-agno usará para storage Postgres **no cambió de firma**.
- `db/sqlite/*`: fixes internos + encoding utf-8.

### 4.6 `skills/agent_skills.py` — ADITIVO
- `_get_skill_reference()`/`_get_skill_script()`: `reference_path`/`script_path` ahora
  `Optional`, devuelven error JSON estructurado si falta (skills/agent_skills.py:216-241,
  285-318). Compatible con `skills/factory.py` (que usa `LocalSkills`/`Skills`).

### 4.7 `tools/function.py` — ADITIVO (serialización)
- Nuevas constantes `SERIALIZED_FIELDS`/`RUNTIME_ONLY_FIELDS` + cache de versión de
  pydantic. `Function.to_dict()`/`from_dict()` con campos explícitos. El decorator `@tool`
  y `Function.from_callable()` **no cambiaron de firma** → `tool_factory.py` intacto.

### 4.8 `workflow/types.py` — FIX de serialización
- `StepRequirement.to_dict()` ahora serializa `executor_requirements` con `req.to_dict()`
  (workflow/types.py:1148-1150; commits `69c05da4a`, `12d74173b`). Afecta solo a quienes
  serializan StepRequirement con HITL executor; yaml-agno no serializa ese tipo (su
  `workflows/step_executor.py` ejecuta, no serializa requirements anidados).

### 4.9 Otros (sin impacto para yaml-agno)
- `client/os.py`: `refresh_metrics(background=...)` + `get_metrics_refresh_status()` — aditivo.
- `remote/base.py`: `refresh_metrics` return type → `Union[...]` — aditivo (yaml-agno no usa).
- `models/base.py`: encoding utf-8 en cache file + mensaje de media distinto — no breaking.
- `tools/function.py` (decorator), `agent/_init.py`/`team/_init.py`: propagación de
  `knowledge` al LearningMachine si `learned_knowledge` está activo — aditivo.
- Nuevos tools/providers: `tools/agentos.py` (+991), `tools/advisor.py` (+214),
  `tools/studio.py` (+302), `tools/scheduler.py` (+69), `tools/smallest.py` (+211),
  `tools/openrouteservice.py` (+410), `models/trustedrouter/` (nuevo provider OpenAILike),
  `vectordb/opensearch/` (nuevo) — todos aditivos.

## 5. Dependencias del entorno (pip) — compatibilidad verificada

| Dependencia | yaml-agno pin | agno 2.8.7 requiere | Compatible |
|---|---|---|---|
| `mcp` | `>=1.0,<1.28` (pyproject:37) | extra `mcp` = `mcp>=1.9.2,<2` | ✅ (`1.9.2 ≤ mcp < 1.28 ⊂ <2`) |
| `pydantic` | `>=2.0` | v2 (cache de version) | ✅ |
| `agno[a2a]` | extra implícito | sigue existiendo | ✅ |
| `fastapi` / `uvicorn` | `fastapi>=0.100` | extra `os` | ✅ |
| `sqlalchemy` | `>=2.0,<3` | extra `os` | ✅ |

## 6. Deuda preexistente detectada (NO causada por la subida)

`pytest -m unit` en yaml-agno contra **agno 2.8.3 instalado** (el pin actual):
**657 passed, 6 failed, 1 skipped**. Los 6 fallos son de `tests/unit/tools/test_mcp_resolver.py`
con `ValueError: MCP command needs to use one of the following executables: {...}`
(comandos `"echo hi"` no permitidos por `ALLOWED_COMMANDS`).

- `ALLOWED_COMMANDS` existe **idéntico** en 2.8.3 instalado (site-packages
  `agno/utils/mcp.py:315,357-358`) y en HEAD (`libs/agno/agno/utils/mcp.py:318,360-361`).
- Conclusión: los 6 tests fallan **independientemente de la subida** — deuda preexistente
  de los tests (usan comandos no permitidos). Fix: usar comandos de la allowlist
  (p.ej. `uvx`, `python`) o mockear `prepare_command`. Esfuerzo: ~0,5 día-agente.

## 7. Contexto `agno_cenf` (fork CENFARG)

- El fork `C:\Dropbox\DOC.RECA\06-Software\agno_cenf` tiene trabajo de interfaces
  Microsoft 365 (commits `2f725b9e7` "feat(os/interfaces): add Microsoft 365 Copilot
  interface", `f93feee94` JWKS validation, `6ca3d8a74` Agent.id compatibility).
- Relevancia: solo si CENF decide tocar el core de agno (interfaces m365). **No afecta**
  la decisión de subida de pin; es un fork para futura contribución upstream.

## 8. VEREDICTO — ¿2.8.3 → 2.8.6/2.8.7 es safe?

**SÍ, es seguro.** No hay **ningún breaking change de API pública** contra la superficie
que yaml-agno importa (42 imports → todos aditivos o en código interno de Agno). Los
cambios de comportamiento relevantes son fixes deseables (MCP tool_name pinneado, mejor
serialización de tools) o gotchas de configuración (colisión `update_user_memory`).

### Qué hay que tocar al subir el pin

1. **`pyproject.toml:22`** — `agno==2.8.3` → `agno==2.8.6` (mínimo) o `agno==2.8.7` (recomendado:
   incluye el fix de seguridad MCP #9379 y el fix de rehydration #9395). Verificar con
   `pip install -e ".[dev]"` + `pytest -m unit`.
2. **Docs STALE** — `AGENTS.md` dice "Agno 2.6.22" y `DECISIONES.md` §1 dice "Agno v2.6.18":
   actualizar a la versión real (2.8.6/2.8.7). `DECISIONES.md` §2.9 citado en §4bis no
   depende de versión.
3. **`agno.db` local** (raíz del repo yaml-agno) y stores de memoria: **regenerar** tras la
   subida por el revamp de entity memory (§4.4). No intentar migrar datos de memoria 2.8.3.
4. **Gotcha `update_user_memory`** — revisar configs YAML que combinen
   `enable_agentic_memory: true` con `learning` (user_memory store): elegir uno solo.
5. **6 tests MCP** — corregir los comandos no permitidos (§6). Puede hacerse antes o
   después de la subida (independiente).
6. **Compatibilidad `mcp<1.28`** — mantener (compatible con `mcp<2` de agno). Si se quiere
   simplificar, se puede subir el pin de `mcp` a `<2` — opcional.

### Tabla resumen de riesgo

| Área | Riesgo | Tipo |
|---|---|---|
| Agent/Team constructor + run | Ninguno | aditivo |
| Workflow primitives + StepType | Ninguno | fix serialización |
| MCP tools | Bajo (comportamiento, no API) | fix seguridad |
| Skills | Ninguno | aditivo |
| DB Postgres/SQLite (storage Agno) | Ninguno (API estable) | aditivo |
| Memoria (LearningMachine) | Medio (datos no migran) | revamp interno |
| AgentOS (client, metrics, interfaces a2a) | Ninguno | aditivo |
| Provider models (base.py) | Ninguno | fix encoding |
