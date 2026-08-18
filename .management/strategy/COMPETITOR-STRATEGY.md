# Strategic Decision: Competidor laburen.com + Stack OSS (Keycloak/Casbin/OpenFGA/OpenShell/gVisor) para yaml-agno

> **Fecha**: 2026-08-11
> **Autor**: Strategic Gestion Team (orquestador, ejecución directa — la delegación a sub-agentes falló por límite de profundidad 2; precedente documentado en STRATEGIC_yaml-agno.md §11.6; validación fractal y provenance gate ejecutados por el orquestador con rigor metodológico)
> **Fuentes primarias**: chatgpt-comparar-repositorios-open-source.md (2026-08-11, export ChatGPT gpt-5-6), EXECUTION-PLAN.md (2026-08-10), STRATEGIC_yaml-agno.md (2026-08-08), AGENTS.md yaml-agno, knowledge_graph_v2.json (ruta corregida), websearch 2026-08-11 (laburen.com, keycloak/keycloak, apache/casbin, openfga/openfga, NVIDIA/OpenShell, google/gvisor)
> **Contexto**: Prioridad #1 = time-to-market multitenant. Proyecto yaml-agno en Fase 1 interna CENF (sprint ~1.5-2.5 semanas, 10-17 días-agente, $90-180 tokens, infra Cloud Run + Supabase free tier $0-15/mes, pin Agno 2.8.7).

---

## Veredicto: GO CONDICIONAL

**Integrar Keycloak+Casbin AHORA: NO-GO. Postergar a Fase 2 con decisión de diseño anticipada (BUY, no MAKE) + spike de de-risking OIDC en Fase 1.**

Razón en una línea: integrar 2 servicios operados (Keycloak JVM + Casbin) hoy duplicaría el timeline de Fase 1 (~1.5-2.5 semanas → +2-4 semanas) sin un cliente externo que lo justifique, y la decisión estratégica correcta no es "auth propia después" sino "adoptar OSS maduro después" — con el contrato Ports/Adapters definido desde ahora para no pagar retrabajo.

---

## Viabilidad

### PMF (yaml-agno vs laburen.com)

**laburen.com NO compite con yaml-agno (librería OSS); compite con el PRODUCTO CENF (Agente Instalador + ArcaMCP).** Evidencia (websearch 2026-08-11):

| Dato laburen | Valor | Fuente |
|---|---|---|
| Qué es | Plataforma no-code de "Empleados de IA" (builder por chat, entrenamiento con datos del cliente, deploy gestionado punta a punta) | laburen.com/en, docs.laburen.com |
| Tracción | 400+ empresas, 3.000+ agentes activos, LATAM + USA; fundada 2023 (Córdoba, AR) por Sebastián Rinaldi | infonegocios.info (2026-01-08) |
| Pricing | Pro $19/mes, Business $99/mes, Growth $499/mes (freemium); enterprise custom ~$1.500/mes (95% de la facturación) | laburen.com/en/plans, toolmage.com (2025-11-15), infonegocios |
| Integraciones | 1.000+ tools: WhatsApp, Tokko CRM, Kommo, Odoo, HubSpot, Salesforce, Gmail, Slack, Google Drive, Cal.com | laburen.com FAQ, docs.laburen.com |
| 2026 | Plan de quintuplicar operación; foco Chile/México/Perú; reconocimientos NVIDIA Inception + Microsoft for Startups | infonegocios (2026-01-08) |
| Sin evidencia de | Facturación electrónica AFIP/ARCA, self-hosted/on-prem, capa de gobernanza declarativa | GAP de evidencia (ausencia observada, no confirmada) |

**Lectura estratégica**: laburen VALIDA el mercado (PyMEs AR/LATAM pagan $19-$1.500/mes por agentes) pero lo cubre con un modelo "managed no-code cerrado". CENF no puede ni debe competir en features (3.000 agentes corriendo vs 0). La competencia es en **metodología + verticalidad + soberanía de datos**:
1. **Vertical regulatorio AR**: facturación AFIP/ARCA (ArcaMCP) — laburen no muestra dominio contable-impositivo; el beachhead real de CENF es el estudio contable (#C0001-EstudioCutignola, validado en knowledge graph).
2. **Self-hosted / data sovereignty**: laburen es cloud managed; yaml-agno sobre Agno puede ofrecer "data stays in VPC" — argumento de venta para PII (Ley 25.326) y estudios contables.
3. **Metodología**: CENF aporta prompting/metodología/34-SPEC governance como activo distribuible (coherente con visión de Gonzalo: valor vía IA, no cara visible).
4. **OSS como canal**: laburen es cerrado; yaml-agno Apache-2.0 captura a los implementadores técnicos que laburen no sirve.

### Riesgos (matriz resumida — severidad + mitigación)

| # | Riesgo | Prob | Sev | Mitigación |
|---|---|---|---|---|
| R-A | **laburen absorbe el mercado PyME AR antes que ArcaMCP** (5x en 2026 + integraciones billing/Odoo ≈ camino a facturación) | ALTA | CRÍTICO | Prioridad ArcaMCP como producto; retainer cliente externo (T-05 EXECUTION-PLAN); la profundidad regulatoria AFIP es barrera que laburen no tiene hoy |
| R-B | **OpenShell es ALPHA** (repo creado 2026-02-24, v0.0.57 PyPI, 442 issues abiertos, status alpha oficial) — el doc ChatGPT lo puntúa ⭐⭐⭐⭐☆ sin advertir madurez | ALTA | ALTO | NO usar sandbox en Fase 1-2. Contención declarativa (allowlists SPEC_11/16, SecretResolver, tool permissions de Agno). Re-evaluar sandbox en Fase 3+ con gVisor como opción madura |
| R-C | **Ops Keycloak** (JVM/Quarkus, ~1GB RAM, DB propia) rompe el perfil serverless free-tier de Fase 1 (Cloud Run + Supabase) | ALTA | MEDIO | Fase 2: instancia Cloud Run pequeña ($15-50/mes) o alternativa liviana Logto (MPL-2.0) si el caso es simple; nunca en Fase 1 |
| R-D | **Riesgo upstream Keycloak**: dependencia Liquibase migra a FSL (no-OSS) — issue #43391 abierto, CNCF rechazó excepción; Keycloak buscando alternativa (Flyway) | MEDIA | BAJO | Vigilar (G-06 trimestral); no blocking: el impacto es en la distribución de Keycloak, no en su API |
| R-E | **Make auth desde cero** (SPEC_19 original: JWT middleware + ScopeEnforcer propios) = ownership de CVEs, key rotation, OIDC a perpetuidad | MEDIA | ALTO | BUY (Keycloak) en Fase 2; contrato `IdentityProvider` en core-cenf-py desde ahora (Core-CENF Mandate) |
| R-F | **OpenFGA maintainer concentration (Okta)** — neutralidad cuestionada en su propio due-diligence CNCF | MEDIA | MEDIO | Elegir Casbin primero (Apache Incubating, in-process, 20K stars); OpenFGA solo si aparece caso ReBAC |
| R-G | **Agno drift sigue siendo el riesgo #1 técnico** (R-01 previo) — Keycloak/Casbin no lo mitigan | ALTA | ALTO | Pin 2.8.7 + G-05 integration tests por SPEC + G-06 revisión trimestral (sin cambio) |
| R-H | **gVisor cambió su método de instalación mid-2026** (multi-file, auto-download se elimina sept 2026) | BAJA | BAJO | Si Fase 3 usa gVisor: instalar vía apt/tarball desde el inicio |

### Costos (supuestos financieros — NO evidencia salvo donde se marca)

| Concepto | Monto | Tipo | Fuente |
|---|---|---|---|
| **Infraestructura** | | | |
| Keycloak en Cloud Run (Fase 2) | $15-50/mes | Supuesto (1 instancia pequeña + egress) | Estimación de patrón Cloud Run; no cotizado |
| Casbin (in-process) | $0 | Evidencia de diseño (no es servicio) | — |
| OpenShell/gVisor sandbox | $0 software (Fase 3+); CPU/mem por sandbox | Supuesto | — |
| Supabase/Postgres adicional para Keycloak | $0-15/mes (Fase 2) | Supuesto | Plan actual free tier |
| **Tokens (desarrollo)** | | | |
| Spike de-risking OIDC en Fase 1 | $5-10 | Supuesto (1-2 días-agente, cache 92-96%) | Patrón P-001/P-002 |
| Integración Keycloak+Casbin completa (Fase 2) | $60-120 | Supuesto (5-8 días-agente con cache) | Derivado de $10-20/SPEC histórico |
| SPEC_19 "desde cero" (alternativa descartada) | $30-60 | Supuesto (3-5 días-agente, EXECUTION-PLAN S5) | EXECUTION-PLAN.md |
| **Operación** | | | |
| Operar Keycloak (backups, upgrades, key rotation) | Horas de Gonzalo/Pablo/Flor — NO cash | Supuesto | — |
| Runtime tokens por agente con Keycloak/Casbin | ~$0 adicional (las policies de Casbin son in-process; Keycloak no consume LLM) | Supuesto razonable | — |
| **NO incluidos** | Mantenimiento OSS, soporte a clientes, tiempo de Gonzalo (oportunidad), costo legal | VACÍO DE EVIDENCIA (heredado de STRATEGIC §3.2) | — |

**Lectura de costos**: el diferencial de timeline (1-2 semanas) cuesta más en **horas humanas** (Keycloak se opera) que en cash. El costo cash de la integración (~$75-140 total) es irrelevante frente a $134/mes de burn actual; el costo REAL es el tiempo de Fase 1. Por eso la decisión es de TIMING, no de viabilidad financiera.

### Provenance (gate read-only ejecutado por el orquestador — verificado contra fuentes primarias 2026-08-11)

| Componente | Licencia (verificada) | Soporte / madurez | Fuente |
|---|---|---|---|
| **Keycloak** (keycloak/keycloak) | **Apache-2.0** | CNCF **Incubating** (2023-04-10), Red Hat/IBM backing, 36K stars, 13 años, 3.108 issues abiertos; ⚠️ dependencia Liquibase FSL en transición (issue #43391) | github.com/keycloak/keycloak, cncf.io/projects/keycloak |
| **Casbin** (apache/casbin) | **Apache-2.0** | **Apache Software Foundation Incubating**, 20.3K stars, multi-lenguaje (Go, Java, Python…), 43 issues abiertos | github.com/casbin/casbin, casbin.apache.org |
| **OpenFGA** (openfga/openfga) | **Apache-2.0** | CNCF **Incubating** (2025-10-28), Okta/Auth0 origin, 5.5K stars; ⚠️ maintainers concentrados en Okta (nota en due-diligence CNCF); storage Postgres 14+/MySQL/SQLite | github.com/openfga/openfga, cncf.io/projects/openfga |
| **OpenShell** (NVIDIA/OpenShell) | **Apache-2.0** | **ALPHA** (repo creado 2026-02-24, PyPI v0.0.57, 442 issues abiertos, status alpha oficial). ⚠️ NO apto producción hoy | github.com/NVIDIA/OpenShell, pypi.org/project/openshell |
| **gVisor** (google/gvisor) | **Apache-2.0** | Maduro (2018, Google, 19K stars, usado en prod por Google); ⚠️ cambio de instalación mid-2026 | github.com/google/gvisor, gvisor.dev |
| Alternativas (no seleccionadas) | Logto **MPL-2.0**, Ory Kratos+Keto **Apache-2.0**, Cerbos **Apache-2.0**, MS Agent Governance Toolkit **MIT**, Firecracker **Apache-2.0** | Verificadas por claims del doc + conocimiento estándar; no auditadas archivo por archivo (marcado como supuesto razonable) | chatgpt-comparar-repositorios-open-source.md |

**Veredicto provenance: PASS-CON-CONDICIONES** — los 5 componentes centrales son Apache-2.0 (compatible con Agno y con el plan de apertura Apache-2.0 de yaml-agno); sin embargo OpenShell debe excluirse de Fase 1-2 por alpha, y el peso operativo de Keycloak condiciona su adopción a Fase 2.

---

## Decisión (punto por punto de las 6 preguntas)

### 1. ¿Integrar Keycloak+Casbin AHORA o postergar a Fase 2? → **POSTERGAR (Fase 2), con decisión anticipada**

- Ponderado contra Prioridad #1 (time-to-market multitenant): integrar ahora agrega 2-4 semanas a un sprint de 1.5-2.5 semanas → duplica el tiempo para el gate G-04 (demo interna), que es el criterio de éxito real de Fase 1.
- El uso interno (3 personas CENF) no necesita un IdP externo: el aislamiento ya está garantizado por (a) composite user_id, (b) filtro `tenant_id` en repos `yamlagno_*`, (c) storage Agno aislado por user_id (Decisión 2.9 EXECUTION-PLAN: NO RLS). Gate L-03 (0 fugas cross-tenant) se mantiene.
- Hallazgo del doc ChatGPT que refuerza: Agno YA declara JWT/RBAC/multi-user/multi-tenant — para Fase 1 no construimos identity, usamos el aislamiento nativo.
- **PERO** la postergación debe ser "de diseño", no "de hecho": se define AHORA el contrato `IdentityProvider`/`AuthorizationProvider` (Ports) en core-cenf-py, para que SPEC_19 parcial (tenant/resolver.py + tenant_context.py) no se escriba contra una interfaz que Keycloak romperá después.
- **Spike de de-risking en Fase 1** ($5-10, 1-2 días): validar round-trip OIDC Keycloak ↔ yaml-agno (login → JWT → claims → enforce Casbin) ANTES de comprometer el diseño de Fase 2. Mismo patrón que P-001/P-002.

### 2. Impacto en el Execution Plan → **SPEC_19 cambia de enfoque (no solo de prioridad)**

| Elemento | Antes (SPEC_19 original) | Después (decisión) |
|---|---|---|
| SPEC_19 Security/Auth/Tenant | "Crítica S2" condicional; si se ejecuta: JWT middleware propio (`JWT_VERIFICATION_KEY`), `ScopeEnforcer` propio, catálogo de scopes propio, audit propio | Fase 2: **REPLACEMENT de enfoque** → Identity via Keycloak (OIDC), authz via Casbin; SPEC_19 parcial actual se conserva como tenant layer |
| Nuevos artefactos Fase 2 | — | SPEC_19b Identity Adapter (Keycloak OIDC, Ports/Adapters en core-cenf-py), SPEC_19c Authorization Adapter (Casbin), evolución de SPEC_06 api/middleware → **CENF Gateway** (tenant isolation + quotas + audit — pieza nueva del doc ChatGPT que NO está en el plan actual) |
| Agno pin | 2.8.7 | **Sin cambio** (Keycloak no toca el runtime) |
| Gates | L-03 (0 fugas cross-tenant) | **Se mantiene**; se agrega L-03b (Fase 2): 0 decisiones de authz fuera de Casbin policy |
| T-05 (retainer si G-04 es externo) | Retainer cliente antes de datos reales | **Se refuerza**: cliente externo = Keycloak adelanta prioridad (es el driver de la Fase 2 de seguridad) |
| S5 del DAG | "colchón, se posterga entera" | Postergada + **redefinida como BUY** — la nota de cierre de S5 debe decir "adoptar Keycloak+Casbin en Fase 2", no "auth pendiente" |

### 3. Make vs Buy → **BUY (Keycloak) con contrato propio; Casbin sobre OpenFGA**

- Identity/auth es el dominio con mayor costo de error; escribir JWT/OIDC/RBAC desde cero = asumir CVEs, key rotation y flows OIDC a perpetuidad. Keycloak (CNCF Incubating, Red Hat, 13 años) es la opción OSS más madura del ecosistema.
- **Core-CENF Mandate aplicado**: NO escribir auth desde cero. core-cenf-py ya provee managers (config/auth/cache/DB); el rol correcto es exponer el **contrato** `IdentityProvider` (Port) + adaptador Keycloak (Adapter) — golden rule: depend de Protocols, inyectan Adapters. El mandato NO significa "core-cenf reemplaza un IdP"; significa que el IdP se integra detrás de un port reutilizable (ArcaMCP y Agente Instalador lo consumirán igual).
- **Casbin sobre OpenFGA**: para RBAC multitenant por tenant/rol/scope, Casbin (in-process, model.conf, Apache Incubating, 20K stars) es suficiente y evita operar un servicio más (OpenFGA requiere su propio Postgres + HTTP). OpenFGA (Zanzibar/ReBAC) solo si aparece el caso de permisos por recurso/documento (p.ej. un agente que accede a documentos específicos por tenant-usuario-recurso).
- Sandbox (OpenShell/gVisor): **ni make ni buy por ahora** — la necesidad real (ejecutar código no confiable) no existe en Fase 1-2; la contención declarativa (allowlists, SecretResolver, tool permissions de Agno) cubre el riesgo. Fase 3+: gVisor (maduro) > OpenShell (alpha).

### 4. Timeline comparison → **SPEC_19 desde cero es más rápido pero compra deuda; Keycloak es más lento pero deja de ser problema**

| Opción | Esfuerzo | Costo tokens | Costo real |
|---|---|---|---|
| SPEC_19 auth desde cero | 3-5 días-agente (~1-2 semanas) | $30-60 | **Deuda de seguridad perpetua** + retrabajo cuando llegue el cliente externo (el 95% del revenue de laburen es enterprise — mismo patrón esperable para CENF) |
| Integrar Keycloak+Casbin (Fase 2) | 5-8 días-agente (~2-4 semanas) | $60-120 | 1-2 semanas más de calendario pero **identity resuelto a 13 años de madurez**; el delta se amortiza en el primer cliente enterprise |
| Spike de-risking OIDC (Fase 1) | 1-2 días-agente | $5-10 | Barato y desbloquea el diseño de Fase 2 sin comprometer el sprint |

**Conclusión de timeline**: la comparación honesta no es "1-2 vs 2-4 semanas" — es "pagar 1-2 semanas AHORA por algo que habrá que re-hacer" vs "pagar 2-4 semanas en Fase 2 por algo definitivo". Contra Prioridad #1: la Fase 1 no debe cargar el costo; la Fase 2 (post-G-04, cuando haya cliente externo o decisión de escalar) sí.

### 5. Posicionamiento vs laburen.com → **COMPETIR EN METODOLOGÍA, NO EN FEATURES**

- laburen tiene 3.000 agentes activos y un builder no-code pulido; **cualquier carrera de features contra laburen está perdida de antemano**. yaml-agno no compite ahí.
- La tesis CENF: **"agentes bien construidos, con gobernanza, en tu infraestructura, para tu vertical"** vs "agentes no-code en la nube de laburen".
- Diferenciadores accionables: (1) **ArcaMCP / facturación AFIP-ARCA** — vertical regulatorio que laburen no cubre (GAP confirmado por ausencia en sus integraciones); (2) **self-hosted / VPC** — "data stays in VPC" (positioning de Agno) para PII y Ley 25.326; (3) **metodología CENF** (34-SPEC governance, prompting, best practices) como activo distribuible vía OSS — coherente con la visión de Gonzalo (valor vía IA, no cara visible); (4) **OSS Apache-2.0** — captura implementadores técnicos que el modelo cerrado de laburen no sirve.
- El mercado VALIDA disposición a pagar ($19-$1.500/mes); el riesgo no es de demanda sino de velocidad de ejecución del producto (ver R-A).

### 6. Open source timing → **MANTENER plan actual (apertura post-Fase 1 con condiciones); NO acelerar por laburen**

- laburen no compite en el plano OSS (yaml-agno es librería, laburen es SaaS) — por lo tanto NO es driver del timing de apertura.
- El driver del timing OSS sigue siendo el riesgo de absorción de Agno (T-01) y la construcción de comunidad, tal como STRATEGIC §8.1: apertura post-Fase 1 con 6 condiciones medibles (Fase 1 completa, ≥20/34 SPECs, CI/CD público, desacople core-cenf, artefactos legales, budget de mantenimiento). Se ratifica.
- La apertura de yaml-agno ES la distribución de la metodología (diferencial #3): cuanto antes se siembre la comunidad Agno, antes CENF deja de depender de su propio marketing. Pero abrir antes de Fase 1/CI = quemar el repo (decisión previa D-05, confidence 0.7, se mantiene).
- **La urgencia real que laburen genera NO es OSS: es PRODUCTO** — ArcaMCP (facturación) debe priorizarse sobre features de yaml-agno no críticas (scheduling/monitoring ya están en Fase 2 del plan; ratificar).

---

## Próximos Pasos

1. **Registrar en DECISIONES.md (Fase 1)**: SPEC_19 postergada a Fase 2 como **BUY Keycloak+Casbin** (no "auth pendiente"); nota de cierre S5 actualizada (EXECUTION-PLAN).
2. **Definir contrato `IdentityProvider`/`AuthorizationProvider` en core-cenf-py** (Ports) — 1 día-agente, desacoplado del runtime; NO implementar adaptador Keycloak todavía.
3. **Spike de-risking OIDC** (Fase 1, $5-10): round-trip Keycloak ↔ yaml-agno (login → JWT → claims → Casbin enforce) para fijar el diseño de Fase 2. Resultado → DECISIONES.md.
4. **Priorizar ArcaMCP como producto** (contra R-A): el competidor real de laburen es ArcaMCP + Agente Instalador, no yaml-agno. El roadmap de yaml-agno no debe robarle días-agente al revenue path.
5. **Vigilar (G-06 trimestral, nov 2026)**: (a) issue Liquibase/FSL de Keycloak (#43391), (b) madurez de OpenShell (alpha → beta), (c) si laburen agrega facturación AFIP (monitoreo trimestral de sus integraciones), (d) método de instalación gVisor si Fase 3 lo usa.
6. **Re-evaluar esta card en el gate de Fase 2** (post-G-04, o antes si G-04 se vuelve externo / retainer T-05 firmado).

---

## Fuentes y Supuestos

### Evidencia (2026-08-11, websearch + lectura de archivos)
- laburen.com/en, /en/plans, /business, docs.laburen.com (FAQ, inicio rápido) — modelo, integraciones, pricing self-service.
- infonegocios.info (2026-01-08) — 400+ empresas, 3.000+ agentes, plan 5x 2026, enterprise ~$1.500/mes (95% facturación), foco Chile/México/Perú. **Fuente periodística, no oficial** — los números enterprise son de prensa (supuesto razonable, no contrato).
- toolmage.com (2025-11-15) — detalle pricing Pro/Business/Growth + freemium.
- github.com/keycloak/keycloak + cncf.io/projects/keycloak — Apache-2.0, CNCF Incubating, Liquibase FSL issue #43391.
- github.com/apache/casbin + casbin.apache.org — Apache-2.0, ASF Incubating.
- github.com/openfga/openfga + cncf.io/projects/openfga + cncf/toc due-diligence — Apache-2.0, CNCF Incubating, concentración Okta.
- github.com/NVIDIA/OpenShell + docs.nvidia.com/openshell + pypi.org/project/openshell — Apache-2.0, ALPHA.
- github.com/google/gvisor + gvisor.dev — Apache-2.0, cambio instalación sept 2026.
- EXECUTION-PLAN.md (2026-08-10) — SPEC_19 condicional, DAG, gates, costos.
- STRATEGIC_yaml-agno.md (2026-08-08) — GO condicional previo, moat gobernanza, §8.1 condiciones OSS.
- AGENTS.md yaml-agno — composite user_id, aislamiento, golden rule build-on-top, dependencias core-cenf.
- chatgpt-comparar-repositorios-open-source.md — stack propuesto; los claims de licencia fueron re-verificados contra fuentes primarias (provenance gate), los claims de features de Agno (JWT/RBAC/multi-tenant) **NO** fueron re-verificados contra docs de Agno en esta sesión (ver GAP-4).

### Supuestos financieros (explícitos, no evidencia)
- Costo por día-agente $10-20 con cache 92-96% (derivado del histórico de SDD, no garantizado).
- Keycloak Cloud Run $15-50/mes: estimación de patrón (instancia pequeña), no cotización.
- Costo de integración Fase 2 $60-120: extrapolación de $10-20/SPEC; NO incluye horas humanas de operación Keycloak (costo real, no cash).

### GAPs de evidencia (escalados)
- **GAP-1**: knowledge_graph_v2.json (ruta corregida `C:\Dropbox\DOC.RECA\01-Doc. Personal\Configuraciones\knowledge_graph_v2.json`) existe y su estructura es legible (nodos clientes CENF: #C0001-EstudioCutignola, #C0008-Addoc, #C0009-ContrerasHnos, #C0010-IESA, #C0011-SOBOCE; nodos amBotHs, metodología, procedimientos), pero el parse completo falló por **encoding mojibake** (caracteres corruptos rompen ConvertFrom-Json). Estructura = evidencia; contenido completo = no verificable en esta sesión.
- **GAP-2**: stack interno de laburen (framework de agentes, modelos, self-host?) NO verificado — no encontré evidencia pública.
- **GAP-3**: números enterprise de laburen ($1.500/mes, 95% facturación) provienen de prensa (infonegocios), no del site oficial.
- **GAP-4**: claims de Agno (JWT/RBAC/multi-user/multi-tenant storage/audit/HITL/tool permissions) provienen del doc ChatGPT — soportados parcialmente por AGENTS.md local (composite user_id, aislamiento por user) pero no re-verificados contra docs oficiales de Agno 2.8.x.
- **GAP-5**: costos de operación Keycloak a 12 meses (horas, backups, upgrades) no cuantificados.
- **GAP-6**: SBOM/auditoría de headers de copyright del stack actual (heredado de STRATEGIC §11.2).

### Riesgos críticos a escalar (no mitigables hoy)
1. **R-A es el riesgo estratégico #1**: laburen (3.000+ agentes, 2026 5x, integraciones billing/Odoo) puede llegar a facturación AFIP antes que ArcaMCP. **No es mitigable con código** — es una carrera de ejecución de producto. Requiere decisión de Gonzalo: prioridad ArcaMCP absoluta sobre features no críticas de yaml-agno.
2. **OpenShell (la opción sandbox "⭐⭐⭐⭐☆" del doc ChatGPT) es ALPHA** — cualquier plan que la incluya en producción en los próximos 6-12 meses es inviable; el doc de ChatGPT subestima su madurez (compresión abusiva).
3. **El CENF Gateway (pieza central de la arquitectura propuesta: tenant isolation + quotas + audit + routing) NO existe en el plan actual ni en el código** — es el verdadero costo oculto de la arquitectura Identity→Gateway→Runtime→Authz→Sandbox; el doc de ChatGPT lo asume implícito.

### Validación fractal (ejecutada por el orquestador — límite de profundidad 2 impidió delegación, precedente §11.6 STRATEGIC previo)
- **Score de complejidad: 14/16** (>10/16 → requiere validación profunda). La complejidad está en el sistema propuesto (5 capas + 3 servicios nuevos + YAML declarativo + multitenant + productos encima), no en el código actual.
- **Compresiones abusivas detectadas en el doc ChatGPT**: (1) "componible fácilmente con Agno" asume un adapter layer que NO existe (el CENF Gateway); (2) Keycloak tratado como servicio liviano cuando es JVM pesada de operar; (3) OpenShell puntuado ⭐⭐⭐⭐☆ sin advertir que es alpha de 6 meses.
- **Valores intermedios faltantes**: costo de operación Keycloak a 12 meses, costo de migración del SPEC_19 parcial existente, costo de integración con ArcaMCP, trigger exacto de cuándo el cliente externo activa la Fase 2 de seguridad (T-05 cubre parcialmente).

---

*Strategic Decision generada por Strategic Gestion Team — 2026-08-11*
*Siguiente paso: registrar decisión en DECISIONES.md de yaml-agno; planificador integra el spike OIDC y el contrato IdentityProvider en el roadmap de Fase 1; Risk Matriz actualiza R-A.*
