# Risk Analysis: Competencia laburen.com + Estrategia Multitenant

> **Fecha**: 2026-08-11 · **Autor**: Risk Team (orquestador + analistas técnico/financiero)
> **Fuentes**: comparativa OSS ChatGPT (2026-08-11, 1713 líneas), EXECUTION-PLAN.md (2026-08-10), SPEC_19_SECURITY_AUTH_API_SURFACE.md (iter4), SPEC_16_HITL_APPROVALS_GUARDRAILS.md (iter4), knowledge_graph_v2.json, investigación web laburen.com (2026-08-11).
> **Estado**: Análisis inicial. Requiere review de @team-strategic y del orquestador principal antes de modificar el Execution Plan.

---

## 1. Veredicto Ejecutivo (respuestas a las 5 preguntas)

| # | Pregunta | Veredicto |
|---|----------|-----------|
| 1 | ¿Cuánto tiempo tenemos sin multitenant? | **6–12 meses de ventana de posicionamiento**, 18–24 de saturación de nicho. Laburen no robará clientes existentes de CENF (consultoría con contexto vs SaaS genérico), pero **gana el top-of-mind** si CENF no existe como opción. El moat real (clientes actuales + método) se erosiona con demoras, no con laburen. |
| 2 | ¿Riesgos de integrar Keycloak+Casbin? | **ALTO**. +6–10 días-agente (35–60% del plan base), SPOF de autenticación, claims mal mapeados = authz silenciosamente rota, duplicación de motores authz con RBACManager propio, curva operativa permanente sin DevOps. La latencia JWKS es casi no-tema si se cachea. |
| 3 | ¿Postergar SPEC_19 vs reemplazar con Keycloak+Casbin? | **FALSA DICOTOMÍA**: SPEC_19 **ya es Keycloak-ready por diseño** (RS256+JWKS, `jwks_file`, `verification_keys`). Diferir tiene costo de rework ≈ 0. Reemplazar hoy tira diseño validado + 73 líneas para comprar SSO/MFA/audit que **ningún cliente pidió**, en el módulo más sensible. Mantener SPEC_19 (JWT nativo Agno), diferir Keycloak/Casbin a Fase 2 como adaptadores detrás de Ports. |
| 4 | ¿Qué cambia en el Execution Plan? | Nada estructural (ruta crítica S0→S2→S4→S6 intacta). **G-04 interno sigue siendo correcto**; el cambio es un **clock duro de 2–4 semanas entre G-04 y T-05 (retainer)** — esa es la verdadera respuesta a laburen. Adelantar mini-SPEC_19 (composite user_id en schema, 1–2 d-a) a Fase 1 como seguro. |
| 5 | ¿Qué riesgo es PEOR? | **Demorar por Keycloak es PEOR en Fase 1** (asimetría ~4:1). El riesgo de "salir sin multitenant" se mitiga **no con Keycloak** (no previene fugas cross-tenant: eso lo hacen los filtros + tests) sino con la disciplina de aislamiento: composite user_id + filtro `tenant_id` + `user_isolation` nativa Agno + **suite de tests cross-tenant como quality gate no negociable** (RT-10/11/12). |

---

## 2. Perfil del Competidor: laburen.com (verificado web 2026-08-11)

| Dimensión | Dato |
|---|---|
| Fundación | 2023, Sebastián Rinaldi (Argentina, bootstrapped) |
| Propuesta | "Empleados de IA" — agentes conectados a WhatsApp, CRM, ERP, billing, sistemas internos; supervisión humana |
| Facturación | u$s300K (2024) → proyección u$s1M (2025) |
| Tracción | 200+ empresas (oct 2025) → **400+ empresas, 3.000+ agentes activos, 50+ partners** (ene 2026) |
| Modelo | SaaS (suscripción por uso) + fees de implementación; Forward Deployed Engineers (FDE/IImC) |
| Producto | "Laburen Agents" (nov 2025): primera plataforma **vibe-code** de LATAM — crear agentes sin código |
| Promesa | 2–8 semanas a primer agente en producción; ROI proyectado antes de invertir |
| Métricas | MRR/ARR, churn, NRR, CAC/LTV/payback; mide "cuánto trabajo real absorben los agentes" |
| Expansión | LATAM activa + internacionalización; presencia mediática alta en AR (TN, iProfesional, SomosPymes, EmpreHouse) |

### Diferenciación CENF vs laburen

| Eje | laburen.com | CENF |
|---|---|---|
| Oferta | Plataforma SaaS + FDE | Consultoría con método propio (#IngenieriaDeContexto) + biblioteca declarativa (yaml-agno) |
| Clientela | PyMEs que escalan sin equipo técnico | Clientes con relación de confianza (Cutignola, Contreras Hnos, Altamore, IESA) |
| Moat | Red de partners + vibe-code | Método + contexto profundo + stack agnóstico (Agno/Hermes/OpenClaw) |
| Riesgo | Se lleva el top-of-mind | Se lleva los *nuevos* clientes que CENF no alcanza a servir |

> **Conclusión**: el solapamiento real es en **implementación**, no en plataforma. CENF no pierde contra laburen por tecnología; pierde por **ausencia en el mercado** si no existe como opción cuando un prospecto busca.

---

## 3. Análisis Detallado por Pregunta

### 3.1 Riesgos de NO salir rápido con multitenant

- **Ventana competitiva**: 6–12 meses para posicionarse, 18–24 para saturación de nicho (estimación analista financiero sobre curva de laburen: $300K→$1M, 200→400+ empresas en 3 meses).
- CENF no compite con laburen por los clientes actuales (consultoría con contexto vs SaaS genérico), pero **cada mes sin producto presentable** = prospectos que eligen a laburen porque "existe y tiene casos".
- La demo G-04 interna (equipo CENF ejecutando tarea real) valida el método, **no** la oferta SaaS. El retainer (T-05) valida la oferta.
- **Riesgo operacional asociado**: presión competitiva puede llevar a recortar el testing de aislamiento (RT-13) — el peor trade posible.

### 3.2 Riesgos de integrar Keycloak+Casbin (Fase 1)

| Riesgo técnico | Detalle |
|---|---|
| Complejidad operacional | Otro servicio + DB propia + upgrades/backups/TLS; HA real en Cloud Run es incómodo (sesiones Infinispan stateful) → single instance frágil o GKE (fuera de Fase 1). 3 personas, cero DevOps. |
| Timeline | **+6–10 días-agente** (35–60%) + 1.5–2.5 d-a de learning curve (realms, clients, mappers, token lifecycle). Fase 1 pasa de 10–17 a 16–27 d-a. El plan ya está al límite con 19 SPECs sin código. |
| Claims mal mapeados | Keycloak DEBE emitir `sub`/`scopes`/`tenant_id`/`principal_id` exactos para el middleware de Agno; un mapper equivocado = validación pasa pero aislamiento no aplica (authz silenciosamente rota). |
| Casbin duplicado | Dos motores authz (Casbin + RBACManager propio de SPEC_19) = dos fuentes de verdad → drift de políticas. Casbin-py tiene madurez menor que casbin (Go); `model.conf` es otro DSL + adapter de persistencia. |
| **Clave** | **Ni Keycloak ni Casbin previenen fugas cross-tenant**: el aislamiento (composite user_id + filtros en repos, Decisión 2.9 NO-RLS) es ortogonal al IdP. Son capas distintas (AuthN/AuthZ vs data isolation). |

### 3.3 Postergar SPEC_19 vs reemplazar con Keycloak+Casbin

- **SPEC_19 (iter4) ya resuelve el 80% del problema con JWT nativo de Agno**: `build_jwt_middleware()` envuelve `agno.os.middleware.jwt.JWTMiddleware` (valida firma, JWKS, exp/aud, extrae scopes/sub) + RBAC propio (ScopeEnforcer, EndpointRegistry, RBACManager con scopes jerárquicos) + aislamiento nativo `user_isolation=True` (`agno.os.middleware.user_scope`: get_scoped_user_id, enforce_owner_on_entity).
- **Es Keycloak-ready por diseño**: un Keycloak emite RS256 y Agno lo valida vía JWKS sin cambiar una línea de yaml-agno. "Diferir" = decisión reversible con costo ≈ 0.
- **Reemplazar hoy** = blast radius máximo en el módulo más sensible, descartando diseño validado + código existente, para comprar features (SSO/SAML/MFA/audit) que **ningún cliente pidió** y que violan la regla inviolable BUILD ON TOP de Agno.
- **Gatillos para adelantar** (condiciones comerciales, no técnicas): primer cliente externo con SSO/SAML/MFA/audit **contractual**, o roles editables por tenant en runtime (→ Casbin detrás del Port RBAC en Fase 2).
- **SPEC_16 HITL/Guardrails**: no cambia con esta decisión. Guardrails = pre-hooks de Agno; PII/Secret masking; tabla `approvals` nativa de Agno. Solo se adelanta si hay clientes externos con datos reales (ya estaba condicionado en el plan).

### 3.4 Impacto en el Execution Plan

| Item del plan | Cambio recomendado |
|---|---|
| G-04 (demo interna) | **Se mantiene como gate**, pero se le agrega **clock duro: 2–4 semanas entre G-04 y T-05** (retainer). Ese clock es la respuesta a laburen. |
| T-05 (retainer antes de datos reales) | Se mantiene; se convierte en el objetivo comercial prioritario post-G-04. RF-10 (insolvencia 55%) se mitiga con el retainer, no con infraestructura. |
| S5 SPEC_19 | De "condicional postergable" a **mini-SPEC_19 en Fase 1** (1–2 d-a): asegurar `tenant_id` composite en schema de DB desde el día 1 (sin JWT completo). El JWT/RBAC completo sigue condicionado a G-04 externo. |
| Ruta crítica | Sin cambios: S0 → S2 (SPEC_03) → S4 → S6. El aislamiento depende de S2 (tenant rows en Postgres), no de Keycloak. |
| Suite de aislamiento | **Nuevo quality gate NO negociable** antes de cualquier cliente externo: tests cross-tenant (2 tenants, misma instancia → 0 fugas), incluido pgvector/RAG (RT-11) y jobs en background (RT-12). |
| Watchlist | Agregar monitoreo competitivo trimestral de laburen (y nuevos entrants) al calendario G-03. |

### 3.5 ¿Qué riesgo es PEOR: demorar por Keycloak, o salir sin multitenant?

**Demorar por Keycloak es PEOR en Fase 1** (asimetría ~4:1):

- **Salir sin multitenant "completo" NO es un riesgo material para uso interno** (3 personas CENF, datos no sensibles entre sí) ni para el gate G-04. El aislamiento básico (composite user_id + filtros + user_isolation nativa) ya está diseñado y es suficiente para el primer cliente si la suite cross-tenant está verde.
- **Salir sin Keycloak es la decisión barata y reversible**: costo de diferir ≈ 0 (SPEC_19 ya es JWKS-ready).
- **Salir sin tests de aislamiento SÍ es catastrófico**: una fuga cross-tenant con cliente externo = destrucción de confianza + incidente legal (Ley 25.326) + reputacional. Ese es el único escenario CRÍTICO aquí.
- **Demorar por Keycloak** multiplica 2–3x el plan base por un beneficio que nadie usa en una demo de 3 personas, y agrava RF-10 (cada semana extra de burn sin revenue).

---

## 4. Matriz de Riesgos Integrada

### 4.1 Riesgos Competitivos / Timing (RF)

| ID | Riesgo | Prob | Impacto | Severidad | Mitigación | Estado |
|---|---|---|---|---|---|---|
| RF-01 | laburen gana top-of-mind del segmento (400+ empresas, vibe-code, media) si CENF no existe como opción | 70% | Alto | **ALTO** | G-04 interno + clock 2–4 sem → T-05 retainer; demo pública del método (facturación/email) | Abierto |
| RF-02 | Cliente de CENF (Cutignola/Contreras/Altamore/IESA) elige laburen por velocidad de implementación | 30% | Alto | **MEDIO** | Profundizar contexto existente; presentar yaml-agno como plataforma propia; retainer primero | Monitoreado |
| RF-03 | Ventana competitiva se cierra antes de lo estimado (proyección $1M 2025, expansión LATAM) | 45% | Alto | **ALTO** | Clock duro G-04→T-05; revisar trimestralmente con watchlist competitiva | Monitoreado |
| RF-04 | Nueva plataforma vibe-code argentina/LATAM (dado el éxito de Laburen Agents, entrants copian el modelo) | 55% | Medio | **MEDIO** | Moat = método + contexto + agnosticismo de runtime; no competir por features no-code | Monitoreado |
| RF-05 | Burn sin revenue mientras competidor acelera (refuerza R-09/R-10 existentes) | 55% | Alto | **ALTO** | Monitoreo tokscale G-03 ($134/mes real ✓); retainer como objetivo prioritario; modelos free | Abierto |
| RF-06 | Presión competitiva induce a recortar suite de aislamiento para acelerar | 50% | Crítico | **CRÍTICO** | Suite cross-tenant = gate NO negociable del primer cliente externo; decisión documentada en DECISIONES.md | Abierto |
| RF-07 | G-04 interno no se convierte en retainer → 18–24 meses de saturación sin presencia comercial | 50% | Alto | **ALTO** | Plan de conversión G-04→T-05 explícito (demo → propuesta → retainer en 2–4 sem) | Abierto |

### 4.2 Riesgos Técnicos — stack Auth/Tenant (RT)

| ID | Riesgo | Prob | Impacto | Severidad | Mitigación | Estado |
|---|---|---|---|---|---|---|
| RT-01 | Keycloak self-managed en Fase 1: toil operativo permanente (DB, upgrades, TLS) con 3 personas sin DevOps | 85% | Alto | **ALTO** | Diferir a Fase 2; si entra: pin + runbook + ~0.5 d-a/sem de mantenimiento | Mitigado (decisión) |
| RT-02 | Slip de timeline: Keycloak agrega 6–10 d-a (35–60%) a plan de 10–17 d-a | 80% | Alto | **ALTO** | Diferir; la comparativa OSS evalúa stacks para escala, no para MVP de 2.5 sem | Mitigado (decisión) |
| RT-03 | SPOF de autenticación: Keycloak caído = sin login/refresh para todos los tenants; HA en Cloud Run frágil | 60% | Crítico | **ALTO** | Diferido desaparece en Fase 1; si se adelanta: instancia Compute + SQL externa + SLO | Mitigado (decisión) |
| RT-04 | Mapper de claims mal configurado: JWT sin `sub`/`scopes`/`tenant` correctos → authz silenciosamente rota | 55% | Crítico | **ALTO** | Golden tests de claims (token real → middleware → assert); solo aplica si Keycloak entra | Monitoreado |
| RT-06 | Casbin + RBACManager duplicados: dos motores authz = drift de políticas | 75% | Medio | **ALTO** | No integrar Casbin en Fase 1; en Fase 2 detrás del Port RBAC con tests de paridad | Mitigado (decisión) |
| RT-08 | Reemplazar SPEC_19 en plena Fase 1: descartar diseño validado para comprar features que el MVP no usa | 60% | Alto | **ALTO** | Mantener SPEC_19 (JWT nativo Agno); Keycloak-ready por diseño; cambiar IdP en vuelo = bug de seguridad | Mitigado (decisión) |
| RT-10 | **Fuga cross-tenant por query sin filtro `tenant_id`** (sin RLS la DB no enforcea nada) | 45% | Crítico | **CRÍTICO** | TenantContext por framework (nunca raw SQL); enforce_owner_on_entity de Agno; suite de tests cross-tenant como quality gate | **Abierto** |
| RT-11 | **Fuga vía pgvector/RAG**: búsqueda semántica sin filtro de tenant — silenciosa, no sale en logs | 40% | Crítico | **CRÍTICO** | `tenant_id` indexado en embeddings + filtro SIEMPRE en retrieval + tests cross-tenant de búsqueda | **Abierto** |
| RT-12 | Jobs en background sin tenant context (scheduler/hitl/guardrails son stubs vacíos): escritura con scope equivocado | 55% | Alto | **ALTO** | Capturar composite al encolar y re-afirmarlo al ejecutar; worker rechaza jobs sin contexto | **Abierto** |
| RT-13 | Presión competitiva recorta testing de aislamiento | 50% | Crítico | **ALTO** | Suite cross-tenant = gate del primer cliente externo; peor trade del roadmap | **Abierto** |
| RT-14 | Contrato de claims de Agno cambia en upgrades → authz rota silenciosamente | 40% | Medio | **MEDIO** | Pin 2.8.7 + tests de contrato JWT + revisar changelog antes de cada bump (G-06) | Monitoreado |
| RT-07 | Casbin-py (si se adoptara): madurez menor que Go, otro DSL, adapter de persistencia | 50% | Medio | **MEDIO** | POC de 1 día antes de comprometerse; evaluar OPA si solo es RBAC declarativo | Diferido |
| RT-09 | Keycloak NO mejora el aislamiento por tenant: compra SSO/MFA/audit que ningún cliente pidió | 70% | Medio | **MEDIO** | Gatillo: requisito contractual del primer cliente externo; sin eso, diferir con consciencia | Diferido |
| RT-05 | Latencia de validación JWKS (si Keycloak entrara) | 30% | Bajo | **BAJO** | Cache JWKS (TTL 300s+) + warm-up + fail-closed con timeout corto | Diferido |

### 4.3 Riesgos Legales / Compliance (integrados por orquestador)

| ID | Riesgo | Prob | Impacto | Severidad | Mitigación | Estado |
|---|---|---|---|---|---|---|
| RL-01 | Fuga cross-tenant con datos de cliente externo = violación Ley 25.326 (datos personales) + daño reputacional | 30% | Catastrófico | **CRÍTICO** | Gate L-03 (0 fugas cross-tenant) antes de conectar cualquier cliente externo; NDA + retainer T-05 antes de procesar datos reales | **Abierto** |
| RL-02 | Licencias: Apache-2.0 de Keycloak/Casbin/Agno/OpenShell/gVisor son compatibles con la estrategia OSS de CENF; Logto (MPL-2.0) descartado por política permisiva | 10% | Bajo | **BAJO** | Stack elegido 100% Apache/MIT; NOTICE/SBOM post-G-04 (ya en checklist STRATEGIC §8.1) | Cerrado |
| RL-03 | Keycloak como dependencia crítica sin SLA documentado ni runbook legal de retención de datos (si se adoptara) | 35% | Medio | **MEDIO** | Solo Fase 2; DPA/retention policy por tenant antes de producción multi-cliente | Diferido |
| RL-04 | Claims de tenant en JWT como fuente de verdad sin validación secundaria → elevación de privilegios entre tenants | 25% | Crítico | **ALTO** | Claims derivados solo de tokens validados (regla Agno); nunca de input cliente; golden tests de elevación | Monitoreado |

### 4.4 Riesgos Operacionales (integrados por orquestador)

| ID | Riesgo | Prob | Impacto | Severidad | Mitigación | Estado |
|---|---|---|---|---|---|---|
| RO-01 | Bus factor 1 (Gonzalo) se agrava con decisión de stack externo (Keycloak) que solo 1 persona domina | 50% | Alto | **ALTO** | Stack nativo Agno (conocido por el equipo) en Fase 1; rotación ownership schema/validación → Pablo/Flor; DECISIONES.md al día (W-07) | Mitigado (decisión) |
| RO-02 | Equipo de 3 personas absorbe operación de identity (Keycloak) sin runbooks → interrupción de servicio en horario no laboral | 40% | Alto | **MEDIO** | Diferir a Fase 2; si entra: runbooks + alerting + on-call definido | Diferido |
| RO-03 | La urgencia competitiva rompe el proceso SDD (spec→design→apply→verify) del plan | 45% | Medio | **MEDIO** | Mini-SPEC_19 sigue SDD con su gate de verificación; la suite cross-tenant NO se salta aunque urja el clock | Monitoreado |
| RO-04 | Demo G-04 se convierte en demo de ventas sin contrato → scope creep del equipo de desarrollo | 40% | Medio | **MEDIO** | T-05 (retainer firmado) antes de trabajo comercial no planificado; Fase 1 interna no se detiene | Monitoreado |

---

## 5. Matriz de Riesgo Agregado (Top por Severidad)

| Severidad | Riesgos |
|---|---|
| **CRÍTICO** | RT-10 (fuga cross-tenant query), RT-11 (fuga pgvector/RAG), RL-01 (Ley 25.326 + reputacional), RF-06 (recorte de suite de aislamiento) |
| **ALTO** | RT-01/02/03/04/06/08/12/13, RF-01/03/05/07, RL-04, RO-01 |
| **MEDIO** | RF-02/04, RT-07/09/14, RL-03, RO-02/03/04 |
| **BAJO** | RT-05, RL-02 |

**Concentración del riesgo**: el 100% de los riesgos CRÍTICOS están en la **disciplina de aislamiento de datos**, NO en el stack de autenticación. Keycloak+Casbin no mitiga ninguno de ellos. La suite de tests cross-tenant y el Gate L-03 los mitigan.

---

## 6. Decisiones y Cambios Propuestos al Execution Plan

1. **NO integrar Keycloak+Casbin en Fase 1** (acuerdo analistas técnico + financiero + orquestador). Stack Fase 1 = JWT nativo Agno (SPEC_19 iter4) + composite user_id + filtros tenant + pgvector filtrado. Costo de diferir ≈ 0.
2. **Adelantar mini-SPEC_19** a Fase 1 (1–2 d-a): asegurar `tenant_id` composite en schema DB desde el día 1 (tables yamlagno_*, embeddings). Sin JWT completo. Protege RT-10/11 desde el primer commit.
3. **Nuevo quality gate (L-03 reforzado)**: suite de tests cross-tenant (2 tenants, misma instancia → 0 fugas) que incluya repos, pgvector/RAG y jobs background. **Gate NO negociable** para el primer cliente externo (T-05). Probablemente el gate más importante del roadmap.
4. **Clock duro G-04 → T-05 de 2–4 semanas**: la demo interna valida el método; el retainer valida la oferta. Ese clock es la respuesta concreta a laburen.
5. **Keycloak/Casbin/OpenShell a Fase 2 como adaptadores** detrás de los Ports ya existentes (AuthPort/AuthorizationPort/SandboxPort), manteniendo el patrón Port/Adapter y la regla BUILD ON TOP. OpenShell: solo como sandbox, NUNCA como frontera multitenant (alpha single-player).
6. **Watchlist competitiva trimestral** (laburen + nuevos entrants vibe-code LATAM) anexada al calendario G-03.
7. **SPEC_16 HITL/Guardrails**: sin cambio de decisión; sigue Fase 2 condicionada a clientes externos con datos reales. Guardrails de PII/secret masking son pre-hooks de Agno (costo bajo de activación cuando se necesite).

---

## 7. Acciones Requeridas

| # | Acción | Dueño | Plazo |
|---|---|---|---|
| A-01 | Review de este análisis por @team-strategic (viabilidad comercial del clock G-04→T-05) | Strategic | 2026-08-14 |
| A-02 | Decisión formal de mini-SPEC_19 en Fase 1 → actualizar EXECUTION-PLAN.md (S5) | Orchestrator + Code Architect | 2026-08-14 |
| A-03 | Definir suite de tests cross-tenant (alcance: repos, pgvector, jobs) como parte de S2/SPEC_03 | Development | En S2 |
| A-04 | Registrar decisiones en DECISIONES.md: "No Keycloak en Fase 1", "Gate L-03 reforzado", "Clock G-04→T-05" | Code Architect | 2026-08-14 |
| A-05 | Agregar watchlist competitiva trimestral al calendario G-03 | Risk Team | Semanal |
| A-06 | Definir plan de conversión demo interna → retainer (demo → propuesta → T-05 en 2–4 sem) | Strategic + Gonzalo | 2026-08-14 |

---

## 8. Fuentes y Provenance

| Fuente | Tipo | Confianza | Estado |
|---|---|---|---|
| chatgpt-comparar-repositorios-open-source.md (2026-08-11, GPT-5-6) | Comparativa OSS | Media (benchmarks de stars/community de snapshot; requiere verificación de código) | Verificado contra SPEC_19 (JWTMiddleware nativo confirmado en spec) |
| EXECUTION-PLAN.md (2026-08-10, Code Architect) | Plan de ejecución verificado contra código | Alta | Vigente; requiere actualización S5 (A-02) |
| SPEC_19 iter4 / SPEC_16 iter4 | Specs de diseño | Alta (verificadas contra agno 2.6.18/2.8.x) | Vigentes |
| laburen.com + 5 fuentes prensa (iProfesional, SomosPymes, EmpreHouse, InnovaciónDigital360, iProUP) | Competitor intelligence | Media-Alta (declaraciones del CEO; métricas 3.000 agentes/400 empresas sin auditoría externa) | Snapshot 2026-08-11; re-verificar trimestralmente |
| knowledge_graph_v2.json | Contexto CENF | Media (migrado, mayormente unverified) | Vigente |

**Evidencia faltante (riesgo abierto)**: no hay verificación independiente de las métricas de laburen (400 empresas, 3.000 agentes, $1M). Los números son declaraciones del CEO en prensa. Impacto en RF-01/03: si las cifras fueran menores, la ventana sería más amplia; si mayores (o partners activos vendiendo), más estrecha. Monitorear.
