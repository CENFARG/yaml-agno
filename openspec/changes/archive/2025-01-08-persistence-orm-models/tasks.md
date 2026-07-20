# Tasks: persistence-orm-models

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 250–350 (9 new files, mechanical ORM mapping) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (foundation slice; no chain) |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Ship all 7 ORM records + mixins + base + unit tests in one foundation slice | PR 1 (single) | `python -m pytest tests/unit/db/test_orm_models.py -v` | N/A — pure declarative; no runtime engine wired (deferred to slice B) | `src/yaml_agno/db/` + `tests/unit/db/` removable without touching any other module |

## Phase 1: Foundation (package + Base + mixins)

- [x] 1.1 Create `src/yaml_agno/db/__init__.py` package marker (docstring only; no imports, no side effects).
- [x] 1.2 Create `src/yaml_agno/db/base.py` with `class Base(DeclarativeBase)`, `TimestampMixin` (`created_at`/`updated_at` server_default `NOW()`, `onupdate=NOW()`), and `TenantMixin` (`tenant_id` FK to `yamlagno.yamlagno_tenants.id` `ondelete=CASCADE`).
- [x] 1.3 RED: `tests/unit/db/__init__.py` + `test_orm_models.py::test_base_is_declarative_and_import_is_side_effect_free` — assert `Base` subclasses `DeclarativeBase` and importing `yaml_agno.db.base` opens no engine/session.
- [x] 1.4 RED: `test_timestamp_and_tenant_mixins_define_columns` — assert the mixin columns exist on a throwaway record using them, with correct nullability and FK ondelete action.

## Phase 2: TenantRecord (root identity, self-FK, CHECKs)

- [x] 2.1 RED: `test_tenant_record_table_and_schema` — assert `__tablename__ == "yamlagno_tenants"`, `__table__.schema == "yamlagno"`, columns `id/name/slug/tenant_kind/parent_org_id/settings` present with correct types.
- [x] 2.2 RED: `test_tenant_record_constraints` — assert CHECK constraints `slug_format`, `valid_tenant_kind`, `org_has_no_parent` exist and UNIQUE on `slug`.
- [x] 2.3 GREEN: Create `src/yaml_agno/db/models/tenant.py` with `TenantRecord(TimestampMixin, Base)` per SPEC_03 §3.1 (self-referential `parent_org_id` FK with string target).
- [x] 2.4 RED→GREEN: `test_tenant_round_trip_in_sqlite` — insert + re-read a `TenantRecord` row in an in-memory SQLite engine; assert `settings` JSONB round-trips and `tenant_kind` defaults to `"org"`.

## Phase 3: Config records (agent / team / workflow)

- [x] 3.1 RED: `test_agent_config_record_table_schema_and_constraints` — assert tablename, schema, UNIQUE `ya_agent_tenant_name_unique` on `(tenant_id, name)`, CHECK `ya_agent_version_positive` (`version >= 1`), column types incl. `ARRAY(String)` for tags.
- [x] 3.2 RED: `test_metadata_attribute_maps_to_metadata_column` — assert `AgentConfigRecord.__table__.c.metadata` exists, `record.metadata_` holds the JSONB payload, and `record.metadata` (class attr) is the SQLAlchemy `MetaData` (NOT the payload).
- [x] 3.3 GREEN: Create `src/yaml_agno/db/models/agent_config.py` with `AgentConfigRecord(TimestampMixin, TenantMixin, Base)` per SPEC_03 §3.2 (trailing-underscore `metadata_` mapped to column `metadata`).
- [x] 3.4 GREEN: Create `src/yaml_agno/db/models/team_config.py` (`TeamConfigRecord`, same column set as agent incl. `tags` + `metadata_`, UNIQUE `ya_team_tenant_name_unique`).
- [x] 3.5 GREEN: Create `src/yaml_agno/db/models/workflow_config.py` (`WorkflowConfigRecord`, same as agent **minus `tags` column**, UNIQUE `ya_wf_tenant_name_unique`).
- [x] 3.6 RED: `test_team_and_workflow_records_table_shape` — assert tablenames/schemas, workflow has NO `tags` column, team has `tags`, both enforce `version >= 1`.

## Phase 4: Remaining records (DI cache, change log, schema version)

- [x] 4.1 GREEN: Create `src/yaml_agno/db/models/di_variable.py` (`DiVariableCacheRecord`, UNIQUE `(tenant_id, provider_name, variable_key)`, CHECK `expires_at > created_at`).
- [x] 4.2 GREEN: Create `src/yaml_agno/db/models/config_change_log.py` (`ConfigChangeLogRecord` with `TimestampMixin` + explicit tenant FK, CHECK `processing_attempts >= 0`, `event_version` default `'1.0'`).
- [x] 4.3 GREEN: Create `src/yaml_agno/db/models/schema_version.py` (`SchemaVersionRecord`, composite PK `(component, version)`, no mixins).
- [x] 4.4 RED: `test_di_cache_change_log_schema_version_constraints` — assert DI UNIQUE + `ya_di_expires_future`, change log CHECK + tenant FK CASCADE, schema_version composite PK.

## Phase 5: Re-export + table registration

- [x] 5.1 GREEN: Create `src/yaml_agno/db/models/__init__.py` re-exporting `Base`, `TimestampMixin`, `TenantMixin`, and all 7 record classes (matching `__all__` from design).
- [x] 5.2 RED: `test_models_init_registers_exactly_seven_tables` — `from yaml_agno.db.models import Base; assert set(Base.metadata.tables) == {seven namespaced names}`.
- [x] 5.3 RED: `test_no_runtime_ddl_in_db_package` — grep `src/yaml_agno/db/` for `create_all`, `engine.begin`, `create_engine(`, `Engine(`; assert zero matches (enforces spec Requirement 7).
- [x] 5.4 GREEN/REFACTOR: Run full unit suite `python -m pytest tests/unit/db/ -v --cov=yaml_agno/db --cov-fail-under=100`; fix any gaps; ensure `ruff check src/yaml_agno/db` and `mypy src/yaml_agno/db` are clean.
