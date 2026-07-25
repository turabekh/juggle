"""Pydantic schemas for the admin module."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from juggle.modules.org.core.schemas import InsuranceOut, WwccOut


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
    status: str


class SuspendUserIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class MergeUsersIn(BaseModel):
    source_id: uuid.UUID  # the duplicate — its data moves and it is deactivated
    target_id: uuid.UUID  # the account to keep


class OrgVerifications(BaseModel):
    organisation_id: uuid.UUID
    name: str
    status: str
    abn: str | None
    wwcc: list[WwccOut]
    insurance: list[InsuranceOut]


class VerifyRequest(BaseModel):
    status: Literal["pending", "verified", "rejected", "expired"]


class RefundRequest(BaseModel):
    reason: str


# Listing moderation rejection reasons (ADR-0006 / EXT-1 §2-E2, §10). `recurring_enrolment`
# is the E2 fence: recurring/term-enrolment classes disguised as one-offs are not allowed.
ListingRejectionReason = Literal[
    "recurring_enrolment", "safety_concern", "misleading_content", "policy_violation", "other"
]


class ListingRejectIn(BaseModel):
    reason: ListingRejectionReason
    note: str | None = None


class ListingModerationOut(BaseModel):
    program_id: uuid.UUID
    status: str
    reason: ListingRejectionReason


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
