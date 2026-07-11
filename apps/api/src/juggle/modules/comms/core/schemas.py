"""Pydantic schemas for the comms module (PRD §8.5)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BroadcastIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    template_key: str | None = Field(default=None, max_length=40)


class BroadcastOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    template_key: str | None
    subject: str
    body: str
    recipient_count: int
    created_at: datetime
