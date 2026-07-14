---
change: skills-wiring
spec: SPEC_30
status: proposed
artifact_store: hybrid
depends_on:
  - openspec/specs/skills-foundation
---

# Proposal: Skills Wiring — AgentFactory forwarding + contract tests (SPEC_30, Slice B)

## Intent (Por qué, ahora)

`AgentConfig.skills` ya es un slot opaco y `SkillsFactory.build` (slice A) ya
construye un `agno.skills.Skills` vivo desde un dict/`SkillsConfig`. Pero
`AgentFactory.build()` sigue IGNORANDO `cfg.skills`: el agente se construye con
`skills=None` sin importar el YAML (`agent_factory.py:103-110`, verificado
`test_agent_factory.py:147` — `result.skills is None` aún con `cfg.skills`
poblado). Slice A es código muerto sin wiring. Slice B cierra el loop:
`cfg.skills` → `SkillsFactory.build(cfg.skills)` → `Agent(skills=...)`, y
verifica los tres contratos de SPEC_30 §5-6 (system-prompt snippet, access
tools, hot-reload) que Agno 2.6.22 garantiza sobre el atributo público
`agent.skills` (exploración obs-2137: `agent.py:432,588`).

## Why Now

- Es el slice dependiente de skills-foundation (A=shipped, B=this). Sin B, A no
  tiene consumidor y SPEC_30 no cierra.
- Los contratos de system-prompt + access tools + hot-reload son observables
  SOLO cuando `Agent` recibe el `Skills` — no se pueden testear contra
  `SkillsFactory` aislada.
- Multi-loader y SKILL.md parsing son explícitamente DEFER (post-MVP, slice C).

## Scope

### In Scope

- **MODIFY** `src/yaml_agno/factories/agent_factory.py`: cuando `cfg.skills is
  not None`, llamar `SkillsFactory.build(cfg.skills)` y forwardear el resultado
  a `Agent(skills=...)`. Cuando `cfg.skills is None`, `skills` queda `None`
  (backward compat — agentes sin skills no se ven afectados).
- **MODIFY** `tests/unit/factories/test_agent_factory.py`: actualizar
  `test_build_all_opaque_slots_tags_metadata_populated` (línea 147) —
  actualmente usa `skills={"list": ["s1"]}` (dict inválido para `SkillsConfig`,
  sin `path`) y afirma `result.skills is None`. Slice B lo rompe: el factory
  ahora valida y propagaría `ValidationError`. Se debe usar un `cfg.skills=None`
  o un dict `{"path": ...}` válido con temp-dir fixture.
- **NEW** tests de contrato SPEC_30 §5-6 (en archivo nuevo o extendiendo el
  existente):
  - **System-prompt snippet**: `Agent` con `skills` poblado tiene el bloque
    `<skills_system>` en su system message (verificado Agno `_messages.py:282`).
  - **Access tools presence**: `agent.skills.get_tools()` retorna exactamente 3
    `Function` objects (`get_skill_instructions`, `get_skill_reference`,
    `get_skill_script`) (Agno `agent_skills.py:150-185`).
  - **Hot-reload**: `agent.skills.reload()` funciona sin error sobre el
    atributo público (Agno `agent_skills.py:54-61` — clears `_skills` dict +
    re-runs `_load_skills`).
  - **Negative**: `Agent` construido con `cfg.skills=None` tiene `agent.skills
    is None` y NO tiene el snippet ni las access tools.
- Fixtures: `tempfile.TemporaryDirectory()` con un subfolder `my-skill/` +
  `SKILL.md` válido (frontmatter `name: my-skill`, `description: test`, body
  markdown). Patrón ya probado en tests de slice A.

### Out of Scope (DEFER)

- **Multi-loader**: `SkillsConfig` queda como entrada única (`path` + `validate`
  SkillsConfig de slice A). Si se requieren múltiples directorios, slice C
  cambia el schema a `list[SkillsConfig]` o añade `paths`.
- **SKILL.md parsing**: Agno lo posee; yaml-agno NO reimplementa.
- **E2E**: agent que responde usando un skill (TASK_011 de SPEC_30).
- **Path traversal test**: contrato sobre `safe_join_relative_path` (TASK_009).
- **Heuristic single-folder vs directory**: contrato sobre `LocalSkills`
  (TASK_010).
- **Cambios a `SkillsConfig`/`SkillsFactory`**: slice A ya shipped, no se toca.
- **`AgentConfig.skills` tipado**: permanece opaco (`dict[str, Any] | None`);
  la validación vive en `SkillsFactory.build` (Option B).

## Capabilities

### New Capabilities

- `skills-wiring`: wiring de `AgentFactory.build` → `Agent(skills=...)` +
  contratos observables (system-prompt snippet, access tools, hot-reload).

### Modified Capabilities

- `skills-foundation`: sin cambio de schema ni de `SkillsFactory`. Pero el
  *comportamiento* de `AgentFactory.build()` cambia (ahora consume
  `cfg.skills`), documentado como delta conductual. El test existente
  `test_build_all_opaque_slots_tags_metadata_populated` se actualiza porque su
  fixture `skills={"list": ["s1"]}` era inválido y ahora se validaría.

## Approach

**Adapter delgado, Option B (consistente con slice A + ToolFactory):**
`AgentConfig.skills` permanece opaco. `AgentFactory.build` delega a
`SkillsFactory.build(cfg.skills)` que ya valida via `TypeAdapter(SkillsConfig)`.

Flujo de wiring en `build()`:
1. Si `cfg.skills is None` → `skills=None` (path actual, cero cambios).
2. Si `cfg.skills is not None` → `skills = SkillsFactory.build(cfg.skills)`
   (retorna `Skills` o propaga `ValidationError`/`FileNotFoundError`/
   `SkillValidationError`).
3. `Agent(skills=skills, ...)` — Agno acepta `Skills | None`.

**Cero lógica reimplementada:** snippet XML, access tools, reload — todos viven
en `agno.skills` y se observan sobre `agent.skills` (atributo público,
verificado obs-2137). Los tests de contrato ASSERT lo que Agno garantiza; no
lo reimplementan.

**Tests de contrato sobre instancia real de Agno** (sin mocks de la interna):
se construye un `Agent` con un `Skills` sobre temp-dir con `SKILL.md` real y
se inspecciona `agent.skills.get_tools()`, `agent.skills.reload()`, y el
system message. Esto valida la integración de punta a punta Agno-side.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/yaml_agno/factories/agent_factory.py` | Modified | `build()` gana wiring `cfg.skills` → `SkillsFactory.build` → `Agent(skills=...)`. |
| `tests/unit/factories/test_agent_factory.py` | Modified | Actualizar fixture `skills={"list":["s1"]}` (inválido post-wiring) a `None` o dict `{"path":...}` válido. |
| `tests/unit/factories/test_agent_factory_skills.py` | NEW | Contratos: snippet, access tools, hot-reload, negative. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Test existente `test_build_all_opaque_slots...:147` rompe — usa `skills={"list":["s1"]}` inválido que ahora se valida. | High | Actualizar el fixture a `cfg.skills=None` (o un dict `{"path": tmp}` válido). Es cambio mecánico, no conductual. |
| System-prompt snippet es observable solo via `_messages` interno de Agno — API frágil entre minor versions. | Med | Pin Agno 2.6.22 (pyproject.toml:22); exploración obs-2137 verificó `_messages.py:282-285,630-633`. Si la aserción es frágil, testear via `agent.skills.get_system_prompt_snippet()` (método público) en su lugar. |
| `LocalSkills.load()` en construcción llama `Path.resolve()` — tests deben pasar path existente o `FileNotFoundError` temprano. | Med | Fixtures temp-dir con `SKILL.md` real (patrón slice A). |
| `SkillValidationError` propagado desde `SkillsFactory.build` si fixture `SKILL.md` no pasa `validate_skill_directory` (nombre con mayúsculas, etc.). | Low | Fixture `my-skill/` (lowercase, hyphens ok, dir-name==skill-name) cumple las reglas verificadas (obs-2137, validator.py:227). |
| `agent.skills.reload()` podría requerir que el path siga existente — si el temp-dir se limpia antes del reload, falla. | Low | Mantener el temp-dir vivo durante el test (context manager). |
| Discrepancia SPEC_30 §4.4: nombra `SkillsConfigFactory` pero shipped usa `SkillsFactory`. | Low | Mantener `SkillsFactory` (convención bare-noun, ya shipped en slice A). Documentado en slice A. |

## Rollback Plan

1. Revertir `agent_factory.py` al `build()` sin forwarding de `skills` (1
   archivo, sin dependientes — `SkillsFactory` sigue existiendo pero sin
   caller).
2. Revertir `test_agent_factory.py:147` a `skills={"list":["s1"]}` + aserción
   `is None`.
3. Eliminar `test_agent_factory_skills.py` (NEW file, sin dependientes).
4. Slice A (`SkillsConfig`/`SkillsFactory`) NO se toca — sigue shipped y
   testeable de forma aislada.
5. `openspec/specs/` no se modifica (sólo delta specs en el change folder) —
   rollback de archivos no toca specs publicados.
6. `git revert` del commit único del slice.

## Dependencies

- **Shipped (slice A)**: `skills-foundation` — `SkillsConfig` + `SkillsFactory`
  ya existen y son testeables.
- **Shipped**: `agent_factory.py` con `build(cfg, resolver=None)` +
  `tool_call_limit` (slices SPEC_01 + SPEC_11C + SPEC_11D).
- **Agno 2.6.22**: `Agent(skills: Optional[Skills])` constructor param
  (`agent.py:432`), atributo público `agent.skills` (`agent.py:588`),
  `Skills.reload()` / `get_tools()` / `get_system_prompt_snippet()`
  (verificado obs-2137).

## Success Criteria

- [ ] `AgentFactory.build(cfg_with_skills)` produce un `Agent` cuyo
  `.skills` es una instancia `agno.skills.Skills` (no `None`).
- [ ] `AgentFactory.build(cfg_without_skills)` produce un `Agent` con
  `.skills is None` (backward compat — cero tests existentes rotos tras
  actualizar el fixture inválido).
- [ ] El system message del agente con skills contiene el bloque
  `<skills_system>` (o `agent.skills.get_system_prompt_snippet()` lo retorna).
- [ ] `agent.skills.get_tools()` retorna exactamente 3 `Function` objects
  (`get_skill_instructions`, `get_skill_reference`, `get_skill_script`).
- [ ] `agent.skills.reload()` ejecuta sin error sobre el atributo público.
- [ ] Agente sin skills NO tiene snippet ni access tools.
- [ ] Cero lógica de parsing/generación reimplementada en yaml-agno.

## Proposal Question Round

Las siguientes preguntas producto se dejan abiertas para revisión del usuario
antes de pasar a `sdd-spec`. Si no se contestan, se asume el default anotado.

1. **System-prompt snippet — aserción sobre `_messages` interno vs método
   público**: Agno expone `agent.skills.get_system_prompt_snippet()` (público,
   `agent_skills.py:90-148`) pero el snippet se INYECTA en el system message
   via `_messages.py:282-285` (interno). ¿Testeamos via el método público (más
   estable, no prueba la inyección real) o via inspección del system message
   construido (prueba la integración real pero acopla a internals de Agno)?
   — **Default: método público `get_system_prompt_snippet()`** para el
   contract test principal; un test adicional de integración leve sobre el
   system message si es estable en 2.6.22.
2. **Fixture del test existente (`test_build_all_opaque_slots...:147`)**: su
   `skills={"list":["s1"]}` es inválido post-wiring. ¿Lo cambiamos a
   `cfg.skills=None` (mantiene la intención "slots opacos ignorados" para los
   otros 8 slots) o a un dict `{"path": tmp}` válido (ejercita el wiring)?
   — **Default: `cfg.skills=None`** (ese test es sobre slots opacos NO
   forwardeados, no sobre skills; el wiring se cubre en el archivo nuevo).
3. **Ubicación de los contract tests**: ¿archivo nuevo
   `test_agent_factory_skills.py` (aislado, espejo del patrón
   `TestAgentFactoryToolsWiring`/`TestAgentFactoryToolCallLimit` dentro del
   mismo archivo) o clase nueva `TestAgentFactorySkillsWiring` dentro de
   `test_agent_factory.py` existente?
   — **Default: clase nueva dentro de `test_agent_factory.py`** (consistencia
   con las clases `TestAgentFactoryToolsWiring` y `TestAgentFactoryToolCallLimit`
   ya ahí).
4. **`agent.skills.reload()` — path debe seguir existiendo**: el reload
   re-corre `LocalSkills.load()` que re-resuelve el path. ¿El test de
   hot-reload mantiene el temp-dir vivo (context manager) o copia el skill a
   un path estable?
   — **Default: temp-dir vivo via `with TemporaryDirectory()`** durante toda
   la aserción de reload.
5. **Alcance del negative test**: ¿solo `cfg.skills=None` → `agent.skills is
   None`, o también `cfg.skills={}` (dict vacío) → comportamiento definido?
   — **Default: solo `cfg.skills=None`** (el caso `dict` vacío no está
   especificado en slice A; `SkillsFactory.build({})` levantaría
   `ValidationError` por `path` requerido, lo cual es correcto y no necesita
   test separado en slice B).
