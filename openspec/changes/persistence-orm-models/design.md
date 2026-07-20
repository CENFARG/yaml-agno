# Design: persistence-orm-models

## Architecture

This slice adds one new package (`yaml_agno.db`) with one `Base`, two mixins,
and seven ORM records. There is no runtime wiring — no engine, no session, no
DDL — just declarative class definitions and an `__init__.py` re-export. The
diagram below shows the dependency edges (solid = Python import; dashed =
SQLAlchemy `ForeignKey`):

```
                  yaml_agno.db.base
                  ├── Base(DeclarativeBase)
                  ├── TimestampMixin
                  └── TenantMixin ──────┐
                                         │ (FK to yamlagno.yamlagno_tenants.id)
                  yaml_agno.db.models    │
                  ├── tenant.py          │  ┌──────────────────────────────┐
                  │    TenantRecord ─────┼──┤ (self-ref parent_org_id FK)   │
                  ├── agent_config.py    │  └──────────────────────────────┘
                  │    AgentConfigRecord (TimestampMixin, TenantMixin)
                  ├── team_config.py
                  │    TeamConfigRecord    (TimestampMixin, TenantMixin)
                  ├── workflow_config.py
                  │    WorkflowConfigRecord (TimestampMixin, TenantMixin)
                  ├── di_variable.py
                  │    DiVariableCacheRecord (TimestampMixin, TenantMixin)
                  ├── config_change_log.py
                  │    ConfigChangeLogRecord (TimestampMixin, explicit tenant FK)
                  ├── schema_version.py
                  │    SchemaVersionRecord (no mixins)
                  └── __init__.py         re-exports Base + 7 records
```

**Why two mixins.** Six of seven tables need both timestamps and `tenant_id`.
`SchemaVersionRecord` needs neither (composite PK, no tenant). Declaring them
once as mixins avoids the trap of one record forgetting `onupdate=NOW()` or the
CASCADE FK. `ConfigChangeLogRecord` uses `TimestampMixin` but **not**
`TenantMixin` because it has its own additional tenant FK alongside
correlation/causation UUIDs — keeping it on the mixin would still work, but
SPEC_03 §3.6 shows the FK inline, so we follow the spec literally.

**Why one shared `Base`.** The future provisioner (slice B) will call
`Base.metadata.create_all(checkfirst=True)`. For that to create all seven
tables, `Base.metadata` must know about all seven — which requires every record
to import `Base` from the same module. The `models/__init__.py` re-export exists
precisely so that `import yaml_agno.db.models` triggers registration of every
table.

**`metadata_` vs `metadata`.** SQLAlchemy's `DeclarativeBase` reserves
`metadata` as a class attribute (the `MetaData` object holding all tables).
Declaring a column attribute named `metadata` would shadow it and break the
ORM. SPEC_03 §3.2 @ai-directive fixes the Python attribute name as `metadata_`
with `mapped_column("metadata", JSONB, ...)` to keep the DB column name. This
mismatch is the single most dangerous footgun in the slice; the unit test
`test_metadata_attribute_maps_to_metadata_column` enforces it explicitly.

## Detailed Design — ORM code

### `src/yaml_agno/db/__init__.py`

```python
"""yaml-agno config-store ORM package (SPEC_03 §3).

Declares the SQLAlchemy 2.0 ``DeclarativeBase`` entities for the ``yamlagno_*``
tables. This slice defines ONLY the ORM models; no engine, session, or DDL is
created here. Downstream SPEC_03 slices (provisioner, repositories, bootstrap)
consume :class:`yaml_agno.db.base.Base` and the record classes.
"""
```

### `src/yaml_agno/db/base.py`

```python
"""Shared DeclarativeBase + mixins for all ``yamlagno_`` ORM entities.

Per SPEC_03 §3 @ai-directive, the core-cenf ``SQLAlchemyAdapter`` requires
``DeclarativeBase`` subclasses (SQLAlchemy 2.0 ORM). yaml-agno therefore uses
declarative ORM here even though Agno itself builds its ``agno_*`` tables with
SQLAlchemy Core (``Table(...)``); the divergence is intentional and mandated
by the core adapter contract.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. All ``yamlagno_*`` records subclass this."""


class TimestampMixin:
    """Adds non-null ``created_at`` / ``updated_at`` with PG server defaults.

    ``updated_at`` advances automatically via ``onupdate=NOW()``. Both columns
    use ``server_default`` (not Python ``default``) so the DB — not the
    application — stamps the time, matching SPEC_03 §3.1.
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), onupdate=text("NOW()"), nullable=False,
    )


class TenantMixin:
    """Adds a non-null ``tenant_id`` FK to ``yamlagno_tenants`` with CASCADE.

    SPEC_03 §5: tenant isolation is enforced at the application layer via
    explicit ``WHERE tenant_id = ?`` filters; this column is the storage-side
    anchor. Six of seven tables use it; ``SchemaVersionRecord`` does not, and
    ``ConfigChangeLogRecord`` declares its own tenant FK inline (SPEC_03 §3.6).
    """

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
```

### `src/yaml_agno/db/models/tenant.py`

```python
"""TenantRecord — ``yamlagno_tenants`` (SPEC_03 §3.1).

Root identity for the config store and the anchor for multi-tenant isolation.
The ``org_has_no_parent`` CHECK enforces kind<->parent consistency only;
cycle prevention (A->B->A) MUST be validated at the application layer before
insert/update — a CHECK cannot express acyclicity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TimestampMixin


class TenantRecord(TimestampMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_tenants``."""

    __tablename__ = "yamlagno_tenants"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9-]+$'", name="slug_format"),
        CheckConstraint(
            "tenant_kind IN ('org','org_user_roles','user')",
            name="valid_tenant_kind",
        ),
        CheckConstraint(
            "tenant_kind <> 'org' OR parent_org_id IS NULL",
            name="org_has_no_parent",
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    tenant_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="org",
    )
    parent_org_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    # created_at / updated_at come from TimestampMixin.
```

### `src/yaml_agno/db/models/agent_config.py`

```python
"""AgentConfigRecord — ``yamlagno_agent_configs`` (SPEC_03 §3.2).

The Pydantic ``AgentConfig`` (SPEC_02) is the validator for ``config_jsonb``;
this class only maps the row. Do not duplicate Pydantic schema fields here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, ForeignKey, Integer, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TenantMixin, TimestampMixin


class AgentConfigRecord(TimestampMixin, TenantMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_agent_configs``."""

    __tablename__ = "yamlagno_agent_configs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", name="ya_agent_tenant_name_unique",
        ),
        CheckConstraint("version >= 1", name="ya_agent_version_positive"),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    # tenant_id comes from TenantMixin.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    config_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list,
    )
    # @ai-directive (SPEC_03 §3.2): Python attribute is `metadata_` (trailing
    # underscore) because `metadata` collides with DeclarativeBase.metadata.
    # The underlying DB column is named `metadata`. Always read/write the
    # JSONB payload via record.metadata_, NEVER via record.metadata.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict,
    )
    # created_at / updated_at come from TimestampMixin.
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
```

### `src/yaml_agno/db/models/team_config.py`

```python
"""TeamConfigRecord — ``yamlagno_team_configs`` (SPEC_03 §3.3).

Mirrors AgentConfigRecord column-for-column (including ``tags`` and
``metadata_``) with a different ``__tablename__`` and UNIQUE constraint name.
``config_jsonb`` validates against the Pydantic ``TeamConfig`` (SPEC_02).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TenantMixin, TimestampMixin


class TeamConfigRecord(TimestampMixin, TenantMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_team_configs``."""

    __tablename__ = "yamlagno_team_configs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", name="ya_team_tenant_name_unique",
        ),
        CheckConstraint("version >= 1", name="ya_team_version_positive"),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    config_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
```

### `src/yaml_agno/db/models/workflow_config.py`

```python
"""WorkflowConfigRecord — ``yamlagno_workflow_configs`` (SPEC_03 §3.4).

Same shape as AgentConfigRecord EXCEPT it has NO ``tags`` column (per
SPEC_03 §3.4 DDL). ``config_jsonb`` validates against the Pydantic
``WorkflowConfig`` (SPEC_02).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TenantMixin, TimestampMixin


class WorkflowConfigRecord(TimestampMixin, TenantMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_workflow_configs`` (no tags)."""

    __tablename__ = "yamlagno_workflow_configs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", name="ya_wf_tenant_name_unique",
        ),
        CheckConstraint("version >= 1", name="ya_wf_version_positive"),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    config_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
```

### `src/yaml_agno/db/models/di_variable.py`

```python
"""DiVariableCacheRecord — ``yamlagno_di_variable_cache`` (SPEC_03 §3.5).

TTL-bounded cache of resolved DI variable values (provider_name + variable_key
→ variable_value). The ``expires_at > created_at`` CHECK is a storage-level
sanity guard; the application must still filter ``expires_at > NOW()`` on read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TenantMixin, TimestampMixin


class DiVariableCacheRecord(TimestampMixin, TenantMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_di_variable_cache``."""

    __tablename__ = "yamlagno_di_variable_cache"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider_name", "variable_key",
            name="ya_di_tenant_provider_key_unique",
        ),
        CheckConstraint(
            "expires_at > created_at", name="ya_di_expires_future",
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    variable_key: Mapped[str] = mapped_column(String(255), nullable=False)
    variable_value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
```

### `src/yaml_agno/db/models/config_change_log.py`

```python
"""ConfigChangeLogRecord — ``yamlagno_config_change_log`` (SPEC_03 §3.6).

Config-store audit log (config.created / config.updated / config.deleted /
flag.toggled). Does NOT replicate Agno RunEvents. Uses TimestampMixin for
``created_at``/``updated_at`` and an explicit tenant FK (not TenantMixin)
because the table also carries correlation/causation UUIDs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base, TimestampMixin


class ConfigChangeLogRecord(TimestampMixin, Base):
    """Persistence row for ``yamlagno.yamlagno_config_change_log``."""

    __tablename__ = "yamlagno_config_change_log"
    __table_args__ = (
        CheckConstraint(
            "processing_attempts >= 0", name="ya_ccl_positive_attempts",
        ),
        {"schema": "yamlagno"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    event_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="1.0",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("yamlagno.yamlagno_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    correlation_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True,
    )
    causation_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True,
    )
    # created_at / updated_at come from TimestampMixin.
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    processing_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
```

### `src/yaml_agno/db/models/schema_version.py`

```python
"""SchemaVersionRecord — ``yamlagno_schema_versions`` (SPEC_03 §3.7).

Tracks which schema version is provisioned. Composite PK (component, version);
no tenant, no mixins. The MECHANISM here differs from Agno's MigrationManager:
yaml-agno MVP only records that a version was applied (gating ``checkfirst``
re-runs). Reversible migrations are a future addition (SPEC_03 §6.2).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from yaml_agno.db.base import Base


class SchemaVersionRecord(Base):
    """Persistence row for ``yamlagno.yamlagno_schema_versions``."""

    __tablename__ = "yamlagno_schema_versions"
    __table_args__ = ({"schema": "yamlagno"},)

    component: Mapped[str] = mapped_column(
        String(100), primary_key=True,
    )
    version: Mapped[str] = mapped_column(String(50), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False,
    )
```

### `src/yaml_agno/db/models/__init__.py`

```python
"""Re-export the shared Base and all seven ``yamlagno_`` ORM records.

Importing this module registers every table on ``Base.metadata`` so that the
future provisioner (SPEC_03 slice B) can call ``Base.metadata.create_all``.
"""

from yaml_agno.db.base import Base, TimestampMixin, TenantMixin
from yaml_agno.db.models.agent_config import AgentConfigRecord
from yaml_agno.db.models.config_change_log import ConfigChangeLogRecord
from yaml_agno.db.models.di_variable import DiVariableCacheRecord
from yaml_agno.db.models.schema_version import SchemaVersionRecord
from yaml_agno.db.models.team_config import TeamConfigRecord
from yaml_agno.db.models.tenant import TenantRecord
from yaml_agno.db.models.workflow_config import WorkflowConfigRecord

__all__ = [
    "Base",
    "TimestampMixin",
    "TenantMixin",
    "TenantRecord",
    "AgentConfigRecord",
    "TeamConfigRecord",
    "WorkflowConfigRecord",
    "DiVariableCacheRecord",
    "ConfigChangeLogRecord",
    "SchemaVersionRecord",
]
```

## Decision log

1. **DeclarativeBase, not Core `Table()`.** SPEC_03 §3 @ai-directive: the
   core-cenf `SQLAlchemyAdapter` requires ORM entities. Agno uses Core because
   it owns its own session machinery; yaml-agno does not.
2. **`MappedAsDataclass` NOT used.** Considered for ergonomic constructors, but
   the mixin field ordering interacts poorly with `MappedAsDataclass` and the
   cost (debugging attribute init order) exceeds the benefit for pure
   persistence records. Plain `DeclarativeBase` it is.
3. **`metadata_` attribute name.** Fixed by SPEC_03 §3.2 @ai-directive — not
   negotiable. Documented inline + enforced by unit test.
4. **`ConfigChangeLogRecord` does not use `TenantMixin`.** Although the column
   set is identical (one FK with CASCADE), SPEC_03 §3.6 shows the FK inline
   alongside correlation/causation UUIDs; we mirror the spec literally so
   future readers can match code to DDL one-to-one.
5. **`SchemaVersionRecord` skips both mixins.** No tenant (cross-cutting
   bookkeeping), composite PK instead of UUID.
6. **`Mapped[UUID | None]` over `Optional[UUID]`.** PEP 604 syntax matches the
   rest of the codebase (Pydantic models already use `X | None`).
7. **SQLite vs Postgres in unit tests.** Unit tests run against SQLite
   in-memory; JSONB compiles via SQLAlchemy's type-coercion layer. PG-only
   constructs (GIN, partial indexes) are deferred to the provisioner slice,
   which runs against a real PG engine.

## Sequence: import-time registration

```
caller imports yaml_agno.db.models
        │
        ├─ yaml_agno.db.base       → class Base, mixins (no tables yet)
        ├─ yaml_agno.db.models.tenant
        │     └─ TenantRecord(Base) → Base.metadata.tables["yamlagno.yamlagno_tenants"]
        ├─ yaml_agno.db.models.agent_config
        │     └─ AgentConfigRecord(Base) → metadata gains yamlagno_agent_configs
        ├─ ... (4 more records)
        └─ __init__ re-exports all names
caller now has Base.metadata.tables with 7 entries; no engine created.
```

## Open questions

None for this slice. The provisioner (slice B) will need to decide how to run
PG-only index creation (`CREATE INDEX ... USING GIN`, partial indexes) — that
belongs in slice B's design, not here.
