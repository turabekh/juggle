"""Party Planner domain models (ADR-0011): vote-to-book birthday planning.

A host builds a ``PartyPlan`` offering up to N ``PlanOption``s (Juggle party
packages, each carrying its slot datetime, + max one custom free-text option).
Invitees join via a tokenized public link (``PlanInvite``), record a ``PlanRsvp``
(parent name/email + attending-kid *count* only — **no child PII lives here**,
INV-3), and cast one editable ``PlanVote``. At the deadline the plan resolves to
a winner; for a package winner the host confirms a booking through the existing
``parties`` rails (INV-1/INV-2 — the planner creates no holds and moves no money
itself).

Privacy (INV-13): votes are anonymous — ``PlanVote`` references the invite solely
for one-vote enforcement (``UNIQUE(plan_invite_id)``); no read path joins them.
Marketing consent is stored in ``PlanMarketingConsent``, deliberately detached
from the purgeable guest record so it survives the post-event PII purge.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class PlanStatus(enum.StrEnum):
    draft = "draft"                        # host assembling; not shareable
    open = "open"                          # link live; RSVP/vote/edit until deadline
    resolved = "resolved"                  # deadline passed; winner known; awaiting host
    booked = "booked"                      # host confirmed a package winner → PartyBooking
    expired_unbooked = "expired_unbooked"  # custom winner / host never booked (terminal)


class PlanOptionKind(enum.StrEnum):
    package = "package"  # a bookable Juggle party package + specific slot
    custom = "custom"    # free-text option; never deposit-bookable


class PlanInviteMode(enum.StrEnum):
    open = "open"    # self-served via the shareable link
    email = "email"  # host-entered per-guest invite


class PlanInviteStatus(enum.StrEnum):
    pending = "pending"    # open-link RSVP awaiting host approval
    approved = "approved"  # counts toward board + tally
    removed = "removed"    # host removed
    blocked = "blocked"    # host blocked (abuse)


class PartyPlan(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "party_plan"

    host_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, name="party_plan_status"), default=PlanStatus.draft, nullable=False
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    theme: Mapped[str] = mapped_column(String(40), default="default", nullable=False)
    # Ordered list of plan_option ids (as strings) = the birthday kid's ranking; drives the
    # ⭐ badge and the resolution tie-break (ADR-0011 edge 4). Voided entries are skipped.
    birthday_kid_ranking: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Opaque ≥128-bit share token, set when the plan opens; noindex, expires at the deadline.
    token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    # Open-link RSVPs are auto-approved so anyone with the share link can vote immediately (one-step
    # RSVP-and-vote). The field is retained so a host can still block/remove abusers (moderation),
    # and to leave room for an opt-in approval mode later; it defaults OFF.
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Soft reference to the winning plan_option (nullable = tie the host must break). Not a hard
    # FK to avoid a circular plan↔option dependency; options are voided, never hard-deleted.
    winning_option_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party_booking.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Once-only markers so scheduler-driven sends/announcements don't repeat each tick.
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    low_rsvp_nudge_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlanOption(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "plan_option"
    __table_args__ = (
        # A package option carries a package + slot and no custom text; a custom option is the
        # inverse. Enforced at the DB layer, not just in Python.
        CheckConstraint(
            "(kind = 'package' AND package_id IS NOT NULL AND slot_id IS NOT NULL "
            "AND custom_text IS NULL) OR "
            "(kind = 'custom' AND custom_text IS NOT NULL AND package_id IS NULL "
            "AND slot_id IS NULL)",
            name="ck_plan_option_kind_shape",
        ),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_plan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[PlanOptionKind] = mapped_column(
        Enum(PlanOptionKind, name="plan_option_kind"), nullable=False
    )
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party_package.id", ondelete="RESTRICT"), nullable=True
    )
    slot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party_slot.id", ondelete="RESTRICT"), nullable=True
    )
    custom_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revote_nudge_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlanInvite(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "plan_invite"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_plan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mode: Mapped[PlanInviteMode] = mapped_column(
        Enum(PlanInviteMode, name="plan_invite_mode"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)  # transactional-only (INV-13)
    parent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[PlanInviteStatus] = mapped_column(
        Enum(PlanInviteStatus, name="plan_invite_status"),
        default=PlanInviteStatus.pending,
        nullable=False,
    )
    # Per-invite capability token for the RSVP/vote-edit surface.
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class PlanRsvp(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "plan_rsvp"
    __table_args__ = (
        CheckConstraint("kid_count >= 0 AND kid_count <= 50", name="ck_plan_rsvp_kid_count"),
    )

    # One RSVP per invite (edit-in-place).
    plan_invite_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_invite.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    attending: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Pseudonymous board fields — parent-chosen, sanitised, never a child identity (INV-13).
    nickname: Mapped[str | None] = mapped_column(String(80), nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PlanVote(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "plan_vote"
    __table_args__ = (
        # One editable vote per invite (ADR-0011 edges 1–2). The invite reference exists ONLY
        # for this constraint + the edge-6 re-vote nudge; no read path exposes vote-by-invite.
        Index("uq_plan_vote_invite", "plan_invite_id", unique=True),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_plan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_invite_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_invite.id", ondelete="CASCADE"), nullable=False
    )
    plan_option_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_option.id", ondelete="CASCADE"), index=True, nullable=False
    )


class PlanReaction(UUIDPkMixin, TimestampMixin, Base):
    """A one-tap emoji reaction by an invite on an option (ADR-0011 Milestone C, gamified layer).
    Aggregate counts only are ever surfaced — reactions are not attributed, consistent with the
    vote-anonymity posture. UNIQUE(invite, option, emoji) makes a tap idempotent/toggleable."""

    __tablename__ = "plan_reaction"
    __table_args__ = (
        Index("uq_plan_reaction", "plan_invite_id", "plan_option_id", "emoji", unique=True),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_plan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_option_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_option.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_invite_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_invite.id", ondelete="CASCADE"), nullable=False
    )
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)


class PlanMarketingConsent(UUIDPkMixin, TimestampMixin, Base):
    """Store-only marketing consent (Spam Act 2003), deliberately detached from the purgeable
    ``PlanInvite`` so it survives the post-event PII purge (ADR-0011 edge 7). No plan FK."""

    __tablename__ = "plan_marketing_consent"
    __table_args__ = (Index("ix_plan_marketing_consent_email", "email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "party_planner_rsvp"


class PlanThrottle(UUIDPkMixin, TimestampMixin, Base):
    """Persistent fixed-window rate-limit counter for the public RSVP/vote surface, so the cap
    survives across worker processes (ADR-0011 abuse controls)."""

    __tablename__ = "plan_throttle"
    __table_args__ = (Index("uq_plan_throttle_scope", "scope_key", unique=True),)

    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)  # e.g. "ip:1.2.3.4" / token
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
