"""WorkflowConfigRecord — ``yamlagno_workflow_configs`` (SPEC_03 §3.4).

Same shape as AgentConfigRecord EXCEPT it has NO ``tags`` column (per
SPEC_03 §3.4 DDL). ``config_jsonb`` validates against the Pydantic
``WorkflowConfig`` (SPEC_02).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
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
