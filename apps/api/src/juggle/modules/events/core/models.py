"""Analytics event model (PRD §13): the funnel instrumentation store.

A minimal append-only event log for product funnel analytics — one row per
tracked event (``search_performed``, ``checkout_completed``, …). Context lives in
a JSONB ``props`` bag (e.g. session/org ids). **No child PII ever** (PRD §11/§13):
callers pass ids and counts, never child names or DOBs.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import UUIDPkMixin
from juggle.db import Base


class AnalyticsEvent(UUIDPkMixin, Base):
    __tablename__ = "analytics_event"

    event_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    props: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
