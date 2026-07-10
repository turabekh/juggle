"""Catalog domain models: venues, programs, and sessions (the bookable unit).

``Session`` carries the capacity invariant that makes overselling impossible at
the DB layer (PRD §12): ``seats_taken`` is a denormalised counter guarded by a
CHECK constraint. The inventory module mutates it transactionally under a row
lock; the constraint is the ultimate backstop.
"""

import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class ProgramStatus(enum.StrEnum):
    draft = "draft"
    published = "published"
    unpublished = "unpublished"


class SessionStatus(enum.StrEnum):
    scheduled = "scheduled"
    cancelled = "cancelled"


class SessionType(enum.StrEnum):
    half_day = "half_day"
    full_day = "full_day"


class Venue(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "venue"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suburb: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    # WGS84 point for PostGIS radius search (PRD §7.1). Spatial index added in search milestone.
    location: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )


class Program(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "program"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Category is editable taxonomy (config module), stored as its key here.
    category: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    status: Mapped[ProgramStatus] = mapped_column(
        Enum(ProgramStatus, name="program_status"), default=ProgramStatus.draft, nullable=False
    )


class Session(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "session"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_session_capacity_positive"),
        CheckConstraint("seats_taken >= 0", name="ck_session_seats_taken_nonneg"),
        # The core invariant — overselling is impossible by constraint.
        CheckConstraint("seats_taken <= capacity", name="ck_session_no_oversell"),
        CheckConstraint("price_cents >= 0", name="ck_session_price_nonneg"),
        CheckConstraint("age_min <= age_max", name="ck_session_age_range"),
        CheckConstraint("ends_at > starts_at", name="ck_session_time_order"),
    )

    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), index=True, nullable=False
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_taken: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    age_min: Mapped[int] = mapped_column(Integer, nullable=False)
    age_max: Mapped[int] = mapped_column(Integer, nullable=False)
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, name="session_type"), default=SessionType.full_day, nullable=False
    )
    drop_off: Mapped[bool] = mapped_column(default=True, nullable=False)  # vs parent-stays
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"), default=SessionStatus.scheduled, nullable=False
    )
