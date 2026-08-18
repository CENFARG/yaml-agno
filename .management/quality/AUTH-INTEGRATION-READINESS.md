# AUTH-INTEGRATION-READINESS — Readiness de yaml-agno para Keycloak/Casbin

- **Fecha**: 2026-08-11
- **Auditor**: code-quality-analyst (quality-team, CENF)
- **Alcance**: `C:\Dropbox\DOC.RECA\06-Software\yaml-agno` (94 archivos .py, 8.818 LOC en `src/yaml_agno`)
- **Propósito**: auditar si yaml-agno puede integrar Keycloak (Identity) + Casbin (Authorization) como
  infraestructura transversal, según la propuesta ChatGPT (chatgpt-comparar-repositorios-open-source.md)
  y el plan core-cenf (CORE-CENF-EXTRACTION-PLAN.md).
- **Dominio de calidad**: internal (ISO/IEC 25010, CISQ) — no aplica dominio IHO en este repo.

---

## 1. EXECUTIVE SUMMARY

| # | Pregunta de auditoría | Veredicto | Confianza |
|---|---|---|---|
| 1 | ¿DependencyManager soporta Identity/Authorization/SandboxProvider? | **GO** — extensible estructuralmente (registries + escape hatch) | REAL |
| 2 | ¿Existen ports aprovechables en core-cenf-py? | **GO PARCIAL** — `auth` (AuthManager) y `permission` (PermissionManager + CasbinPermissionAdapter) YA EXISTEN; NO hay TenantPort/SandboxPort/AuditPort | REAL |
| 3 | ¿Acoplamiento a la ausencia de Keycloak/Casbin? | **GO** — cero referencias, acoplamiento solo al contrato `request.state` de Agno | REAL |
| 4 | ¿TenantResolver (87 líneas) sirve como base de ExecutionContext? | **WATCH** — base de parsing correcta, pero NO es un contexto; falta agregado ExecutionContext nuevo | REAL |
| 5 | ¿SPEC_19 implementado vs rehacer? | **~40% implementado** — lo JWT-específico se rehace; lo RBAC/scope es provider-agnóstico y reutilizable | REAL |
| 6 | ¿Soporta meter auth externa sin refactor mayor? | **GO** — las costuras ya tienen la forma correcta (ports/adapter/DI) | REAL |
| 7 | ¿Qué impide integrar Keycloak+Casbin HOY? | **5 bloqueantes** — ver §4; el crítico es un **no-op silencioso de config** | REAL |

**Insight clave**: yaml-agno NO necesita un refactor mayor para recibir auth externa — la arquitectura
YAML → Pydantic → Factory → Agno con DI en composition root es exactamente la forma que la propuesta
ChatGPT pide. Pero hay dos verdades incómodas: (a) **SPEC_19 (JWT/RBAC) es Semilla/Draft — el núcleo
(ScopeEnforcer, EndpointRegistry, RBACManager, AuditLogger, build_jwt_middleware) NO está implementado**;
(b) **core-cenf-py ya tiene 2 de los 5 ports propuestos (AuthManager ≈ IdentityPort, PermissionManager ≈
AuthorizationPort con adapter Casbin planificado) y yaml-agno NO los consume**. El costo real no es
"meter Keycloak" sino: reconciliar la versión de agno (2.6.22 pinneada vs 2.8.3 instalada), implementar el
núcleo de SPEC_19, y decidir el modelo de autorización (claims-based vs Casbin vs híbrido).

---

## 2. RESPUESTAS DETALLADAS POR PREGUNTA

### 2.1 ¿DependencyManager soporta extenderlo con Identity/Authorization/SandboxProvider?

**GO — REAL (verificado en código).**

`AgnoResolver` (`src/yaml_agno/di/agno_resolver.py`) es una fachada de dominio sobre el
`DependencyManager` de core-cenf con un patrón de **registros tipados como DATA**:
`MODEL_REGISTRY` / `STORAGE_REGISTRY` / `WORKFLOW_REGISTRY` (`di/registries.py`) + método de escape
`resolve_class(module_path, class_name)` (agno_resolver.py:183-198). El motor de carga (importlib +
allowlist + cache) se delega a `ImportlibDependencyAdapter` — yaml-agno NO reimplementa.

Extender con `IdentityProvider` / `AuthorizationProvider` / `SandboxProvider` es **mecánico**:
añadir un registry dict nuevo + un método de dominio (`resolve_identity("keycloak")`), siguiendo el
mismo patrón que `resolve_model` (agno_resolver.py:95-127). Restricción: el allowlist sembrado es
`agno.*` exclusivamente (registries.py:98-106); los adapters de core-cenf/Keycloak/Casbin no caen bajo
esos prefijos — se resolverían como **instanciación directa en composition root** (patrón ya usado:
`build_agno_resolver` instancia `StructlogAdapter`, `NoopObservabilityAdapter`, `ClassificationAdapter`,
`InMemoryConfigAdapter` en agno_resolver.py:255-285, que es precisamente lo que la golden rule permite).

**Matiz**: la extensión "natural" NO es añadir providers al AgnoResolver sino **consumir los managers que
core-cenf ya expone** (AuthManager, PermissionManager — ver 2.2). El AgnoResolver resuelve clases de
**dominio Agno**; identity/authorization son **infraestructura transversal** y el punto de inyección
correcto es el wiring del AgentOS (AgentOSFactory / middleware), no el resolver de modelos.

### 2.2 ¿Ya hay ports/interfaces en core-cenf-py que puedan adaptarse?

**GO PARCIAL — REAL (verificado en el repo core-cenf v0.1.2 clonado local).**

core-cenf-py tiene 23 módulos con `ports.py`. Mapeo contra los 5 ports propuestos por ChatGPT:

| Port propuesto | Port REAL en core-cenf | Evidencia | ¿Consumido por yaml-agno? |
|---|---|---|---|
| IdentityPort | **`auth` — `AuthManager` Protocol** (`validate_token` async, `get_claims`, `refresh_jwks`, `validate_scopes`; setea contextvars `tenant_id`/`principal_id`; adapters `JwtAuthAdapter` HS256, `StaticAuthAdapter`) | `core_infrastructure/auth/ports.py:25-105` | ❌ NO |
| AuthorizationPort | **`permission` — `PermissionManager` Protocol** (`check_permission(tenant_id, principal_id, principal_type, resource_type, resource_id, action, context)` → `PermissionDecision`; **basado en pycasbin con RBAC domains**; adapters `CasbinPermissionAdapter`, `InMemoryPermissionAdapter`) | `core_infrastructure/permission/ports.py:76-215` | ❌ NO |
| TenantPort | ✖ No hay módulo dedicado — tenancy vive en `TokenClaims.tenant_id` + contextvar + filtros de `database` | — | — |
| SandboxPort | ✖ No existe | — | — |
| AuditPort | ✖ No existe (parcial: `bus_event`/`observability` como transporte, sin contrato de auditoría de seguridad) | — | — |

**Implicación estratégica**: la propuesta ChatGPT pide "yaml-agno → Ports → core-cenf-py" — la mitad de
ese contrato **ya existe en core-cenf y no se usa**. El camino más barato NO es definir ports nuevos en
yaml-agno sino inyectar `AuthManager`/`PermissionManager` (Protocols ya publicados) en el wiring del
AgentOS. Lo que falta en core-cenf: un adapter Keycloak (JWKS/RS256/OIDC) para `AuthManager` (hoy solo
HS256 + static) y la superficie Tenant/Sandbox/Audit.

En yaml-agno, el único port propio es `AgentOSFactoryPort` (`ports/agentos_ports.py:21-40`, contrato
`build(config) -> AgentOS`). No hay ports de seguridad propios.

### 2.3 ¿Qué tan acoplado está el código a la ausencia de Keycloak/Casbin?

**GO — acoplamiento bajo, REAL.**

- `rg keycloak|casbin|openfga|cerbos` en `src/` → **cero coincidencias**. El código no sabe que Keycloak
  no existe (ni que debería existir).
- El acoplamiento real es al **contrato de Agno**, no a un IdP: `TenantContextMiddleware`
  (`api/middleware/tenant_context.py`) lee `request.state.tenant_claim` (claim JWT `tnt`) y
  `request.state.user_sub` (claim `sub`) — campos que el JWTMiddleware de Agno (o cualquier middleware
  OIDC que los poble) debe setear. `AuthorizationAdapter` (`agentos/authorization_adapter.py:34-86`)
  traduce `AuthorizationSettings` → `AuthorizationConfig` nativo de Agno.
- **Brecha**: no hay plug point en el nivel de aplicación para un IdP externo más allá del JWTMiddleware
  de Agno. Insertar Keycloak requiere implementar `build_jwt_middleware` (spec-only, SPEC_19 §1.3) o un
  middleware propio que valide contra el JWKS de Keycloak y poble `request.state` con el mismo contrato.

### 2.4 ¿TenantContext (73 líneas) sirve como base para ExecutionContext?

**WATCH — es base de parsing, NO es un contexto. REAL.**

`tenant/resolver.py` (medido: **87 líneas**, no 73) contiene `TenantResolver` — un **parser puro** del
composite `{tenant_id}:{principal_id}`: `extract_tenant()` y `extract_principal()` (particiona en el
primer `:` para preservar principals con colones). Cumple la "single-seam rule" con `resolve_user_id()`
(memory/user_identity.py): resolver BUILDS, TenantResolver CONSUMES. Tests presentes y sólidos
(`tests/unit/tenant/test_resolver.py` incluye round-trip con `resolve_user_id`).

La propuesta ChatGPT pide un `ExecutionContext` con `tenant_id, principal_id, user_id, roles,
permissions, agent_id, session_id, request_id`. Eso NO existe: TenantResolver no conoce roles,
permissions, ni metadata de request. **Conclusión**: se reutiliza TenantResolver como componente de
parsing del nuevo agregado, pero `ExecutionContext` es una abstracción NUEVA que debería ensamblar:
`TenantResolver` (parse) + claims del IdentityProvider (roles/scopes) + metadata del request
(request_id/session_id) + agent_id. Es el agregado correcto para threadear en Authorization y Sandbox.

### 2.5 SPEC_19: ¿qué está implementado y qué habría que rehacer con Keycloak?

**~40% implementado. REAL (grep + lectura de código).**

SPEC_19 (`specs/SPEC_19_SECURITY_AUTH_API_SURFACE.md`, Maturity "Semilla", Status Draft) describe
JWT+RBAC+isolation+catálogo de endpoints. **El directorio `src/yaml_agno/security/` que la spec
referencia NO EXISTE** (grep global de `JWTMiddleware|ScopeEnforcer|EndpointRegistry|RBACManager|
BasicAuthMiddleware|AuditLogger` en `src/` → cero coincidencias).

| Componente SPEC_19 | Estado | Con Keycloak |
|---|---|---|
| `AuthorizationSettings` en `AgentOSConfig` (`models/config/agentos_config.py:40-53`) | ✅ Implementado | Se mantiene; el dict `config` pasa a ser opaco al proveedor |
| `AuthorizationAdapter` → `AuthorizationConfig` + `user_isolation=True` (`agentos/authorization_adapter.py`) | ✅ Implementado | **REHACER**: el paso de `basic_auth`/`config` al `AuthorizationConfig` es un **no-op silencioso** (ver §4 R1) |
| `TenantContextMiddleware` composite user_id (`api/middleware/tenant_context.py`) | ✅ Implementado | Se mantiene; **requiere mapper de claims** para que Keycloak emita `tnt` (R4) |
| `resolve_user_id()` (memory/user_identity.py) + `TenantResolver` (tenant/resolver.py) | ✅ Implementado | Se mantienen intactos (provider-agnóstico) |
| Validator CORS wildcard bajo RBAC (`agentos_config.py:206-223`) | ✅ Implementado | Se mantiene |
| `build_jwt_middleware` (SPEC_19 §1.3) — wrapper del JWTMiddleware de Agno | ❌ Spec-only | **REHACER como adapter OIDC/Keycloak** (discovery URL + JWKS del realm + mapeo de claims) |
| `ScopeEnforcer` (§2.3) — enforce de scopes por ruta | ❌ Spec-only | Se implementa tal cual (provider-agnóstico) |
| `EndpointRegistry` (§6.3) — catálogo ruta→scope | ❌ Spec-only | Se implementa tal cual (provider-agnóstico) |
| `RBACManager` + `ROLE_SCOPES` (§3.2) — rol→scopes | ❌ Spec-only | **REHACER parcial**: mapear realm/client roles de Keycloak a scopes, merge con custom roles YAML |
| `BasicAuthMiddleware` (§1.2, dev-only) | ❌ Spec-only | Se implementa tal cual (dev-only) |
| `AuditLogger` / `AuditEvent` (§7.1) | ❌ Spec-only | Implementar; idealmente sobre un futuro `AuditPort` de core-cenf |
| CORS configurator + SecurityHeaders (§5) | ❌ Spec-only | Implementar (provider-agnóstico) |

**Regla**: lo que es JWT/IdP-específico se rehace; lo que es RBAC/scope/catálogo es reutilizable tal cual.

### 2.6 ¿El código soporta meter una capa de auth externa sin refactor mayor?

**GO — REAL.**

Evidencia de calidad estructural que sostiene el veredicto:
- **Patrón ports/adapter con DI en composition root** en toda la base (golden rule razonablemente
  respetada; veredicto CORE-CENF-EXTRACTION-PLAN §2: la violación sería importar adapters en lógica de
  negocio — no ocurre; los 4 adapters instanciados viven en `di/agno_resolver.py`, el composition root).
- **mypy --strict limpio en 94 archivos** (CODE-QUALITY_REPORT.md: "Success: no issues found in 94
  source files").
- **TDD con evidencia RED**: `tests/unit/tenant/test_resolver.py`, `tests/unit/memory/test_user_identity.py`,
  `tests/unit/api/middleware/test_tenant_context.py` (incluye anti-spoofing: JWT autenticado sin claim
  `tnt` → header `X-Tenant-Id` NO se confía → 401), `tests/unit/factories/test_agentos_factory.py`
  (wiring authorization via adapter), `tests/unit/domain/test_agentos_config.py` (validators RBAC/CORS).
- **Rework rate 8.9%** (git numstat, 2026-05-01→2026-08-11) — por debajo del baseline ~15% (SouthMap).
- El seam de integración ya existe: `AgentOSFactory._build_authorization_config` (agentos_factory.py:485-524)
  inyecta `AuthorizationAdapter` opcional; la autenticación entra por el mismo canal que cualquier
  middleware de Agno (request.state contract).

### 2.7 ¿Qué impide integrar Keycloak+Casbin HOY?

Ver §4 (Risks). Resumen de bloqueantes:
1. **R1 (CRITICAL)**: `AuthorizationConfig` ignora silenciosamente `basic_auth`/`config` en agno 2.8.3
   (verificado por ejecución) → cualquier config de Keycloak puesta en `authorization.config` no tendría
   efecto.
2. **R2 (HIGH)**: drift de versión agno (pin `2.6.22` vs instalado `2.8.3`) → APIs de JWT/Authorization
   pueden diferir.
3. **R3 (HIGH)**: núcleo de SPEC_19 (enforcement) no implementado → hay que implementarlo antes de
   mapear Keycloak.
4. **R4 (HIGH)**: Keycloak no emite claim `tnt` por defecto → el anti-spoofing de TenantContextMiddleware
   fail-fastea 401 para JWTs sin `tnt`; se requiere token mapper.
5. **R5 (MEDIUM)**: no existen SandboxPort ni AuditPort (ni en core-cenf ni en yaml-agno).

---

## 3. DECISIONS REQUIRED

| # | Decisión | Opciones | Trade-offs | Owner | Deadline |
|---|----------|----------|------------|-------|----------|
| D1 | **Reconciliar versión de agno** antes de escribir cualquier adapter de auth | (a) Upgradear pin a 2.8.3 (la instalada, JWT surface verificada) — (b) fijar env a 2.6.22 (la que la SPEC verificó) | (a) exige re-verificar AuthorizationConfig/JWTMiddleware y los 6 fails P2.9 de MCP; (b) congela features nuevas | Orchestrator + dev team | 2026-08-14 |
| D2 | **Modelo de autorización** para el MVP | (a) Claims-based (scopes en JWT, diseño SPEC_19 actual) — (b) Policy-based (Casbin vía core-cenf PermissionManager, RBAC domains) — (c) **Híbrido**: Keycloak identity + scope enforcement claims-based en API + Casbin para decisiones resource-level | (a) simple, sin servidor extra; (b) alineado a propuesta ChatGPT, tenant-aware, pero +1 servicio; (c) lo mejor de ambos, más superficie | Strategic Advisor | 2026-08-18 |
| D3 | **Dónde viven los ports de seguridad** | (a) yaml-agno consume `AuthManager`/`PermissionManager` de core-cenf (ya existen, golden rule) + adapter Keycloak nuevo — (b) yaml-agno define `IdentityPort`/`AuthorizationPort` propios y core-cenf los implementa | (a) ~80% del beneficio con ~20% del esfuerzo (mismo argumento que CORE-CENF-EXTRACTION-PLAN §4); (b) desacopla distribución pero duplica superficie | Orchestrator | 2026-08-18 |
| D4 | **Construir `ExecutionContext`** (agregado nuevo: TenantResolver + claims + request metadata) | (a) Ahora, como parte del slice auth — (b) post-MVP | (a) es el vector para threadear auth/sandbox/audit correctamente sin parsear strings (recomendación ChatGPT §final); (b) pospone el problema | Dev team | 2026-08-25 |
| D5 | **Alcance del primer slice Keycloak** | (a) Solo Identity (Keycloak OIDC/JWKS → claims → composite user_id), sin Casbin — (b) Identity + Casbin juntos | (a) entrega valor en ~2-3 días-agente, valida el seam; (b) más completo pero 2 integraciones nuevas de una vez | Orchestrator | 2026-08-20 |

---

## 4. QUALITY RISKS

| Severidad | Riesgo | Evidencia | Mitigación | Early signal |
|-----------|--------|-----------|------------|--------------|
| **CRITICAL** | R1: `AuthorizationConfig` descarta silenciosamente `basic_auth`/`config` — config de seguridad declarativa que no hace nada (con Keycloak, `authorization.config` sería no-op) | Ejecución: `AuthorizationConfig(basic_auth={'u':'p'}, config={'x':1})` → objeto sin esos campos (pydantic v2 extra=ignore); `AuthorizationAdapter.build()` y `_build_authorization_config_legacy` los pasan así | Mapeo explícito de campos (verification_keys, jwks_file, algorithm, audience, admin_scope, user_isolation) + tests de contrato que aserten el contenido del AuthorizationConfig | Cualquier config puesta en `authorization.config` que no se refleje en runtime |
| **HIGH** | R2: Drift de versión agno — pin `agno==2.6.22` (pyproject) vs 2.8.3 instalada en el entorno; SPEC_19 verificada contra 2.6.18 | `import agno; agno.__version__` → 2.8.3; pyproject.toml pin 2.6.22; CODE-QUALITY_REPORT.md P2.9 (6 fails MCP atribuidos a 2.8.3) | D1: reconciliar pin; re-verificar `agno.os.middleware.jwt` y `AuthorizationConfig` en la versión elegida | Fails de tests que mencionan APIs de agno cambiadas |
| **HIGH** | R3: Núcleo SPEC_19 no implementado — ScopeEnforcer/EndpointRegistry/RBACManager/AuditLogger/build_jwt_middleware son diseño, no código | grep `src/` → cero coincidencias; `src/yaml_agno/security/` no existe; Maturity "Semilla" | Planificar implementación del núcleo como prerrequisito del slice Keycloak (D5) | Nuevos endpoints del AgentOS API sin scope enforcement |
| **HIGH** | R4: Keycloak no emite claim `tnt` — sin token mapper, todo request JWT-autenticado sin `tnt` → 401 (fail-fast por diseño anti-spoofing) | `tenant_context.py:142-153`: JWT sin `tenant_claim` y con `user_sub` → `None` → `UserIdentityResolutionError` → 401 | Token mapper de Keycloak (custom claim `tnt` desde realm/organization) documentado en el slice Identity; test de integración con claims reales | Requests 401 con JWT válido |
| **MEDIUM** | R5: Sin SandboxPort ni AuditPort en ninguna capa — el sandboxing y la auditoría de seguridad quedan fuera de contrato | core-cenf: 23 módulos, sin `sandbox` ni `audit`; yaml-agno: sin referencia; SPEC_19 §7.1 AuditLogger spec-only | Definir AuditPort en core-cenf (o consumir bus_event); SandboxPort diferido a slice sandbox | Decisiones de "quién audita auth" sin dueño |
| **MEDIUM** | R6: No existe bloque `security` a nivel agent (authorization.policy / sandbox.profile) en los modelos de config — la propuesta ChatGPT lo asume | grep `security|sandbox|permission|policy` en `models/config/` → cero coincidencias; solo existe `agentos.authorization` a nivel instancia | Documentar que el YAML describe intención solo a nivel AgentOS hoy; decidir si agent-level security es del slice | YAML de agentes con bloques security que Pydantic rechaza (extra=forbid) |
| **LOW** | R7: Sin test de integración contra un IdP real (testcontainer Keycloak) — los tests cubren el seam pero no el flujo end-to-end | tests/unit/... tenant/middleware/factory presentes; sin tests de integración con IdP | Añadir test de integración opt-in con Keycloak testcontainer en el slice Identity | — |

---

## 5. TRACEABILITY ANNEX

| Métrica/Dato | Script/Comando ejecutado | Fuente | Timestamp |
|---|---|---|---|
| 94 archivos .py, 8.818 LOC `src/yaml_agno` | `Get-ChildItem -Recurse -Filter *.py | Measure-Object` + `Get-Content | Measure-Object -Line` | `src/yaml_agno/` | 2026-08-11 |
| 325 commits totales | `git log --oneline | Measure-Object -Line` | repo git yaml-agno | 2026-08-11 |
| ADD=125.660 DEL=11.216 NET=114.444 REWORK=8,9% (desde 2026-05-01) | `git log --numstat --pretty=format:%H|%an --since=2026-05-01` + agregación PowerShell | repo git | 2026-08-11 |
| Commits bulk: 4a05366 (19.875 líneas, 2026-07-27), d1d7218 (4.918, 2026-06-17) | `git log --numstat` agregado por commit | repo git | 2026-08-11 |
| Autores desde 2026-05-01: yaml-agno-spec 324, CENF_ARG 1 | `git log --pretty=format:%an | Group-Object` | repo git | 2026-08-11 |
| `AuthorizationConfig` acepta solo 7 campos (sin basic_auth/config) | `python -c "from agno.os.config import AuthorizationConfig; ..."` (agno 2.8.3 instalada) | entorno local | 2026-08-11 |
| agno instalada = 2.8.3 (pin pyproject = 2.6.22) | `python -c "import agno; print(agno.__version__)"` + lectura pyproject.toml | entorno local + pyproject.toml | 2026-08-11 |
| Cero coincidencias `JWTMiddleware|ScopeEnforcer|EndpointRegistry|RBACManager|BasicAuthMiddleware|AuditLogger` en src | `grep` sobre `src/` | `src/yaml_agno/` | 2026-08-11 |
| Cero coincidencias `keycloak|casbin|openfga|cerbos` en *.py | `grep` sobre repo (include *.py) | repo | 2026-08-11 |
| Cero coincidencias `security|sandbox|permission|policy` en `models/config/` | `grep` | `models/config/` | 2026-08-11 |
| core-cenf: 23 módulos, `auth/ports.py` (AuthManager), `permission/ports.py` (PermissionManager) | `Get-ChildItem core_infrastructure -Recurse -Filter ports.py` + lectura | core-cenf-py v0.1.2 (clon local) | 2026-08-11 |
| tenant/resolver.py = 87 líneas (TenantResolver) | `Read` | `src/yaml_agno/tenant/resolver.py` | 2026-08-11 |
| mypy --strict limpio en 94 files | citado de `CODE-QUALITY_REPORT.md:60` | documento del repo (no re-ejecutado — ver 6C) | 2026-08-11 |

**Ajuste por bulk commits (Regla 3 / CENF)**: las cifras LOC incluyen docs/specs/openspec y al menos un
commit bulk (`4a05366`, 2026-07-27, +19.875/-0, importación masiva — candidato a exclusión). Los 8.818 LOC
de `src/yaml_agno` son la cifra neta de código fuente; usar 8.818 como denominador de productividad.

---

## 6. ANNEXES

### 6A. Detalle de calidad interna (ISO 25010 / CISQ / OWASP)

- **Maintainability (Bien)**: separación YAML→Pydantic→Factory→Agno; DI por constructor; registries
  declarativos como DATA; composición LIFO con `AsyncExitStack` (lifespan.py) — nunca `asyncio.gather`
  (regla inviolable 3).
- **Reliability (Bien)**: fail-fast en `resolve_user_id` (rechaza `None`/bare — bloquea el fall-through
  de Agno al bucket `"default"`); circuit breaker en resilience/; retry policies en workflows/.
- **Security (Mixto)**: anti-spoofing correcto en TenantContextMiddleware (JWT `tnt` authoritative,
  header no confiable si hay JWT activo); `user_isolation=True` forzado en AuthorizationAdapter;
  **pero** R1 (no-op silencioso de config) y R3 (enforcement no implementado) dejan la superficie de
  autorización nominal, no efectiva, hoy.
- **Usability/Compatibility (Bien)**: `extra="forbid"` en configs (errores tempranos de YAML);
  lazy imports para deps opcionales (interfaces.py).
- **Riesgo OWASP relevante**: la clase de bug más peligrosa aquí es "configuración de seguridad que se
  acepta y se ignora" (R1) — equivalente a un fail-open silencioso en el plano declarativo.

### 6B. Detalle de calidad de dominio

No aplica (proyecto sin dominio IHO S-57/S-52/S-58). Sección declarada no aplicable.

### 6C. Datos crudos

- `CODE-QUALITY_REPORT.md` (repo raíz) — remediación FULL del audit previo: mypy --strict 0 errores en
  94 files; P2.9 pendiente (6 fails MCP contra agno 2.8.3, **DATO FALTANTE**: verificación en CI limpio).
- `CORE-CENF-EXTRACTION-PLAN.md` — 6 archivos consumen core-cenf, 5 managers, 17 líneas de import;
  recomendación NO-GO Escenario A, GO parcial (core-cenf a extra opcional).
- `chatgpt-comparar-repositorios-open-source.md` — arquitectura propuesta (Keycloak+Casbin+Docker MVP;
  yaml-agno como "Agno Declarative Adapter" sobre core-cenf "CENF Infrastructure + Security Contracts").
- Números git crudos disponibles en `%TEMP%\ya_numstat.txt` (dump numstat por commit, 2026-08-11).

---

*Generado por code-quality-analyst (quality-team, CENF) — 2026-08-11. Cada métrica tiene script + fuente +
timestamp (§5). Veredicto global: GO para integrar Keycloak+Casbin con 5 decisiones (D1-D5) y la
resolución del riesgo R1 como prerrequisito.*
