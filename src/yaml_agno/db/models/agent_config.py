"""AgentConfigRecord — ``yamlagno_agent_configs`` (SPEC_03 §3.2).

The Pydantic ``AgentConfig`` (SPEC_02) is the validator for ``config_jsonb``;
this class only maps the row. Do not duplicate Pydantic schema fields here.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
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
