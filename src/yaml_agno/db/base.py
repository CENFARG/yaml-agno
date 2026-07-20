"""Shared DeclarativeBase + mixins for all ``yamlagno_`` ORM entities.

Per SPEC_03 §3 @ai-directive, the core-cenf ``SQLAlchemyAdapter`` requires
``DeclarativeBase`` subclasses (SQLAlchemy 2.0 ORM). yaml-agno therefore uses
declarative ORM here even though Agno itself builds its ``agno_*`` tables with
SQLAlchemy Core (``Table(...)``); the divergence is intentional and mandated
by the core adapter contract.

This module declares ONLY classes — no engine, session, or DDL. Importing it
has no database side effects (enforced by ``test_base_is_declarative_and_*``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. All ``yamlagno_*`` records subclass this."""


class TimestampMixin:
    """Adds non-null ``created_at`` / ``updated_at`` with PG server defaults.

    ``updated_at`` advances automatically via ``onupdate=NOW()``. Both columns
    use ``server_default`` (not Python ``default``) so the DB — not the
    application — stamps the time, matching SPEC_03 §3.1.
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
        nullable=False,
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
