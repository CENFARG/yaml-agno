# Design: auth-vq010-isolation-guard

## Technical Approach

Approach 3 (ratified): ONE shared predicate `_require_isolated_auth` in `src/yaml_agno/agentos/authorization_adapter.py` beside `_map_authorization_config` (SSOT already owning `_SUPPORTED_FIELDS` and the `user_isolation=True` build invariant). Both enforcement sites call it; each raises its own exception type. `YamlAgentOS.__init__` is authoritative (closes direct-construction + `create_app` + external-ASGI bypass); `run_server` adds early refusal. Factory path stays reference-only. Implements delta spec `agentos-authorization-build / ADDED isolation-refusal` (10 scenarios); closes Judgment Day CRITICAL #3120.

## Architecture Decisions

| # | Option | Tradeoff | Decision |
|---|---|---|---|
| D1 | Location: `authorization_adapter.py` vs private in `api/app.py` | Adapter = zero drift with factory invariant; adds one `runtime→agentos` import (already transitively real via `api`) | `authorization_adapter.py` (shared SSOT) |
| D2 | Contract: raise inside vs return message | Raising forces one exception type on both boundaries; `str \| None` lets constructor raise `ValueError` (JD-01 convention) and server `RuntimeError` (existing VQ010 tests) | Return `str \| None`; call sites raise |
| D3 | Layers: `run_server` only / `YamlAgentOS` only / both | run_server-only leaves direct-`YamlAgentOS` bypass open; YamlAgentOS-only defers refusal past kwargs; both ≈15 LOC, defense-in-depth | Both (YamlAgentOS authoritative) |
| D4 | Strictness: truthy vs identity | Truthy admits `"true"`/`1`; identity matches existing `run_server` guard and spec ("only `is True` satisfies the guard") | `is True` on `authorization` AND `user_isolation` |
| D5 | `run_server` signature | Explicit `authorization_config` param churns public API for no behavioral gain | Keep `**yaml_agentos_kwargs`; predicate reads kwargs |
| D6 | Message strategy | Per-site texts drift; one canonical message is greppable by tightened VQ010 query | One canonical message (VQ010, `user_isolation`, required form, dev seam) raised verbatim by both sites |

Validation order in `YamlAgentOS.__init__` stays deterministic: agent-source ambiguity → JD-01 → VQ010 (new guard right after the JD-01 block, `app.py:189`, before `_resolve_agents`/`super().__init__`).

## Interfaces / Contracts

```python
# src/yaml_agno/agentos/authorization_adapter.py (private; __all__ unchanged)
def _require_isolated_auth(
    authorization: bool,
    authorization_config: AuthorizationConfig | None,
) -> str | None:
    """Return the VQ010 refusal message, or None when the config is acceptable."""
```

Fires iff `authorization is True` AND (`authorization_config is None` OR `authorization_config.user_isolation is not True`). `authorization` of `None`/`False`/`0`/`1`/`"true"` returns `None` — `run_server`'s existing `is not True` guard (`server.py:120-126`) keeps handling that. Reads only the public Agno field `AuthorizationConfig.user_isolation` (anti-Frankenstein: no Agno internals, no RLS/Casbin, no `os.environ`, no monkeypatch).

Call sites:
1. `api/app.py` `YamlAgentOS.__init__` — after JD-01: violation → `ValueError(message)` BEFORE `super().__init__`.
2. `runtime/server.py` `run_server` — existing guard kept verbatim; then same predicate → `RuntimeError(message)` BEFORE `create_app` (`:128`).

## Data Flow

```
run_server(**kw) ─auth not True→ RuntimeError(VQ010)      [existing, kept]
                 └_require_isolated_auth─msg→ RuntimeError [new, before create_app]
YamlAgentOS(**kw) ─JD-01→ ValueError                      [existing, kept]
                  └_require_isolated_auth─msg→ ValueError  [new, before super().__init__]
AgentOSFactory.build ─adapter(user_isolation=True)→ AgentOS [NO CHANGE — reference]
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/yaml_agno/agentos/authorization_adapter.py` | Modify | Add `_require_isolated_auth` (~20 LOC with docstring) |
| `src/yaml_agno/api/app.py` | Modify | Isolation guard after JD-01; `ValueError` before `super().__init__`; docstring Raises |
| `src/yaml_agno/runtime/server.py` | Modify | Predicate → `RuntimeError` before `create_app`; docstring Raises |
| `src/yaml_agno/factories/agentos_factory.py` | None | Reference only; test-asserted |
| `tests/unit/agentos/test_authorization_adapter.py` | Modify | `TestRequireIsolatedAuth` truth table; extend Req 5 privacy test |
| `tests/unit/runtime/test_run_server_auth.py` | Modify | Isolation negatives; refusal-before-`create_app`; FakeServer run-once positive |
| `tests/unit/api/test_app_jwt_mode.py` | Modify | `YamlAgentOS` negatives (`ValueError` matching VQ010); JD-01/dev positives preserved |
| `tests/unit/factories/test_agentos_factory.py` | Modify | Adapter-path `user_isolation is True` content assert; legacy override → `AuthorizationBuildError` |
| `.chats/decisions.yaml` (VQ010 entry) | Modify | Query tightened: presence-only grep → refusal wording (guard + `user_isolation is not True` + refusal exceptions) |
| `DECISIONES.md` (VQ010 row / D-F1-10 note) | Modify | Same tightening; Spanish narrative per repo convention |

## Testing Strategy

Strict TDD: every behavioral task starts RED (failing test), then GREEN, then REFACTOR.

| Layer | What to Test | Approach |
|---|---|---|
| Unit — predicate | Truth table: (True, None) / (True, isolation=False) / (True, implicit default) → message; (True, isolation=True) → None; authorization ∈ {False, None, 0, 1, "true"} → None; message names VQ010 + `user_isolation` | Direct calls in `TestRequireIsolatedAuth` |
| Unit — `run_server` | 3 isolation negatives → `RuntimeError` VQ010; nonexistent `config_path` still `RuntimeError` (refusal precedes `create_app`, never `FileNotFoundError`); `"true"` → `RuntimeError`; valid isolated config + FakeServer → `run()` once | Existing file + new tests |
| Unit — `YamlAgentOS` | (True, None)/(True, False)/(True, implicit) → `ValueError` matching VQ010; JD-01 preserved; valid config constructs, `get_app()` mounts no `TenantContextMiddleware` | Existing file + new tests |
| Unit — factory | Adapter build yields `user_isolation is True` (content); no-adapter `user_isolation` override → `AuthorizationBuildError` | Content assertions |
| Gates | `python -m pytest` 840+ green; `ruff check .`; `mypy src/yaml_agno`; `python scripts/spec_gate.py all` 34/34 | Full suite per commit |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Pure in-process, construction-time refusal.

## Migration / Rollout

No migration required. Rollback: revert the three source edits (predicate + two guards) in one corrective commit; S5a.1 sources/specs untouched → restores verified `826f9d2` behavior.

## Open Questions

None.
