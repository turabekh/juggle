"""Pydantic request/response schemas for the inventory module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HoldCreate(BaseModel):
    session_id: uuid.UUID
    quantity: int = Field(default=1, gt=0, le=20)


class HoldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    quantity: int
    status: str
    expires_at: datetime


class AvailabilityOut(BaseModel):
    session_id: uuid.UUID
    capacity: int
    seats_taken: int
    seats_remaining: int
