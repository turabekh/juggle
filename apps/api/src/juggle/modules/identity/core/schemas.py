"""Pydantic request/response schemas for the identity module."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # Seconds until the access token expires — lets the client refresh proactively.
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class OtpRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)


class OtpVerify(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    code: str = Field(min_length=4, max_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_admin: bool
    created_at: datetime


class ChildCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    medical_notes: str | None = Field(default=None, max_length=1000)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    photo_consent: bool = False


class ChildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    date_of_birth: date
    medical_notes: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    photo_consent: bool


class CoGuardianInvite(BaseModel):
    email: EmailStr


class CoGuardianOut(BaseModel):
    """A co-guardian relationship from the current user's point of view."""

    id: uuid.UUID
    other_email: str
    other_name: str | None
    direction: str  # 'sent' (I invited them) | 'received' (they invited me)
    accepted: bool
