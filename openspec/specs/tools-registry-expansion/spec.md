---
change: tools-registry-expansion
spec: SPEC_11
artifact: spec
status: archived
---

# tools-registry-expansion

Expanded BUILTIN_REGISTRY from 5 to 134 adapters covering the full Agno 2.6.22 tool surface. Pure DATA — no logic change.

## Requirements
1. BUILTIN_REGISTRY MUST cover all importable Agno tool modules (134 entries).
2. ToolkitAdapter/build/_filter_kwargs logic UNCHANGED (generic, works for any toolkit).
3. Optional-dep tools included (lazy resolve_class — fail at BUILD, not load).
4. Non-standard class names verified (CsvTools, Searxng, PerplexitySearch, etc.).
5. Excluded: mcp/mcp_toolbox/streamlit/google.auth/google.base (managed elsewhere).

## Scenarios
- GIVEN BUILTIN_REGISTRY WHEN len() THEN >= 131
- GIVEN calculator/shell/airflow WHEN build via AgnoResolver THEN isinstance Toolkit
- GIVEN optional-dep tool (e.g. wikipedia) WHEN in registry THEN present (lazy)
