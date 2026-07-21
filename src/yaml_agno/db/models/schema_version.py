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
