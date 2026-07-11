"""Q&A domain model (PRD §7.2): a public question on a listing + the provider's
answer. Structured Q&A replaces free-text parent↔provider chat (support burden +
safeguarding), so there's no threading — one question, one provider reply.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class ListingQuestion(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "listing_question"

    # Q&A attaches to the program (the "listing"), not a single session.
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    asker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    answered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
