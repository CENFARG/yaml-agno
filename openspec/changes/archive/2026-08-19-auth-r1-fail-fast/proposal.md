---
change: auth-r1-fail-fast
spec: SPEC_12 Slice 3 / SPEC_19 §4 R1
status: proposed
artifact_store: hybrid
depends_on: []
---

# Proposal: auth-r1-fail-fast — Eliminar el fail-open declarativo R1 (S5a.0)

## Intent / Por qué

R1 (CRITICAL, reproducido 2026-08-18 contra agno 2.8.7 instalado): `AuthorizationConfig`
de Agno acepta EXACTAMENTE 7 campos (`verification_keys, jwks_file, algorithm,
verify_audience, audience, admin_scope, user_isolation`); pydantic `extra=ignore`
dropea `basic_auth` y cualquier key de `settings.config` sin sink. Hoy DOS sitios
hacen forward ciego: `AuthorizationAdapter.build()` (`kwargs.update(resolved_config)`
+ `kwargs["basic_auth"]`, authorization_adapter.py:77-81) y
`AgentOSFactory._build_authorization_config_legacy` (agentos_factory.py:515-524,
forwards `basic_auth` + `config` — ambos no-op). Resultado: config de seguridad que
el operador cree activa y NO está — fail-open declarativo (clase OWASP "security
config accepted but ignored"). Los tests T007a-e solo asieren `cfg is not None`:
jamás detectaron el drop.

**Éxito**: el build de authorization es fail-fast — whitelist de los 7 campos reales,
rechazo explícito de `basic_auth`/keys desconocidas, invariant `user_isolation=True`,
contract tests que asieren CONTENIDO. Es prerrequisito de S5a (JWT+Casbin): construir
auth sobre un plano declarativo que miente es indefendible.

Ratificado: D-F1-10 (2026-08-18), gate VQ011, AUTH-INTEGRATION-READINESS §4 R1.

## Scope

### In Scope
- Whitelist module-level (`_SUPPORTED_FIELDS`) en `authorization_adapter.py`: mapear
  SOLO los 6 campos settables desde `settings.config` (con resolución `${SECRET:...}`);
  `user_isolation=True` es invariante del adapter, no settable.
- Key desconocida en `settings.config` → `AuthorizationBuildError` listando los 7
  campos soportados (precedente: SPEC_29 OnReject, D-F1-08 MemoryConfig).
- `basic_auth` → `AuthorizationBuildError`: agno 2.8.7 no tiene sink; pointer a
  SPEC_19 §1.2 BasicAuthMiddleware (S5a.2).
- `user_isolation` explícito en `config` → `AuthorizationBuildError` (su valor se
  pisaría en silencio = nuevo mini-no-op).
- Legacy path (`agentos_factory.py`) delega al mismo whitelist; `${SECRET:...}` sin
  resolver en legacy → raise (pasar el literal sería otro fail-open).
- `AuthorizationSettings.basic_auth` (agentos_config.py:53): marcado UNSUPPORTED en
  docstring/Field description (deprecation documentada; removal en S5a.2).
- Tests: rewrite T007b/d/e con keys reales + content assertions (`cfg.user_isolation
  is True`, `cfg.algorithm == "HS256"`, raises) — RED primero. Update factory tests
  (test_agentos_factory.py:799,841).

### Out of Scope (DEFER)
- JWT wiring real (S5a.1), Casbin vía core-cenf PermissionManager (VQ013, S5a),
  Keycloak + token mapper `tnt` (S5b).
- BasicAuthMiddleware dev-only SPEC_19 §1.2 — el sink futuro de basic_auth.
- Removal total del campo `basic_auth` del schema (S5a.2).
- R4/R5 del readiness doc (claims mapper, AuditPort).

## Capabilities

### New Capabilities
- `agentos-authorization-build`: contrato fail-fast del build de `AuthorizationConfig`
  — whitelist 7 campos, rechazo unknown/basic_auth/override de invariant, resolución
  de secrets, `user_isolation=True` invariante.

### Modified Capabilities
- Ninguna (yaml-agentos-foundation Scenario 8 — default `authorization=False` — es
  ortogonal y no se toca).

## Approach

**Fail-fast, no silent-ignore**: una config de auth aceptada e ignorada es
vulnerabilidad, no bug cosmético; un warning en log no es contrato alcanzable por
quien opera el build. **Rechazar `basic_auth`, no mapearlo**: no existe sink en agno
2.8.7; fabricar uno apurado viola build-on-top, y la regla anti-no-op corta en ambas
direcciones (sin sink → sin campo efectivo). **Un solo contrato compartido**: función
de mapeo pura en `authorization_adapter.py` usada por adapter Y legacy path — R1
muere en los DOS sitios que nombra la evidencia. Strict TDD: contract tests RED con
content assertions antes del GREEN.

## Affected Areas

| Area | Impact | Descripción |
|------|--------|-------------|
| `src/yaml_agno/agentos/authorization_adapter.py` | Modified | Whitelist + rechazos + helper compartido. |
| `src/yaml_agno/agentos/errors.py` | Modified | Docstring ampliado; sin clase nueva. |
| `src/yaml_agno/factories/agentos_factory.py` | Modified | Legacy path delega al whitelist. |
| `src/yaml_agno/models/config/agentos_config.py` | Modified | Field `basic_auth` marcado UNSUPPORTED. |
| `tests/unit/agentos/test_authorization_adapter.py` | Modified | Contract tests RED-first. |
| `tests/unit/factories/test_agentos_factory.py` | Modified | Legacy-path tests alineados. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Rompe configs YAML con `basic_auth`/keys inválidas | Alta (intencional) | Error accionable: lista los 7 campos + alternativa S5a.2; migración documentada en el spec delta. |
| Tests T007b/d/e existentes fallan (keys ficticias) | Cierta | Rewrite RED-first planneado. |
| Drift agno > 2.8.7 cambia campos de AuthorizationConfig | Baja | `_SUPPORTED_FIELDS` documenta versión verificada; contract test = tripwire. |
| Rechazo de `user_isolation` en config sorprenda | Baja | Mensaje: "security invariant, always True". |

## Rollback Plan

`git revert` del commit del slice. Código de build-time + tests: sin estado persistido
ni migraciones. El campo `basic_auth` queda en el schema (no se remueve), así que las
configs siguen parseando idéntico tras el revert.

## Dependencies

- Ninguna nueva. agno==2.8.7 (pin verificado hoy), pydantic v2, pytest existentes.

## Success Criteria

- [ ] Config válida → `cfg.user_isolation is True` + cada campo asertado por CONTENIDO
      (`cfg.algorithm == "HS256"`, etc.).
- [ ] Key desconocida → `AuthorizationBuildError` listando los 7 soportados.
- [ ] `basic_auth` con `enabled=True` → `AuthorizationBuildError` mencionando agno 2.8.7.
- [ ] `user_isolation` en config → `AuthorizationBuildError`.
- [ ] Legacy path: mismos rechazos + secret-ref sin resolver → raise.
- [ ] VQ011: `kwargs.update` en authorization_adapter.py → ZERO.
- [ ] `python -m pytest tests/unit/agentos/ tests/unit/factories/test_agentos_factory.py -m unit` en verde.

## Proposal question round

1. **`user_isolation` explícito en `config`**: asumo RECHAZAR siempre (invariant).
   ¿O permitir `true` explícito?
2. **Visibilidad del helper**: asumo función privada compartida importada por la
   factory. ¿O API pública para S5a?
3. **`basic_auth` con `enabled=False`**: asumo que el guard gana (nada se construye,
   no hay fail-open). ¿O rechazo también en disabled?
4. **Deprecation del campo**: asumo docstring + Field description. ¿O además
   `DeprecationWarning` en parse?
