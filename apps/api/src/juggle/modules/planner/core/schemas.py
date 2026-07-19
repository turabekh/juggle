"""Schemas for the AI holiday planner (parent-facing, §7 discovery).

Data-minimisation (INV-3): the planner works from child *ages* only — never
names, DOB, or medical info — so nothing sent to the LLM can carry child PII.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanRequest(BaseModel):
    """A parent's brief. Ages are plain integers, not child records."""

    ages: list[int] = Field(min_length=1, max_length=8)
    date_from: date
    date_to: date
    suburb: str | None = Field(default=None, max_length=120)
    postcode: str | None = Field(default=None, max_length=4)
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = Field(default=None, ge=1, le=100)
    budget_cents: int | None = Field(default=None, ge=0)
    categories: list[str] | None = Field(default=None, max_length=10)
    day_type: str | None = Field(default=None)  # 'weekday' | 'weekend' | None
    start_after_hour: int | None = Field(default=None, ge=0, le=23)
    drop_off_only: bool = False


class CandidateSession(BaseModel):
    """A live, bookable session offered to the composer. Public listing data
    only — this is what the LLM sees, so it carries no child PII."""

    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    program_id: uuid.UUID  # identifies the activity — used to vary the plan across days
    title: str
    category: str
    organisation_name: str
    venue_name: str
    suburb: str | None
    starts_at: datetime
    ends_at: datetime
    price_cents: int
    age_min: int
    age_max: int
    seats_remaining: int
    distance_km: float | None


# --- what the composer (LLM or rules) returns -------------------------------


class PlanDraftItem(BaseModel):
    session_id: uuid.UUID
    for_ages: list[int]
    reason: str = Field(max_length=300)


class PlanDraft(BaseModel):
    """The composer's selection — validated against the candidate set before use."""

    items: list[PlanDraftItem]
    summary: str = Field(default="", max_length=800)


# --- API response ------------------------------------------------------------


class PlanItem(BaseModel):
    session: CandidateSession
    for_ages: list[int]
    reason: str


class PlanDay(BaseModel):
    day: date
    items: list[PlanItem]


class PlanOut(BaseModel):
    days: list[PlanDay]
    total_cents: int
    summary: str
    generated_by: str  # 'ai' | 'rules'
    candidate_count: int
