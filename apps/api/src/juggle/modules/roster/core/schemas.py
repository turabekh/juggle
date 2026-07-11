"""Pydantic schemas for the roster module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RosterRow(BaseModel):
    """One child on a session's roster (PRD §8.3). Contains child PII — provider
    (org member) access only, never exposed publicly or in analytics."""

    booking_id: uuid.UUID
    booking_child_id: uuid.UUID
    child_first_name: str
    age: int
    medical_notes: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    form_answers: dict[str, Any]
    attended: bool
    attended_at: datetime | None


class RosterOut(BaseModel):
    session_id: uuid.UUID
    count: int
    attended_count: int
    rows: list[RosterRow]


class AttendanceIn(BaseModel):
    attended: bool


class AttendanceOut(BaseModel):
    booking_child_id: uuid.UUID
    attended: bool
    attended_at: datetime | None
