"""Pydantic schemas for the qanda module (PRD §7.2)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class QuestionIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


class QuestionOut(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID
    body: str
    answer: str | None
    answered_at: datetime | None
    asker_label: str
    created_at: datetime
