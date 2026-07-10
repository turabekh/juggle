"""Pydantic schemas for search results (the parent-facing discovery cards)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class SearchCard(BaseModel):
    """One session as shown on a listing card (PRD §7.1)."""

    session_id: uuid.UUID
    program_id: uuid.UUID
    title: str
    category: str
    organisation_name: str
    venue_name: str
    suburb: str | None
    postcode: str | None
    starts_at: datetime
    ends_at: datetime
    price_cents: int
    age_min: int
    age_max: int
    seats_remaining: int
    session_type: str
    drop_off: bool
    distance_km: float | None  # None when the search had no coordinates


class SearchResults(BaseModel):
    items: list[SearchCard]
    limit: int
    offset: int
