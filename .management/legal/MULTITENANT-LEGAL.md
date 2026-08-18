# Dictamen Legal DELTA — Multitenant Platform yaml-agno (Data Protection + Sandbox + SaaS)

> **Fecha**: 2026-08-11
> **Autor**: Legal Team CENF (orquestador, consolidación directa — mismo método del dictamen previo; el límite de profundidad de sub-agentes documentado en COMPLIANCE-LEGAL §11.5 aplica igual, sin delegación anidada)
> **Fuentes**: COMPLIANCE-LEGAL_yaml-agno.md (2026-08-08 — base obligatoria: Fase 1 🟡 L-01..L-06, Fase 3 OSS 🔴 O-01..O-07, dominios A-G, matriz RL-01..RL-13, cláusulas modelo §5.2, checklist contrato §3.1); chatgpt-comparar-repositorios-open-source.md (2026-08-11 — modelo multitenant propuesto, secciones 1-22); Engram #2759 (postura seguridad mínima viable, top-5 amenazas STRIDE-lite); Engram #2754/#2753 (dictamen previo)
> **Naturaleza**: Opinión preliminar de compliance — **NO constituye asesoramiento legal vinculante**; requiere validación de abogado/a matriculado/a antes de decisiones contractuales o de lanzamiento comercial.
> **Jurisdicción asumida**: Argentina (CABA) — default CENF; GDPR como watch (COMPLIANCE-LEGAL §7).
> **Carácter**: DELTA multitenant sobre COMPLIANCE-LEGAL_yaml-agno.md. No repite el análisis de Fase 1/OSS; lo referencia (ej. "RL-06, COMPLIANCE-LEGAL §1.3") e integra las 7 preguntas de multitenancy.

---

## 0. Resumen Ejecutivo (TL;DR) + semáforo

**Veredicto global multitenant: 🟡 CON OBSERVACIONES — GO condicionado.**

La plataforma multitenant es **legalmente viable en Argentina** bajo Ley 25.326 + CCyC, con el mismo patrón del dictamen previo: **el desarrollo no tiene bloqueo legal; el onboarding de tenants reales sí está condicionado** a un set de condiciones legales y de evidencia (ML-01..ML-10, §9). No hay nada en el modelo propuesto (Keycloak → JWT → CENF Gateway → yaml-agno → Casbin/OpenFGA → Sandbox) que genere un riesgo legal insalvable; los riesgos materiales están en **cross-tenant contamination (RL-14), falla de sandbox (RL-15) y la elección de auth propio vs Keycloak (RL-16)** — los tres tienen mitigación definida y de costo bajo-medio.

Punto central del análisis: el art. 11 Ley 25.326 exige "medidas técnicas y organizativas apropiadas" según el grado de riesgo — **NO exige aislamiento físico**. La separación lógica rigurosa (tenant_id como propiedad de seguridad en toda la capa de datos + authorization policy + sandbox) es, en principio, **medida suficiente y proporcionada** (§3), siempre que CENF pueda acreditar su implementación con **evidencia técnica** (tests de aislamiento cross-tenant, audit trail, RLS) y no solo con cláusulas contractuales.

**Semáforo por pregunta**:

| # | Pregunta | Semáforo | Veredicto corto |
|---|---|---|---|
| 1 | Responsabilidad legal (agente daña: ¿quién responde?) | 🟡 | Marco claro (CCyC 1716, 1743-1744, 1753, 1757); reparto de riesgo exige matriz contractual explícita. Matiz: art. 1757 (actividad riesgosa) puede alcanzar al operador del runtime |
| 2 | Contrato multitenant (SaaS) | 🟡 | Evoluciona el contrato de servicios de Fase 1 (§3.1) a SaaS: +AUP, +SLA, +subprocesadores, +exit/borrado; checklist definido (§2), plantilla por redactar |
| 3 | Data isolation (Keycloak+Casbin vs art. 11 + Disp. 47/2018) | 🟡 | Separación lógica ES suficiente en derecho; condicionado a implementación rigurosa + paquete de evidencia (§3) |
| 4 | Sandbox legal (`rm -rf` en sandbox) | 🟡 | Dentro del tenant: cubierto por caps + backup + HITL. Falla cross-tenant: riesgo real de CENF no capeable por dolo/culpa grave (art. 1743) → mitigar con aislamiento real + seguro |
| 5 | Disclaimer IA (agentes deciden) | 🟡 | Las cláusulas modelo §5.2 se **intensifican** en contexto autónomo multitenant: deny-default, HITL por acción, disclaimers por output, Ley 20.488 |
| 6 | Cross-tenant contamination | 🔴 | Riesgo #1. Sin notificación obligatoria en Ley 25.326, pero best practice 72h + plan de respuesta + remedios contractuales son **condición de onboarding** |
| 7 | Auth propio (SPEC_19) vs Keycloak | 🟢 | Decisión legal clara: **Keycloak** (diligencia debida, art. 1724 CCyC + art. 11 Ley 25.326); auth propio amplía superficie de culpa. Apache 2.0 sin riesgo de licencia |

**Semáforo global por pregunta: 1 🟢 / 5 🟡 / 1 🔴 (Q6, con plan de mitigación definido).**

Las condiciones L-01..L-06 del dictamen previo **siguen vigentes** y no se repiten aquí (L-01 contrato+encargado+mandato ARCA, L-02 consentimiento, L-03 SPEC_16/19, L-04 disclaimers+HITL, L-05 cesión de derechos, L-06 pin). Las condiciones multitenant ML-01..ML-10 (§9) **se suman** a L-01..L-06, no las reemplazan.

---

## §1. Responsabilidad legal: ¿quién responde si un agente hace algo mal en un tenant?

### 1.1 Análisis normativo

El agente no es persona jurídica: **no tiene subjetividad** — sus actos se atribuyen a quien lo configura, lo instruye o lo opera (instrumento/medio de ejecución). El régimen aplicable es el de responsabilidad civil del CCyC:

| Actor | Supuesto de daño | Base normativa | Atribución |
|---|---|---|---|
| **Tenant (cliente operador)** | Su agente ejecuta una acción dañosa **dentro de su propio dominio** (borra datos propios, emite comprobante erróneo) o hacia terceros **siguiendo sus instrucciones** | arts. 1716 (deber de reparar), 1724 (culpa), 362 ss. (mandato, por analogía: el agente actúa como instrumento del mandante) | El cliente responde como **usuario/operador del instrumento**: quien se sirve del agente y se beneficia de su actuación asume los actos dentro del encargo. En el contrato se pacta que el tenant garantiza sus instrucciones, configuraciones y el uso de sus usuarios (§2) |
| **Tenant (guardián)** | El agente es una **actividad riesgosa** (ejecuta código, accede a sistemas) | **art. 1757** (hecho de las cosas y actividades riesgosas: responsabilidad **objetiva**; no eximen autorización administrativa ni cumplimiento de técnicas de prevención) | El tenant como guardián de su agente puede responder objetivamente por el riesgo de la actividad que explota. Matiz importante: el tenant es quien decide configurar el agente y sus herramientas |
| **CENF (plataforma)** | **Defecto de la plataforma**: falla de aislamiento, vulnerabilidad explotada, error de autorización, indisponibilidad | arts. 1716, 1724 (culpa = omisión de la diligencia debida según la naturaleza de la obligación y las circunstancias); incumplimiento contractual de la cláusula de seguridad (art. 11 Ley 25.326 como estándar contractualizado) | CENF responde por **su propia culpa**: la del servicio que vende. No responde por los actos autónomos del agente que el cliente configura, salvo que el defecto de la plataforma los haya habilitado |
| **CENF (guardián del runtime)** | La actividad de **ejecutar código en sandbox** puede calificarse de actividad riesgosa | **art. 1757** (posible aplicación objetiva al operador del runtime) | **Riesgo de interpretación**: un tribunal podría aplicar responsabilidad objetiva a CENF como guardián de la actividad de ejecución. Mitigación: contrato explícito + evidencia de medidas (§3) + disclaimers + seguro (§4-d). Este punto **requiere validación de abogado matriculado** |

### 1.2 La distinción culpa leve vs dolo/culpa grave (art. 1743)

- La cláusula que **exime o limita la responsabilidad por dolo o culpa grave es nula** (art. 1743 CCyC). Solo es válida la limitación para **culpa leve** (art. 1744) y riesgos no previsibles.
- Consecuencia operativa: los caps del contrato (§5.2 cláusula 2) **no protegen a CENF** si el daño deriva de su dolo o culpa grave (ej. aislamiento implementado a sabiendas de su falla, negligencia grosera en la gestión de secretos). Esto refuerza la recomendación técnica: **aislamiento real + evidencia**, no solo papeles.
- **El cliente no puede imputar a CENF** el dolo de un agente que el propio cliente configuró; la prueba de "culpa grave" de CENF en un ecosistema de agentes es terreno novedoso — los logs, audit trail y HITL son la mejor defensa (§1.4).

### 1.3 Ley 24.240 (producto defectuoso, arts. 40-42) — matiz B2B

- En relación **B2B** (cliente PyME persona jurídica que usa la plataforma como insumo productivo), no aplica la responsabilidad por vicios/riesgos del producto de la Ley 24.240 (art. 1: destinatario final; el uso productivo queda fuera) — aplica el régimen general del CCyC.
- **Matiz del art. 3 Ley 24.240**: si el cliente es **monotributista persona humana** (ej. estudio contable unipersonal), la presunción de consumo puede operar en caso de duda → cláusulas abusivas nulas (arts. 37-38). Mitigación prudencial (ya adoptada en Fase 1, COMPLIANCE-LEGAL §3.2): declaración expresa de uso profesional/B2B en el contrato y cláusulas equilibradas, sin sorpresivas (arts. 988-989 CCyC).

### 1.4 Respuesta concreta

1. **Dentro del tenant**: responde el cliente (operador de su agente), salvo que el daño derive de defecto de la plataforma.
2. **Hacia terceros por acción del agente del tenant**: responde el tenant (instrumento que controla); CENF solo si el defecto de la plataforma habilitó la acción.
3. **CENF** responde por defectos del servicio, fallas de aislamiento y su propia culpa; la limitación contractual no cubre dolo/culpa grave (art. 1743).
4. **Contractualmente** hay que repartir el riesgo con: matriz de responsabilidad, garantía del cliente sobre instrucciones/datos, HITL, backups, caps y excepciones (§5.2 ampliada en §2 y §4-e).

**Confianza**: media-alta en el marco general; el matiz del art. 1757 aplicado al operador del runtime **requiere validación de profesional matriculado** (es interpretación novedosa).

---

## §2. Contrato multitenant (SaaS) — cláusulas mínimas

### 2.1 Comparación con el contrato de Fase 1 (COMPLIANCE-LEGAL §3.1)

| Aspecto | Fase 1 (consultoría/servicios) | Multitenant (SaaS) | Δ |
|---|---|---|---|
| Naturaleza | Prestación de servicios (CCyC arts. 1251 ss.), obligación de medio, proyecto finito | **Servicio continuo** (SaaS): obligación de disponibilidad, soporte, actualización | Cambio de naturaleza: de proyecto a servicio continuo |
| SLA/uptime | No aplicaba | **SLA + remedios** (créditos, rescisión) — nuevo | Nuevo |
| Uso aceptable (AUP) | No aplicaba | **AUP + conducta prohibida** (uso ilegal, scraping, modelos prohibidos) | Nuevo |
| Aislamiento/seguridad | Cláusula genérica de medidas | **Cláusula específica de aislamiento por tenant** + evidencia (§3) | Refuerzo |
| Subprocesadores/cloud | No aplicaba (deploy local) | **Lista de subprocesadores + consentimiento para transferencia internacional** (art. 12 Ley 25.326) | Nuevo |
| Exit | Devolución de datos al terminar | **Exit + borrado automático y certificado** (art. 11, 16 Ley 25.326) | Refuerzo |
| Responsabilidad del tenant | El cliente garantiza base legal de datos | **El tenant administra sus propios usuarios, credenciales y configuraciones**; CENF no responde por uso indebido interno | Nuevo |

### 2.2 Cláusulas MÍNIMAS del contrato SaaS multitenant (CCyC arts. 958, 961, 988-989, 1251 ss.; Ley 25.506)

1. **Partes y definiciones** (tenant, usuario, agente, output, sandbox, datos del tenant, subprocesador).
2. **Objeto SaaS**: plataforma multitenant de agentes; descripción del servicio, módulos, límites (qué NO hace la plataforma); **el tenant no adquiere el software, adquiere una licencia de uso** (ver cláusula 9).
3. **Administración del tenant**: el tenant designa admins, gestiona sus usuarios y credenciales; es **responsable del uso que sus usuarios den a los agentes** (incluidos agentes configurados por el propio tenant). CENF no responde por uso indebido interno del tenant (§1).
4. **Uso aceptable (AUP) y conducta prohibida**: actividades ilegales, intentos de acceso cross-tenant, inyección de código malicioso, uso de herramientas para dañar a terceros, violación de derechos de terceros. Consecuencias: suspensión, rescisión, responsabilidad.
5. **SLA/uptime y remedios**: disponibilidad objetivo, ventanas de mantenimiento, créditos por incumplimiento, **excepciones** (fuerza mayor, mantenimiento programado, acciones del tenant). La omisión de SLA no invalida el contrato, pero expone a CENF a reclamos por falta de estándar pactado — definirlo es protección.
6. **Propiedad de datos e IP**: **datos del tenant (inputs/outputs) = propiedad del tenant** (con licencia al operador para prestar el servicio); IP de la plataforma, agentes base, templates YAML y código CENF = propiedad CENF (Ley 11.723); **el tenant retiene IP de sus agentes/configuraciones**; CENF no reclama derechos sobre el conocimiento del tenant.
7. **Licencia de uso de la plataforma**: limitada, no exclusiva, revocable, para uso interno del tenant (SaaS, no distribución).
8. **Subprocesadores y transferencia internacional**: lista de subprocesadores (cloud, LLMs), consentimiento del tenant para transferencia internacional de datos (art. 12 Ley 25.326 — storage/LLM fuera de Argentina), derecho a actualizar la lista con notificación. **Refuerza el hallazgo previo** (COMPLIANCE-LEGAL §2.3: transferencia a LLMs USA requiere consentimiento + cláusulas).
9. **Seguridad y aislamiento**: CENF garantiza las medidas de art. 11 Ley 25.326 + Disp. AAIP 47/2018 (nivel según datos), **aislamiento lógico por tenant**, cifrado en tránsito, gestión de secretos, y **derecho del tenant a recibir evidencia de las medidas** (§3.2). No es una garantía de "imposibilidad de fuga" — es una garantía de medidas razonables y proporcionadas (matiz importante de redacción).
10. **Cláusula de encargado de tratamiento (DPA-lite)**: CENF = encargado, cliente = responsable (art. 4 Ley 25.326; COMPLIANCE-LEGAL §2.2); instrucciones documentadas, finalidad, medidas, ARCO (arts. 14-16), notificación de incidentes al responsable.
11. **Exit / devolución y borrado**: al terminar, exportación de datos del tenant en formato estándar y **borrado completo certificado** dentro de plazo (art. 11, 16 Ley 25.326); retención mínima por obligaciones fiscales del cliente (Ley 11.683 art. 70 — 10 años, política tiered, ver Engram #2759).
12. **Rescisión**: causales, preaviso, suspensión por AUP, efectos (exit + borrado).
13. **Responsabilidad y limitaciones**: caps (mayor entre 12 meses de fees o valor del contrato), exclusión de daños indirectos, **excepciones por dolo/culpa grave, cláusula de encargado y daños cross-tenant causados por CENF** (art. 1743) — ver §5.2 previo ampliada.
14. **Mandato ARCA** (si aplica el caso de uso): poder especial limitado y revocable (CCyC arts. 362 ss.; RG ARCA 2904/2010), Anexo C del previo — **referenciar, no re-analizar** (dominio F).
15. **Jurisdicción y ley aplicable**: CABA + derecho argentino (obligatorio).
16. **Disposiciones generales + firma electrónica**: notificaciones, cesión, modificación; **firma electrónica simple válida con conformidad, firma digital con presunción de autoría e integridad (art. 3 Ley 25.506)** — recomendada para el contrato y el DPA.

**Anexos**: A) descripción técnica + SLA detallado; B) AUP; C) política de privacidad + consentimientos; D) DPA-lite; E) mandato ARCA (si aplica); F) lista de subprocesadores.

### 2.3 Respuesta concreta

El contrato SaaS multitenant **evoluciona y amplía** el de Fase 1: las 10 cláusulas de §3.1 previo quedan y se agregan AUP, SLA, subprocesadores, aislamiento específico y exit/borrado certificado. **Condición**: redactar plantilla CENF antes del primer tenant real (ML-01, §9). Confianza media-alta en el checklist; redacción final a validar por abogado matriculado.

---

## §3. Data isolation — ¿Keycloak + Casbin satisfacen art. 11 Ley 25.326 + Disp. AAIP 47/2018?

### 3.1 Análisis normativo

- **Art. 11 Ley 25.326**: el responsable/usuario de datos debe adoptar **"las medidas técnicas y organizativas que resulten necesarias para garantizar la seguridad y confidencialidad"** — el estándar es de **adecuación al grado de riesgo**, no de máximo absoluto.
- **Disp. AAIP 47/2018**: niveles de seguridad **básico, medio y crítico** según la naturaleza de los datos; las medidas se graduan por nivel. La separación **lógica** entre datasets (por ejemplo, clave de tenant en todas las consultas) es una técnica reconocida para cumplir el nivel medio; el aislamiento físico solo se vuelve exigible como medida razonable cuando el análisis de riesgo lo justifica (datos críticos, altísimo volumen, amenaza específica).
- **Arts. 6 y 7 Ley 25.326**: la calidad de los datos y el tratamiento de datos sensibles refuerzan el deber de acceso restringido — que es exactamente lo que tenant_id + authorization policy implementan.
- **Criterio "medida razonable y proporcionada"**: el estándar argentino (y el europeo, art. 32 GDPR como watch) no exige "imposibilidad de fuga"; exige **diligencia técnica proporcional al riesgo**. Un esquema con identidad federada (Keycloak), autorización por política (Casbin/OpenFGA), tenant_id como propiedad de seguridad en toda la capa de datos y sandbox por ejecución está **por encima** del estándar mínimo.

### 3.2 Evidencia técnica que CENF debe poder presentar (acreditar diligencia, no solo cláusula)

Para que la separación lógica sea defensable ante un reclamo del cliente o de la AAIP, CENF debe poder mostrar:

| Evidencia | Qué demuestra | Responsable |
|---|---|---|
| **tenant_id en toda la capa de datos** (sessions, memories, knowledge, files, agents, runs, traces, tool_calls, credentials, sandboxes, audit_events — modelo del doc de comparación §19) | Diseño con tenant como propiedad de seguridad, no filtro SQL ad-hoc | Devs |
| **RLS / aislamiento a nivel de base de datos** (Postgres RLS como capa de defensa última) | Defensa en profundidad: aunque fallara la app, la BD aísla | Devs |
| **Tests de aislamiento cross-tenant en CI** (intento de acceso A→B como test automatizado) | La garantía está probada, no prometida | Devs (extiende SPEC_19, L-03 previo) |
| **Audit trail inmutable** (audit_events con tenant_id, request_id) | Capacidad de reconstruir cualquier acceso | Devs |
| **Revisión de seguridad periódica** (revisión de policies Casbin, revisión de claims JWT, pentest puntual) | Mantenimiento del estándar en el tiempo | Devs/Infra |
| **SBOM + CVE tracking del stack de seguridad** (Keycloak, Casbin, sandbox) | Diligencia continua sobre componentes críticos (se integra con O-03/RL-07 previo) | Infra |

### 3.3 Respuesta concreta

**Sí, en derecho la separación lógica (Keycloak + Casbin + tenant_id + sandbox) es suficiente** como "medida técnica y organizativa apropiada" del art. 11, porque la ley no exige aislamiento físico sino adecuación al riesgo (Disp. AAIP 47/2018). **Condición**: implementación rigurosa + paquete de evidencia §3.2 disponible antes del primer tenant (ML-03). Sin la evidencia, la cláusula contractual es solo una promesa sin acreditar — y ante un incidente, el tribunal evaluará la **diligencia real** (art. 1724), no la letra del contrato. **Confianza alta en el marco normativo; la implementación está [VACÍO DE EVIDENCIA: SPEC_19/RLS en camino, aún no verificada en producción]**.

---

## §4. Sandbox legal — ¿estamos cubiertos si un agente ejecuta `rm -rf`?

### 4.1 (a) Daños DENTRO del propio tenant (destrucción de datos del cliente)

- Es el escenario más probable y el más fácil de cubrir contractualmente: la limitación de responsabilidad (§5.2 cláusula 2: cap = 12 meses de fees; exclusión de daños indirectos) aplica a **culpa leve**. Un `rm -rf` ejecutado por el agente configurado por el cliente, dentro del sandbox del cliente, sobre datos del propio cliente, con las herramientas que el cliente habilitó → **daño autoinfligido**; el tenant no puede trasladarlo a CENF salvo defecto de la plataforma.
- Mitigación técnica que refuerza la legal: **backups por tenant** (el backup es la garantía real de no pérdida, no la promesa) + **HITL para acciones destructivas** (deny-default, §5).
- Cláusula específica: "el tenant es responsable de sus configuraciones de backup/rotación y de las herramientas que habilita a sus agentes" (ya prevista en §2.2 cláusula 3).

### 4.2 (b) Daños a TERCEROS / otro tenant (falla cross-tenant del sandbox)

- Si el aislamiento **falla** y el agente del tenant A daña al tenant B o a terceros → CENF responde por **culpa** (art. 1716, 1724: falló la diligencia debida en la frontera que CENF prometió). La excepción de dolo/culpa grave del art. 1743 opera **en contra de CENF**: un fallo de aislamiento grave (ej. sandbox mal configurado a sabiendas) no es capeable.
- **Conclusión dura**: el cap contractual NO protege a CENF en el escenario cross-tenant con culpa grave. La mitigación es **técnica, no contractual**: aislamiento real (gVisor/Firecracker como profundidad, no solo Docker — doc de comparación §12), tests de aislamiento, deny-default de red, no-root, read-only FS.
- Nota criminal informática: un tercero que explota la falla de aislamiento podría configurar acceso ilegítimo (CP arts. 153 bis, 173 bis) — la responsabilidad penal recae en el atacante, pero la negligencia de CENF en la frontera alimenta el reclamo civil.

### 4.3 (c) El sandbox como "medida de seguridad" ante reclamos

- Ante un reclamo por incidente de datos: el sandbox es parte de las **"medidas técnicas y organizativas"** del art. 11 Ley 25.326 + Disp. AAIP 47/2018 — su existencia y configuración acreditan el estándar (nivel medio/crítico).
- Ante un reclamo civil: el sandbox es **evidencia de diligencia debida** (art. 1724) — demuestra que el daño no provino de omisión de cuidado.
- Valor probatorio: los **audit logs de ejecución en sandbox** (qué pidió el agente, qué se ejecutó, qué se denegó) son la evidencia clave en cualquier disputa (HITL, denials, tool_calls). Recomendación: **conservación de audit_events** con política de retención definida.

### 4.4 (d) Seguro cyber como mitigación

- El seguro de ciberseguridad (ciber riesgo) **no reemplaza** las medidas técnicas ni el cumplimiento, pero transfiere parte del riesgo financiero de incidentes (respuesta a incidentes, notificación, defensa legal, daños a terceros). `[VACÍO DE EVIDENCIA: sin cotización ni verificación de cobertura cyber en Argentina — pendiente de @finance-team y de proveedor de seguros]`.
- Cobertura a verificar: daños a terceros (third-party liability), cross-tenant, costos de notificación, pérdida de datos del cliente. La exclusión de "uso de IA" es un riesgo real de mercado — negociarla explícitamente.

### 4.5 (e) Cláusula específica de ejecución de código/agentes en sandbox

```
EJECUCIÓN EN SANDBOX. La plataforma ejecuta el código y las herramientas de los
agentes dentro de entornos aislados (sandbox) con políticas de filesystem, red y
procesos restrictivas (deny-default). CENF no garantiza que el sandbox sea
impenetrable; garantiza la implementación diligente de las medidas descritas en
el Anexo de Seguridad. El tenant es responsable de las herramientas, prompts y
acciones que habilita a sus agentes, y de activar la aprobación humana (HITL)
para acciones irreversibles. La responsabilidad de CENF por daños a terceros
derivados de fallas de aislamiento se rige por el art. 1743 CCyC (no se excluye
el dolo ni la culpa grave).
```

### 4.6 Respuesta concreta

**Dentro del tenant: sí, cubierto** (caps + backup + HITL). **Cross-tenant: cubierto solo si el aislamiento es real** — el cap no aplica a dolo/culpa grave (art. 1743), así que la protección es técnica (defensa en profundidad) + evidencia de auditoría + seguro. **Confianza media-alta**; la redacción de la cláusula y la evaluación del riesgo residual cross-tenant requieren validación profesional.

---

## §5. Disclaimer IA — nivel necesario cuando los agentes toman decisiones

### 5.1 ¿Cambia el nivel en contexto multitenant autónomo?

**Sí, se intensifica.** En Fase 1 los agentes operaban bajo supervisión cercana del estudio contable (HITL manual natural). En una plataforma multitenant, cada tenant configura agentes con autonomía variable; CENF no controla ni supervisa cada ejecución. Por eso las cláusulas modelo §5.2 del previo se mantienen **y se agregan**:

| Requisito | Fase 1 (§5.2 previo) | Multitenant (delta) | Norma |
|---|---|---|---|
| Outputs no vinculantes | ✓ | ✓ + **disclaimer visible en cada output entregado** (en la UI/API, no solo en el contrato) | CCyC 958, 961; buena fe |
| HITL acciones irreversibles | ✓ (emisión comprobantes, pagos, presentaciones, envíos) | ✓ + **deny-default por configuración**: las acciones de riesgo están DENEGADAS salvo habilitación expresa del tenant; HITL obligatorio para emisión, pagos, presentaciones fiscales, envíos a terceros | CCyC 1743-1744; art. 11 Ley 25.326 (proporcionalidad) |
| No presentar outputs como dictamen/certificación profesional | ✓ | ✓ + **prohibición explícita en AUP** y en los templates de agentes contables (verificación de matrícula, Ley 20.488 arts. 2-3) | Ley 20.488 arts. 2-3 |
| Advertencias de verificación humana | ✓ | ✓ + **configuración de agentes con instrucciones de verificación** (el prompt del agente le ordena requerir confirmación humana) | art. 961 CCyC |
| Default de riesgo | — | **deny-default**: herramientas con `requires_confirmation: true` por defecto; el tenant debe opt-in explícito para autonomía mayor | art. 11 Ley 25.326; art. 1724 |

### 5.2 Respuesta concreta

Las cláusulas modelo §5.2 del previo **siguen siendo la base**; en multitenant se agregan: (1) disclaimer en cada output, (2) deny-default con opt-in explícito por tenant, (3) HITL por tipo de acción configurable pero **irrenunciable para acciones irreversibles**, (4) prohibición de outputs como dictamen/certificación en AUP + templates (Ley 20.488). El nivel NO baja con la autonomía: **sube**. **Confianza alta** en el diseño; la redacción por validar.

---

## §6. Cross-tenant contamination — ¿qué pasa si un bug expone datos entre tenants?

### 6.1 (a) Responsabilidad de CENF ante el tenant afectado

- Doble vía: **incumplimiento contractual** de la cláusula de seguridad (§2.2 cláusula 9 — medidas razonables, art. 11 Ley 25.326 incorporado como estándar) + **responsabilidad civil** (art. 1716 ss.). Si la fuga deriva de defecto del aislamiento → culpa de CENF; el cap aplica salvo dolo/culpa grave (art. 1743). Es el **riesgo mayor de la plataforma** (RL-14, §8).
- El tenant afectado reclama: daño directo (fuga de sus datos), daño reputacional, costos de notificación a sus propios titulares, sanciones AAIP si procedieran (registro/investigación).

### 6.2 (b) Obligaciones de notificación — Ley 25.326 y best practice

- **Ley 25.326 NO impone notificación obligatoria de breaches** (a diferencia de GDPR art. 33 — 72 h). La AAIP recomienda notificar; hay proyecto de reforma (estado 2026 `[VACÍO DE EVIDENCIA: verificar avance de la reforma]` — COMPLIANCE-LEGAL §2.3).
- Best practice adoptada por CENF (previo): **notificación al responsable en 72 h** (alineada con GDPR futuro). En multitenant esto se **contractualiza**: el DPA-lite (§2.2 cláusula 10) obliga a CENF a notificar al tenant responsable el incidente, su alcance y la remediación; el tenant decide la notificación a sus titulares (art. 14-16 ARCO) y a la AAIP.
- **Documentar el procedimiento** (playbook de incidentes: detección → contención → análisis → notificación 72 h → remediación → lecciones aprendidas) — es condición de onboarding (ML-04).

### 6.3 (c) Obligación de informar a la AAIP cuando corresponda

- Como **encargado**, CENF no tiene obligación directa de denunciar a la AAIP (la relación es con el responsable). Pero: (1) si CENF tiene **bases propias** comprometidas (registro AAIP art. 21 + Dec. 1558/2001 — COMPLIANCE-LEGAL §2.2), el deber de colaboración/investigación aplica; (2) ante una **investigación de oficio**, la evidencia de §3.2 (audit trail, tests de aislamiento) es la defensa. No hay obligación de "auto-denuncia" en el texto vigente — best practice es documentar y cooperar.

### 6.4 (d) Remedios contractuales

| Remedio | Contenido |
|---|---|
| Garantía de medidas | CENF garantiza medidas de art. 11 + Disp. 47/2018 (no garantiza impenetrabilidad — matiz de redacción §2.2 cláusula 9) |
| Indemnización | Cap + exclusión de indirectos, con **excepción expresa para fuga de datos personales** si el mercado lo pide (cláusula negociable; en B2B la exclusión de indirectos suele mantenerse) |
| Remediación | Obligación de CENF de remediar el defecto, notificar, asistir al tenant en la gestión |
| Plan de respuesta a incidentes | Playbook documentado + tiempos (72 h) + equipo responsable + escalamiento |
| Suspensión/rescisión | Derecho del tenant afectado a suspender o rescindir sin penalidad si CENF no remedía en plazo |

### 6.5 (e) Impacto en confianza/mercado

La fuga cross-tenant es **mortal para una plataforma multitenant B2B PyME**: destruye la propuesta de valor (datos compartidos en la misma infra) y genera efecto cascada (todos los tenants revisan su permanencia). El dictamen lo alinea con STRIDE-lite #1 de Engram #2759 (cross-tenant CRÍTICA, SPEC_19+RLS). El costo reputacional excede el legal — es un argumento más para la rigurosidad técnica como inversión legal (RL-14).

### 6.6 (f) Cómo la evidencia técnica protege a CENF

En cualquier reclamo, el tribunal/la AAIP evalúa **diligencia real** (art. 1724). La evidencia de §3.2 (tests de aislamiento en CI, audit trail con request_id, revisión de policies, SBOM/CVE del stack) demuestra que el incidente no provino de omisión de cuidado → reduce la calificación de culpa (de grave a leve) y hace **operativo el cap** del contrato. Sin evidencia, el cap es letra muerta.

### 6.7 Respuesta concreta

**Es el riesgo #1 de la plataforma (RL-14, 🔴)**. El derecho argentino no impone notificación obligatoria, pero la **contractualización de 72 h + playbook + remedios + evidencia de aislamiento** son condición de onboarding de tenants (ML-04, ML-03). Con eso, el riesgo pasa de "materialización sin red" a "incidente gestionado con responsabilidad capeada". **Confianza media-alta** en el esquema; requiere validación profesional de la cláusula de fuga de datos.

---

## §7. Comparativa legal: auth propio (SPEC_19) vs Keycloak (OSS maduro)

### 7.1 Análisis desde la perspectiva LEGAL (no técnica)

| Criterio legal | Auth propio (SPEC_19) | Keycloak (OSS maduro, Apache 2.0) | Fundamentación |
|---|---|---|---|
| **(a) Diligencia debida / estándar de cuidado** | Componente de seguridad escrito desde cero por CENF = **mayor superficie de error humano** en el componente más crítico (identidad) | Componente maduro (~35k stars, 100+ releases, auditado, OIDC/OAuth2/SAML/MFA) | **art. 1724 CCyC**: culpa = no observar la diligencia debida según la naturaleza de la obligación y las circunstancias. Usar un componente probado en el mercado para identidad es lo que un operador diligente hace; reinventarlo sin justificación técnica es asumir riesgo de culpa. **art. 11 Ley 25.326**: "medidas técnicas apropiadas" — un IdP auditado es más defendible como "apropiado" que un IdP propio sin historia |
| **(b) Superficie de error → probabilidad de culpa** | Bug en auth = incidente de identidad/cross-tenant → reclamo por incumplimiento de garantía de seguridad + art. 1716 | Bug posible pero con comunidad que lo encuentra/parchea primero; SBOM + CVE tracking del componente | La probabilidad de que el defecto se materialice y la culpa se califique es **mayor** con auth propio (sin historia de seguridad, sin parches de comunidad) |
| **(c) Evidencia de diligencia ante reclamos** | Difícil de acreditar: "confíe en nuestro código" | Fácil: componente estándar + SBOM + CVE tracking + configuraciones según OWASP/IAM best practices | Ante reclamo de cliente o AAIP, la evidencia de diligencia es material: Keycloak + SBOM + versión parcheada es una defensa mucho más sólida que código propio |
| **(d) Licencia** | Sin riesgo de licencia (código propio) pero con riesgo de calidad | **Apache 2.0 — sin riesgo de licencia** (verificado: doc de comparación §3 + COMPLIANCE-LEGAL §1.1; ~35k stars). A diferencia de Logto (MPL-2.0, file-level copyleft), Apache 2.0 no impone obligaciones de reciprocidad | El stack completo propuesto (Keycloak, Casbin, gVisor, Firecracker, OpenShell, OpenFGA) es Apache 2.0 → coherente con la decisión OSS de yaml-agno (COMPLIANCE-LEGAL Fase 3) |
| **(e) Riesgo reputacional/de mercado** | Un incidente de identidad en plataforma multitenant es reputacionalmente destructivo (RL-14, RL-16) | Componentes reconocidos (Keycloak/Casbin) son **señal de seriedad** para clientes PyME B2B y para due diligence de futuros inversores | El mercado SaaS/B2B argentino valora estándares reconocidos; explicar "usamos Keycloak" es más vendible que "construimos nuestro propio IdP" |
| **(f) Costo legal de la decisión** | Costo legal **diferido y alto**: cada incidente de identidad tiene costo de defensa, indemnización y reputación | Costo legal **anticipado y bajo**: licencia permisiva, comunidad, evidencia de diligencia | La decisión de hoy define el perfil de riesgo legal de los próximos años |

### 7.2 Conclusión legal recomendada

**Legalmente se recomienda Keycloak (o un IdP maduro equivalente: Ory, Auth0-managed si el costo lo permite), NO auth propio.** Fundamentos: (1) la diligencia debida (art. 1724) y las medidas apropiadas (art. 11 Ley 25.326) se acreditan con componentes probados; (2) auth propio maximiza la probabilidad de culpa en el componente más crítico; (3) la evidencia de diligencia ante reclamos es materialmente superior con componentes estándar + SBOM + CVE tracking; (4) Apache 2.0 no genera conflicto de licencia con el stack ni con la apertura OSS planificada. **El riesgo RL-16 (auth propio) se mitiga adoptando Keycloak** — es una decisión de riesgo legal, no solo técnica. **Confianza alta.**

Nota: si aun así se eligiera auth propio, debería tratarse como **excepción documentada con análisis de riesgo** y con las garantías de §3.2 (tests, revisión de seguridad externa) elevadas al máximo — el dictamen no lo recomienda.

---

## §8. Matriz de riesgos legales nuevos (RL-14+) — integrada con RL-01..RL-13

Los riesgos RL-01..RL-13 del dictamen previo (COMPLIANCE-LEGAL §8) **siguen vigentes**. Se agregan los riesgos multitenant. La severidad se expresa como prob × impacto (🔴 ALTA / 🟠 MEDIA / 🟢 BAJA). Alineación @risk-team: estos IDs se integran a la matriz consolidada del risk-team en su próxima ronda.

| ID | Riesgo legal multitenant | Severidad (prob × impacto) | Fase | Mitigación | Dueño |
|---|---|---|---|---|---|
| **RL-14** | **Cross-tenant contamination** (bug expone datos entre tenants) — el riesgo #1 de la plataforma | 🔴 ALTA (prob MEDIA-baja si SPEC_19/RLS rigurosos; impacto CRÍTICO) | 2 (multitenant) | ML-03 (evidencia aislamiento), ML-04 (playbook 72 h), cláusula fuga de datos §6.4, RLS + tests CI | Devs + Legal |
| **RL-15** | **Falla del sandbox** (fuga de ejecución cross-tenant; daño a terceros) | 🔴 ALTA (prob baja con gVisor/Firecracker; impacto ALTO, no capeable por dolo/culpa grave art. 1743) | 2 | Defensa en profundidad (gVisor/Firecracker, no solo Docker), deny-default red/FS, tests de escape, seguro cyber (§4) | Devs/Infra + Legal |
| **RL-16** | **Auth propio (SPEC_19)** — superficie de error en identidad → culpa (art. 1724), incumplimiento de garantía de seguridad | 🟠 MEDIA (se elimina con Keycloak; ALTA si se construye propio) | 2 | **Decisión Keycloak** (§7), SBOM + CVE tracking del IdP | Gonzalo + Legal |
| **RL-17** | **Incumplimiento de SLA/uptime** (cliente sin servicio, daño operativo) | 🟠 MEDIA | 2 | SLA con remedios (créditos) + excepciones + cap (§2.2 cláusula 5) | Product + Legal |
| **RL-18** | **Autonomía del agente sin HITL suficiente** (acción irreversible sin aprobación) → daño al tenant o terceros, disclaimers insuficientes | 🟠 MEDIA (impacto ALTO si ocurre) | 2 | Deny-default, HITL irrenunciable para irreversibles, disclaimers por output (§5), AUP | Legal + Devs |
| **RL-19** | **Exit/borrado incompleto del tenant** (datos residuales tras rescisión) → violación art. 11, 16 Ley 25.326 + reclamo del cliente | 🟠 MEDIA | 2 | Borrado automático certificado + retención fiscal documentada (Ley 11.683 art. 70; §2.2 cláusula 11) | Devs + Legal |
| **RL-20** | **Datos sensibles de terceros en knowledge base cross-tenant** (un tenant indexa datos de empleados de otro o del mismo con datos sensibles sin base legal) | 🟠 MEDIA | 2 | Garantía de base legal del tenant + filtrado PII (SPEC_16) + minimización (§2.2 cláusula 3; extiende RL-13) | Legal |
| **RL-21** | **Sin cobertura de seguro cyber verificada** (riesgo financiero de incidentes sin transferir) | 🟠 MEDIA | 2 | Cotizar cobertura con exclusiones de IA negociadas (§4.4) | Finance + Legal |

**Nota de integración**: RL-14 y RL-15 son los dos riesgos que **cambian la naturaleza** del dictamen previo (de herramienta interna a plataforma con datos de terceros en la misma infra). Ninguno es bloqueante absoluto: ambos tienen mitigación técnica + contractual definida. RL-16 se **elimina** con la decisión Keycloak (ML-07).

---

## §9. Checklist accionable multitenant — condiciones legales pre-lanzamiento

Se **suman** a L-01..L-06 del previo (que siguen vigentes). Numeración ML (Multitenant Legal). Todas son condiciones del **onboarding del primer tenant real** (G-04 del previo), no del desarrollo.

| # | Condición | Norma | Responsable | Antes de |
|---|---|---|---|---|
| **ML-01** | Plantilla de contrato SaaS multitenant firmado (§2.2, 16 cláusulas + 6 anexos) | CCyC arts. 1251 ss., 958, 961; Ley 25.506 | Legal | Primer tenant |
| **ML-02** | Matriz de responsabilidad §1 + cláusula de ejecución en sandbox §4.5 + disclaimers intensificados §5.2 | CCyC arts. 1716, 1743-1744; Ley 20.488 arts. 2-3 | Legal | Primer tenant |
| **ML-03** | Paquete de evidencia de aislamiento: tenant_id en toda la capa, RLS, tests cross-tenant en CI, audit trail, revisión de seguridad | Ley 25.326 art. 11; Disp. AAIP 47/2018 | Devs | Primer tenant con datos reales |
| **ML-04** | Playbook de incidentes documentado: detección → contención → notificación al responsable en 72 h → remediación; procedimiento AAIP | Ley 25.326 art. 11; GDPR art. 33 (watch); art. 1724 CCyC | SRE + Legal | Primer tenant |
| **ML-05** | DPA-lite multitenant: CENF encargado, cliente responsable, instrucciones, ARCO, notificación de incidentes (extiende L-01) | Ley 25.326 arts. 4, 5, 14-16 | Legal | Primer tenant |
| **ML-06** | Exit/borrado automático certificado del tenant + política de retención (tiered, fiscal 10 años) | Ley 25.326 arts. 11, 16; Ley 11.683 art. 70 | Devs + Legal | Primer tenant |
| **ML-07** | **Decisión formal: Keycloak (IdP maduro), no auth propio** — registrada en DECISIONES.md con fundamento legal (§7) | art. 1724 CCyC; art. 11 Ley 25.326 | Gonzalo + Legal | Diseño de seguridad finalizado |
| **ML-08** | SLA definido con remedios y excepciones (incluido en ML-01) | CCyC arts. 958, 1743 | Product + Legal | Primer tenant |
| **ML-09** | SBOM + CVE tracking del stack de seguridad (Keycloak, Casbin, sandbox) — integra O-03/RL-07 | Diligencia debida (art. 1724); Apache 2.0 §4 (notices) | Infra | Primer tenant |
| **ML-10** | Seguro cyber cotizado y verificado (cobertura third-party + cross-tenant; exclusiones de IA negociadas) | Mitigación financiera (CCyC 1708 ss.) | Finance + Legal | Lanzamiento comercial |

---

## §10. Veredicto global

### Multitenant Platform: 🟡 **CON OBSERVACIONES — GO condicionado**

- **Desarrollo de la plataforma multitenant: SIN bloqueo legal.** La arquitectura propuesta (Keycloak → JWT → Gateway → yaml-agno → Casbin/OpenFGA → Sandbox) es compatible con la legislación argentina; la separación lógica satisface en derecho el art. 11 Ley 25.326 (no exige aislamiento físico); Keycloak Apache 2.0 no introduce riesgo de licencia.
- **Onboarding del primer tenant real: CONDICIONADO** a ML-01..ML-10 (§9) + L-01..L-06 previos. Sin contrato SaaS + DPA + disclaimers + evidencia de aislamiento + playbook de incidentes, los riesgos RL-14/RL-15 pasan de latentes a materializables con red de responsabilidad parcial.
- **Dos decisiones que se toman HOY con impacto legal futuro**: (1) **Keycloak, no auth propio** (ML-07 — elimina RL-16); (2) **aislamiento como inversión legal** (tests + RLS + audit trail = evidencia de diligencia ante reclamos, art. 1724).
- El dictamen previo sigue vigente en todo lo no modificado aquí (Fase 1/OSS, dominios A-G, O-01..O-07).

### Postura de seguridad coherente (Engram #2759): la amenaza cross-tenant CRÍTICA (SPEC_19+RLS) coincide con RL-14; la exfiltración de secretos y la prompt injection (top-5) alimentan RL-15 y RL-18. El dictamen legal y la postura técnica apuntan al mismo lugar: **rigor de aislamiento + HITL + evidencia**.

---

## §11. Fuentes, vacíos de evidencia y supuestos

### 11.1 Fuentes normativas citadas
Ley 25.326 (arts. 2, 4, 5, 6, 7, 11, 12, 14-16, 21) + Decreto 1558/2001; **Disposición AAIP 47/2018** (niveles de seguridad); CCyC (arts. 958, 961, 988-989, 362-373, 1251 ss., 1708-1780: 1716, 1724, 1743-1744, 1753, 1757); Ley 24.240 (arts. 1-3, 37-38, 40-42 — B2B); Ley 25.506 (firma electrónica/digital, art. 3); Ley 20.488 (arts. 2-3); Ley 11.723; Ley 11.683 (art. 70); CP arts. 153 bis, 173 bis; RG ARCA 2904/2010; GDPR arts. 3, 27, 28, 30, 33, 49, 83 (watch); Apache License 2.0.

### 11.2 Evidencia verificada (provenance) — separada de la interpretación
- **Modelo multitenant**: chatgpt-comparar-repositorios-open-source.md (2026-08-11) — arquitectura Keycloak→Gateway→yaml-agno→Casbin/OpenFGA→Sandbox; tenant_id como propiedad de seguridad (§19); regla de oro JWT ≠ authorization ≠ sandbox (§20). Leído directamente.
- **Licencias del stack** (no re-auditadas — se usan como evidencia del previo §1.1 y del doc de comparación): Keycloak, Casbin, OpenFGA, gVisor, Firecracker, OpenShell = **Apache 2.0**; Logto = MPL-2.0 (descartado por política de licencias). Sin hallazgo nuevo que requiera re-auditoría.
- **Dictamen previo**: COMPLIANCE-LEGAL_yaml-agno.md (2026-08-08) — L-01..L-06, O-01..O-07, RL-01..RL-13, cláusulas §5.2, checklist §3.1, dominios A-G. Leído directamente.
- **Postura de seguridad**: Engram #2759 (top-5 amenazas: cross-tenant CRÍTICA, secretos CRÍTICA, prompt injection ALTA, credenciales ALTA, supply chain MEDIA-ALTA).

### 11.3 Vacíos de evidencia escalados [requieren verificación humana]
- **[VACÍO DE EVIDENCIA: interpretación tributaria detallada ARCA (RG 4291, retenciones/IIBB, monotributo vs SAS) — pendiente de @finance-team]** (dominio F del previo, referenciado; NO analizado aquí — encuadre legal de mandato ARCA RG 2904/2010 + CCyC 362 ss. sí es de este dictamen, §2.2 cláusula 14).
- **[VACÍO DE EVIDENCIA: SPEC_19/RLS y tests de aislamiento cross-tenant aún no verificados en producción]** (§3.2, §8 — condicionan ML-03).
- **[VACÍO DE EVIDENCIA: seguro cyber — sin cotización ni verificación de cobertura en Argentina; exclusiones de IA del mercado 2026]** (§4.4, ML-10).
- **[VACÍO DE EVIDENCIA: estado 2026 de la reforma de Ley 25.326 / notificación de breaches; práctica vigente de la AAIP sobre notificación voluntaria]** (§6.2 — arrastre del previo §11.3).
- **[VACÍO DE EVIDENCIA: matrícula profesional del equipo CENF para supervisión HITL contable (Ley 20.488)]** (§5 — arrastre del previo §11.3).
- **[VACÍO DE EVIDENCIA: decisiones de adecuación UE para Argentina — verificar estado 2026]** (GDPR watch, arrastre del previo §11.3).

### 11.4 Supuestos
- CENF opera en Argentina (CABA); jurisdicción default. Clientes: PyMEs argentinas B2B (con matiz art. 3 Ley 24.240 para monotributista persona humana).
- La plataforma multitenant es un **managed service SaaS** (no la librería OSS aislada) — esto eleva la intensidad de los dominios B/G respecto del previo (encargado de tratamiento permanente, subprocesadores, transferencias internacionales).
- El tenant es **responsable del tratamiento** de sus datos; CENF es **encargado** (art. 4 Ley 25.326) — salvo bases propias de CENF.
- La regla de oro del modelo (Authentication ≠ Authorization ≠ Sandbox) se implementa tal como está diseñada; la evidencia de aislamiento es verificable en CI.
- No hay tenants reales en producción aún (si ya existen, RL-14/RL-15 pasan a materializados).

### 11.5 Limitación de ejecución
Sin delegación a sub-roles (mismo límite de profundidad documentado en COMPLIANCE-LEGAL §11.5 y STRATEGIC §11.6). Análisis ejecutado por el orquestador con el rigor metodológico del previo: evidencia separada de interpretación, confianza por afirmación, vacíos escalados. Pendientes para próximas rondas: **dominio F con @finance-team**; revisión de redacción contractual por abogado matriculado; cotización de seguro cyber.

---

## §12. Communication Contract (CENF Standard v1.0 — 4 artifacts)

### 12.1 Human Brief (≤10 líneas ejecutivas)

1. La plataforma multitenant es legalmente viable en Argentina: 🟡 GO condicionado — sin bloqueo para el desarrollo, onboarding de tenants condicionado a ML-01..ML-10.
2. El art. 11 Ley 25.326 NO exige aislamiento físico: separación lógica rigurosa (tenant_id + Casbin + sandbox) es suficiente en derecho, con evidencia técnica.
3. Riesgo #1: cross-tenant contamination (RL-14, 🔴) — se gestiona con tests de aislamiento en CI, playbook de incidentes 72 h y cláusula de fuga.
4. Riesgo #2: falla de sandbox cross-tenant (RL-15, 🔴) — el cap contractual NO cubre dolo/culpa grave (art. 1743): la protección es aislamiento real + seguro.
5. Decisión legal recomendada: **Keycloak, NO auth propio** — diligencia debida (art. 1724) y evidencia ante reclamos. Apache 2.0 sin riesgo de licencia.
6. Los disclaimers de IA del previo se intensifican en multitenant: deny-default, HITL irrenunciable para acciones irreversibles, Ley 20.488.
7. El contrato SaaS multitenant (16 cláusulas + 6 anexos) amplía el de Fase 1: AUP, SLA, subprocesadores, exit/borrado certificado.
8. Antes del primer tenant: contrato + DPA + consentimientos + mandato ARCA (L-01..L-02 previos siguen vigentes).
9. Pendiente @finance-team: detalle tributario ARCA; pendiente de mercado: seguro cyber.
10. Nada de esto es asesoramiento legal vinculante — validar con abogado matriculado antes de firmar contratos.

### 12.2 Decision Card — decisión legal GO/NO-GO multitenant

| Campo | Valor |
|---|---|
| **Decisión** | **GO condicionado** (desarrollo) / **NO-GO para onboarding de tenants** hasta cumplir ML-01..ML-10 + L-01..L-06 |
| **Condiciones bloqueantes** | ML-03 (evidencia aislamiento), ML-04 (playbook 72 h), ML-01/ML-02 (contrato + matriz responsabilidad), ML-07 (decisión Keycloak) |
| **Riesgos que la decisión acepta** | RL-14/RL-15 como riesgos gestionados (no eliminados) |
| **Dueño de la decisión** | Gonzalo + Legal (validación profesional) |
| **Vigencia** | Revisar al materializarse tenants reales, cambios normativos (reforma Ley 25.326) o incidentes |

### 12.3 Evidence Package (normativa + fuentes con refs)

- Normativa citada: Ley 25.326 arts. 2, 4, 5, 6, 7, 11, 12, 14-16, 21 + Dec. 1558/2001; Disp. AAIP 47/2018; CCyC arts. 958, 961, 988-989, 362-373, 1251 ss., 1708-1780 (1716, 1724, 1743-1744, 1753, 1757); Ley 24.240 arts. 1-3, 37-38, 40-42; Ley 25.506 art. 3; Ley 20.488 arts. 2-3; Ley 11.723; Ley 11.683 art. 70; CP arts. 153 bis, 173 bis; RG ARCA 2904/2010; GDPR arts. 3, 27, 28, 30, 33, 49, 83; Apache License 2.0.
- Fuentes del modelo: chatgpt-comparar-repositorios-open-source.md (2026-08-11, §3/§19/§20); COMPLIANCE-LEGAL_yaml-agno.md (2026-08-08, §1.1/§2/§3.1/§5.2/§8/§9/§11); Engram #2759, #2754, #2753.
- Provenance de licencias: Keycloak/Casbin/OpenFGA/gVisor/Firecracker/OpenShell Apache 2.0 (doc de comparación + previo §1.1 — usadas como evidencia, no re-auditadas).

### 12.4 Handoff Contract (pendientes, bloqueos, coordinación)

| Ítem | Estado | Destino |
|---|---|---|
| Redacción de plantilla contractual SaaS multitenant (§2.2) | Pendiente | **Profesional matriculado** (abogado) — borrador listo para validación |
| Validación del matiz art. 1757 (actividad riesgosa del runtime) | Pendiente | **Profesional matriculado** — interpretación novedosa |
| Detalle tributario ARCA (RG 4291, retenciones, IIBB) | `[VACÍO DE EVIDENCIA]` | **@finance-team** (especialista-tributario/contador-arca) |
| Cotización seguro cyber (cobertura cross-tenant, exclusiones IA) | `[VACÍO DE EVIDENCIA]` | **@finance-team** + proveedor de seguros |
| Integración RL-14..RL-21 a matriz consolidada | Coordinación | **@risk-team** (riesgo-legal) en su próxima ronda |
| Verificación SPEC_19/RLS/tests cross-tenant en producción | `[VACÍO DE EVIDENCIA]` | **Devs** (condición ML-03) |
| Reforma Ley 25.326 / notificación de breaches (estado 2026) | `[VACÍO DE EVIDENCIA]` | Legal (monitoreo normativo trimestral, G-06) |
| Decisión formal Keycloak vs auth propio (ML-07) | Acción | **Gonzalo + Legal** — registrar en DECISIONES.md |

**Bloqueos**: ninguno absoluto. Los bloqueantes de onboarding (ML-03, ML-04, ML-01/02, ML-07) tienen camino definido y de costo bajo-medio. **Nada de este dictamen es vinculante sin validación de profesional matriculado.**

---

*Dictamen DELTA generado por Legal Team CENF — 2026-08-11*
*Opinion preliminar — requiere validación de abogado/a matriculado/a antes de uso contractual o lanzamiento comercial.*
*Base: COMPLIANCE-LEGAL_yaml-agno.md (2026-08-08) — referenciado, no reemplazado.*


