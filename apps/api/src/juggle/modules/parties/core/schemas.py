"""Pydantic schemas for the parties module (supply side — Milestone B1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PackageCreate(BaseModel):
    venue_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    per_head_price_cents: int = Field(ge=0)
    min_headcount: int = Field(ge=1)
    max_headcount: int = Field(ge=1)
    deposit_pct: int | None = Field(default=None, ge=10, le=100)
    outdoor: bool = False


class PackageUpdate(BaseModel):
    """Editable fields of a package. Venue may change (must stay within the org)."""

    venue_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    per_head_price_cents: int = Field(ge=0)
    min_headcount: int = Field(ge=1)
    max_headcount: int = Field(ge=1)
    deposit_pct: int | None = Field(default=None, ge=10, le=100)
    outdoor: bool = False


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    venue_id: uuid.UUID
    name: str
    description: str | None
    per_head_price_cents: int
    min_headcount: int
    max_headcount: int
    deposit_pct: int | None
    outdoor: bool
    status: str


class PackageDetailOut(PackageOut):
    """Public package view enriched with provider + venue names for the booking page."""

    organisation_name: str
    venue_name: str
    venue_suburb: str | None
    deposit_pct_effective: int


class SlotCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def _end_after_start(self) -> "SlotCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class SlotsCreate(BaseModel):
    # Generous cap so a date-range generator (weekdays × time windows) fits in one batch.
    slots: list[SlotCreate] = Field(min_length=1, max_length=500)


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    package_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    status: str


class BookSlotIn(BaseModel):
    headcount: int = Field(ge=1)


class AdjustHeadcountIn(BaseModel):
    headcount: int = Field(ge=1)


class PartyBookingOut(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    package_id: uuid.UUID
    headcount: int
    total_cents: int
    deposit_cents: int
    balance_cents: int
    status: str
    # Deposit PaymentIntent client_secret — only on a fresh booking, for the Payment Element.
    client_secret: str | None = None


# --- Request-to-quote (Milestone C, PRD §9 / ADR-0009) -----------------------


class QuoteRequestIn(BaseModel):
    """A parent's brief. Structured fields only — no chat (EXT-1 §10).

    INV-3: the party is described by kid count + an age band. There is deliberately no field
    for a child's name or birth date, and ``notes`` is labelled "no kids' names" in the UI.
    """

    organisation_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    suburb: str = Field(min_length=1, max_length=120)
    kid_count: int = Field(ge=1, le=200)
    child_age_min: int = Field(ge=0, le=18)
    child_age_max: int = Field(ge=0, le=18)
    budget_cents: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _coherent(self) -> "QuoteRequestIn":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.child_age_max < self.child_age_min:
            raise ValueError("child_age_max must be >= child_age_min")
        return self


class QuoteIn(BaseModel):
    """The provider's offer. ``venue_id`` + the time window + the price become a bespoke,
    unlisted package and a single slot; accepting books that slot on the existing rails."""

    venue_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    headcount: int = Field(ge=1, le=200)
    per_head_price_cents: int = Field(ge=0)
    message: str | None = Field(default=None, max_length=1000)
    deposit_pct: int | None = Field(default=None, ge=10, le=100)

    @model_validator(mode="after")
    def _end_after_start(self) -> "QuoteIn":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class RevisionRequestIn(BaseModel):
    """The parent's single counter-offer message (ADR-0009 — one round, then accept or lapse)."""

    message: str = Field(min_length=1, max_length=1000)


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    organisation_id: uuid.UUID
    package_id: uuid.UUID
    slot_id: uuid.UUID
    headcount: int
    per_head_price_cents: int
    total_cents: int
    message: str | None
    revision_message: str | None
    revision_count: int
    expires_at: datetime
    booking_id: uuid.UUID | None
    status: str


class QuoteDetailOut(QuoteOut):
    """Quote enriched for display: when it starts, where, and whether a revision is still open."""

    starts_at: datetime
    ends_at: datetime
    venue_name: str
    organisation_name: str
    deposit_cents: int
    can_request_revision: bool


class QuoteRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    guardian_id: uuid.UUID
    organisation_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    suburb: str
    kid_count: int
    child_age_min: int
    child_age_max: int
    budget_cents: int | None
    notes: str | None
    status: str


class QuoteRequestDetailOut(QuoteRequestOut):
    organisation_name: str
    quote: QuoteDetailOut | None = None
