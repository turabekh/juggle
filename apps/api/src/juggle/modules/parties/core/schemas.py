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
