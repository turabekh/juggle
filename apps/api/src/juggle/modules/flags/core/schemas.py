"""Pydantic schemas for the flags module."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    description: str | None
    enabled: bool
    rollout_percentage: int
    targeting: dict[str, Any] | None


class FlagUpsert(BaseModel):
    enabled: bool
    rollout_percentage: int = Field(default=0, ge=0, le=100)
    targeting: dict[str, Any] | None = None
    description: str | None = None


class FlagEvaluation(BaseModel):
    key: str
    enabled: bool
