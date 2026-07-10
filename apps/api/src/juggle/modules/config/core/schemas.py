"""Pydantic schemas for the config module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SettingItem(BaseModel):
    key: str
    value: Any
    default: Any
    minimum: float
    maximum: float
    description: str


class SettingUpdate(BaseModel):
    # int | float so integer settings (TTLs, days) keep their int type through
    # validation; a plain `float` would coerce 600 → 600.0 and fail the int check.
    value: int | float
    note: str | None = None


class SettingVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    is_current: bool
    note: str | None
    changed_by_id: uuid.UUID | None
    created_at: datetime
