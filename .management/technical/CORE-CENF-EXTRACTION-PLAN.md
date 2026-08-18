# CORE-CENF-EXTRACTION-PLAN — Extracción de interface mínima (G-02)

- **Fecha**: 2026-08-09
- **Autor**: Code Architect (development-team, CENF)
- **Contexto**: Correcciones Gonzalo (2026-08-09). Objetivo G-02: evaluar si yaml-agno puede
  desacoplarse de `core-cenf-py` con una interface mínima (Protocols), respetando la golden
  rule (depender de Protocolos, inyectar adapters) y la ruta de revenue (yaml-agno = librería
  core; ArcaMCP/Agente Instalador = productos).
- **Dependencia actual**: `core-cenf-py @ git+https://github.com/CENFARG/core-cenf-py.git@v0.1.2`
  (yaml-agno `pyproject.toml:26`; el tag v0.1.2 es el que tiene el nombre de distribución
  correcto `core-cenf-py`).

---

## 1. Consumo REAL de core-cenf en yaml-agno (evidencia verificada)

**6 archivos** importan `core_infrastructure` (git grep):

| Archivo | Import | Símbolo |
|---|---|---|
| `src/yaml_agno/di/agno_resolver.py:22` | `core_infrastructure.common.errors` | `ValidationError` |
| `src/yaml_agno/di/agno_resolver.py:23` | `core_infrastructure.config.ports` | `ConfigManager` |
| `src/yaml_agno/di/agno_resolver.py:24-27` | `core_infrastructure.dependency` | `DependencyManager` |
| `src/yaml_agno/di/agno_resolver.py:28` | `core_infrastructure.errors.adapters` | `ClassificationAdapter` ⚠️ adapter directo |
| `src/yaml_agno/di/agno_resolver.py:29` | `core_infrastructure.errors.ports` | `ErrorHandlingManager` |
| `src/yaml_agno/di/agno_resolver.py:30` | `core_infrastructure.logger.adapters` | `StructlogAdapter` ⚠️ adapter directo |
| `src/yaml_agno/di/agno_resolver.py:31` | `core_infrastructure.logger.ports` | `LoggerManager` |
| `src/yaml_agno/di/agno_resolver.py:32` | `core_infrastructure.observability.adapters` | `NoopObservabilityAdapter` ⚠️ adapter directo |
| `src/yaml_agno/di/agno_resolver.py:33` | `core_infrastructure.observability.ports` | `ObservabilityManager` |
| `src/yaml_agno/di/agno_resolver.py:255` | `core_infrastructure.config.adapters.in_memory_config_adapter` | `InMemoryConfigAdapter` ⚠️ adapter directo (lazy) |
| `src/yaml_agno/di/secret_resolver.py:27` | `core_infrastructure.common.errors` | `ValidationError` |
| `src/yaml_agno/di/secret_resolver.py:28` | `core_infrastructure.config.ports` | `ConfigManager` |
| `src/yaml_agno/di/secret_resolver.py:82` | `core_infrastructure.config.adapters.in_memory_config_adapter` | `InMemoryConfigAdapter` ⚠️ adapter directo (lazy) |
| `src/yaml_agno/di/value_resolver.py:18` | `core_infrastructure.config.ports` | `ConfigManager` |
| `src/yaml_agno/workflows/retry_policy.py:18` | `core_infrastructure.errors` | `ErrorClassification, ErrorHandlingManager` |
| `src/yaml_agno/workflows/step_executor.py:17` | `core_infrastructure.errors` | `ErrorHandlingManager` |
| `src/yaml_agno/db/repositories/agent_config_repository.py:25` | `core_infrastructure.database` | `DatabaseManager` (lazy, TYPE_CHECKING) |

### Managers consumidos: 5 + 1 helper

1. **ConfigManager** (`config.ports`) — agno_resolver, secret_resolver, value_resolver
2. **ErrorHandlingManager** (`errors.ports` / `errors`) — agno_resolver, retry_policy,
   step_executor (+ `ErrorClassification` + `ClassificationAdapter`)
3. **LoggerManager** (`logger.ports`) — agno_resolver (+ `StructlogAdapter`)
4. **ObservabilityManager** (`observability.ports`) — agno_resolver (+ `NoopObservabilityAdapter`)
5. **DatabaseManager** (`database`) — agent_config_repository (lazy)
6. **DependencyManager** (`dependency`) — agno_resolver
7. `ValidationError` (`common.errors`) — helper de errores

**Concentración**: el 90% de los imports vive en `di/agno_resolver.py` (10 de 17 líneas de
import + 4 de los 4 adapters directos). El resto son usos de ports en archivos de negocio.

## 2. ¿Golden rule cumplida?

- **core-cenf-py YA expone ports/Protocols**: 23 módulos con `ports.py` (config, errors,
  logger, observability, database, dependency, secrets, cache, state_machine, taskqueue, etc.)
  y 78 archivos de adapters. Verificado: `src/core_infrastructure/<modulo>/ports.py` para
  los 23 managers (AGENTS.md core-cenf: "Every manager has exactly one Protocol... Your code
  depends on the Protocol. The adapter is injected at startup").
- **yaml-agno MEZCLA**: importa ports (correcto) pero **instancia adapters directamente** en
  el wiring (`ClassificationAdapter`, `StructlogAdapter`, `NoopObservabilityAdapter`,
  `InMemoryConfigAdapter` — todos en `di/agno_resolver.py`). 
- **Matiz importante**: instanciar adapters en el **resolver/composition root** es
  precisamente lo que la golden rule permite ("the adapter is injected at startup"). La
  violación sería importar adapters en **lógica de negocio** — eso NO ocurre (retry_policy y
  step_executor usan `ErrorHandlingManager` de `errors`/`errors.ports`, no de `errors.adapters`).
- **Conclusión parcial**: la golden rule está razonablemente respetada hoy. La deuda real es
  de **distribución**: `core-cenf-py` es un repo privado (git+https con token) — yaml-agno no
  puede publicarse en PyPI público mientras dependa de él.

## 3. ¿Qué implica extraer una interface mínima?

### Escenario A — Interface mínima propia (Protocols CENF en yaml-agno)
Definir `yaml_agno/ports/` con Protocols propios (ConfigPort, ErrorHandlingPort,
LoggerPort, ObservabilityPort, DatabasePort, DependencyPort) + adapters internos que
deleguen a core-cenf si está instalado (o implementen lo mínimo necesario).

- **Tamaño estimado**:
  - 6 Protocols + errores compartidos: **~250-350 líneas** (firmas de los métodos que
    yaml-agno realmente llama — no la superficie completa de core-cenf).
  - 2-4 adapters delegantes (los únicos instanciados hoy): **~150-250 líneas**.
  - Re-wiring en `di/agno_resolver.py` + `secret_resolver.py` + `retry_policy.py` +
    `step_executor.py` + `value_resolver.py` + `agent_config_repository.py`: **~100 líneas
    tocadas** (mecánico).
  - `pyproject.toml`: mover `core-cenf-py` a extra opcional (`[project.optional-dependencies]`)
    → **~5 líneas**.
- **Esfuerzo**: **1-2 días-agente** (incluye tests de los Protocols y adapters delegantes).
- **Riesgos**:
  - **API drift**: si core-cenf cambia firmas, los adapters delegantes rompen (mitigable
    con tests de contrato).
  - **Doble mantenimiento**: la interface propia duplica (parcialmente) los ports de
    core-cenf — hay que decidir quién es el dueño.
  - **py.typed**: core-cenf NO publica `py.typed` (verificado: no existe el archivo); los
    adapters delegantes propios sí lo harían → mejora el typing estricto de yaml-agno
    (hoy el override `ignore_missing_imports` en pyproject:115-123 lo enmascara).
- **Beneficio real**: yaml-agno deja de depender del repo privado → publicable en PyPI,
    instalable sin `GIT_AUTH_TOKEN` (hoy el CI pide token, ver DECISIONES §3).

### Escenario B — Mantener core-cenf como dependencia (status quo)
- Cero trabajo. La golden rule ya se respeta en el código de negocio; los 4 adapters en el
  resolver son el patrón "composition root" aceptado.
- Limitación: yaml-agno queda atado al repo privado (no publicable pública, CI requiere
  token, instalación de terceros imposible).

## 4. Recomendación GO / NO-GO

**NO-GO (por ahora) para el Escenario A, salvo que el objetivo sea publicación pública.**

Razones:
1. **La dependencia está acotada**: 6 archivos, 5 managers, 17 líneas de import. No hay
   acoplamiento estructural; es un acoplamiento de dependencia pip.
2. **core-cenf ya ofrece los ports**: la "interface mínima" en realidad ya existe y
   yaml-agno la consume. Extraer Protocols propios duplicaría superficie sin ganar
   desacoplamiento (solo ganaría independencia de distribución).
3. **La ruta de revenue (G-02) es "interface mínima para desacoplar"** — pero el desacople
   que importa para el negocio es poder **distribuir** yaml-agno (librería core del stack).
   Eso se resuelve más barato de otra forma (ver abajo).
4. **El costo de mantener dos interfaces** (core-cenf ports + yaml-agno ports) supera el
   beneficio a la escala actual (3 personas + agentes).

**Alternativa recomendada (GO parcial, más barato)**:
- **Mover `core-cenf-py` a extra opcional** en `pyproject.toml` y degradar su uso a
  "si está instalado, se usa; si no, yaml-agno corre con adapters in-memory propios"
  (los mismos que core-cenf expone: InMemoryConfigAdapter, NoopObservabilityAdapter,
  etc.). Esto es el **80% del beneficio con ~20% del esfuerzo** (~0,5 día-agente):
  - yaml-agno publicable en PyPI (core-cenf queda como extra `[cenf]`).
  - CI sin token para la build base; token solo si se activa el extra.
  - Sin duplicar ports: los usos en código de negocio siguen contra los Protocolos.
- **Cuándo sí hacer el Escenario A**: cuando yaml-agno se publique y haya usuarios
  externos, o cuando core-cenf madure lo suficiente para publicarse público. Re-evaluar
  en la release 1.0.

## 5. Pasos concretos (si se aprueba la alternativa)

1. **Auditar qué métodos usa yaml-agno de cada manager** (grep de `config.get_`,
   `error.classify`, `logger.`, etc.) → lista de superficie mínima (ya 80% identificada
   en §1).
2. **`pyproject.toml`**: `core-cenf-py` → `[project.optional-dependencies].cenf`; ajustar
   comentario de la línea 23-26; mantener `allow-direct-references` solo si el extra queda
   como direct reference.
3. **`di/agno_resolver.py`**: `try: import core_infrastructure... except ImportError: usar
   fallback interno` (patrón que core-cenf ya usa para sus adapters opcionales, ver
   AGENTS.md core-cenf "Import Safety & Lazy Loading").
4. **Tests**: un test unit por fallback (config/logger/errors/observability/db/dependency)
   sin core-cenf instalado.
5. **CI**: dos jobs (base sin extra, full con extra).
6. **Riesgo residual**: `agent_config_repository.py:25` usa `DatabaseManager` lazy — si el
   extra no está, el repo de configs falla con error claro (documentar el requisito de
   Postgres/SQLite vía core-cenf o adaptador propio delgado).
