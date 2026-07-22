---
requirement:
  id: yaml-agentos-foundation
  parent_spec: SPEC_06
  slice: "A"
  status: proposed
---

# Spec: yaml-agentos-foundation (SPEC_06 Slice A)

> Minimal HTTP foundation. A `YamlAgentOS(AgentOS)` subclass that inherits the
> full native Agno 2.6.22 router set, plus a uvicorn entry point. Corrects the
> four SPEC_06 defects (wrong import paths, non-existent helpers, always-on
> authorization that blocks integration tests).

## Scenarios

### Scenario 1: YamlAgentOS subclass accepts a pre-built agent list

```gherkin
GIVEN a list containing one native agno.Agent instance
WHEN YamlAgentOS(agents=[agent]) is instantiated
THEN the resulting object is an instance of agno.os.AgentOS
AND its .agents attribute contains the provided agent
```

RFC 2119: The constructor MUST accept an `agents=[...]` keyword argument whose
entries are forwarded unchanged to `super().__init__(agents=...)`. It SHALL NOT
mutate, re-build, or filter the provided list.

### Scenario 2: YamlAgentOS builds agents from a YAML config path

```gherkin
GIVEN a YAML file at config_path containing a list of agent definitions
AND each definition matches the AgentConfig schema (SPEC_02)
WHEN YamlAgentOS(config_path="agents.yaml") is instantiated
THEN each YAML entry is validated via AgentConfig.model_validate
AND each validated config is built via AgentFactory.build(cfg) (SPEC_01)
AND the resulting agno.Agent list is forwarded to super().__init__(agents=...)
```

RFC 2119: A YAML entry that fails `AgentConfig` validation MUST raise
`pydantic.ValidationError` and SHALL NOT be silently skipped. An invalid YAML
document (parse error) MUST raise `yaml.YAMLError`. Empty `agents=[]` SHALL be
accepted and forwarded as-is.

### Scenario 3: Providing both config_path and agents raises

```gherkin
GIVEN the caller passes both agents=[...] and config_path="..."
WHEN YamlAgentOS(agents=[...], config_path="...") is instantiated
THEN a ValueError is raised with a message mentioning the ambiguity
```

RFC 2119: The constructor MUST reject the ambiguous call.

Note (verified Agno 2.6.22): `AgentOS.__init__` itself REQUIRES at least one of
`agents`, `teams`, `workflows`, `knowledge`, or `db`. Passing NEITHER source
therefore raises `ValueError("Either agents, teams, workflows, knowledge bases
or a database must be provided.")` from the parent. Slice A surfaces this
unchanged; the test asserting the default `authorization=False` provides a
minimal agent list so the parent's invariant is satisfied.

### Scenario 4: get_app() returns a FastAPI app with native routes

```gherkin
GIVEN YamlAgentOS(agents=[<one real agno.Agent>]) is instantiated
WHEN .get_app() is called
THEN the returned object is an instance of fastapi.FastAPI
AND the app exposes the native route POST /agents/{agent_id}/runs
AND the app exposes the native route GET /health
AND the app exposes GET /agents
```

RFC 2119: `get_app()` MUST call `super().get_app()` and return its result after
optional extension mounting. The native route set MUST be inherited unchanged;
slice A SHALL NOT remove, rename, or shadow any native route.

### Scenario 5: get_app() optionally mounts liveness and readiness

```gherkin
GIVEN YamlAgentOS(agents=[...], mount_health=True)
WHEN .get_app() is called
THEN the app exposes GET /health/liveness
AND the app exposes GET /health/readiness

GIVEN YamlAgentOS(agents=[...], mount_health=False)
WHEN .get_app() is called
THEN the app does NOT expose GET /health/liveness
AND the app does NOT expose GET /health/readiness
```

RFC 2119: `mount_health` MUST default to `True`. When `True`, both extension
routes SHALL be mounted via `app.include_router(...)`. When `False`, neither
route SHALL be added.

### Scenario 6: Liveness returns alive

```gherkin
GIVEN a YamlAgentOS app with mount_health=True
WHEN GET /health/liveness is called
THEN the response status code is 200
AND the JSON body is {"status": "alive"}
```

### Scenario 7: Readiness returns ready with empty checks (slice A)

```gherkin
GIVEN a YamlAgentOS app with mount_health=True
WHEN GET /health/readiness is called
THEN the response status code is 200
AND the JSON body status field is "ready"
AND the JSON body checks field is an empty object
```

RFC 2119: Slice A readiness SHALL report `ready` unconditionally with an empty
`checks` map. The Postgres ping lands with SPEC_03 B-E; until then the route
SHALL NOT fabricate a fake `{"postgres": ...}` entry.

### Scenario 8: authorization defaults to False and is forwarded to AgentOS

```gherkin
GIVEN YamlAgentOS(agents=[...]) is instantiated without an explicit authorization kwarg
THEN the resulting object's .authorization attribute is False
AND the value forwarded to super().__init__ is authorization=False

GIVEN YamlAgentOS(agents=[...], authorization=True)
THEN the resulting object's .authorization attribute is True
```

RFC 2119: Slice A MUST default `authorization=False`. The constructor MUST
forward the caller-provided value to `super().__init__(authorization=...)`. A
docstring warning SHALL state that production deployments MUST pass
`authorization=True` + `AuthorizationConfig(user_isolation=True)` once SPEC_04's
`resolve_user_id` ships.

### Scenario 9: Extra AgentOS kwargs pass through

```gherkin
GIVEN YamlAgentOS(agents=[...], enable_mcp_server=True, telemetry=False)
THEN the values are forwarded to super().__init__ unchanged
AND the resulting object reflects enable_mcp_server=True
```

RFC 2119: The constructor MUST accept arbitrary `**agentos_kwargs` and forward
them to `super().__init__(...)`. It SHALL NOT swallow or rename native AgentOS
parameters.

### Scenario 10: runtime.create_app returns the FastAPI app

```gherkin
GIVEN a list of real agno.Agent instances
WHEN runtime.create_app(agents=[...]) is called
THEN the returned object is an instance of fastapi.FastAPI
AND it is the same app YamlAgentOS(agents=[...]).get_app() would produce
```

### Scenario 11: runtime.run_server starts uvicorn (binding only)

```gherkin
GIVEN runtime.run_server(agents=[...], host="127.0.0.1", port=0)
THEN uvicorn.Server is constructed with the YamlAgentOS app
AND the server's configuration reflects host="127.0.0.1"
AND run_server does not call .run() inside the test (injectable server factory)
```

RFC 2119: `run_server` MUST accept a `server_factory` injection hook used by
tests to avoid actually starting a TCP listener. The default factory SHALL
construct a `uvicorn.Server(uvicorn.Config(app, host=host, port=port))` and call
`.run()` on it.

## Non-Goals

- No tenant isolation, no composite `user_id` middleware (DEFER to SPEC_04).
- No rate limiting (DEFER to SPEC_19).
- No MCP enablement wiring beyond pass-through `enable_mcp_server` kwarg.
- No DB session resolution — `db=None` and Agno's `auto_provision_dbs=True` handle
  in-memory runs for slice A.
- No `core-cenf-py ConfigManager` integration — slice A reads YAML files directly.
