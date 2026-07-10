"""Schemas for the notifications module: caller inputs + the read model."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class ConfirmationSession:
    """One booked session, passed in by the caller to render a confirmation."""

    session_id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    venue_name: str
    children: list[str] = field(default_factory=list)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    subject: str
    to_email: str
    status: str
    detail: dict[str, Any]
    created_at: datetime
