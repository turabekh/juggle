"""Pydantic schemas for the analytics module (PRD §8.6)."""

import uuid

from pydantic import BaseModel


class ProgramStat(BaseModel):
    program_id: uuid.UUID
    title: str
    category: str
    status: str
    sessions: int
    capacity_total: int
    booked_total: int
    fill_rate: float          # 0..1 across the program's sessions
    revenue_cents: int        # gross confirmed bookings value


class FamilyMix(BaseModel):
    total: int
    new: int                  # exactly one confirmed booking with this org
    returning: int            # two or more (repeat customers)


class OrgAnalytics(BaseModel):
    organisation_id: uuid.UUID
    revenue_cents: int
    bookings: int             # confirmed bookings (orders per session)
    sessions_total: int
    published_sessions: int
    capacity_total: int
    booked_total: int
    fill_rate: float          # 0..1 overall
    families: FamilyMix
    programs: list[ProgramStat]
