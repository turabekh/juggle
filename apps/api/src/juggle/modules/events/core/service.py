"""Events service (PRD §13): record funnel events + read funnel counts.

Bottom of the layering, like ``audit`` — every higher module can call ``record``
with an event type + non-PII context. The canonical event taxonomy (PRD §13) is
listed in ``EVENT_TYPES`` so the funnel always reports all stages, even zero ones.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.events.core.models import AnalyticsEvent

# PRD §13 event taxonomy, in funnel order.
EVENT_TYPES: list[str] = [
    "search_performed",
    "listing_viewed",
    "checkout_started",
    "checkout_completed",
    "booking_cancelled",
    "session_filled",
    "listing_published",
    "provider_signup",
]


def record(
    db: Session,
    *,
    event_type: str,
    props: dict[str, Any] | None = None,
) -> None:
    """Append one funnel event. Callers pass ids/counts only — never child PII."""
    db.add(AnalyticsEvent(event_type=event_type, props=props or {}))
    db.flush()


def funnel_counts(db: Session, *, since: datetime | None = None) -> dict[str, int]:
    """Count events per type (optionally since a time). All taxonomy types are
    present, defaulting to 0."""
    stmt = select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id)).group_by(
        AnalyticsEvent.event_type
    )
    if since is not None:
        stmt = stmt.where(AnalyticsEvent.occurred_at >= since)
    observed = {event_type: int(n) for event_type, n in db.execute(stmt).all()}
    return {event_type: observed.get(event_type, 0) for event_type in EVENT_TYPES}


def uid(value: uuid.UUID | None) -> str | None:
    """Helper for building non-PII props from an id."""
    return str(value) if value is not None else None
