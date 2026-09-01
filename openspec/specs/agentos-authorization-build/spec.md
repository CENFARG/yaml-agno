# agentos-authorization-build Specification

## Purpose

Define the fail-fast contract for building Agno's `AuthorizationConfig` from
yaml-agno's `AuthorizationSettings`. This capability exists to kill the R1
declarative fail-open (reproduced 2026-08-18 against installed agno 2.8.7):
`AuthorizationConfig` accepts exactly 7 fields (`verification_keys, jwks_file,
algorithm, verify_audience, audience, admin_scope, user_isolation`); pydantic
`extra=ignore` silently drops `basic_auth` and unknown `settings.config` keys,
so blind dict-forwarding yields security config the operator believes active
but is not. Gates satisfied by this spec: VQ011 (`.chats/decisions.yaml`) and
D-F1-10 (`DECISIONES.md`).

## Scope

### In Scope

- `src/yaml_agno/agentos/authorization_adapter.py` — field whitelist,
  rejections, shared private mapping helper.
- `src/yaml_agno/factories/agentos_factory.py` — legacy path delegates to the
  same helper; unresolved-secret rejection.
- `src/yaml_agno/models/config/agentos_config.py` — `AuthorizationSettings.basic_auth`
  documented UNSUPPORTED.
- `tests/unit/agentos/test_authorization_adapter.py`,
  `tests/unit/factories/test_agentos_factory.py` — content-asserting contract
  tests (RED first).

### Out of Scope (DEFER)

- JWT wiring (S5a.1), Casbin `PermissionManager` (S5a), Keycloak (S5b).
- `BasicAuthMiddleware` dev-only (SPEC_19 §1.2, S5a.2) — the future sink for
  `basic_auth`.
- Removal of the `basic_auth` field from the schema (S5a.2).
- R4/R5 of AUTH-INTEGRATION-READINESS (claims mapper, AuditPort).

## Requirements

### Requirement: Whitelist mapping of AuthorizationConfig fields

`AuthorizationAdapter.build()` MUST map ONLY the six settable fields from
`settings.config` onto `AuthorizationConfig`: `verification_keys`, `jwks_file`,
`algorithm`, `verify_audience`, `audience`, `admin_scope`. `user_isolation`
MUST NOT be settable from config (invariant requirement below). Any config key
outside the whitelist MUST raise `AuthorizationBuildError` whose message names
the offending key and enumerates the seven fields accepted by agno 2.8.7. The
whitelist check MUST run BEFORE secret resolution. The adapter MUST NOT blindly
forward the settings dict into `AuthorizationConfig` (no `dict.update`-style
blind merge). When `enabled=False`, the disabled guard MUST return
`(False, None)` before any config rejection applies.

#### Scenario: Valid config maps every settable field

- GIVEN `enabled=True` and `config = {"verification_keys": ["vk-1", "vk-2"], "jwks_file": "/etc/agentos/jwks.json", "algorithm": "HS256", "verify_audience": True, "audience": "agentos-api", "admin_scope": "agentos:admin"}`
- WHEN `AuthorizationAdapter(secret_manager).build(settings)` is called
- THEN it returns `(True, cfg)` with `cfg` an `AuthorizationConfig`
- AND each of the six values is present on `cfg` unchanged

#### Scenario: Unknown key rejected with the full field list

- GIVEN `enabled=True` and `config = {"foo": 1}`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised
- AND the message names `"foo"` and lists the seven agno 2.8.7 fields (`verification_keys, jwks_file, algorithm, verify_audience, audience, admin_scope, user_isolation`)

#### Scenario: Whitelist error wins over secret resolution

- GIVEN `enabled=True` and `config = {"foo": "${SECRET:JWT_SIGNING_KEY}"}`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` reports the unknown key `"foo"`, not a secret failure
- AND `secret_manager` was never invoked

#### Scenario: Empty config dict is valid

- GIVEN `enabled=True` and `config = {}`
- WHEN `build(settings)` is called
- THEN it returns `(True, cfg)` with `cfg.user_isolation is True` and all other fields at agno defaults

#### Scenario: None config is valid

- GIVEN `enabled=True` and `config = None`
- WHEN `build(settings)` is called
- THEN it returns `(True, cfg)` with `cfg.user_isolation is True`

#### Scenario: Disabled guard wins over unknown key

- GIVEN `enabled=False` and `config = {"foo": 1}`
- WHEN `build(settings)` is called
- THEN it returns `(False, None)` and no exception is raised (disabled = nothing built = no fail-open)

#### Scenario: No blind dict-forward remains (VQ011 static gate)

- GIVEN the contents of `src/yaml_agno/agentos/authorization_adapter.py` after the change
- WHEN searched for `kwargs.update`
- THEN zero matches are found

### Requirement: basic_auth rejection — no sink in agno 2.8.7

When `enabled=True`, presence of `settings.basic_auth` (any dict, including
empty) MUST raise `AuthorizationBuildError`. The message MUST state that agno
2.8.7's `AuthorizationConfig` has no `basic_auth` sink and MUST point to the
future sink: `BasicAuthMiddleware` (SPEC_19 §1.2, slice S5a.2). When
`enabled=False`, the disabled guard MUST win: `build()` returns `(False, None)`
without error.

#### Scenario: basic_auth with enabled=True rejected with actionable pointer

- GIVEN `enabled=True` and `basic_auth = {"admin": "s3cr3t-pw"}`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised
- AND the message mentions `basic_auth`, `agno 2.8.7`, and `BasicAuthMiddleware` (S5a.2)

#### Scenario: Empty basic_auth dict is still rejected

- GIVEN `enabled=True` and `basic_auth = {}`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised (rejection is by field presence, not content)

#### Scenario: Disabled guard wins over basic_auth rejection

- GIVEN `enabled=False` and `basic_auth = {"admin": "s3cr3t-pw"}`
- WHEN `build(settings)` is called
- THEN it returns `(False, None)` and no exception is raised

### Requirement: user_isolation invariant owned by the adapter

`AuthorizationAdapter.build()` MUST always construct `AuthorizationConfig`
with `user_isolation=True`. An explicit `user_isolation` key in
`settings.config` MUST raise `AuthorizationBuildError` for ANY value —
including `True` — because a silently-ignored override recreates the R1 no-op
class. The message MUST state that `user_isolation` is a security invariant
always set to `True` by the adapter and not settable from YAML.

#### Scenario: Invariant applied when key absent

- GIVEN `enabled=True` and `config = {"algorithm": "HS256"}` (no `user_isolation` key)
- WHEN `build(settings)` is called
- THEN the returned config satisfies `cfg.user_isolation is True`

#### Scenario: Explicit user_isolation=True rejected

- GIVEN `enabled=True` and `config = {"user_isolation": True, "algorithm": "HS256"}`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised stating the invariant

#### Scenario: Explicit user_isolation=False rejected identically

- GIVEN `enabled=True` and `config = {"user_isolation": False}`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised (same rejection; the invariant is not negotiable via YAML)

### Requirement: Secret resolution restricted to whitelisted keys

`${SECRET:KEY}` references MUST be resolved only for values of the six
whitelisted keys. An unresolvable reference (secret callable raising `KeyError`)
or a resolver returning `None` MUST raise `AuthorizationBuildError` naming the
secret key. This preserves existing Slice 3 behavior as a regression guard.

#### Scenario: Secret resolved on a whitelisted key

- GIVEN `enabled=True`, `config = {"algorithm": "HS256", "verification_keys": ["${SECRET:JWT_SIGNING_KEY}"]}`, and a secret callable returning `"hush-hush"` for `JWT_SIGNING_KEY`
- WHEN `build(settings)` is called
- THEN the returned config satisfies `cfg.verification_keys == ["hush-hush"]` and `cfg.algorithm == "HS256"`

#### Scenario: Unresolvable secret raises

- GIVEN `enabled=True`, `config = {"verification_keys": ["${SECRET:MISSING_KEY}"]}`, and a secret callable raising `KeyError("MISSING_KEY")`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised naming `MISSING_KEY`

#### Scenario: Resolver returning None raises

- GIVEN `enabled=True`, `config = {"algorithm": "${SECRET:NULL_KEY}"}`, and a secret callable returning `None`
- WHEN `build(settings)` is called
- THEN `AuthorizationBuildError` is raised (no `None` leaks into `AuthorizationConfig`)

### Requirement: Legacy path parity via the shared private helper

`AgentOSFactory._build_authorization_config_legacy` MUST build through the
SAME private mapping helper used by `AuthorizationAdapter` (module-level in
`authorization_adapter.py`, `_`-prefixed, absent from `__all__` — S5a may
promote it if needed). The legacy path MUST produce the same rejections as the
adapter (unknown key, `basic_auth`, `user_isolation` override). The legacy path
performs no secret resolution: any `${SECRET:...}` reference still present MUST
raise `AuthorizationBuildError` naming the secret key — forwarding the literal
string would be another silent fail-open.

#### Scenario: Legacy rejects unknown key identically

- GIVEN an `AgentOSFactory` built WITHOUT an injected authorization adapter (legacy path) and `authorization = {"enabled": True, "config": {"foo": 1}}`
- WHEN the factory builds the authorization config
- THEN `AuthorizationBuildError` is raised with the same seven-field message as the adapter

#### Scenario: Legacy rejects basic_auth identically

- GIVEN the legacy path and `authorization = {"enabled": True, "basic_auth": {"admin": "s3cr3t-pw"}}`
- WHEN the factory builds the authorization config
- THEN `AuthorizationBuildError` is raised mentioning `BasicAuthMiddleware` (S5a.2)

#### Scenario: Legacy raises on unresolved secret literal

- GIVEN the legacy path and `authorization = {"enabled": True, "config": {"algorithm": "HS256", "verification_keys": ["${SECRET:JWT_SIGNING_KEY}"]}}`
- WHEN the factory builds the authorization config
- THEN `AuthorizationBuildError` is raised naming `JWT_SIGNING_KEY`
- AND the literal `"${SECRET:JWT_SIGNING_KEY}"` is never forwarded into `AuthorizationConfig`

#### Scenario: Helper stays private (API surface)

- GIVEN `yaml_agno.agentos.authorization_adapter.__all__` after the change
- WHEN inspected
- THEN it exports no mapping helper (only adapter and error names)

#### Scenario: Legacy builds valid config with the invariant

- GIVEN the legacy path and `authorization = {"enabled": True, "config": {"algorithm": "HS256", "verification_keys": ["vk-1"]}}`
- WHEN the factory builds the authorization config
- THEN the result satisfies `user_isolation is True` and `algorithm == "HS256"`

### Requirement: Contract tests assert built content

The authorization contract tests (`tests/unit/agentos/test_authorization_adapter.py`,
`tests/unit/factories/test_agentos_factory.py`) MUST assert the CONTENT of the
constructed `AuthorizationConfig` — not merely `cfg is not None`. The full unit
suite MUST pass after the change.

#### Scenario: Content assertions on a valid build

- GIVEN `enabled=True` and `config = {"algorithm": "HS256", "verification_keys": ["vk-1"], "verify_audience": True}`
- WHEN the contract test for a valid build runs
- THEN it asserts at least `cfg.user_isolation is True`, `cfg.algorithm == "HS256"`, `cfg.verification_keys == ["vk-1"]`, `cfg.verify_audience is True`

#### Scenario: No existence-only assertions remain

- GIVEN the rewritten authorization contract tests
- WHEN searched for assertions whose sole content check on the built config is `is not None`
- THEN zero matches are found

#### Scenario: Unit suite green

- GIVEN the change applied
- WHEN `python -m pytest tests/unit/agentos/ tests/unit/factories/test_agentos_factory.py -m unit` runs
- THEN all tests pass (0 failed)

### Requirement: Schema documents basic_auth as UNSUPPORTED

`AuthorizationSettings.basic_auth` MUST remain a parseable field (not removed
until S5a.2) whose docstring and `Field` description mark it UNSUPPORTED in
agno 2.8.7, with an actionable pointer to `BasicAuthMiddleware` (S5a.2). Parsing
MUST NOT emit `DeprecationWarning` — the failure contract lives in build, not
in parse.

#### Scenario: basic_auth still parses

- GIVEN a settings dict `{"enabled": True, "basic_auth": {"admin": "s3cr3t-pw"}}`
- WHEN `AuthorizationSettings.model_validate(...)` runs
- THEN validation succeeds and `basic_auth == {"admin": "s3cr3t-pw"}`

#### Scenario: Field description marks UNSUPPORTED

- GIVEN the `basic_auth` field definition in `agentos_config.py`
- WHEN its description/docstring is read
- THEN it contains "UNSUPPORTED" and references S5a.2 `BasicAuthMiddleware`

#### Scenario: No DeprecationWarning at parse time

- GIVEN a settings dict containing `basic_auth`
- WHEN `AuthorizationSettings.model_validate(...)` runs with `warnings.catch_warnings(record=True)`
- THEN no `DeprecationWarning` is recorded

### Requirement: isolation-refusal

Authenticated startup MUST be isolated or refused. The guard fires when
`authorization` is strictly `True` (identity comparison: `0`, `1`, and
`"true"` MUST NOT satisfy it) AND `authorization_config` is `None`, or its
`user_isolation` is not strictly `True`. In that case the system MUST refuse:

| Entry point | Refusal | Timing |
|---|---|---|
| `YamlAgentOS` construction | `ValueError` naming VQ010 and `user_isolation` | BEFORE delegating to the Agno superclass |
| `run_server` | `RuntimeError` referencing VQ010 | BEFORE `create_app` is invoked |

Preserved invariants: `authorization=False` (dev path) MUST remain unchanged
and bootable; the JD-01 mutual exclusion (`authorization` +
`mount_tenant_context`) MUST remain intact; the YAML factory path
(`AgentOSFactory` via the authorization adapter) MUST continue to build
`AuthorizationConfig` with `user_isolation=True` (factory invariant
unchanged — test-asserted, no factory code change). The VQ010 verification
query (`.chats/decisions.yaml` + `DECISIONES.md`) MUST be tightened from a
presence-only grep to refusal wording matching this contract.

#### Scenario: run_server refuses missing config

- GIVEN `run_server` with `authorization=True` and `authorization_config=None`
- WHEN it starts
- THEN it raises `RuntimeError` referencing VQ010
- AND `create_app` is never invoked

#### Scenario: run_server refuses non-isolated config

- GIVEN `run_server` with `authorization=True`, first with explicit `user_isolation=False`, then with implicit default (unset)
- WHEN it starts once per case
- THEN each start raises `RuntimeError` referencing VQ010 before `create_app`

#### Scenario: run_server rejects truthy authorization

- GIVEN `run_server` with `authorization="true"`
- WHEN it starts
- THEN it raises `RuntimeError` referencing VQ010 (only `is True` satisfies the guard)

#### Scenario: run_server boots valid isolated config

- GIVEN `run_server` with `authorization=True`, an `authorization_config` with `user_isolation=True`, and a fake server
- WHEN it starts
- THEN construction succeeds and the server `run()` is invoked exactly once

#### Scenario: YamlAgentOS refuses unisolated construction

- GIVEN `YamlAgentOS` with `authorization=True`, separately with `authorization_config=None`, explicit `user_isolation=False`, implicit default
- WHEN constructed once per case
- THEN each construction raises `ValueError` BEFORE delegating to the Agno superclass

#### Scenario: YamlAgentOS preserves JD-01

- GIVEN `YamlAgentOS` with `authorization=True`, a valid isolated `authorization_config`, and `mount_tenant_context=True`
- WHEN constructed
- THEN `ValueError` for JD-01 mutual exclusion is raised

#### Scenario: YamlAgentOS accepts isolated config

- GIVEN `YamlAgentOS` with `authorization=True`, a valid isolated `authorization_config`, and `mount_tenant_context=False`
- WHEN constructed and `get_app()` is called
- THEN construction succeeds
- AND the app mounts no `TenantContextMiddleware`

#### Scenario: Dev path unchanged

- GIVEN `create_app` without authorization
- WHEN called
- THEN it returns a `FastAPI` app
- AND an integration request with an `X-Tenant-Id` header returns 200

#### Scenario: Factory invariant unchanged

- GIVEN `AgentOSFactory` with the authorization adapter and `authorization.enabled=True`
- WHEN the authorization config is built
- THEN its `user_isolation` is strictly `True`
- AND without the adapter, a `user_isolation` override raises `AuthorizationBuildError`

#### Scenario: VQ010 query tightened

- GIVEN the VQ010 entry in `.chats/decisions.yaml` and D-F1-10 in `DECISIONES.md`
- WHEN read after the change
- THEN the verification query expresses the refusal contract (strict isolation refusal), not presence-only grep
