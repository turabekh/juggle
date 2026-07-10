"""Pydantic request/response schemas for the org module."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    abn: str | None = None
    created_at: datetime


class AbnUpdate(BaseModel):
    abn: str = Field(min_length=1, max_length=20)


class WwccCreate(BaseModel):
    staff_name: str = Field(min_length=1, max_length=200)
    wwcc_number: str = Field(min_length=1, max_length=64)
    expiry_date: date


class WwccOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    staff_name: str
    wwcc_number: str
    expiry_date: date
    status: str
    created_at: datetime


class InsuranceCreate(BaseModel):
    file_ref: str = Field(min_length=1, max_length=500)
    expiry_date: date | None = None


class InsuranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_ref: str
    expiry_date: date | None
    status: str
    created_at: datetime


class MemberCreate(BaseModel):
    user_account_id: uuid.UUID
    role: Literal["owner", "staff"] = "staff"


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    user_account_id: uuid.UUID
    role: str
