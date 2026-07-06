# PROYECTO.yaml-agno — Definición estratégica

> **Propósito de este documento**: fijar en una sola pantalla la definición
> estratégica de yaml-agno (scope, visión, misión, filosofía, propósito) para
> que cualquier humano o agente que se sume entienda en 2 minutos qué es esto,
> por qué existe y qué NO es. Es la brújula; las decisiones operativas viven en
> `DECISIONES.md` y el detalle técnico en los 33 SPECs (`specs/INDEX.md`).
>
> **Fuentes**: `VISION.md` (brief original) + `DECISIONES.md` (12 decisiones).
> Si hay tensión entre este documento y VISION.md, **este manda** en lo
> operativo (VISION.md es el deseo histórico; este es el alcance verificado).

---

## PROPÓSITO — para qué existe

**Hacer que crear un equipo agéntico de Agno sea repetible y predecible, en
vez de un acto artesanal caótico.**

Hoy, cada vez que CENF arma un equipo agéntico para un cliente, el agente de
programación tiene que razonar profundo desde cero: arquitectura distinta,
prompts escritos distinto, configs (temperatura, tokens, learning) en
variables distintas. Eso **no escala**. yaml-agno existe para que ese
razonamiento profundo se haga **una sola vez** (cómo es el equipo, los prompts,
las tools custom) y el resto (lo que se repite ~80%) sea **config estructurada**.

---

## MISIÓN — qué hacemos, día a día

Construir y mantener una **librería Python pip-installable** que es una capa
declarativa **YAML sobre Agno Framework**: define agentes, equipos, workflows,
tools, knowledge, memory, storage, models y scheduler enteramente en YAML
(patrón **YAML → Pydantic → Factory**), **sin escribir Python para las features
built-in de Agno**. Solo se escribe Python "chiquito" para tools que Agno no
trae o que son específicas del cliente.

- **Ahora (Fase 1)**: herramienta interna de CENF para dar a clientes equipos
  agénticos para tareas reales (facturación AFIP, Excel/SAP, emails, meetings).
- **Después (Fase 2-3)**: base sobre la que se apoya el agente de programación
  + amBOTHS (open-source, usuario final generando sus propios equipos hablando
  en lenguaje natural).

---

## VISIÓN — el norte

**Que cualquier persona —incluso sin saber programar ni conocer Agno— pueda
tener equipos agénticos autónomos resolviendo tareas reales**, generados al
hablar con su agente personalizado (amBOTHS), apoyados en yaml-agno como el
DSL que el agente de programación usa.

Norte conceptual: **la config básica es estructurada y repetible** (el agente
no razona profundo sobre config); **el razonamiento profundo se reserva para
definir el equipo, los prompts de cada agente y las tools custom**. Red de
equipos interconectados con "interconocimiento cognitivo" (cada uno sabe qué
otros existen y para qué sirven, vía contratos input/output).

---

## FILOSOFÍA — principios no negociables

1. **Build ON TOP, nunca frankestein.** No reimplementar lo que Agno ya trae
   (runtime, sesión, memoria, A2A, retry). Solo abstraer **lo que se repite**.
2. **El razonamiento profundo va a un solo lugar.** El equipo, los prompts y
   las tools custom. El resto (temperatura, tokens, learning, formato) es
   config estructurada y repetible.
3. **Agente = caja negra con contrato.** Misión + input schema + output schema
   + dependencias + cómo se comunica. El cliente ve input+output; el developer
   ve la estructura YAML clara.
4. **Composición por interconexión.** Las cajas negras se interconectan entre
   sí o con el usuario. Equipos compartidos (ej: "perfilador" reutilizado por
   facturación, emails, meetings).
5. **El usuario es el referente último.** El agente asiste, no decide solo
   sobre alcance ni decisiones estratégicas.
6. **Calidad sobre inmediatez.** Strict TDD, specs coherentes, máxima
   trazabilidad/rollback (git + Engram). No shortcuts.

---

## SCOPE — qué está adentro y qué afuera

### Adentro — Fase 1 (MVP, el AHORA)
- Librería pip-installable: YAML → Pydantic → Factory → objetos Agno.
- `ref://` URI scheme para registry, `${ENV_VAR}` interpolation, hot-reload,
  multi-file + manifest.
- Pipeline de validación: YAML → env var → Pydantic → Registry → Factory.
- CEL + Callables **desde día 1**.
- Multi-tenant storage, strict TDD 100%+ coverage, integración CodeGraph (solo
  autoría, no runtime).
- Definición en YAML de: agentes, equipos, workflows, tools, knowledge,
  memory, storage, model providers, context providers, scheduler.

### Adentro — Fase 2 (mediano plazo)
- Equipo agéntico de apoyo al agente de programación: Agno Expert
  (docs + CodeGraph), Prompting Expert, Model Selector.
- ~80% de casos reales de CENF cubiertos.

### Afuera (no es yaml-agno)
- ❌ **No es un orquestador** (eso es amBOTHS).
- ❌ **No es una UI** (eso es Goose / agent-ui).
- ❌ **No es un sistema completo** (eso es amBOTHS).
- ❌ **No es "abstraer TODO Agno"** — solo lo que se repite (~80%).
- ❌ **amBOTHS no se construye en este milestone** (Fase 3, visión).

---

## CÓMO SE RELACIONA CON LOS DEMÁS DOCUMENTOS

| Documento | Qué es | Cuándo leerlo |
|---|---|---|
| **PROYECTO.md** (este) | Definición estratégica (brújula) | Cuando alguien se suma / dudas de alcance |
| **DECISIONES.md** | 12 decisiones técnicas inviolables + estado + reglas | Al retomar tras compactación |
| **VISION.md** | Brief histórico original (deseo, contexto amplio) | Para entender el "por qué" profundo |
| **SESSION_RESUME.md** | Estado de sesión actual | Al inicio de cada sesión |
| **specs/INDEX.md** | Índice de los 33 SPECs por grupo temático | Para navegar el detalle técnico |
