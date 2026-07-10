"""Provider organisation domain models: org, membership/roles, and the
verification records (WWCC, insurance) gated before go-live (PRD §8.1, §11)."""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class OrgStatus(enum.StrEnum):
    pending = "pending"          # signed up, not yet approved
    approved = "approved"        # may publish listings
    suspended = "suspended"


class OrgRole(enum.StrEnum):
    owner = "owner"
    staff = "staff"


class VerificationStatus(enum.StrEnum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


class Organisation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "organisation"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    abn: Mapped[str | None] = mapped_column(String(20), nullable=True)  # validated via ABR
    status: Mapped[OrgStatus] = mapped_column(
        Enum(OrgStatus, name="org_status"), default=OrgStatus.pending, nullable=False
    )
    # Decreases on provider-initiated cancellations (PRD §8.3).
    reliability_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    stripe_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class OrgMember(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "org_member"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_account_id", name="uq_org_member"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, name="org_role"), default=OrgRole.staff, nullable=False
    )


class WwccRecord(UUIDPkMixin, TimestampMixin, Base):
    """WA Working with Children Check per child-facing staff member (PRD §11).

    Manually verified at MVP; expiry tracked so roster assignment can be blocked
    on expiry.
    """

    __tablename__ = "wwcc_record"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    org_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("org_member.id", ondelete="SET NULL"), nullable=True
    )
    staff_name: Mapped[str] = mapped_column(String(200), nullable=False)
    wwcc_number: Mapped[str] = mapped_column(String(64), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.pending,
        nullable=False,
    )


class InsuranceDoc(UUIDPkMixin, TimestampMixin, Base):
    """Public-liability certificate; manual review at MVP (PRD §8.1, §11)."""

    __tablename__ = "insurance_doc"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_ref: Mapped[str] = mapped_column(String(500), nullable=False)  # object-store key
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status", create_type=False),
        default=VerificationStatus.pending,
        nullable=False,
    )
