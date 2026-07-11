"""Analytics service (PRD §8.6): provider fill rate, revenue, and family mix.

A pure read-aggregation module (no table of its own) at the top of the layering.
It authorises via ``org`` membership and rolls up ``catalog`` sessions +
``booking`` records into per-program and org-level figures. Revenue is the gross
value of confirmed bookings (unit price × children). "New vs returning" counts a
family as returning once it has two or more confirmed bookings with the org.

Search-impression analytics (PRD §8.6/§13) needs event instrumentation that does
not exist yet, so it is deliberately out of scope here.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.analytics.core.schemas import (
    FamilyMix,
    FunnelOut,
    FunnelStage,
    OrgAnalytics,
    ProgramStat,
)
from juggle.modules.booking.core.models import Booking, BookingChild, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.models import ProgramStatus, SessionStatus
from juggle.modules.events.core import service as events_service
from juggle.modules.org.core import service as org_service


class NotOrgMember(Exception):
    """Caller is not a member of the organisation."""


def _fill(booked: int, capacity: int) -> float:
    return round(booked / capacity, 4) if capacity > 0 else 0.0


def platform_funnel(db: Session, *, days: int, since: datetime) -> FunnelOut:
    """Platform-wide funnel event counts over a window (PRD §13, admin-only)."""
    counts = events_service.funnel_counts(db, since=since)
    return FunnelOut(
        days=days,
        stages=[FunnelStage(event_type=k, count=v) for k, v in counts.items()],
    )


def org_analytics(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> OrgAnalytics:
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotOrgMember(str(organisation_id))

    # Per-booking revenue + guardian, for confirmed bookings across the org.
    booking_rows = db.execute(
        select(
            Booking.session_id,
            Booking.guardian_id,
            Booking.unit_price_cents,
            func.count(BookingChild.id),
        )
        .join(BookingChild, BookingChild.booking_id == Booking.id)
        .where(
            Booking.organisation_id == organisation_id,
            Booking.status == BookingStatus.confirmed,
        )
        .group_by(Booking.id, Booking.session_id, Booking.guardian_id, Booking.unit_price_cents)
    ).all()

    revenue_by_session: dict[uuid.UUID, int] = {}
    bookings_by_session: dict[uuid.UUID, int] = {}
    bookings_per_guardian: dict[uuid.UUID, int] = {}
    total_revenue = 0
    total_bookings = 0
    for session_id, guardian_id, unit_price, child_count in booking_rows:
        value = int(unit_price) * int(child_count)
        revenue_by_session[session_id] = revenue_by_session.get(session_id, 0) + value
        bookings_by_session[session_id] = bookings_by_session.get(session_id, 0) + 1
        bookings_per_guardian[guardian_id] = bookings_per_guardian.get(guardian_id, 0) + 1
        total_revenue += value
        total_bookings += 1

    programs = catalog_service.list_org_programs(
        db, organisation_id=organisation_id, actor_id=actor_id
    )
    program_stats: list[ProgramStat] = []
    sessions_total = published_sessions = 0
    capacity_total = booked_total = 0

    for program in programs:
        sessions = catalog_service.list_program_sessions(db, program.id)
        p_capacity = p_booked = p_sessions = p_revenue = 0
        for s in sessions:
            if s.status is SessionStatus.cancelled:
                continue
            p_sessions += 1
            p_capacity += s.capacity
            p_booked += s.seats_taken
            p_revenue += revenue_by_session.get(s.id, 0)

        program_stats.append(
            ProgramStat(
                program_id=program.id,
                title=program.title,
                category=program.category,
                status=program.status.value,
                sessions=p_sessions,
                capacity_total=p_capacity,
                booked_total=p_booked,
                fill_rate=_fill(p_booked, p_capacity),
                revenue_cents=p_revenue,
            )
        )
        sessions_total += p_sessions
        if program.status is ProgramStatus.published:
            published_sessions += p_sessions
        capacity_total += p_capacity
        booked_total += p_booked

    returning = sum(1 for n in bookings_per_guardian.values() if n >= 2)
    families = FamilyMix(
        total=len(bookings_per_guardian),
        new=len(bookings_per_guardian) - returning,
        returning=returning,
    )

    return OrgAnalytics(
        organisation_id=organisation_id,
        revenue_cents=total_revenue,
        bookings=total_bookings,
        sessions_total=sessions_total,
        published_sessions=published_sessions,
        capacity_total=capacity_total,
        booked_total=booked_total,
        fill_rate=_fill(booked_total, capacity_total),
        families=families,
        programs=program_stats,
    )
