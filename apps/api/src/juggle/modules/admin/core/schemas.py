"""Pydantic schemas for the admin module."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class OrgAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    reliability_score: float
    abn: str | None
    created_at: datetime


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    is_admin: bool


class RefundRequest(BaseModel):
    reason: str


class ImpersonationCreate(BaseModel):
    target_user_id: uuid.UUID
    mode: Literal["view_as", "act_as"]
    reason: str | None = None


class ImpersonationTokenOut(BaseModel):
    session_id: uuid.UUID
    token: str
    mode: str
    expires_at: datetime


class ImpersonationSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    impersonator_id: uuid.UUID
    target_id: uuid.UUID
    mode: str
    reason: str | None
    expires_at: datetime
    ended_at: datetime | None
