"""Config domain models: versioned, audit-logged runtime platform settings.

Every operational lever the founder needs (fee %, seat-hold TTL, payout delay,
taxonomy, ...) is a row here, editable through the admin panel with no deploy
(PRD §10.1). Changes are versioned: each edit inserts a new row; exactly one row
per key is ``is_current``. Bounds/validation live in the config service.
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class PlatformSetting(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "platform_setting"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_platform_setting_key_version"),
    )

    key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
