"""Identity domain models: the auth principal and guardian family profiles.

``UserAccount`` is the single auth principal for guardians, provider staff, and
admins (role/context decides capability). Child records follow PRD §7.3 / §11
data-minimisation: first name + DOB only, no surname, no photos.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
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
    # Unique when present (Postgres treats NULLs as distinct) so SMS one-time-code
    # sign-in can resolve an account by phone. Stored normalised (see service).
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
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


class GuardianLink(UUIDPkMixin, TimestampMixin, Base):
    """A co-guardian relationship (PRD §7.3, "multiple guardians per family").

    The inviter (``guardian_id``) adds another account (``member_id``); once the
    invitee accepts, the two share access to each other's children and see each
    other's bookings. Access is symmetric but requires ``accepted`` — you can't
    unilaterally gain access to someone's children.
    """

    __tablename__ = "guardian_link"
    __table_args__ = (
        UniqueConstraint("guardian_id", "member_id", name="uq_guardian_link"),
    )

    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RefreshToken(UUIDPkMixin, TimestampMixin, Base):
    """A DB-backed, revocable refresh token (one per active device/session).

    Only the SHA-256 hash of the opaque token is stored. Tokens are rotated on
    every use: refreshing revokes the presented token and issues a new one, so a
    stolen-then-reused token is detectable. Logout revokes the row; an admin can
    revoke every row for a user, severing all their sessions immediately.
    """

    __tablename__ = "refresh_token"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The token this one was rotated into — lets reuse of a rotated token be traced.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_token.id", ondelete="SET NULL"), nullable=True
    )


class AuthThrottle(UUIDPkMixin, TimestampMixin, Base):
    """Persistent fixed-window rate-limit counter for the SMS one-time-code sink.

    Mirrors ``party_planner.PlanThrottle``: one row per scope (a normalised
    number, a client IP, or the global ``otp`` bucket) so the SMS-bombing / cost
    caps survive across worker processes. Read ``FOR UPDATE`` so concurrent
    requests can't both slip under the cap.
    """

    __tablename__ = "auth_throttle"
    __table_args__ = (Index("uq_auth_throttle_scope", "scope_key", unique=True),)

    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)  # e.g. "otp:ip:1.2.3.4"
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class OtpChallenge(UUIDPkMixin, TimestampMixin, Base):
    """A pending SMS one-time-code sign-in challenge, keyed by phone.

    Stores only a keyed hash of the code. Short-lived (config ``otp_ttl_minutes``)
    and attempt-capped (``otp_max_attempts``); consumed exactly once on success.
    """

    __tablename__ = "otp_challenge"

    phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
