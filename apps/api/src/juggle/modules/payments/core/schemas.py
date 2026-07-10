"""Pydantic schemas for the payments module."""

import uuid

from pydantic import BaseModel, ConfigDict


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_cents: int
    application_fee_cents: int
    currency: str
    status: str
