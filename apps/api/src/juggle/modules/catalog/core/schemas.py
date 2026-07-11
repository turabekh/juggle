"""Pydantic request/response schemas for the catalog module."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VenueCreate(BaseModel):
    organisation_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    suburb: str | None = Field(default=None, max_length=120)
    postcode: str | None = Field(default=None, max_length=8)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _coords_paired(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    suburb: str | None
    postcode: str | None


class ProgramCreate(BaseModel):
    organisation_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str = Field(min_length=1, max_length=60)


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    title: str
    description: str | None
    category: str
    status: str


class SessionCreate(BaseModel):
    venue_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(gt=0)
    price_cents: int = Field(ge=0)
    age_min: int = Field(ge=0, le=18)
    age_max: int = Field(ge=0, le=18)
    session_type: Literal["half_day", "full_day"] = "full_day"
    drop_off: bool = True
    what_to_bring: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _sane_ranges(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.age_min > self.age_max:
            raise ValueError("age_min must be <= age_max")
        return self


class DuplicateSessionsIn(BaseModel):
    # Whole-day forward shift applied to every session (preserves time-of-day).
    shift_days: int = Field(ge=1, le=730)


class BulkSessionsIn(BaseModel):
    # A batch of sessions to create in one transaction (PRD §8.2 bulk creation).
    # The client expands a template + date range into fully-formed items.
    items: list[SessionCreate] = Field(min_length=1, max_length=60)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    program_id: uuid.UUID
    venue_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    capacity: int
    seats_taken: int
    seats_remaining: int
    price_cents: int
    age_min: int
    age_max: int
    session_type: str
    drop_off: bool
    status: str


class SessionDetailOut(SessionOut):
    """Public listing-detail view (PRD §7.2): the session plus the program,
    provider, and venue context a parent needs before booking."""

    title: str
    category: str
    description: str | None
    organisation_name: str
    venue_name: str
    suburb: str | None
    postcode: str | None
    # Provider trust signals (PRD §7.2 verification badges).
    provider_approved: bool = False
    provider_abn: bool = False
    provider_wwcc_verified: bool = False
    provider_insurance_verified: bool = False
