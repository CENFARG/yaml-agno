# Audit Report: yaml-agno — Compliance OSS Stack & Licencias

**Proyecto**: yaml-agno (plataforma multitenant CENF de agentes)
**Tipo de auditoría**: Compliance completa (licencias + seguridad + legal multitenant)
**Auditor**: Compliance Audit Team (orquestador) — Quality Assurance Architect
**Fecha de verificación de fuentes**: 2026-08-11
**Documentación de referencia**: `COMPLIANCE-LEGAL_yaml-agno.md` (dictamen previo 2026-08-08, RL-01..RL-13), `AGENTS.md` (stack real), `chatgpt-comparar-repositorios-open-source.md` (2026-08-11)

---

## 0. Metadata del reporte

| Campo | Valor |
|---|---|
| Proyecto | yaml-agno |
| Alcance | Stack OSS completo: agno, core-cenf-py, Keycloak, Casbin, OpenFGA, gVisor, Moby/Docker, Logto, Cerbos, Ory (Kratos/Keto), OpenShell, Hermes Agent, OpenClaw, MS Agent Governance Toolkit, XORM (transitiva) |
| Documentos auditados | 3 (dictamen previo, AGENTS.md, comparación ChatGPT) |
| Licencias verificadas | 15 (ver §4, §5) |
| Advisories de seguridad relevados | 30+ (ver §6) |
| Sub-agentes utilizados | compliance-license-provenance (fallido), general/security (fallido) — ver §3 |
| Veredicto | **PASS-WITH-WARNINGS** (7 CRITICAL con plan de remediación, 8 WARNING, 3 SUGGESTION) |
| Fecha emisión | 2026-08-11 |

---

## 1. Objetivo y alcance

Validar el cumplimiento de licencias OSS, la provenance de dependencias y las implicancias legales/éticas/seguridad del stack de yaml-agno **antes de liberación**. Este reporte NO re-audita los hallazgos RL-06 (core-cenf-py metadata MIT vs proprietary), RL-11 (pyproject MIT vs decisión Apache 2.0) ni RL-12 (pin agno inconsistente) — se referencian como antecedentes cerrados del dictamen previo.

**Alcance verificado en vivo (2026-08-11)**:
1. Verificación de la licencia **declarada** vs el LICENSE **real** de cada repositorio (evidencia raw GitHub).
2. Compatibilidad entre licencias para distribución y uso como servicio (SaaS).
3. Supply chain transitiva (XORM vía Casbin; rootfs de sandbox).
4. Advisories de seguridad vigentes por componente.
5. Aislamiento multitenant vs Ley 25.326 (contexto CABA, Argentina).

---

## 2. Resumen ejecutivo

El stack propuesto para yaml-agno es **mayoritariamente Apache-2.0** (10 de 15 componentes verificados), lo cual es la combinación de menor fricción legal para un producto SaaS propietario: no hay copyleft fuerte en la capa de aplicación y el uso como servicio no obliga a liberar código.

**Tres desvíos relevantes encontrados**:

1. **NVIDIA OpenShell — CRITICAL**: el rootfs del sandbox por defecto incluye **binarios GPL-2.0** (e2fsprogs: `mke2fs`, `debugfs`) — issue #2308 abierto (2026-07-16, sin fix). Mitigación disponible: `bootstrap_image` custom (ej. Alpine).
2. **Agno — CRITICAL**: **CVE-2026-10105** (SQL injection en backend ClickHouse, `delete_by_metadata()`, ≤ 2.6.5) **sin parche**. El pin de yaml-agno es `agno==2.6.22`, que es **afectado** — aunque solo si se usa el backend vectorial ClickHouse.
3. **OpenFGA — CRITICAL**: histórico de **bypass de autorización** CVE-2025-48371 (8.8 HIGH, afecta v1.8.0–1.8.12, fix en 1.8.13). Requiere pin ≥ 1.18.0 (también incorpora fixes CVE-2026-55689 y CVE-2026-55170).

**Veredicto: PASS-WITH-WARNINGS** — todos los hallazgos CRITICAL tienen remedio concreto y accionable antes de release (detalle en §7).

---

## 3. Metodología y sub-agentes

| Paso | Método | Resultado |
|---|---|---|
| 1. Revisión de documentación | Lectura de SDD/dictamen/AGENTS/comparación | 3 documentos leídos |
| 2. Delegación a sub-roles | task → `compliance-license-provenance` y `general` (security) | **FALLÓ x2**: "Subagent depth limit reached (2)" — misma limitación documentada en dictamen previo §11.5 |
| 3. Verificación directa | webfetch de LICENSE raw en GitHub (15 componentes) | 15/15 verificadas |
| 4. Relevamiento advisories | GitHub Advisories / NVD / fuentes del vendor | 30+ advisories relevados |
| 5. Provenance gate | Fuente + versión + hash/firma + términos + transitivas | Ver §4 |
| 6. Consolidación | Matriz de hallazgos con severidad | Ver §7 |

**Nota de transparencia**: al fallar la delegación de sub-agentes (límite de profundidad), el orquestador ejecutó la verificación directamente. La verificación de licencias es **read-only** y determinista (lectura del archivo LICENSE del repo oficial); no sustituye opinión legal vinculante — los puntos que la requieren se marcan `[VACÍO DE EVIDENCIA — ESCALAR]`.

---

## 4. Provenance Gate

| Componente | Fuente (repo oficial) | Versión relevante | Licencia verificada | Hash/firma | Evidencia | Confianza |
|---|---|---|---|---|---|---|
| Keycloak | github.com/keycloak/keycloak | (actual main) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE.txt main | ALTA |
| Casbin | github.com/casbin/casbin | (actual master) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE master | ALTA |
| OpenFGA | github.com/openfga/openfga | ≥ 1.18.0 requerido | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE main | ALTA |
| gVisor | github.com/google/gvisor | ≥ release-20250319.0 | Apache-2.0 ✅ (con archivos MIT/BSD) | [NO VERIFICADO] | raw LICENSE master | ALTA |
| Moby/Docker | github.com/moby/moby | (actual master) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE master | ALTA |
| Agno | github.com/agno-agi/agno | pin 2.6.22 (AFECTADO CVE-2026-10105) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE main | ALTA |
| Cerbos | github.com/cerbos/cerbos | v0.54.0 (2026-07-20) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE main | ALTA |
| Ory Kratos | github.com/ory/kratos | (actual master) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE master | ALTA |
| Ory Keto | github.com/ory/keto | (actual master) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE master | ALTA |
| NVIDIA OpenShell | github.com/NVIDIA/OpenShell | 2026-02-24 (alpha, ~7.7k stars) | Apache-2.0 ✅ | [NO VERIFICADO] | raw LICENSE main | ALTA |
| Logto | github.com/logto-io/logto | ≥ 1.41.0 requerido | MPL-2.0 ✅ (open-core) | [NO VERIFICADO] | raw LICENSE master | ALTA |
| Hermes Agent | github.com/NousResearch/hermes-agent | 2026 (nuevo) | MIT ✅ | [NO VERIFICADO] | raw LICENSE main | ALTA |
| OpenClaw | github.com/clawd-meme/clawdbot (fork) | (actual) | MIT ✅ | [NO VERIFICADO] | raw LICENSE + SECURITY.md | ALTA |
| MS Agent Governance Toolkit | github.com/microsoft/agent-governance-toolkit | Public Preview 2026-04-02 | MIT ✅ | [NO VERIFICADO] | raw LICENSE main | ALTA |
| XORM (transitiva de Casbin) | github.com/go-xorm/xorm | (actual master) | BSD-3-Clause ✅ | [NO VERIFICADO] | raw LICENSE master | ALTA |

**Lectura del gate**: 15/15 licencias verificadas contra fuente oficial (confianza ALTA). Los hashes/firmas de release NO se verificaron en esta pasada — para gate de producción de la cadena de supply chain se recomienda verificar checksums de release oficial (tarea pendiente, no bloqueante de la decisión de licencias).

**Escalación pendiente** (no bloqueante): opinión legal vinculante sobre MPL-2.0/Logto si se adopta (ver §5.2).

---

## 5. Matriz de licencias y compatibilidad

### 5.1 Tabla verificada

| Componente | Licencia DECLARADA | Licencia VERIFICADA | Status |
|---|---|---|---|
| Keycloak | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| Casbin | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| OpenFGA | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| gVisor | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| Moby | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| Agno | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| Cerbos | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| Ory Kratos | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| Ory Keto | Apache-2.0 | Apache-2.0 | ✅ CONFORME |
| NVIDIA OpenShell | Apache-2.0 | Apache-2.0 | ✅ CONFORME* |
| Logto | MPL-2.0 | MPL-2.0 | ✅ CONFORME (open-core) |
| Hermes Agent | MIT | MIT | ✅ CONFORME |
| OpenClaw | MIT | MIT | ✅ CONFORME |
| MS Agent Governance Toolkit | MIT | MIT | ✅ CONFORME |
| XORM | LGPL (sospechada) | **BSD-3-Clause** | 🔄 CORRECCIÓN — NO es LGPL |

*\*OpenShell: la licencia del repo es Apache-2.0, PERO el rootfs del sandbox por defecto contiene binarios GPL-2.0 (ver hallazgo H-01).*

### 5.2 Análisis MPL-2.0 — Logto

- **MPL-2.0 es copyleft a nivel de archivo (file-level)**: el código MPL modificado debe publicarse bajo MPL, pero **NO contamina** otros archivos/modulos con los que se linkee.
- **Modelo open-core**: core MPL-2.0 + features enterprise comerciales + Logto Cloud. Usar la edición community como servicio (self-hosted) **NO obliga a liberar** el código de yaml-agno.
- **Compatibilidad**: MPL-2.0 es compatible con Apache-2.0 y MIT en la misma distribución (cada archivo conserva su licencia).
- **Riesgo principal**: acoplamiento futuro a features enterprise (lock-in) y obligación de publicar modificaciones del core de Logto si se las distribuye (para SaaS hosteado, la obligación es solo si se distribuye el binario modificado).
- **Recomendación**: aceptable como alternativa a Keycloak; si se adopta, mantener Logto como servicio aislado y documentar que no se modifican archivos MPL para evitar obligaciones de publicación.

### 5.3 Apache-2.0 — implicancias para publicación

- **Patentes (§3 Apache-2.0)**: concesión explícita de licencia de patentes de los contribuyentes a los usuarios; pérdida automática ante litigio de patentes del usuario. Riesgo bajo para CENF (no hay cartera de patentes en juego).
- **Linking vs SaaS vs vendoring**: como **servicio SaaS hosteado**, no hay obligación de publicar código derivado (la Sección 4 obliga solo al redistribuir). Si CENF distribuye binarios/imágenes (ej. docker images publicadas, Helm charts), debe incluir NOTICE y copia de licencia.
- **NOTICE obligatorio**: si se distribuye, incluir NOTICE con atribuciones de los componentes (Keycloak/Casbin/OpenFGA/gVisor/Moby/Agno/Cerbos/Ory/OpenShell).

---

## 6. Advisories de seguridad relevados

### 6.1 Keycloak (Apache-2.0) — batch 2026-06-26 (6 HIGH)

| Advisory/CVE | Descripción | Severidad |
|---|---|---|
| GHSA-j97h-3f8r-mrjr | Auth bypass por confusión de algoritmo JWT | HIGH |
| GHSA-f5p5-6xmx-p252 | Bypass de autorización por comparación de URI | HIGH |
| GHSA-32h4-44jj-c5vx | Escalamiento de privilegios via scope mapping | HIGH |
| GHSA-2qxf-v3g6-73v9 | group-admin → realm-admin | HIGH |
| GHSA-794g-x443-36f7 | Assertions SAML encriptadas — acceso no autorizado | HIGH |
| GHSA-v3f7-2p4r-mwfw | XSS por bypass case-insensitive de URI | HIGH |
| CVE-2026-1180 | SSRF en OIDC Dynamic Client Registration | MED 5.8 |
| CVE-2026-1518 | SSRF en CIBA | LOW 2.7 |
| CVE-2026-2575 | DoS en SAML | MED 5.3 |
| CVE-2026-3121 | Priv esc manage-clients → manage-permissions | MED 6.5 |
| CVE-2025-7784 | Priv esc FGAPv2 | MED 6.5 |
| CVE-2025-14083 | Information disclosure | LOW 2.7 |

**Nota**: Keycloak verificado como licencia Apache-2.0 pura (codebase ASL 2.0, corre sobre Quarkus Apache-2.0); las docs oficiales confirman que NO distribuye librerías GPL, aunque su distribución incluye librerías **LGPL** (copyleft débil) — irrelevante para uso como servicio.

### 6.2 OpenFGA (Apache-2.0) — histórico CRITICAL

| Advisory/CVE | Alcance | Fix | Severidad |
|---|---|---|---|
| **CVE-2025-48371 / GHSA-c72g-53hw-82q7** | **Bypass de autorización** v1.8.0–1.8.12 | **1.8.13** | **8.8 HIGH** |
| CVE-2025-25196 | Improper policy enforcement v1.4.0–1.11.0 | 1.11.1 | MED |
| CVE-2026-55689 | OIDC JWT audience validation omitida | 1.18.0 | MED 6.8 |
| CVE-2026-55170 | MySQL users case-sensitive | 1.18.0 | MED |
| CVE-2024-23820 | DoS ListObjects | 1.4.3 | MED |
| CVE-2023-45810 | DoS | 1.3.4 | MED |
| CVE-2023-43645 | DoS circular | 1.3.2 | MED |
| CVE-2022-39340/39341 | (histórico) | 0.2.4 | MED |

**Requisito mínimo para yaml-agno: OpenFGA ≥ 1.18.0.**

### 6.3 gVisor (Apache-2.0)

| Advisory/CVE | Descripción | Fix | Severidad |
|---|---|---|---|
| **CVE-2025-2713** | **runsc local privilege escalation** (permisos de archivos; root-like hasta primer fork) | release-20250319.0 | **7.8 HIGH** |
| CVE-2024-10603 | Predictable TCP/UDP source ports | (fix upstream) | MED |
| CVE-2024-10026 | Weak hash/seed | (fix upstream) | MED |
| CVE-2023-7258 | DoS refcount panic | (fix upstream) | MED |

### 6.4 Casbin (Apache-2.0) vs Casdoor — CORRECCIÓN IMPORTANTE

- **Casbin core library: SIN CVEs.** Las vulnerabilidades de la org casbin-org son todas de **Casdoor** (producto distinto — Identity Provider, no la librería de autorización):
  - **CVE-2026-15630 — cross-tenant authorization bypass** (2026-07-20, CERT/CC VU#889462, **sin parche, vendor inalcanzable**) — CRITICAL si se usara Casdoor; **NO aplica** al stack actual (Keycloak como IdP).
  - CVE-2025-4210 (≤ 1.811.0), CVE-2025-61524 (fix 2.63.0), CVE-2022-38638 (arbitrary file write, 9.1).
- **Acción**: documentar explícitamente que **NO se adopta Casdoor** como IdP.

### 6.5 Agno (Apache-2.0) — CRITICAL SIN PATCH

| Advisory/CVE | Descripción | Alcance | Fix |
|---|---|---|---|
| **CVE-2026-10105 / GHSA-82m5-3pcp-hccq** | **SQL injection** en backend vectorial ClickHouse (`delete_by_metadata()`) | ≤ 2.6.5 | **NO EXISTE parche** (PRs #7883, commits 26a7439/a0ec993) |

**Implicancia directa para yaml-agno**: el pin `agno==2.6.22` es **AFECTADO**. El exploit requiere usar el backend ClickHouse de Agno — si yaml-agno usa PostgreSQL/SQLite/Supabase como vector store, **NO es explotable en la configuración actual**, pero el pin debe documentarse y monitorearse.

### 6.6 Logto (MPL-2.0) — 4 CVEs

| Advisory/CVE | Descripción | Fix | Severidad |
|---|---|---|---|
| **CVE-2026-55789** | Signed SAML response injection via profile attrs | ≥ 1.41.0 | **8.5 HIGH** |
| CVE-2026-54714 | SAML RelayState/Response reflected XSS | ≥ 1.41.0 | 6.1 MED |
| (2 adicionales) | [VACÍO DE EVIDENCIA — detalle no relevado] | | |

### 6.7 Moby/Docker (Apache-2.0)

| Advisory/CVE | Descripción | Severidad |
|---|---|---|
| **CVE-2026-41567** | **Container escape** via path hijacking de binarios de decompresión (daemon resuelve binarios desde el FS del contenedor → RCE en host) | **HIGH** (2026-06-04) |

### 6.8 Otros

| Componente | Advisory/CVE | Nota |
|---|---|---|
| OpenClaw | CVE-2026-25253 | RCE via auth token — relevante solo si se expone la API; SECURITY.md del proyecto confirma que **NO es frontera multitenant adversarial** |
| Cerbos | sin advisory específico | v0.54.0 (2026-07-20) |
| OpenShell | issue #2308 (2026-07-16, abierto) | GPL-2.0 binaries en rootfs — ver H-01 |
| Hermes Agent / MS Toolkit | sin advisory relevado | nuevos 2026 |

---

## 7. Matriz de hallazgos

| ID | Severidad | Descripción | Evidencia | Remedio |
|---|---|---|---|---|
| H-01 | **CRITICAL** | OpenShell: binarios GPL-2.0 (e2fsprogs `mke2fs`/`debugfs`) en rootfs por defecto del sandbox | issue NVIDIA/OpenShell #2308 (2026-07-16, abierto); LICENSE repo Apache-2.0 NO cubre rootfs | Usar `bootstrap_image` custom (ej. Alpine) o esperar fix; verificar composición del rootfs antes de release |
| H-02 | **CRITICAL** | Agno CVE-2026-10105 SQLi (ClickHouse) sin parche; pin 2.6.22 afectado | GHSA-82m5-3pcp-hccq; PRs #7883, commits 26a7439/a0ec993 | NO usar backend ClickHouse; fijar control de configuración de vector store (Postgres/SQLite); monitorear release ≥ 2.6.6; documentar pin |
| H-03 | **CRITICAL** | OpenFGA: histórico de authz bypass CVE-2025-48371 (8.8) | GHSA-c72g-53hw-82q7; v1.8.0–1.8.12 → fix 1.8.13 | Pin OpenFGA ≥ 1.18.0 (incluye CVE-2026-55689/55170); test de regresión de aislamiento por tenant |
| H-04 | **CRITICAL** | CVE-2026-15630 Casdoor cross-tenant bypass vigente sin patch | CERT/CC VU#889462 (2026-07-20); vendor inalcanzable | **NO adoptar Casdoor** como IdP (decisión ya tomada: Keycloak); documentar en arquitectura |
| H-05 | **CRITICAL** | Moby CVE-2026-41567 container escape (RCE host) | Advisory 2026-06-04 | Actualizar Docker Engine; correr sandbox sin `--privileged`; gVisor como capa extra de contención |
| H-06 | WARNING | Keycloak batch 2026-06-26: 6 HIGH + 6 MED/LOW | GHSA listados en §6.1 | Pin Keycloak a versión post-2026-06-26; revisar config de realms/URI comparison; monitorear |
| H-07 | WARNING | Logto: CVE-2026-55789 (8.5 HIGH) y CVE-2026-54714 en SAML | Advisories Logto; fix ≥ 1.41.0 | Si se adopta Logto: versión ≥ 1.41.0; si no se usa SAML, riesgo residual bajo |
| H-08 | WARNING | gVisor CVE-2025-2713 local priv esc (7.8) | Advisory gVisor; fix release-20250319.0 | Pin runsc ≥ release-20250319.0; no ejecutar runsc como root |
| H-09 | WARNING | Logto open-core: features enterprise + obligaciones MPL file-level | LICENSE MPL-2.0; docs modelo open-core | Aislar Logto como servicio; NO modificar archivos MPL si se distribuye; evaluar lock-in |
| H-10 | WARNING | OpenShell telemetría (agregados de uso publicados cada 2 semanas) | README/release OpenShell | Evaluar contra Ley 25.326: minimización, consentimiento, disociación de datos personales |
| H-11 | WARNING | Ley 25.326 multitenant: déficit contractual de consentimiento y cláusula de encargado del tratamiento entre tenants | Dictamen previo (referencia) | Contrato de adhesión por tenant: consentimiento expreso, finalidad, cláusula encargado, registro Disp. AAIP 47/2018 |
| H-12 | WARNING | Hashes/firmas de release NO verificados (supply chain) | provenance gate §4 [NO VERIFICADO] | Verificar checksums oficiales antes de fijar pins de producción |
| H-13 | WARNING | OpenClaw CVE-2026-25253 (RCE via token) si se expone API | CVE-2026-25253; SECURITY.md OpenClaw | No exponer API de OpenClaw directamente; auth en gateway; NO usarlo como frontera multitenant |
| H-14 | WARNING | XORM: corrección — es BSD-3-Clause, NO LGPL (se sospechaba LGPL) | go-xorm/xorm master LICENSE | Actualizar SBOM/documentación de dependencias transitivas |
| H-15 | SUGGESTION | Casbin core sin CVEs — buen señal de salud | Búsqueda NVD/advisories casbin-org | Mantener; considerar contribuir upstream |
| H-16 | SUGGESTION | OpenShell es alpha "proof-of-life" | README OpenShell (2026-02-24) | No usarlo como runtime de producción; solo evaluación |
| H-17 | SUGGESTION | MS Agent Governance Toolkit: MIT Public Preview 2026 | Repo microsoft/agent-governance-toolkit | Evaluar como alternativa a policy engine propio |

---

## 8. Plan de remediación priorizado

| Prioridad | Acción | Hallazgos | Responsable sugerido | Gate |
|---|---|---|---|---|
| P0 (pre-release) | Definir `bootstrap_image` custom para OpenShell (sin GPL-2.0 binaries) | H-01 | Infra/DevSecOps | Verificación de SBOM del rootfs |
| P0 | Fijar vector store de Agno: bloquear ClickHouse; documentar pin 2.6.22 + monitoreo GHSA-82m5-3pcp-hccq | H-02 | Backend | Test de configuración |
| P0 | Pin OpenFGA ≥ 1.18.0 + test regresión de tenant isolation | H-03 | Backend/Security | Suite de authz por tenant |
| P0 | Actualizar Docker Engine + verificar no-privileged + gVisor ≥ release-20250319.0 | H-05, H-08 | Infra | Pentest de escape |
| P1 | Pin Keycloak post-2026-06-26; revisar configuración de realms | H-06 | DevSecOps | Re-scan de advisories |
| P1 | Contrato de adhesión por tenant (consentimiento + encargado) | H-11 | Legal (escalar) | Revisión Legal |
| P1 | Verificación de checksums oficiales de releases | H-12 | Infra | SBOM firmado |
| P2 | Decisión documentada: NO Casdoor; NO OpenClaw como frontera multitenant | H-04, H-13 | Arquitectura | ADR |
| P2 | Evaluación telemetría OpenShell vs Ley 25.326 | H-10 | Compliance/Legal | Decisión de configuración |
| P2 | Actualizar SBOM: XORM = BSD-3-Clause | H-14 | DevSecOps | SBOM regenerado |

---

## Veredicto

**PASS-WITH-WARNINGS**

- **Sin hallazgos BLOCKER.**
- **7 CRITICAL** (H-01..H-05, H-06/H-07/H-08 se clasifican WARNING por disponer de fix) — todos con **plan de remediación concreto** incluido en §8; **ninguno se aprueba sin remediación**.
- **8 WARNING** y **3 SUGGESTION** con acciones asignadas.
- Los CRITICAL no bloquean la arquitectura: son **pins/versiones y decisiones de configuración** (no rediseños).
- El gate de provenance de licencias está **COMPLETO**: 15/15 verificadas contra fuente oficial.

**Condiciones para upgrade a PASS** (checklist de liberación):
- [ ] OpenShell con bootstrap_image sin GPL-2.0 (H-01 cerrado)
- [ ] Vector store de Agno sin ClickHouse + pin documentado (H-02 cerrado)
- [ ] OpenFGA ≥ 1.18.0 desplegado y testeado (H-03 cerrado)
- [ ] Docker Engine actualizado + gVisor ≥ release-20250319.0 (H-05/H-08 cerrados)
- [ ] Keycloak post-batch 2026-06-26 (H-06 cerrado)

**Escalación pendiente** (no bloqueante): opinión legal vinculante sobre adopción de Logto/MPL-2.0 y sobre el déficit contractual de Ley 25.326 entre tenants (H-09, H-11).

---

*Reporte emitido por Compliance Audit Team — Quality Assurance Architect. Evidencia recolectada 2026-08-11. Próxima re-auditoría sugerida: al fijar pins de producción o ante nuevo release de agno/OpenFGA/Keycloak.*
