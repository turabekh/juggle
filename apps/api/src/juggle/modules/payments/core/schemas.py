"""Pydantic schemas for the payments module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_cents: int
    application_fee_cents: int
    fee_gst_cents: int = 0
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


class OnboardIn(BaseModel):
    organisation_id: uuid.UUID
    return_url: str | None = None
    refresh_url: str | None = None


class OnboardLinkOut(BaseModel):
    url: str


class ConnectStatusOut(BaseModel):
    onboarded: bool
    charges_enabled: bool
    payouts_enabled: bool


class RefreshIn(BaseModel):
    organisation_id: uuid.UUID


class PaymentConfigOut(BaseModel):
    live: bool
    publishable_key: str | None
