"""Pydantic schemas for the audit module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    impersonated_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    detail: dict[str, Any]
    created_at: datetime
