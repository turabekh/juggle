"""Pydantic schemas for the roster module."""

import uuid
from typing import Any

from pydantic import BaseModel


class RosterRow(BaseModel):
    """One child on a session's roster (PRD §8.3). Contains child PII — provider
    (org member) access only, never exposed publicly or in analytics."""

    booking_id: uuid.UUID
    child_first_name: str
    age: int
    medical_notes: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    form_answers: dict[str, Any]


class RosterOut(BaseModel):
    session_id: uuid.UUID
    count: int
    rows: list[RosterRow]
