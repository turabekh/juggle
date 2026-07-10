"""Pydantic schemas for the booking module (cart checkout + order views)."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckoutChild(BaseModel):
    child_id: uuid.UUID
    form_answers: dict[str, Any] = Field(default_factory=dict)


class CheckoutItem(BaseModel):
    hold_id: uuid.UUID
    children: list[CheckoutChild] = Field(min_length=1)


class CheckoutRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    items: list[CheckoutItem] = Field(min_length=1)


class BookingChildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    child_id: uuid.UUID
    form_answers: dict[str, Any]


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    organisation_id: uuid.UUID
    payment_id: uuid.UUID | None
    status: str
    unit_price_cents: int
    children: list[BookingChildOut]


class OrderOut(BaseModel):
    payment_id: uuid.UUID
    amount_cents: int
    application_fee_cents: int
    currency: str
    status: str
    bookings: list[BookingOut]


class SessionCancelResult(BaseModel):
    session_id: uuid.UUID
    cancelled_bookings: int
    refunded_payments: int
    reliability_score: float
