"""Identity domain models: the auth principal and guardian family profiles.

``UserAccount`` is the single auth principal for guardians, provider staff, and
admins (role/context decides capability). Child records follow PRD §7.3 / §11
data-minimisation: first name + DOB only, no surname, no photos.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class UserStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"


class UserAccount(UUIDPkMixin, TimestampMixin, Base):
    """Auth principal. Guardians, provider members, and admins are all users."""

    __tablename__ = "user_account"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # MFA is required for admin accounts (PRD §10.4); populated when enrolled.
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.active, nullable=False
    )


class Child(UUIDPkMixin, TimestampMixin, Base):
    """A guardian's child. Minimum data only; guardian-only access."""

    __tablename__ = "child"

    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    medical_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    photo_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
