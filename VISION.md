# VISION.yaml-agno

> **Documento consolidado de la visión del proyecto yaml-agno**
>
> Fuente: conversación completa del 30-may-2025 al 02-jun-2026
> (sesión Claude Code `fb784b73-84e5-4817-848d-fc21638b22a1`).
> Objetivo: que un agente lea TODO en un solo mensaje y entienda la visión completa.

---

## 0. RESUMEN EJECUTIVO (TL;DR)

**yaml-agno** es una librería pip-installable que permite definir **agentes, equipos
y workflows de Agno enteramente en YAML**, sin escribir Python para las features
built-in. Se complementa con un **meta-agente** (equipo agéntico de documentación
y codificación de Agno + equipo de prompting/ingeniería de contexto) que ayuda a
programar sobre yaml-agno.

**Fase 1 (ahora)**: yaml-agno como herramienta interna de **CENF** (consultora
argentina) para dar a clientes equipos agénticos para tareas reales (facturación
AFIP, procesamiento de Excel, emails, meetings, SAP, etc.).

**Fase 2 (futuro)**: **Ambots-Hs** — sistema agéntico open-source donde el usuario
final, hablando con su Ambots personalizado, genera y configura sus propios equipos
agénticos de forma autónoma, apoyado en la arquitectura de yaml-agno.

**Norte conceptual**: la configuración básica debe ser **estructurada y repetible**
para que el agente (al momento de codificar) **no tenga que razonar profundo sobre
config**. El razonamiento profundo se reserva para: **definir el equipo, los prompts
de cada agente y las tools custom** que no trae Agno.

---

## 1. CONTEXTO INSTITUCIONAL

### 1.1 CENF
- **Consultora argentina** (escribiste "SEMP" una vez por typo).
- **NO programa directamente**: usa agentes de programación (OpenCode, ClaudeCode,
  Antigravity) para generar código y configs.
- **Stack existente de la consultora**:
  - Python + FastAPI + Pydantic
  - PostgreSQL, Qdrant, Redis
  - fastMCP para comunicación inter-agentes
  - Goose como GUI / capa de presentación

### 1.2 Ambots-Hs (visión a largo plazo, NO existe todavía)
- **amBotHs** = "am" de "I am" Bot (IA) + "HS" de Human-System (humanos), hace referencia a "ambos" (Humano + Máquina)
- Visión open-source: cualquier usuario final, hablando con su Ambots personalizado
  en lenguaje natural, podría generar sus propios equipos agénticos.
- **Capa core (referencia futura)**: `MASTER_OpenSpec_Core_Infra_SOTA_2026.md`
- **Idea original (referencia histórica)**: `Descripción Proyecto AmBtoHs 30.05.2025.txt`

### 1.3 Estado del proyecto
- **Ambots NO está construido** — es una idea/visión arquitectónica.
- Lo que compartiste inicialmente al asistente "no es la última versión, fue lo
  que empezamos con poco conocimiento". El brief actual es la versión consolidada.

---

## 2. EL PROBLEMA QUE RESOLVEMOS

### 2.1 El problema de los agentes generalistas (skills)
Hoy en CENF usan agentes generalistas (CloudCode, OpenCode, Antigravity) que tienen:
- Mucho system prompt propio (delegación, subcreación de agentes)
- Carga cognitiva alta que los hace MALOS para automatizaciones específicas

**Equipos agénticos son mejores porque**:
- Son abstractos y autónomos
- Tienen misión clara
- Se comunican estructuradamente con el orquestador
- El agente de programación (Gus/Cloud) solo los coordina, NO ejecuta la tarea

### 2.2 Validación: Skills → Teams
**Metodología CENF**:
1. Resolver tarea con agente de programación + skills
2. Si funciona → transformar en equipo agéntico yaml-agno
3. Equipo queda disponible como endpoint reutilizable

**Por qué funciona**: si el agente de programación puede hacerlo, el team también.
Cada vez que CENF arma un equipo agéntico para un cliente:
- Arquitectura diferente
- Prompts escritos de forma distinta
- Configuraciones (temperatura, tokens, learning) en variables distintas
- **Tu gente (el agente) tiene que razonar profundo CADA VEZ**
- Resultado: no escalable, no repetible, caótico

### 2.3 Lección aprendida: NO al frankestin (por eso yaml-agno)
**Ya intentaste esto antes con un agente de IA. Terminó en un frankenstein**:
- Parches sin diseño
- **Reescribiendo código que Agno ya resolvía por sí mismo**
- No funcionó ni siquiera reescribiendo.

**Implicación para yaml-agno**:
- ❌ NO es "pegar código al estilo frankestin"
- ❌ NO es reescribir features que Agno ya trae
- ✅ Es **diseño desde cero** apoyándose en Agno
- ✅ Es **abstraer lo que se repite**, no todo

---

## 3. LA SOLUCIÓN: yaml-agno

### 3.1 Qué ES
- **Librería Python pip-installable**
- Capa de configuración declarativa sobre **Agno Framework**
- Patrón: **YAML → Pydantic → Factory**
- Permite definir: agentes, equipos, workflows, tools, knowledge, memory, storage,
  model providers, context providers, scheduler, en YAML.

### 3.2 Qué NO ES
- ❌ No es un orquestador (eso es Ambots/Ambots-Hs)
- ❌ No es una UI (eso es Goose)
- ❌ No es un sistema completo (eso es Ambots-Hs)
- ❌ No es "abstraer todo Agno" — es abstraer **lo que se repite** (~80% de casos)

### 3.3 Principios de diseño

1. **Sin Python para features built-in de Agno**. Solo se escribe Python "chiquito"
   para tools que Agno **no trae** o que son **específicas del cliente**.

2. **Caja negra para el cliente, estructura clara para el developer**.
   El cliente ve al agente como **input + output** (no le importa qué hay dentro).
   El developer ve la estructura clara del YAML.

3. **Agente = caja negra con contrato**. Cada agente/team/workflow se define con:
   - **Qué hace** (misión)
   - **Qué espera recibir** (input schema)
   - **Qué devuelve** (output schema)
   - **De qué depende** (otros teams a los que necesita llamar)
   - **Cómo se comunica** (MCP para herramientas / A2A nativo de Agno para inter-agente)

4. **Composición por interconexión**. Las cajas negras se interconectan entre sí
   o con el usuario directamente. Esa red se apoya sobre equipos agénticos
   realizados en Agno.

5. **Carga dinámica de YAMLs desde DB** + endpoints dinámicos en AgentOS.

6. **El razonamiento profundo va a un solo lugar**: **cómo es el equipo, los
   prompts de cada agente y las tools custom**. El resto (temperatura, tokens,
   learning, formato) es config estructurada y repetible.

### 3.4 Features de la librería

| Feature | Estado MVP | Notas |
|---|---|---|
| `ref://` URI scheme para registry | ✅ MVP | Equipos "llamables" con interfaz estructurada |
| `${ENV_VAR}` interpolation | ✅ MVP | Para secrets, configs por entorno |
| Pipeline validación: YAML → env var → Pydantic → Registry → Factory | ✅ MVP | |
| Hot-reload | ✅ MVP | Recargar configs sin restart |
| Multi-file projects + manifest | ✅ MVP | |
| Strict TDD 100%+ coverage | ✅ MVP | Obligatorio |
| CEL + Callables | ✅ MVP | Ambos desde día 1, no uno después del otro |
| Multi-tenant storage | ✅ MVP | |
| CodeGraph (integración) | ✅ MVP | Repo externo: https://github.com/colbymchenry/codegraph |

### 3.5 La ambigüedad CEL vs Callable (resuelta)
Algunos campos de Agno aceptan DOS tipos:
- **Callable**: función Python (referencia a registry con `ref://`)
- **CEL string**: expresión CEL de Google, directa en YAML

**Resolución**:
- Si `evaluator` es string → tratar como CEL
- Si `evaluator` tiene `ref://` → buscar en registry
- Validar sintaxis CEL
- Documentar claramente en specs

### 3.6 Integración con CodeGraph
- **CodeGraph** = grafo semántico del código Agno (clases, funciones, imports,
  herencia, FTS). Repo: https://github.com/colbymchenry/codegraph
- Es **parte del equipo agéntico de apoyo al agente de programación**
- **NO se carga en runtime** de yaml-agno — solo en autoría
- Permite a los subagentes consultar el grafo, no solo docs en prosa

---

## 4. CASOS DE USO REALES (no hipotéticos)

### 4.1 Facturación CENF + AFIP
> "Pongámosle nuestro manejador de facturas, generador de facturas de CENF, que se
> conecta a un equipo agéntico que se conecta y tiene los datos de la API para
> conectarse a AFIP y genera la factura en función de lo que el usuario le dijo:
> signo pesos, crear factura a su orquestador para cliente tal, código X, monto Y,
> leyenda Z, el equipo va y hace."

Input: comando estructurado (`#crear factura cliente=X monto=Y leyenda=Z`)
Output: factura electrónica emitida en AFIP

### 4.2 Estudio contable: Excel SAP
> Cliente: contador con Excel que llena y verifica.
> Equipo agéntico: recibe Excel + directivas de prompting + directivas del usuario.
> Cada subagente resuelve "una parte chiquitita" (leer SAP, validar reglas, etc.).
> Output: Excel lleno y validado, o mensaje de validación.

### 4.3 Workflow repetitivo del cliente (la metodología CENF)
1. Vamos a un nuevo cliente, **grabamos video**, nos cuenta las reglas de negocio
2. Definimos el equipo agéntico de las reglas de negocio
3. Obtenemos prompting + tools necesarias (leer Excel específico, saber dónde está cada cosa)
4. Resolvemos la tarea
5. **Se guarda en un paquete de equipo agente** y queda disponible como **endpoint**
   para llamar de manera repetitiva

### 4.4 Otros casos mencionados
- Generación de ofertas comerciales
- Manejo de base de costos contables
- Lectura de emails + generación de respuestas
- Resúmenes de reuniones (Google Meet)
- Conexión a Gmail + Node.plm + generación de infografías
- Generación de procedimientos (crear carpeta de clientes, hacer seguimiento, etc.)

---

## 5. ARQUITECTURA (por fases)

### 5.1 FASE 1: yaml-agno solo (MVP — el AHORA)
- Librería pip-installable
- Solo CENF, sin Ambots
- El agente de programación de CENF genera YAMLs usando:
  - **CodeGraph** (MCP, autoria)
  - **MCP de docs de Agno** (siempre en ejecución)
  - **MCP propio de codificación de Agno** (futuro, todavía en desarrollo)
- Carga dinámica desde DB → endpoints dinámicos en AgentOS

### 5.2 FASE 2: yaml-agno + agente de programación + equipo agéntico
- CENF integra a su agente de programación un **equipo agéntico de apoyo** con:
  - **Agno Expert** (docs + codificación de Agno + CodeGraph)
  - **Prompting Expert** (mejores prácticas de prompting)
  - **Model Selector** (cuál modelo para cada caso)
- Este equipo se apoya sobre yaml-agno mismo
- Permite generar equipos agénticos para clientes de forma autónoma

### 5.3 FASE 3: Ambots-Hs (visión open-source)
- Usuario final habla con su Ambots personalizado
- Ambots conoce la misión, visión y objetivos del usuario
- Ambots tiene todos los recursos disponibles (CodeGraph, Agno, prompting, etc.)
- Ambots puede **crear nuevos equipos agénticos** o llamar a los existentes
- El usuario final no programa: habla en lenguaje natural
- **El equipo agéntico NO se crea directamente** — se crea a través del agente
  de programación + la arquitectura (yaml-agno es el DSL que el agente de
  programación usa)

### 5.4 Diagrama de la visión completa (referencia)
```
┌─────────────────────────────────────────────────────────────────┐
│                       FASE 3: AMBOTS-HS                         │
│  Usuario Final → Ambots (orquestador personalizado)             │
│                          │                                       │
│                          ▼                                       │
│                 Agente de Programación                            │
│                          │                                       │
│                          ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          Equipo Agéntico de Apoyo (yaml-agno)             │   │
│  │  ┌────────────┐ ┌──────────────┐ ┌──────────────────┐    │   │
│  │  │ Agno       │ │ Prompting    │ │ Model Selector   │    │   │
│  │  │ Experts    │ │ + Ing.Contexto│ │                  │    │   │
│  │  │ + CodeGraph│ │              │ │                  │    │   │
│  │  └────────────┘ └──────────────┘ └──────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          ▼                                       │
│                yaml-agno configs                                  │
│                          │                                       │
│                          ▼                                       │
│              Agno runtime + fastAPI                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. META-AGENTES: los primeros entregables (CRÍTICO)

Confirmaste explícitamente que **los primeros equipos agénticos a construir son
internos**, no para clientes:

### 6.1 Equipo agéntico de documentación y codificación de Agno
- Tiene el **MCP de docs de Agno** (existente)
- Tiene el **MCP de codificación de Agno** (a construir, expone CodeGraph)
- Tiene **CodeGraph** integrado (https://github.com/colbymchenry/codegraph)
- Sabe cómo Agno está documentado Y cómo Agno está codificado
- **Por qué primero**: sin esto, el agente de programación no puede generar
  yaml-agno configs válidas.

### 6.2 Equipo agéntico de prompting e ingeniería de contexto para agentes
- Mejores prácticas de prompting (extraídas de los mejores agentes del mundo)
- Ingeniería de contexto: cómo estructurar el contexto que recibe un agente
- **Por qué primero**: sin esto, los prompts de cada team en yaml-agno son
  inconsistentes y volvemos al caos de las skills.

### 6.3 Por qué estos dos son MVP
> *"el meta-agente que guía la programación sobre yaml-agno es uno de los primeros
> equipos agénticos que deberíamos realizar porque junto con el de prompting e
> ingeniería de contexto para agentes son necesarios en sí mismos para poder usar
> y programar sobre Agno, y obviamente si lo tenemos hecho sobre yaml-agno"*

**Secuencia de dependencias**:
1. yaml-agno mínimo (Phase 1 del SDD)
2. Meta-agente construido sobre yaml-agno mínimo
3. Resto de equipos agénticos para clientes

---

## 7. COMUNICACIÓN ESTRUCTURADA / INTERCONOCIMIENTO COGNITIVO

### 7.1 Concepto
> *"Cada uno de estos equipos vive en un mundo autónomo pero sabe cómo se
> interconecta. Tienen una condición cognitiva de interconocimiento: el
> orquestador sabe todos los equipos agénticos que tiene y para qué funciona
> cada uno."*

**Clave**: El agente del usuario (Cloud/Gus) y el equipo agéntico deben saber:
- Qué les va a llegar (input schema)
- Cómo les van a hablar (prompting del sistema)
- Qué para qué sirve (misión)

**Si no hay este "interconocimiento cognitivo", no funcionan.**

### 7.2 Equivalente a skill, pero a nivel agéntico
Una skill hoy expone: nombre + descripción breve de para qué funciona.
Un equipo agéntico en Ambots-Hs expone: **la misma metadata, pero con
capacidades ejecutables reales y contrato de input/output**.

### 7.3 Protocolos soportados
- **MCP** (Model Context Protocol): exposición de capacidades como herramientas.
- **A2A** (Agent-to-Agent): comunicación directa entre agentes — **estándar nativo
  de Agno** (`agno/os/interfaces/a2a/`), expone `agent-card.json` + `message:send`/
  `message:stream`; consumible vía `A2AClient` y `RemoteAgent/Team/Workflow`.

> **ACP eliminado del alcance.** En la evolución de la arquitectura se descartaron
> protocolos experimentales no soportados por el runtime: **ACP no existe en Agno**
> (verificado en código fuente). La comunicación inter-agente y la exposición de
> capacidades se realiza exclusivamente mediante **A2A nativo de Agno**
> (inter-agente) complementado por **MCP** (herramientas). Ver SPEC_26
> (A2A Interface) y SPEC_05 (workflows/teams).

### 7.4 Metadatos cognitivos (lo que yaml-agno debe poder declarar)

> **`cognitive_profile` NO es un protocolo de transporte.** Es el **contrato
> declarativo** de entrada/salida y dependencias que un equipo expone en su
> `AgentCard` (a través de A2A) y en su esquema de Pydantic V2 (SPEC_02). Es la
> metainformación que permite a Gus/Cloud (el agente programador) **interconectar
> cajas negras** y validar que encajen los contratos input/output. Vive como
> slots opacos en `AgentConfig` (SSOT SPEC_02), no como una API de mensajería.

```yaml
cognitive_profile:
  mission: "Generate invoices for CENF clients via AFIP"
  capabilities:
    - "Connect to AFIP API"
    - "Generate PDF invoices"
    - "Validate tax codes"
  input_schema: "InvoiceRequest"
  output_schema: "InvoiceResult"
  dependencies:
    - team: "profiler"
      reason: "Get client tax information"
  communication_protocols:
    - type: "MCP"
      endpoint: "/mcp/generate_invoice"
    - type: "A2A"
      method: "query_user_profile"
```

### 7.5 Compartición de recursos
Equipos distintos pueden compartir agentes (ej: "perfilador" compartido entre
team de Facturas, team de Emails, team de Meetings).

---

## 8. CONSTRAINTS Y CONVENCIONES (acordados con el asistente)

### 8.1 Metodología de desarrollo
- **Strict TDD con 100%+ coverage** (obligatorio)
- **200-250 líneas máximo por PR** (budget ajustado, no 400)
- **feature-branch-chain** para PRs encadenados
- **Granularidad máxima en commits** (máxima trazabilidad y rollback posible
  tanto en git como en Engram)
- **gitflow** como branching model base

### 8.2 Constraints en specs
- **Usar `mcp agno-docs` SIEMPRE** en la ejecución + delegar a subagentes con
  esa capacidad
- **Mantener patterns de diseño y codestyle de Agno** en:
  - El código Python de la librería yaml-agno
  - Las convenciones YAML que escriben los developers
- **Pipeline de validación**: YAML → env var → Pydantic → Registry → Factory

### 8.3 Decisiones de diseño tomadas
- ✅ **APPROACH B**: YAML → Pydantic → Factory
- ✅ **CEL + Callables desde día 1** (no uno después del otro)
- ✅ **Trust en Phase 1** definido por el agente
- ✅ **Carpeta de trabajo**: `C:\Dropbox\DOC.RECA\06-Software\yaml-agno`

---

## 9. OBJETIVOS

### 9.1 Corto plazo (3-6 meses)
1. yaml-agno MVP funcional (librería pip-installable)
2. Validar con 2-3 casos reales de CENF (facturación AFIP + estudio contable + algo más)
3. Construir los **dos meta-agentes** (docs/codificación Agno + prompting/ing contexto)
4. Iterar sobre la spec hasta que el flujo "agente de programación → yaml-agno
   → agente Agno ejecutándose" sea repetible

### 9.2 Mediano plazo (6-12 meses)
1. yaml-agno cubre ~80% de los casos reales de CENF
2. El equipo agéntico de apoyo al agente de programación es estable
3. Empezar a ofrecer equipos agénticos a clientes
4. Empezar a diseñar la interfaz de Ambots (proto, no full)

### 9.3 Largo plazo (12-24 meses)
1. Ambots-Hs como open-source
2. Cualquier usuario final, hablando con su Ambots, puede generar sus propios
   equipos agénticos de forma autónoma
3. Red de nodos de agentes interconectados vía A2A (nativo Agno) + MCP (tools)
4. El equipo agéntico se crea a través del agente de programación + la arquitectura
   (yaml-agno es el DSL que el agente de programación usa)

---

## 10. DICCIONARIO DE CONCEPTOS

| Término | Definición |
|---|---|
| **CENF** | La consultora (vos) |
| **Ambots-Hs** | amBotHs = "am" de "I am" Bot (IA) + "HS" de Human-System (humanos). Visión open-source: usuario final hablando con su Ambots puede generar equipos agénticos |
| **Ambots** | El agente principal con el que habla el usuario final en amBotHs (montado sobre Gus/Goose/OpenCode/CloudCode) |
| **Agente de programación** | El agente IA que CENF usa para generar código (OpenCode/ClaudeCode/Antigravity) |
| **yaml-agno** | La librería: capa YAML sobre Agno Framework |
| **Agno** | Framework de agentes de IA en Python |
| **CodeGraph** | Repo externo con grafo semántico del código Agno (https://github.com/colbymchenry/codegraph) |
| **MCP** | Model Context Protocol — para exposición de capacidades (tools de teams al orquestador) |
| **MSP** | NO es typo de MCP. Es la forma de incrustar el team al orquestador (vía MCP/skill/etc) |
| **A2A** | Agent-to-Agent — estándar nativo de Agno para comunicación inter-agente (AgentCard + message:send/stream) |
| **ACP** | ~~Agentic Communication Protocol~~ — **ELIMINADO del alcance**. No existe en Agno (verificado). Reemplazado por A2A nativo + MCP. |
| **CEL** | Common Expression Language (Google) — strings de lógica runtime |
| **Callable** | Función Python referenciable vía `ref://` |
| **ref://** | URI scheme de yaml-agno para referenciar entradas del registry |
| **Equipo agéntico** | Conjunto de agentes que colaboran para una tarea (en Agno: `Team`) |
| **Interconocimiento cognitivo** | Cada agente sabe qué otros existen y para qué sirven |
| **Equipo llamable** | Equipo expuesto con interfaz estructurada (input/output) y disponible para ser invocado |
| **AFIP** | Solo un EJEMPLO de caso de uso (facturación electrónica). NO es importante para yaml-agno, es solo ilustrativo |
| **Goose** | NOT Goose. Es **Gus** — agente de inteligencia sobre el que puede montarse amBotHs (confirmar con usuario) |
| **Skill (legacy)** | Forma actual de CENF: prompting + código. **PROBLEMA**: agente generalista tiene mucha carga cognitiva. Se reemplaza por equipos agénticos autónomos |
| **Context Providers (Agno)** | Metafora arquitectónica: Sub-agent architecture, read/write separation, namespace limpio. Similar a cómo los equipos agénticos se comunican con el orquestador |

---

## 11. REFERENCIAS A ARCHIVOS (no analizados en esta conversación)

| Ruta | Qué contiene | Estado |
|---|---|---|
| `C:\Dropbox\DOC.RECA\06-Software\yaml-agno\` | Carpeta de trabajo del proyecto yaml-agno | Vacía, por crear |
| `C:\Dropbox\DOC.RECA\03-CENF\03-Proyectos CENF\0003_2025-amBotHs\02-Descripción\Descripción Proyecto AmBtoHs 30.05.2025.txt` | Idea original de Ambots-Hs | Histórico, no es la última versión |
| `C:\Dropbox\DOC.RECA\03-CENF\05-Recursos\25-db_Prompt\development\core_infra_CENF\core-infrastructure\openspec\MASTER_OpenSpec_Core_Infra_SOTA_2026.md` | Capa core (futuro) | Referencia futura, no del MVP |
| `C:\Users\gonza\.claude\projects\C--Dropbox-DOC-RECA\fb784b73-84e5-4817-848d-fc21638b22a1.jsonl` | JSONL de la conversación origen de este brief | Fuente del brief |
| `C:\Dropbox\DOC.RECA\06-Software\yaml-agno\.chats\fb784b73-transcript.md` | Transcript limpio extraído | 205KB, 30 mensajes |
| https://github.com/colbymchenry/codegraph | Repo de CodeGraph | Dependencia externa a integrar |

---

## 12. NOTAS FINALES

- **El alcance final de yaml-agno está ABIERTO**. La decisión entre "librería
  completa" vs "preconfiguración adaptativa" depende del análisis de la visión
  completa (este brief). El brief sugiere fuertemente la librería completa.

- **Fase 1 es la herramienta interna de CENF**. Ambots-Hs no se construye en
  este milestone.

- **Los meta-agentes son el MVP, no AFIP**. Los primeros equipos agénticos a
  construir son los que permiten construir yaml-agno mismo, no equipos para
  clientes.

- **NO reinventar Agno**. Usar Agno como base, abstraer solo lo que se repite.

- **El usuario (vos) es el referente último** sobre el alcance y las decisiones
  estratégicas. El agente solo asiste, no decide solo.

---

*Brief generado el 2026-06-02 a partir de la sesión*
*`fb784b73-84e5-4817-848d-fc21638b22a1` de Claude Code.*
