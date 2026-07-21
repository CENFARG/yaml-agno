# Reporte de Bugs y Deuda Técnica — yaml-agno v0.1 (integración core-cenf)

**Fecha:** 2026-07-21  
**Contexto:** Integración de yaml-agno v0.1 con core-cenf-py v0.1.0 para el PoC `strategic-gestion-team`.  
**Autor:** Gentle AI Orchestrator (integración agente-agente)

---

## Resumen

Se encontraron **5 issues** durante la integración, 2 de los cuales son **bloqueantes** (crash en runtime) y 3 son **deuda técnica** que reduce robustez y previsibilidad.

---

## ISSUE 1 (BLOQUEANTE): `PydanticConfigAdapter` no implementa `set_value()`

### Archivo
`src/yaml_agno/di/agno_resolver.py`, línea 269

### Síntoma
`AttributeError: 'PydanticConfigAdapter' object has no attribute 'set_value'`

### Causa raíz
```python
# agno_resolver.py:267-269
# set_value es el método del puerto ConfigManager que tanto
# PydanticConfigAdapter como InMemoryConfigAdapter exponen.
resolved_config.set_value(
    "dependency.allowlist_paths",
    list(AGNO_ALLOWLIST_PREFIXES),
)
```

El comentario (línea 267-268) afirma que ambos adapters exponen `set_value()`, pero esto es FALSO:

| Adapter | `set_value()` |
|---|---|
| `InMemoryConfigAdapter` | ✅ Sí (línea 247) |
| `PydanticConfigAdapter` | ❌ No existe |
| Puerto `ConfigManager` | ❌ No lo declara |

Además, el flujo en línea 253:
```python
resolved_config = config if config is not None else PydanticConfigAdapter()
```

Cuando el caller no pasa `config` explícito (caso default), se construye `PydanticConfigAdapter()` que NO soporta `set_value()`. La función siempre crashea en ese camino salvo que el caller ya haya pre-seedeado `dependency.allowlist_paths`.

### Reproducción
```python
from yaml_agno.di import build_agno_resolver
resolver = build_agno_resolver()  # crash: AttributeError
```

### Fix aplicado en el PoC
Usar `InMemoryConfigAdapter(initial_data={...})` con el allowlist pre-seedeado, para que la guarda `if not dep_section.get("allowlist_paths")` sea False y nunca se ejecute `set_value()`.

### Fix recomendado para release

**Opción A (mínima):** Agregar `set_value` al puerto `ConfigManager` e implementarlo en `PydanticConfigAdapter`.

**Opción B (defensiva):** Envolver el seed en try/except y hacer fallback a log/warning:
```python
try:
    resolved_config.set_value("dependency.allowlist_paths", list(AGNO_ALLOWLIST_PREFIXES))
except AttributeError:
    # Log warning: no se pudo seedear allowlist en este adapter
    # El caller debe pre-seedearlo o pasar strict_allowlist=True
    if strict_allowlist:
        raise
```

**Opción C (limpiar arquitectura):** Separar la responsabilidad de allowlist del ConfigManager. El allowlist debería ser un parámetro directo de `ImportlibDependencyAdapter` o de `build_agno_resolver()`, no un efecto secundario de mutar la configuración. Ejemplo:
```python
def build_agno_resolver(allowlist: list[str] | None = None, ...):
    if allowlist is None:
        allowlist = list(AGNO_ALLOWLIST_PREFIXES)
    dep_adapter = ImportlibDependencyAdapter(
        config, logger, errors,
        allowlist=allowlist,  # ← nuevo param
    )
```

---

## ISSUE 2 (BLOQUEANTE): `AGNO_ALLOWLIST_PREFIXES` no incluye `"agno.tools."`

### Archivo
`src/yaml_agno/di/registries.py`, líneas 98-104

### Síntoma
`ValidationError: Module path 'agno.tools.duckduckgo' is not in allowlist`

### Causa raíz
```python
AGNO_ALLOWLIST_PREFIXES: Final[list[str]] = [
    "agno.models.",
    "agno.db.",
    "agno.workflow.",
    "agno.team.",
    "agno.agent",
]
```

Falta `"agno.tools."`. Sin embargo, **todos los toolkits en `BUILTIN_REGISTRY`** (`registry.py`) usan `agno.tools.*` como module_path:

- `agno.tools.calculator`
- `agno.tools.duckduckgo`
- `agno.tools.file`
- `agno.tools.python`
- `agno.tools.website`
- ... ~130 entries más

Es decir: cualquier toolkit builtin que se intente resolver vía `ToolFactory` → `ToolkitAdapter.build()` → `resolver.resolve_class()` va a crashear porque el allowlist no cubre su module_path.

### Impacto
**Total.** Ningún toolkit builtin puede resolverse con la configuración de allowlist actual. Todo usuario que use builtin tools en YAML recibe `ValidationError`.

### Fix aplicado en el PoC
Pre-seedear el allowlist manualmente con `"agno.tools."` incluido:
```python
InMemoryConfigAdapter(initial_data={
    "dependency": {
        "allowlist_paths": [
            "agno.models.", "agno.tools.", "agno.db.",
            "agno.workflow.", "agno.team.", "agno.agent",
        ],
    },
})
```

### Fix recomendado para release
Agregar `"agno.tools."` a `AGNO_ALLOWLIST_PREFIXES`:
```python
AGNO_ALLOWLIST_PREFIXES: Final[list[str]] = [
    "agno.models.",
    "agno.tools.",       # ← AGREGAR (bloqueante)
    "agno.db.",
    "agno.workflow.",
    "agno.team.",
    "agno.agent",        # ← ver Issue 3
]
```

---

## ISSUE 3 (DEUDA TÉCNICA): `"agno.agent"` sin trailing dot en `AGNO_ALLOWLIST_PREFIXES`

### Archivo
`src/yaml_agno/di/registries.py`, línea 103

### Detalle
```python
"agno.agent",   # sin trailing dot
"agno.models.",  # con trailing dot
"agno.db.",      # con trailing dot
```

`ImportlibDependencyAdapter._is_allowlisted()` (línea 88) usa `startswith()`:
```python
return any(module_path.startswith(prefix) for prefix in self._allowlist)
```

Con `"agno.agent"` (sin dot), el prefijo matchea:
- `agno.agent` ✅ (Agno Agent class en `agno.agent` → bien)
- `agno.agent.Something` ✅ (submódulos → bien)
- `agno.agentic_memory` ✅ (colisión por prefijo → **mal** — no es un módulo Agno)
- `agno.agent_something_else` ✅ (colisión → **mal**)

Con `"agno.agent."` (con dot), solo matchea:
- `agno.agent` ❌ **problema**: el módulo `agno.agent` NO comienza con `"agno.agent."`
- `agno.agent.Something` ✅

### Impacto
Bajo (ninguna colisión real hoy), pero inconsistente con el resto del allowlist y puede causar falsos positivos si Agno agrega submódulos con prefijo `agno.agent*` en el futuro.

### Fix recomendado
```python
"agno.agent.",   # con trailing dot para consistencia
```
Y verificar que el módulo raíz `agno.agent` es alcanzable. Si no lo es porque `startswith("agno.agent.")` no matchea `agno.agent`, usar dos entradas:
```python
"agno.agent",    # para el módulo raíz (sin dot)
"agno.agent.",   # para submódulos (con dot)
```

O cambiar la lógica de `_is_allowlisted` para que un prefix sin dot matchee también `module_path == prefix` además de `startswith(prefix + ".")`.

---

## ISSUE 4 (DEUDA TÉCNICA): Acoplamiento arquitectónico en `build_agno_resolver()`

### Archivo
`src/yaml_agno/di/agno_resolver.py`, líneas 248-281

### Detalle
`build_agno_resolver()` mezcla 3 responsabilidades en una función:

1. **Gestión de configuración** — lee/escribe secciones en `ConfigManager`
2. **Seeding de defaults** — si falta `dependency.allowlist_paths`, lo siembra como efecto secundario sobre el config
3. **Construcción de dependencias** — ensambla logger, errors, observability, y el adapter de dependencias

El seeding (responsabilidad 2) está en el lugar equivocado. El allowlist es un concepto de `ImportlibDependencyAdapter`, no de `ConfigManager`. Que el caller tenga que mutar su config manager para que funcione el adapter es un leak de abstracción.

El flujo actual:

```
caller → build_agno_resolver(config=None)
  → PydanticConfigAdapter()     (creación implícita)
  → config.set_value(...)        (mutación del config, CRASHEA)
  → ImportlibDependencyAdapter(config, ...)  (lee allowlist del config)
```

Lo correcto:

```
caller → build_agno_resolver(allowlist=AGNO_ALLOWLIST_PREFIXES)
  → ImportlibDependencyAdapter(..., allowlist=allowlist)
```

### Impacto
Medio. No es un crash inmediato, pero:
- Obliga al caller a conocer el protocolo interno de seeding
- Hace que `PydanticConfigAdapter` (el adapter default) sea incompatible con el camino default
- Viola el principio de segregación de interfaces: el adapter de dependencias no debería mutar el objeto de configuración

### Fix recomendado
Ver **Opción C** del Issue 1: pasar `allowlist` como parámetro directo a `build_agno_resolver()` y a `ImportlibDependencyAdapter`.

---

## ISSUE 5 (DEUDA TÉCNICA): Default implícito `PydanticConfigAdapter()` incompatible con seed

### Archivo
`src/yaml_agno/di/agno_resolver.py`, línea 253

### Detalle
```python
resolved_config = config if config is not None else PydanticConfigAdapter()
```

El default de `config` es `None`. Cuando es `None`, se construye `PydanticConfigAdapter()` que:
1. Busca YAML + `CENF_` prefijos en env (innecesario para yaml-agno standalone)
2. NO implementa `set_value()` (choca con Issue 1)
3. Es el adaptador más pesado de core-cenf (lee archivos, mergea jerarquías)

Si el objetivo de `build_agno_resolver(config=None)` es "usar defaults sensatos sin configuración externa", el adapter debería ser `InMemoryConfigAdapter()` que:
- Comienza vacío → permite seeding
- Soporta `set_value()` → seed funciona
- No requiere YAML ni env vars → standalone

### Impacto
Bajo (se manifiesta como Issue 1 cuando no hay pre-seeding), pero revela que el default no es el correcto para el caso de uso natural.

### Fix recomendado
```python
resolved_config = config if config is not None else InMemoryConfigAdapter()
```

Esto hace que:
- `build_agno_resolver()` sin argumentos FUNCIONE (Issue 1 desaparece)
- El seeding de allowlist fluya correctamente
- No dependa de archivos YAML ni env vars para operar

---

## Resumen de fixes por prioridad

| # | Prioridad | Archivo | Fix |
|---|---|---|---|
| 2 | 🔴 **BLOQUEANTE** | `registries.py:98-104` | Agregar `"agno.tools."` a `AGNO_ALLOWLIST_PREFIXES` |
| 1 | 🔴 **BLOQUEANTE** | `agno_resolver.py:269` | Hacer que `set_value()` no crashee cuando el adapter no lo soporta |
| 5 | 🟡 Deuda | `agno_resolver.py:253` | Cambiar default de `PydanticConfigAdapter()` a `InMemoryConfigAdapter()` |
| 4 | 🟡 Deuda | `agno_resolver.py:258-272` | Separar allowlist en parámetro directo, no mutación de config |
| 3 | ⚪ Consistencia | `registries.py:103` | Normalizar `"agno.agent"` → `"agno.agent."` |

---

## Test de regresión sugerido

```python
# Debe funcionar SIN argumentos (standalone mode)
resolver = build_agno_resolver()
model = resolver.resolve_model("openrouter:deepseek/deepseek-v4-flash")
assert model is not None

# Debe poder resolver builtin tools
cls = resolver.resolve_class("agno.tools.duckduckgo", "DuckDuckGoTools")
assert cls is not None

# Debe respetar allowlist custom (strict mode)
resolver2 = build_agno_resolver(adapter=ImportlibDependencyAdapter(allowlist=["agno.models."], strict=True))
with pytest.raises(ValidationError):
    resolver2.resolve_class("agno.tools.duckduckgo", "DuckDuckGoTools")
```
