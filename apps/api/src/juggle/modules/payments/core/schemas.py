"""Pydantic schemas for the payments module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_cents: int
    application_fee_cents: int
    currency: str
    status: str


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    session_id: uuid.UUID | None
    amount_cents: int
    status: str
    scheduled_for: datetime | None


class PayoutRunResult(BaseModel):
    released: int
    total_cents: int
