"""Notifications domain models: a log of messages sent (PRD §7.4, §7.5).

Low-level delivery record — the audit trail for transactional comms. Callers
pass fully-formed content; this module renders, sends via the gateway, and logs.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class NotificationLog(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "notification_log"

    # Recipient user (nullable — deletion shouldn't erase the delivery record).
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), index=True, nullable=True
    )
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    kind: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
