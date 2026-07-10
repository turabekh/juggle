"""Audit domain models: the append-only audit trail (PRD §10.4, INV-10/11).

Every admin mutation and every impersonation action lands here with the true
actor recorded even during impersonation. Rows are never updated or deleted.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class AuditEvent(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "audit_event"

    # The true actor. During impersonation this is the impersonator.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Set only when the action was taken while impersonating someone.
    impersonated_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
