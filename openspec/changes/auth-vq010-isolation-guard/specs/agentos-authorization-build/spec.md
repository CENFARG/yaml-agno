# Delta for agentos-authorization-build

## ADDED Requirements

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
