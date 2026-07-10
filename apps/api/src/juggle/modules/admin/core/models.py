"""Admin domain models: impersonation sessions for support (PRD §10.3).

A time-boxed, audited session where an admin acts as a guardian or provider
member. ``view_as`` is read-only; ``act_as`` permits mutations. The impersonation
token carries both the target (``sub``) and the true actor; sensitive actions
(payment instruments, bank details, credentials, child-data export) remain
blocked in both modes.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class ImpersonationMode(enum.StrEnum):
    view_as = "view_as"    # read-only
    act_as = "act_as"      # full actions


class ImpersonationSession(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "impersonation_session"

    impersonator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    mode: Mapped[ImpersonationMode] = mapped_column(
        Enum(ImpersonationMode, name="impersonation_mode"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
