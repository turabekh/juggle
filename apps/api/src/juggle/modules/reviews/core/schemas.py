"""Pydantic schemas for the reviews module (PRD §7.6)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewSubmitIn(BaseModel):
    """A guardian's review of a completed booking. Body is auto-screened for
    child names before it is accepted (PRD §7.6 — no child names in content)."""

    booking_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1, max_length=2000)


class ProviderReplyIn(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)


class ModerateIn(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=500)


class ReviewPublicOut(BaseModel):
    """A published review as shown on provider/listing pages. Author is labelled,
    never named in full; never carries child PII."""

    id: uuid.UUID
    rating: int
    body: str
    author_label: str
    created_at: datetime
    provider_reply: str | None
    provider_reply_at: datetime | None


class RatingSummary(BaseModel):
    average: float | None
    count: int


class ReviewListOut(BaseModel):
    summary: RatingSummary
    items: list[ReviewPublicOut]


class ReviewOut(BaseModel):
    """Full review view for the author, provider, and moderators."""

    id: uuid.UUID
    booking_id: uuid.UUID
    organisation_id: uuid.UUID
    program_id: uuid.UUID
    session_id: uuid.UUID
    rating: int
    body: str
    status: str
    rejection_reason: str | None
    author_label: str
    program_title: str
    provider_reply: str | None
    provider_reply_at: datetime | None
    created_at: datetime


class ReviewableBooking(BaseModel):
    """A confirmed, completed booking the guardian hasn't reviewed yet — the
    frontend uses this to offer a 'Leave a review' action (PRD §7.5/§7.6)."""

    booking_id: uuid.UUID
    session_id: uuid.UUID
    program_title: str
    organisation_name: str
    starts_at: datetime
