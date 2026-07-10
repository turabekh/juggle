"""Flags domain models: feature flags with rollout and targeting (PRD §10.1).

Per-flag on/off, percentage rollout, and per-org targeting, all editable from
the admin flags UI. Evaluation logic lives in the flags service.
"""

from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class FeatureFlag(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "feature_flag"
    __table_args__ = (
        CheckConstraint(
            "rollout_percentage >= 0 AND rollout_percentage <= 100",
            name="ck_feature_flag_rollout_range",
        ),
    )

    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # e.g. {"org_ids": ["..."], "user_ids": ["..."]}
    targeting: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
