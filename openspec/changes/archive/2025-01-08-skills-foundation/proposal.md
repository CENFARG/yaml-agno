---
change: skills-foundation
spec: SPEC_30
status: proposed
artifact_store: hybrid
depends_on: []
---

# Proposal: Skills Foundation — Schema + Factory (SPEC_30, Slice A)

## Intent (Por qué, ahora)

`AgentConfig.skills` ya existe como slot opaco (`dict | None`) pero no hay nada que lo consuma: ningún schema lo valida y ningún factory lo convierte en un `agno.skills.Skills` vivo. SPEC_30 §2-3 define el contrato; SPEC_11 (Tools) ya demostró el patrón adapter en `tool_factory.py` (Option B: config opaca + `TypeAdapter` dentro de `build`). Esta change introduce el slice fundacional — **schema `SkillsConfig` + `SkillsFactory.build()`** — para que `skills:` deje de ser configuración muerta y se vuelva construible y testeable de forma aislada, sin acoplar todavía el `AgentFactory`.

## Scope

### In Scope
- `src/yaml_agno/skills/schema.py`: `SkillsConfig` Pydantic V2 (`path: str`, `validate: bool = True`).
- `src/yaml_agno/skills/factory.py`: `SkillsFactory.build(config) -> Skills` — adapter delgado.
- `src/yaml_agno/skills/__init__.py`: re-export de `SkillsConfig` y `SkillsFactory`.
- Tests: validación de schema, construcción con `LocalSkills` real sobre temp-dirs con fixtures `SKILL.md`, propagación de `SkillValidationError`, retorno de instancia `Skills` válida, comportamiento con config mínima.

### Out of Scope (DEFER a slice B — `skills-wiring`)
- `AgentFactory.build` wiring del kwarg `skills=` a `agno.Agent(skills=...)`.
- Tests de contrato de system-prompt (inyección `<skills_system>` en el agente).
- Hot-reload (`agent.skills.reload()`).
- Integración e2e config-YAML → Agent con skills.
- Cualquier parsing/validación/generación de SKILL.md propia — Agno lo posee.

## Approach

**Adapter delgado, Option B (consistente con ToolFactory):** `AgentConfig.skills` permanece opaco (`dict | None`). La validación vive DENTRO de `SkillsFactory.build` vía `TypeAdapter(SkillsConfig)` — el límite de validación se mueve de config-parse a factory-build, no desaparece.

Flujo de `build(config)`:
1. `TypeAdapter(SkillsConfig).validate_python(config)` → instancia validada.
2. `LocalSkills(path=config.path, validate=config.validate)` — constructor de Agno, que hace `Path(path).resolve()`.
3. `Skills(loaders=[local_skills])` — envoltura orquestadora de Agno.
4. Retorna la instancia `Skills`.

**Naming:** `SkillsFactory` (convención bare-noun de `ToolFactory`/`AgentFactory`, NO `SkillsConfigFactory` de SPEC_30 §4.4).

**Cero lógica de negocio reimplementada:** todo el parsing de frontmatter, validación de `SKILL.md`, generación de snippet XML, y exposición de tools (`get_skill_instructions`/`reference`/`script`) vive en `agno.skills`. yaml-agno solo mapea config → constructores Agno.

## Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `src/yaml_agno/skills/schema.py` | New | `SkillsConfig` Pydantic V2 (2 campos). |
| `src/yaml_agno/skills/factory.py` | New | `SkillsFactory.build()` — adapter a `LocalSkills` + `Skills`. |
| `src/yaml_agno/skills/__init__.py` | Modified | Re-export público (actualmente stub vacío). |
| `tests/yaml_agno/skills/` | New | Suite de tests con fixtures temp-dir `SKILL.md`. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `LocalSkills.__init__` resuelve path en construcción (no en `load`) — tests deben pasar path existente o esperar `FileNotFoundError` temprano | Medium | Confirmado en explore (loaders/local.py:12); fixtures temp-dir garantizan path válido. |
| `SkillValidationError` se eleva hard cuando `validate=True` y `SKILL.md` inválido — propagación debe ser transparente, no capturada | Low | No capturar en factory; dejar burbujear (contrato explícito del adapter). |
| Acoplamiento a API interna de Agno (`Skills`, `LocalSkills`) que puede cambiar entre minor versions | Low | Pin Agno 2.6.22 (pyproject.toml:22); explore verificó todas las firmas contra esa versión. |
| `AgentConfig.skills` queda opaco sin consumidor hasta slice B — revisor podría ver slice A como "incompleto" | Medium | Documentar explícitamente en docstrings y proposal que slice B es dependiente y planificado. |

## Rollback Plan

Eliminar los 3 archivos nuevos (`schema.py`, `factory.py`) y revertir `__init__.py` a stub vacío. Sin migración de datos ni estados intermedios: `AgentConfig.skills` sigue siendo opaco-no-consumido, idéntico al estado pre-change. `git revert` del commit único del slice.

## Dependencies

- **Ninguna externa nueva.** Agno 2.6.22 ya provee `agno.skills.Skills`, `LocalSkills`, `SkillValidationError` (verificado).
- **No depende de SPEC_11** (Tools) — skills y tools son ejes independientes.
- Slice B (`skills-wiring`) dependerá de este slice A para el wiring en `AgentFactory`.

## Success Criteria

- [ ] `SkillsConfig(path=".", validate=True)` valida correctamente; `validate=False` permitido.
- [ ] `SkillsFactory.build({"path": tmp, "validate": True})` retorna `Skills` con un `LocalSkills` activo.
- [ ] `SkillValidationError` de Agno se propaga sin captura cuando un `SKILL.md` es inválido y `validate=True`.
- [ ] Suite de tests pasa con fixtures `SKILL.md` reales en temp-dirs (sin mocks de Agno).
- [ ] Cero lógica de parsing/validación de SKILL.md reimplementada en yaml-agno.
- [ ] `__init__.py` re-exporta API pública (`SkillsConfig`, `SkillsFactory`).

## Proposal question round

Propuesta derivada de exploration ya validada contra Agno 2.6.22. Supuestos clave que conviene confirmar antes de spec:

1. **¿`SkillsConfig` es un solo loader (un `path` + `validate`) o una lista de loaders?** SPEC_30 §3 sugiere config por-agente con un directorio; `Skills(loaders=[...])` de Agno acepta múltiples. Asunción del proposal: **un loader por `SkillsConfig`** (un directorio raíz de skills). Si se requiere multi-directorio, el schema cambia a `list[SkillsConfig]` o se añade campo `paths`.
2. **¿`validate=True` como default es correcto para yaml-agno?** Agno lo usa así. Pero en CI/tests con fixtures parciales podría ser ruidoso. Asunción: **mantener default de Agno**; tests controlan el flag explícitamente.
3. **¿La factory debe aceptar también una instancia `SkillsConfig` pre-parseada** (además de dict opaco), como hace `ToolFactory` con `ToolEntry`? Asunción: **sí** — `build(config: dict | SkillsConfig)`, simetría con ToolFactory.
4. **¿Re-exportar además `LocalSkills`/`SkillValidationError`** desde `yaml_agno.skills` para conveniencia del consumidor de slice B, o mantener el namespace minimal? Asunción: **minimal** — solo `SkillsConfig` y `SkillsFactory`.

## Capabilities

### New Capabilities
- `skills-foundation`: Schema `SkillsConfig` + factory adapter delgado a `agno.skills.Skills`. Fundamento construible y testeable para skills; wiring de agente es slice B separado.

### Modified Capabilities
- None — `AgentConfig.skills` permanece opaco sin cambio de behavior (el consumidor llega en slice B).
