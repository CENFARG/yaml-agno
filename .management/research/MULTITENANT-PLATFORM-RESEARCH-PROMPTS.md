# Deep Research Prompts — Multitenant Platform sobre Agno + Dashboard + Onboarding

> **Proyecto**: Plataforma SaaS multitenant sobre Agno Framework.
> **Componentes propietarios**: `yaml-agno` (librería pip que abstrae Agno via YAML declarativo; 14/34 SPECs, 718 tests) y `core-cenf-py` (21 managers de infraestructura, privado).
> **Arquitectura recomendada (decisión preliminar)**: AGNO NATIVO PRIMERO → auditar qué resuelve Agno antes de integrar Keycloak/Casbin/OpenFGA. `yaml-agno` = "Agno Declarative Adapter"; `core-cenf-py` = "CENF Infrastructure + Security Contracts" via Ports/Adapters.
> **Competidor de referencia**: laburen.com (Argentina, "AI Employees", 3 planes, no OSS).
> **Fecha de calibración de fuentes**: agosto 2026. Todos los prompts asumen ventana de datos hasta **agosto 2026**.

---

## Tema 1: Arquitectura Multitenant sobre Agno Nativo

**Pregunta central**: ¿Qué capacidades multitenant reales tiene Agno en su versión actual (2.8.x) y qué gaps debemos llenar con software externo?

### 1. Prompt de Investigación Profunda (Perplexity)

**Enfoque Sugerido**: Web
**Herramientas Recomendadas**: Investigación Profunda

```markdown
Actuá como arquitecto de plataformas agentic especializado en seguridad multitenant y frameworks de agentes (Python). Ayudás a un equipo argentino que construye una plataforma SaaS multitenant sobre Agno Framework (agno-agi/agno), con una capa declarativa propia (yaml-agno, que abstrae Agno via YAML) y una librería de infraestructura privada (core-cenf-py, 21 managers).

CONTEXTO Y OBJETIVO
Necesito un informe de auditoría exhaustivo sobre las capacidades multitenant NATIVAS de Agno en su versión estable actual (2.8.x, agosto 2026) y una identificación precisa de los gaps que requieren software externo. El equipo ya sabe que Agno ofrece "JWT-based RBAC y multi-user/multi-tenant isolation out of the box", pero necesita saber EXACTAMENTE qué cubre y qué no, antes de decidir si integrar Keycloak, Casbin u OpenFGA. Decisión de alto riesgo: no queremos agregar infraestructura que Agno ya resuelve, ni confiar en Agno donde no cubre.

ALCANCE TEMPORAL Y DE FUENTES
- Estado actual: versión 2.8.x (o la más reciente publicada en PyPI al momento de investigar) y su documentación oficial (docs.agno.com), release notes y changelog.
- Considerar evolución desde v2.3.13 (diciembre 2025, cuando se agregó RBAC fine-grained para Agents/Teams/Workflows) hasta hoy.
- Fuentes primarias: repositorio agno-agi/agno (issues, PRs, releases), docs.agno.com (secciones Security & Auth, AgentOS, AuthorizationConfig), ejemplos oficiales de RBAC (symmetric/asymmetric, scope mapping, user isolation), repos agno-agi/agentos-railway y agno-agi/agent-platform-railway.
- Fuentes secundarias: artículos técnicos 2026 sobre Agno y plataformas agentic multitenant.

PLAN DE INVESTIGACIÓN
1. Inventariar el modelo de autorización de AgentOS: qué claims JWT usa (scopes por defecto, sub para user ID), qué endpoints están gated, cómo se configura `AuthorizationConfig` (incluyendo `user_isolation=True`), y cómo funciona el sistema jerárquico de scopes (agent/team/workflow/component).
2. Verificar QUÉ recursos cubre el aislamiento multitenant cuando `user_isolation=True`: sessions, memory, traces, approvals, agent/team/workflow run lookups, knowledge, files, MCP. Listar explícitamente lo cubierto vs lo NO cubierto.
3. Determinar si Agno soporta organizations/teams dentro de un tenant (¿es solo user-level o existe jerarquía org → team → user → resource?). ¿El JWT sub es un user ID global o un tenant ID?
4. Analizar los patrones de aislamiento implementados en agentos-railway y agent-platform-railway (¿usan user_isolation? ¿cómo emiten JWTs? ¿qué proveedor IdP asumen?).
5. Evaluar la extensibilidad del RBAC: ¿se puede agregar un middleware de autorización custom? ¿Hay hooks para inyectar scopes propios? ¿Cómo se mapean claims de proveedores externos (p.ej. claim `permissions` de WorkOS vía `scopes_claim`)?
6. Construir matriz comparativa: Agno nativo (user_isolation ON) vs Agno + Casbin (pycasbin embebido) vs Agno + OpenFGA vs Agno + Keycloak. Para cada opción: qué resuelve, qué agrega, costo operativo, latencia, complejidad.

CONSULTAS DE BÚSQUEDA SUGERIDAS
- "Agno AgentOS user_isolation tenant isolation scope RBAC"
- "agno-agi/agno release 2.8 changelog security"
- "Agno AuthorizationConfig multi-issuer JWT WorkOS scopes claim"
- "Agno AgentOS RBAC agent team workflow permissions scopes"
- "agentos-railway deployment JWT permissions architecture"

MANEJO DE INFORMACIÓN FALTANTE O CONFLICTIVA
- Si la documentación no especifica cobertura de algún recurso (p.ej. knowledge o files), marcarlo explícitamente como "no documentado / requiere verificación en código" en lugar de asumir.
- Si hay discrepancias entre docs y release notes, reportarlas con cita a ambas fuentes.
- NO especular sobre versiones futuras; basarse en releases publicados.

FORMATO DE SALIDA
1. Resumen ejecutivo (5-7 bullets): capacidades nativas confirmadas + gaps principales.
2. Modelo de autorización de AgentOS: diagrama de flujo en texto (JWT → middleware → scopes → endpoint) y tabla de recursos aislados vs no aislados.
3. Tabla comparativa Agno nativo vs +Casbin vs +OpenFGA vs +Keycloak (columnas: aislamiento, granularidad, costo operativo mensual estimado, latencia, complejidad de integración, mantenimiento).
4. Recomendación con criterios de decisión explícitos: ¿en qué punto de crecimiento de tenants (N usuarios, N agentes por tenant) cada opción se justifica?
5. Limitaciones y datos no verificables.
Citar en línea con [1][2] toda afirmación de hecho, estadística o claim de documentación. NO incluir bibliografía final; solo citas en línea.
```

### 2. Queries de Búsqueda Específicas

- **Google**: `Agno AgentOS user_isolation AuthorizationConfig tenant isolation RBAC 2026`
- **Google**: `Agno 2.8 release notes security scopes RBAC agents teams workflows`
- **GitHub**: `repo:agno-agi/agno "tenant" isolation issue`
- **GitHub**: `repo:agno-agi/agno "user_isolation" OR "AuthorizationConfig" code`
- **GitHub**: `topic:agno agentos multitenant`
- **GitHub**: `agno-agi/agentos-railway README permissions JWT`
- **YouTube**: `Agno framework multi-tenant agent platform tutorial`
- **Papers**: `multi-tenant isolation patterns AI agent platforms 2025 2026`

### 3. Estructura de Datos Esperada

```
agno_multitenant_audit:
  version_analizada: string            # p.ej. 2.8.x
  auth_model:
    jwt_claims: [claim, default, configurable_via]
    scopes: {scope_name: grants[]}
    middleware_hooks: [extensibilidad]
  isolation_coverage:
    resource: {sessions, memory, traces, approvals, runs, knowledge, files, MCP}
    estado: covered | not_covered | undocumented
    flag_requerido: user_isolation=True | n/a
  tenant_model:
    jerarquia: user_level | org_team_level | ambos
    sub_semantica: user_id | tenant_id
  patrones_referencia:
    agentos_railway: {aislamiento, idp_asumido, jwt_issuance}
    agent_platform_railway: {...}
  comparativa_opciones:
    opcion: agno_nativo | agno_casbin | agno_openfga | agno_keycloak
    resuelve: [features]
    gaps_restantes: [features]
    costo_operativo_usd_mes: number
    latencia_extra: string
    complejidad: low|medium|high
  recomendacion: {criterio, umbrales_escala, opcion_ganadora}
  limitaciones: [strings]
```

---

## Tema 2: Análisis Competitivo — Laburen.com

**URL**: https://laburen.com/en (ya analizada; se requiere profundización)

### 1. Prompt de Investigación Profunda (Perplexity)

**Enfoque Sugerido**: Web
**Herramientas Recomendadas**: Investigación Profunda

```markdown
Actuá como analista competitivo especializado en startups de inteligencia artificial en LATAM. Ayudás a un equipo que construye una plataforma SaaS multitenant de agentes AI en Argentina y quiere entender a fondo a su competidor más cercano: Laburen.com (laburen.com, "AI Employees", fundada 2023 por Sebastián Rinaldi, con clientes como Hertz, Audi, Ford y Yamaha).

CONTEXTO Y OBJETIVO
Laburen NO es open source y no publica su arquitectura técnica. Necesito un perfil competitivo completo basado en evidencia pública: prensa, entrevistas, job postings, redes sociales, programas de aceleración, reviews de clientes y rastros técnicos (dominios, integraciones, plataformas). El objetivo es responder: ¿qué modelo de negocio, stack y proceso de ventas/onboarding usan, y qué podemos imitar o superar?

DATOS YA CONFIRMADOS (verificar y ampliar, no repetir sin valor agregado)
- 3 planes en el sitio: Enterprise (equipo dedicado, "diagnóstico gratuito"), Business (self-service) y "Soy tu Claw" (asistente personal WhatsApp, soytuclaw.com).
- Prensa 2025-2026 reporta precios publicados: Pro US$19/mes, Business US$99/mes, Growth US$499/mes (verificar vigencia).
- ~400+ empresas clientes (ago 2026) y 3.000+ agentes de IA activos; crecimiento 400% neto en 2025, bootstrapped ("fondos propios"), expansión 170% de nómina en 2026, 30 búsquedas laborales abiertas.
- Programas: NVIDIA Inception, Microsoft for Startups, Google for Startups, AWS Startups, Anthropic Select Services Partner, Cloudflare for Startups.
- Producto estrella: "Laburen Agents" (plataforma vibe-code, lenguaje natural → automatizaciones, lanzamiento nov 2025).
- Modelo híbrido con "Ingeniero de Implementación en Cliente" (IImC).
- Tech signals visibles: sitio en Sanity (CDN), dashboard.laburen.com, +1000 integraciones (WhatsApp, Drive, Calendar, Gmail, Slack, ClickUp, Trello, GitHub, Outlook, CRMs, ERPs).

PLAN DE INVESTIGACIÓN
1. Biografía y trayectoria de Sebastián Rinaldi: perfil profesional previo a Laburen, apariciones en medios (infobae, TN, El Cronista, ámbito, iProUP, NEURA/Economía Real, programas de TV/radio 2025-2026), funding declarado o negado, equipo directivo.
2. Stack tecnológico inferido: revisar job postings (Product Engineers Full Stack, AI Engineers) para inferir lenguajes/frameworks (¿Python? ¿Node? ¿Next.js?), integraciones listadas, señales de infraestructura (Cloudflare, Sanity), y cualquier mención a frameworks de agentes (Agno, LangChain, CrewAI, OpenAI, Anthropic) en entrevistas o notas.
3. Modelo de pricing completo: confirmar Pro/Business/Growth vs Enterprise vs Soy tu Claw; ¿hay API pública con pricing o todo pasa por "contact sales"? ¿Qué incluye cada plan (límites de agentes, mensajes, integraciones)?
4. Reviews y reputación: búsqueda en G2, Capterra, ProductHunt, Trustpilot, Google Reviews, Reddit (r/argentina, r/CharruaDevs, r/programacion) y LinkedIn; sentimiento y quejas recurrentes (soporte, facturación, resultados prometidos vs entregados).
5. Análisis de los cases de éxito (Hertz, Audi, Ford, Yamaha, Taraborelli, Pan American Energy): ¿evidencia de agentes autónomos reales o automatización tradicional (chatbots, flujos no-code, RPA)? Buscar métricas publicadas (p.ej. "un agente absorbe el trabajo de 20 empleados", "98% reducción de tiempos de respuesta") y su verosimilitud.
6. Presencia en GitHub / OSS / comunidad técnica: búsqueda de org laburen en GitHub, contribuciones, posts técnicos, talks, presencia en LinkedIn de su equipo técnico.

CONSULTAS DE BÚSQUEDA SUGERIDAS
- "Laburen Sebastián Rinaldi entrevista stack tecnología agentes"
- "Laburen.com review clientes opiniones G2 Capterra"
- "Laburen Agents vibe-code plataforma arquitectura"
- "Laburen.com pricing planes precios 2026"
- "Laburen Hertz Audi Yamaha caso éxito agente IA"

MANEJO DE INFORMACIÓN FALTANTE O CONFLICTIVA
- Distinguir claramente entre hechos verificados (prensa, sitio oficial), inferencias (job postings, señales técnicas) y especulación. Marcar cada uno.
- Cuando la prensa reporte métricas de marketing (p.ej. "20 empleados equivalentes"), indicar si son claims del CEO sin auditoría independiente.
- Si no hay reviews en G2/Capterra, decirlo explícitamente ("sin presencia verificable en X al 2026") en lugar de inventar.

FORMATO DE SALIDA
1. Resumen ejecutivo (5 bullets): posicionamiento, modelo de ingresos, tracción, riesgos.
2. Perfil del fundador y equipo.
3. Stack tecnológico: tabla de señales → inferencia → nivel de confianza (alta/media/baja).
4. Modelo de pricing: tabla de planes con precios verificados y fecha de la fuente.
5. Reputación: resumen de reviews con sentimiento agregado y quejas recurrentes.
6. Veracidad de cases de éxito: análisis crítico de cada claim con evidencia a favor/contra.
7. Implicaciones estratégicas para nuestra plataforma: qué copiar, qué evitar, dónde diferenciarse.
Citar en línea con [1][2] toda afirmación. NO incluir bibliografía final; solo citas en línea.
```

### 2. Queries de Búsqueda Específicas

- **Google**: `laburen.com Sebastián Rinaldi entrevista stack tecnología`
- **Google**: `laburen.com precios planes Pro Business Growth 2026`
- **Google**: `laburen.com opiniones reviews clientes`
- **Google**: `laburen.com case study Hertz Audi Ford Yamaha agente IA`
- **GitHub**: `"laburen" org OR user search`
- **GitHub**: `"laburen.com" en README OR site`
- **YouTube**: `Sebastián Rinaldi Laburen entrevista`
- **YouTube**: `Laburen.com empleados IA demo`
- **Papers**: `AI agents adoption Latin America SMB case studies 2025 2026`

### 3. Estructura de Datos Esperada

```
laburen_profile:
  fundador: {nombre, trayectoria[], menciones_prensa[], linkedin_url, claims_directos[]}
  equipo: {directivos[], tamaño_reportado, crecimiento_2026}
  financiacion: {tipo: bootstrapped|funding, ronda?, monto?, fuente, fecha}
  stack_inferido:
    señal: {job_postings, dominio, integraciones, entrevistas}
    inferencia: string
    confianza: alta|media|baja
    framework_agentes_mencionado: agno|langchain|crewai|propio|ninguno
  pricing:
    plan: Pro|Business|Growth|Enterprise|Soy tu Claw
    precio_usd_mes: number
    fuente: {url, fecha}
    modalidad: self_service|contact_sales
  reputacion:
    plataforma: G2|Capterra|ProductHunt|Trustpilot|Reddit|LinkedIn
    presente: bool
    score: string
    quejas_recurrentes: [strings]
  cases_exito:
    cliente: Hertz|Audi|Ford|Yamaha|otros
    claim_publicado: string
    evidencia: {favorable[], desfavorable[], independiente: bool}
  implicaciones: [strings]
  limitaciones: [strings]
```

---

## Tema 3: Proyectos Open Source Similares

**Pregunta central**: ¿Existe algún proyecto OSS que combine Agno + multitenant + dashboard + onboarding?

### 1. Prompt de Investigación Profunda (Perplexity)

**Enfoque Sugerido**: Web
**Herramientas Recomendadas**: Investigación Profunda

```markdown
Actuá como investigador técnico de ecosistemas open source especializado en plataformas de agentes AI. Ayudás a un equipo que construye una plataforma SaaS multitenant sobre Agno Framework (Python) y necesita saber: ¿qué proyectos OSS existentes combinan runtime de agentes + multitenancy + dashboard web + onboarding, y cuáles de ellos están construidos sobre Agno?

CONTEXTO Y OBJETIVO
Necesito un mapa exhaustivo (agosto 2026) de proyectos open source comparables y de templates/starter que puedan acelerar nuestro desarrollo. Prioridad: 1) proyectos que usan Agno/AgentOS como base con UI o multitenancy; 2) plataformas de agentes multitenant self-hosted en cualquier stack; 3) templates de dashboard para agentes. NO investigar herramientas de chatbot simples ni solo frameworks sin UI.

PISTAS CONFIRMADAS PARA PARTIR (verificar y expandir)
- repos agno-agi/agentos-railway y agno-agi/agent-platform-railway (AgentOS deployable, JWT + permisos).
- Plataformas OSS multitenant detectadas: Synkora (getsynkora/synkora-ai, MIT, multi-tenant workspaces, web UI, RAG, billing, HITL), PH Agent Hub (kainotomo, MIT, multi-tenant real con UI chat+admin), Agentbot (Eskyee/agentbot-opensource, Next.js 16 + shadcn/ui dashboard + onboarding wizard + Docker per-agent), mission-control (builderz-labs, dashboard de orquestación self-hosted).
- Plataformas conocidas a comparar: Dify (Apache 2.0, workspaces), LangFlow, Flowise, SuperAGI, AgentGPT, Open WebUI, n8n, Knowlee, CrewAI Enterprise, OpenClaw.

PLAN DE INVESTIGACIÓN
1. Rastrear en GitHub todo proyecto que combine "agno" con dashboard/admin/platform/saas: buscar "agno dashboard", "agno admin panel", "agno platform", "agno saas", "agno agentos ui", "agno nextjs". Incluir forks de agentos con UI agregada.
2. Para cada proyecto OSS encontrado, documentar: licencia, lenguaje/stack, stars, actividad (último commit), arquitectura (backend, frontend, DB), modelo multitenant (real vs multi-user), features (RAG, billing, HITL, canales), y si usa Agno u otro framework.
3. Comparar las plataformas grandes (Dify, LangFlow, Flowise, SuperAGI, AgentGPT, n8n, Open WebUI): ¿cuál tiene multitenancy real? ¿cuál tiene onboarding guiado? ¿alguna es extensible con Agno o Python puro?
4. Investigar starters/templates de AgentOS con UI: ¿hay templates oficiales o comunitarios de dashboard para AgentOS? ¿qué UI usan (Gradio, Streamlit, Next.js, React Admin)?
5. Evaluar qué stack de dashboard usan los proyectos top (Next.js+shadcn/ui vs React Admin vs Streamlit) y qué patrones de onboarding implementan (wizards, cuestionarios de diagnóstico).
6. Identificar los 3-5 proyectos MÁS REUTILIZABLES para nuestro caso (Agno + Python backend + dashboard multitenant) y justificar.

CONSULTAS DE BÚSQUEDA SUGERIDAS
- "agno dashboard admin panel platform github"
- "agno agentos ui starter template"
- "open source AI agent platform multi-tenant self-hosted"
- "Dify multitenant vs LangFlow vs Flowise comparison 2026"
- "agent platform open source dashboard agents"

MANEJO DE INFORMACIÓN FALTANTE O CONFLICTIVA
- Un repo sin commits recientes (>6 meses) debe marcarse como "inactivo/abandonado" y NO recomendarse como base sin advertencia.
- Si un proyecto dice "multi-tenant" pero la documentación no muestra aislamiento de datos, marcarlo como "multi-user" por defecto (distinción crítica).
- No confundir frameworks (LangGraph, CrewAI) con plataformas (Dify, Flowise): clasificar explícitamente.

FORMATO DE SALIDA
1. Resumen ejecutivo: ¿existe un proyecto OSS que haga TODO (Agno + multitenant + dashboard + onboarding)? ¿Sí/No y cuál es lo más cercano?
2. Tabla maestra de proyectos: nombre, URL, licencia, stack, stars, actividad, multitenant (real/user), UI (sí/no, tipo), onboarding (sí/no), framework base.
3. Sección "Proyectos sobre Agno/AgentOS": detalle de cada uno con patrón de UI y aislamiento usado.
4. Análisis de gaps: qué features de nuestro roadmap (onboarding guiado tipo laburen, diagnóstico automatizado) ningún OSS resuelve hoy.
5. Recomendación: ¿forkear un proyecto, usar un starter, o construir dashboard propio sobre AgentOS? Con tradeoffs.
Citar en línea con [1][2]. NO incluir bibliografía final; solo citas en línea.
```

### 2. Queries de Búsqueda Específicas

- **Google**: `open source AI agent platform multi-tenant self-hosted 2026`
- **Google**: `agno framework dashboard admin panel platform github`
- **Google**: `Dify vs Flowise vs LangFlow multitenant comparison 2026`
- **GitHub**: `agno dashboard` (topic/code search)
- **GitHub**: `"agno" "dashboard" OR "admin" OR "platform" language:Python`
- **GitHub**: `topic:multi-tenant topic:ai-agents topic:self-hosted`
- **GitHub**: `fork:true agno-agi/agentos-railway`
- **YouTube**: `open source agent platform dashboard self-hosted demo`
- **Papers**: `design patterns multi-tenant AI agent platforms survey 2026`

### 3. Estructura de Datos Esperada

```
oss_landscape:
  proyectos:
    nombre: string
    url_github: string
    licencia: MIT|Apache-2.0|otra
    stack: {backend, frontend, db}
    stars: number
    ultimo_commit: date
    actividad: activo|mantenimiento|abandonado
    multitenant: real|multi_user|ninguno
    aislamiento: {nivel, mecanismo}
    ui: {existe: bool, tipo: nextjs|react_admin|streamlit|gradio|otro}
    onboarding_guiado: bool
    framework_agentes: agno|langchain|crewai|langgraph|propio|ninguno
    features: [billing, rag, hitl, canales, api_publica]
  proyectos_agno: [nombres que usan agno/agentos]
  templates_agentos_ui: [{nombre, ui, url}]
  comparativa_mayores:
    plataforma: Dify|LangFlow|Flowise|SuperAGI|AgentGPT|n8n|OpenWebUI
    multitenant: bool
    onboarding: bool
    extensible_python: bool
  gaps_detectados: [strings]
  recomendacion: {estrategia, justificacion, tradeoffs}
  limitaciones: [strings]
```

---

## Tema 4: Dashboard + Panel de Administración + Onboarding

**Pregunta central**: ¿Cuál es el stack más eficiente para construir un dashboard multitenant con onboarding guiado para agentes Agno?

### 1. Prompt de Investigación Profunda (Perplexity)

**Enfoque Sugerido**: Web
**Herramientas Recomendadas**: Investigación Profunda

```markdown
Actuá como arquitecto frontend/fullstack especializado en SaaS B2B multitenant y en productos de agentes AI. Ayudás a un equipo con backend Python sólido (Agno Framework + capa declarativa YAML propia + librería de infraestructura core-cenf-py con Ports/Adapters) que ahora necesita la capa comercial: dashboard web multitenant + panel de administración + sistema de onboarding guiado estilo laburen.com (cuestionario → diagnóstico → roadmap de agentes con ROI).

CONTEXTO Y OBJETIVO
Necesito una recomendación de stack y patrones de producto (agosto 2026) para construir: 1) dashboard del cliente (gestión de sus agentes, sessions, usage, billing); 2) panel de administración de la plataforma (gestión de tenants, usuarios, agentes globales, planes); 3) onboarding guiado tipo wizard que genere un "diagnóstico gratuito" automatizado y un roadmap de agentes con ROI proyectado. El backend ya expone APIs (AgentOS tiene 50+ endpoints SSE/WebSocket) y autenticación JWT. La decisión de stack es de alto impacto: queremos velocidad sin sacrificar control del UI ni aislamiento multitenant.

PISTAS CONFIRMADAS PARA PARTIR (verificar y expandir)
- Ecosistema 2026: Next.js 16 + React 19 + TypeScript + Tailwind v4 + shadcn/ui es el stack dominante para dashboards; Refine (35k+ stars, MIT, headless, vive dentro de Next.js, tiene guía de multitenancy y useStepsForm para wizards) vs React-Admin (MUI, SPA propia, EE paga desde ~€145/mes con RBAC/audit) vs AdminJS (auto-generado desde ORM, requiere servidor Node aparte).
- Templates: Apex/Signal/Flux (Next.js 16 + shadcn/ui), TanStack Table, React Query, Recharts.
- Referencia funcional: laburen.com ofrece diagnóstico gratuito + onboarding guiado con preguntas + auditoría de procesos + roadmap de agentes con ROI.
- Autenticación: NextAuth/Auth.js, Clerk, Logto (free tier 50k MAU), Keycloak.

PLAN DE INVESTIGACIÓN
1. Mejores prácticas de onboarding para plataformas de agentes AI: patrones de wizard step-by-step, progressive profiling (el usuario responde preguntas → el sistema sugiere agentes), "diagnóstico gratuito" automatizado (cuestionario → roadmap de agentes → ROI proyectado). Buscar casos documentados (laburen, otros players de "AI employees", SaaS de automatización) y métricas de conversión si existen.
2. Comparativa de frameworks de dashboard 2026: Refine vs React-Admin vs AdminJS vs shadcn/ui puro para nuestro caso (multitenant + admin interno + customer dashboard). Evaluar: multitenancy support nativo, server components/SSR, auth providers, cost, curva.
3. Autenticación + autorización en frontend: patrones para integrar JWT de nuestro backend (AgentOS/IdP) con Next.js: session management, refresh tokens, route protection por rol (tenant admin vs platform admin vs user self-service), tenant context.
4. Aislamiento de datos en frontend: tenant context provider, row-level filtering en queries, prefetch por tenant, cómo evitar data leaks entre tenants en el cliente.
5. Patrones de admin panel: separación de áreas (platform admin vs tenant admin vs user self-service), gestión de tenants (crear/suspender/plan), métricas de uso por tenant.
6. Templates open source de "AI agent platform" con dashboard: qué se puede reutilizar (ver también Tema 3: Agentbot, Synkora, PH Agent Hub) y qué patrón de onboarding implementan.

CONSULTAS DE BÚSQUEDA SUGERIDAS
- "Refine vs React Admin vs shadcn/ui multitenant dashboard 2026"
- "AI agent onboarding wizard progressive profiling best practices"
- "Next.js multitenant SaaS auth role-based tenant context pattern"
- "onboarding questionnaire ROI roadmap agents AI sales"
- "open source AI agent dashboard Next.js shadcn template"

MANEJO DE INFORMACIÓN FALTANTE O CONFLICTIVA
- Las métricas de conversión de onboarding (p.ej. % de usuarios que completan el wizard) suelen ser datos propietarios: indicar cuando no haya evidencia pública y basarse en best practices de SaaS onboarding (signup-to-activation) documentadas.
- Distinguir opiniones de vendors (blogs de Refine/React-Admin) de evaluaciones independientes.

FORMATO DE SALIDA
1. Resumen ejecutivo: stack recomendado con justificación en 5 bullets.
2. Comparativa de frameworks de dashboard (tabla: framework, modelo (headless/opinionado), Next.js fit, multitenancy, auth, costo, estrellas, casos de uso ideales).
3. Arquitectura frontend propuesta: separación de rutas (customer dashboard / tenant admin / platform admin), tenant context, patrones de data fetching con aislamiento.
4. Patrones de onboarding: desglose del wizard de diagnóstico (pasos, datos capturados, lógica de generación de roadmap/ROI, triggers de conversión).
5. Stack de autenticación recomendado con flujo de sesión JWT.
6. Riesgos y decisiones de tradeoff (p.ej. SSR vs SPA, costos de templates premium).
Citar en línea con [1][2]. NO incluir bibliografía final; solo citas en línea.
```

### 2. Queries de Búsqueda Específicas

- **Google**: `Refine vs React Admin 2026 multitenant admin panel Next.js`
- **Google**: `SaaS onboarding wizard best practices activation rate progressive profiling`
- **Google**: `Next.js multitenant SaaS architecture tenant isolation frontend`
- **Google**: `AI agent platform dashboard template open source 2026`
- **GitHub**: `topic:nextjs-dashboard topic:saas topic:multitenant`
- **GitHub**: `"agent dashboard" OR "agents dashboard" language:TypeScript`
- **YouTube**: `SaaS onboarding wizard UI/UX best practices`
- **YouTube**: `Refine framework multitenant tutorial`
- **Papers**: `progressive profiling personalization SaaS onboarding AI 2026`

### 3. Estructura de Datos Esperada

```
dashboard_stack_recomendacion:
  stack:
    framework: refine|react_admin|adminjs|shadcn_puro|otro
    version_2026: string
    ui_library: shadcn|mui|ant|tailwind
    charting: recharts|otro
    table: tanstack_table
    data_fetching: react_query|server_components
  comparativa_frameworks:
    framework: string
    modelo: headless|opinionado|autogenerado
    nextjs_fit: bueno|medio|malo
    multitenancy_support: nativo|guia|ninguno
    auth_providers: [nextauth, clerk, logto, keycloak, custom]
    costo: {core, enterprise_ee_usd_mes}
    stars: number
  onboarding_patterns:
    wizard_pasos: [{paso, datos_capturados, objetivo}]
    diagnostico_automatizado: {inputs, outputs, motor_roadmap, calculo_roi}
    progressive_profiling: bool
    metricas_conversion_publicas: string|none
  frontend_arquitectura:
    rutas: [customer_dashboard, tenant_admin, platform_admin]
    tenant_context: {provider, propagacion, prevencion_leaks}
    auth_flow: {session, refresh, route_guards}
  admin_panel_patterns:
    platform_admin: [gestion_tenants, planes, metricas_globales]
    tenant_admin: [gestion_agentes, usuarios, usage, billing]
  riesgos: [strings]
  limitaciones: [strings]
```

---

## Tema 5: Keycloak vs Casbin vs OpenFGA vs Logto — Decisión Diferida

**Pregunta central**: Dado que Agno ya tiene JWT+RBAC nativo, ¿necesitamos un sistema externo de autorización o podemos extender el nativo?

### 1. Prompt de Investigación Profunda (Perplexity)

**Enfoque Sugerido**: Web
**Herramientas Recomendadas**: Investigación Profunda

```markdown
Actuá como arquitecto de seguridad especializado en autorización para plataformas de agentes AI. Ayudás a un equipo que construye una plataforma SaaS multitenant sobre Agno Framework (que YA incluye JWT-based RBAC nativo con scopes jerárquicos y user_isolation opt-in para sessions, memory, traces y approvals). La decisión en juego: ¿extendemos el RBAC nativo de Agno, o integramos un sistema externo (Keycloak, Casbin, OpenFGA, Logto)?

CONTEXTO Y OBJETIVO
Necesito un informe de decisión (agosto 2026) con evidencia actualizada sobre: extensibilidad real del RBAC de Agno; adecuación de cada alternativa para un modelo de autorización `tenant → role → agent → resource → action`; costo operativo; y patrones que usan plataformas comparables (Dify, LangFlow, Flowise, Synkora, PH Agent Hub). El equipo valora: simplicidad operativa, bajo costo inicial, y no duplicar lo que Agno ya resuelve. Decisión diferida: primero auditar (Tema 1), luego decidir — este informe debe entregar criterios y umbrales, no solo una respuesta.

PISTAS CONFIRMADAS PARA PARTIR (verificar y expandir)
- Agno RBAC nativo: JWT middleware con scopes (claim `scopes`, configurable vía `scopes_claim` para WorkOS `permissions`), scopes jerárquicos por endpoint (agents, teams, workflows, components), user_isolation opt-in en AuthorizationConfig, multi-issuer self-hosted soportado, ejemplos con JWTs asimétricos (RS256) y custom scope mappings.
- Opciones externas: Casbin/pycasbin (librería embebida, PERM metamodel, RBAC/ABAC/ACL, múltiples adapters de storage, $0 self-hosted), OpenFGA (CNCF, Zanzibar-style ReBAC, servicio externo, SDKs multi-lenguaje), Keycloak (IAM completo, gratuito OSS pero pesado en operación, token exchange RFC 8693 para agentes delegados, integración MCP), Logto (auth moderna OIDC/OAuth 2.1, multi-tenancy, RBAC, free tier ~50k MAU).
- Comparativas públicas 2026 existentes: OpenFGA vs Casbin, Logto vs Keycloak, top 7 herramientas OSS de autorización (incluye OPA, Cerbos, Oso, SpiceDB, Ory Keto, Cedar, Permify).

PLAN DE INVESTIGACIÓN
1. Extensibilidad del RBAC de Agno: ¿puede un middleware custom extender/reescribir scopes? ¿hay hooks de autorización? ¿qué pasa con permisos a nivel de TOOL/recursos individuales dentro de un agente (p.ej. qué tool puede llamar qué usuario)? Verificar en docs, código y ejemplos de RBAC.
2. Casbin embebido (pycasbin): ¿es suficiente para `tenant → role → agent → resource → action`? Evaluar modelo PERM, filtered policy management, integración con FastAPI/AgentOS, y límites (sin relaciones tipo Zanzibar).
3. OpenFGA: ¿cuándo justifica un servicio externo (complejidad relacional, delegación, organizaciones anidadas)? Costo operativo y latencia de checks.
4. Keycloak: ¿es necesario como IdP si Agno acepta cualquier JWT firmado con la clave correcta? Evaluar el patrón "Agno como resource server + IdP externo que emite tokens" vs "Agno emite sus propios tokens". Costo en Cloud Run ($13-57/mes reportado) vs Logto Cloud free tier vs Casbin self-hosted ($0).
5. Cómo manejan la autorización plataformas comparables (Dify, LangFlow, Flowise, Synkora, PH Agent Hub, Open WebUI): patrones documentados (workspaces, orgs, RBAC propio, OIDC).
6. Estado del arte 2025-2026 en autorización para agentes AI: papers y artículos sobre agent identity, tool-level authorization, MCP auth (OAuth 2.0 + token exchange), consent, y auditoría de acciones de agentes.

CONSULTAS DE BÚSQUEDA SUGERIDAS
- "Casbin vs OpenFGA vs OPA authorization model comparison 2026"
- "Keycloak vs Logto pricing free tier 2026"
- "AI agent authorization tool-level permissions OAuth token exchange MCP"
- "Dify multitenant RBAC authorization implementation"
- "Agno AgentOS custom middleware authorization extension"

MANEJO DE INFORMACIÓN FALTANTE O CONFLICTIVA
- Los costos de infraestructura dependen del proveedor y región: reportar rangos con fuente y fecha, no cifras únicas.
- Si Agno no documenta un hook de autorización, indicarlo como "no documentado; verificar en código fuente" en lugar de asumir que existe.
- Distinguir requisitos actuales (equipo chico, pocos tenants) de requisitos futuros (enterprise, delegación compleja): la recomendación debe escalonarse en el tiempo.

FORMATO DE SALIDA
1. Resumen ejecutivo: ¿extender nativo, o integrar externo? Con escenario temporal (ahora / 6-12 meses / 18+ meses).
2. Análisis de extensibilidad de Agno (qué se puede lograr con middleware/scopes custom, con ejemplos si existen).
3. Matriz de decisión: opción (nativo extendido, pycasbin, OpenFGA, Keycloak, Logto) × criterios (aislamiento, granularidad, delegación, costo, operación, madurez) con puntuación y justificación.
4. Patrones de la industria: tabla de plataformas comparables y su enfoque de autorización.
5. Costo operativo: tabla con rangos mensuales por opción y fuentes.
6. Decisión recomendada con umbrales explícitos (N tenants, N roles, presencia de delegación/ReBAC).
7. Riesgos de seguridad específicos de agentes (tool-level leaks, token scope creep) y cómo mitigarlos.
Citar en línea con [1][2]. NO incluir bibliografía final; solo citas en línea.
```

### 2. Queries de Búsqueda Específicas

- **Google**: `Casbin vs OpenFGA vs OPA vs Cerbos 2026 authorization tools comparison`
- **Google**: `Keycloak vs Logto pricing free tier OIDC multi-tenant`
- **Google**: `OAuth 2.0 token exchange AI agent delegated access MCP`
- **Google**: `authorization for AI agents tool level permissions 2026`
- **GitHub**: `repo:casbin/pycasbin examples rbac tenant`
- **GitHub**: `topic:openfga topic:ai-agents OR topic:agent`
- **GitHub**: `repo:agno-agi/agno "middleware" OR "authorization"`
- **YouTube**: `OpenFGA Zanzibar authorization explained`
- **YouTube**: `Casbin RBAC Python tutorial FastAPI`
- **Papers**: `fine-grained authorization AI agents Zanzibar ReBAC 2025 2026`

### 3. Estructura de Datos Esperada

```
autorizacion_decision:
  agno_extensibilidad:
    hooks_middleware: [strings|none]
    custom_scopes: bool
    tool_level_permissions: {soportado: bool, mecanismo}
    documentos_clave: [urls]
  opciones:
    opcion: nativo_extendido|pycasbin|openfga|keycloak|logto
    tipo: embebido|servicio_externo|idp
    modelo: rbac|rebac|abac|acl
    adecuacion_modelo_tenant_role_agent_resource_action: alta|media|baja
    costo_usd_mes: {rango, fuente, fecha}
    operacion: {complejidad, mantenimiento}
    madurez: {stars, licencia, comunidad}
  industria:
    plataforma: Dify|LangFlow|Flowise|Synkora|PH_Agent_Hub|OpenWebUI
    enfoque_autorizacion: string
  criterios_escalonados:
    fase_actual: recomendacion
    fase_6_12m: recomendacion
    fase_18m: recomendacion
    umbrales: [{variable: tenants|roles|relaciones, valor: number, desencadena: opcion}]
  riesgos_agentes: [strings]
  limitaciones: [strings]
```

---

## Notas de Ejecución (cómo usar estos prompts)

1. **Orden recomendado de ejecución**: Tema 1 (auditoría Agno) → Tema 5 (decisión de autorización, dependiente del 1) → Tema 4 (stack dashboard, dependiente de qué APIs expondremos) → Tema 3 (reutilizar OSS) → Tema 2 (competidor, puede correr en paralelo).
2. **Configuración en Perplexity/DeepResearch**: usar **Investigación Profunda** para los 5 temas (son multi-parte y de alto riesgo). Si se quiere una pasada rápida inicial, usar **Búsqueda Profesional** con las queries listadas en la sección 2 de cada tema.
3. **Fecha límite de datos**: indicar explícitamente "hasta agosto 2026" en cada ejecución para evitar datos obsoletos.
4. **Verificación cruzada**: para Tema 1 y Tema 5, pedir que los hechos de Agno se verifiquen contra docs.agno.com Y el repo agno-agi/agno (dos fuentes independientes).
5. **Salidas**: cada informe debe cerrarse con una sección de "Implicaciones para CENF" que alimente directamente la decisión de arquitectura (SPEC_19 → siguiente fase) y el roadmap de dashboard.
