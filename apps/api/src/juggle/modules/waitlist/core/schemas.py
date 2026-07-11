"""Pydantic schemas for the waitlist module (PRD §7.7)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class JoinWaitlistIn(BaseModel):
    session_id: uuid.UUID


class WaitlistEntryOut(BaseModel):
    """A guardian's own waitlist place. When ``status == 'offered'`` the frontend
    uses ``offer_hold_id`` to claim the seat via the normal checkout."""

    id: uuid.UUID
    session_id: uuid.UUID
    status: str
    position: int | None  # 1-based place in the queue while waiting; null once offered/done
    program_title: str
    organisation_name: str
    starts_at: datetime
    ends_at: datetime
    offer_hold_id: uuid.UUID | None
    offer_expires_at: datetime | None
    created_at: datetime


class SessionWaitlistOut(BaseModel):
    """Provider/admin view of a session's queue depth (no guardian PII)."""

    session_id: uuid.UUID
    waiting: int
    offered: int


class WaitlistRunResult(BaseModel):
    """Result of an ops reconciliation sweep."""

    sessions_processed: int
    offers_made: int
    offers_expired: int
