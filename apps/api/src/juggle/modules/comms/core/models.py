"""Comms domain model (PRD §8.5): a record of a provider broadcast.

A ``Broadcast`` is one message a provider sent to the families booked on a
session (template-guarded — no free-text parent↔provider chat). The per-recipient
emails are recorded in the ``notifications`` log; this table is the provider-side
record of *what was sent to whom* (subject/body + how many families received it)
so the org can see its own outbound history.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class Broadcast(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "broadcast"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    # Optional preset the provider chose from (template-guarded messaging).
    template_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
