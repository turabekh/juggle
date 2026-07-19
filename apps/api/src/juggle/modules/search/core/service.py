"""Search service: geo + attribute query over live, published inventory.

Search sits at the top of the layering, so it may read across the catalog and
org domains to assemble listing cards in a single SQL query. It is read-only —
there is nothing to mutate here.

Availability shown is ``capacity - seats_taken``. That is conservative: an
expired-but-not-yet-reclaimed hold can only *understate* availability, never
oversell the display (a background reclaim job keeps it tight — see inventory).
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import Select, cast, func, select
from sqlalchemy.orm import Session

from juggle.modules.catalog.core.models import (
    Program,
    ProgramStatus,
    SessionStatus,
    Venue,
)
from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.events.core import service as events_service
from juggle.modules.org.core.models import Organisation
from juggle.modules.search.core.schemas import SearchCard

DEFAULT_RADIUS_KM = 25.0
MAX_LIMIT = 100

# WA has no daylight saving (INV-7): a fixed +8 offset is exact year-round, so "which day
# of the week / after school" is evaluated in Perth local time, not UTC.
PERTH_TZ = "Australia/Perth"
PERTH_OFFSET = timedelta(hours=8)
AFTER_SCHOOL_HOUR = 15  # 3pm local — the "after school this week" cutoff (E2)
WEEKDAYS = frozenset({0, 1, 2, 3, 4})  # Mon..Fri (Python weekday numbering)
WEEKEND = frozenset({5, 6})            # Sat, Sun
FEED_HORIZON_DAYS = 7                  # bound feeds to the near term (this week/weekend)


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _perth_local(col: Any) -> Any:
    """A ``timestamptz`` column rendered as Perth wall-clock (``AT TIME ZONE``)."""
    return func.timezone(PERTH_TZ, col)


def search_sessions(
    db: Session,
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    suburb: str | None = None,
    postcode: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    child_age: int | None = None,
    category: str | None = None,
    price_max_cents: int | None = None,
    session_type: str | None = None,
    days_of_week: frozenset[int] | None = None,
    start_after_local_hour: int | None = None,
    available_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> list[SearchCard]:
    now = now or datetime.now(UTC)
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    # Row shape varies (a distance column is appended for geo queries), so the
    # generic is left loose.
    stmt: Select[tuple[Any, ...]] = (
        select(ProgramSession, Program, Venue, Organisation)
        .join(Program, ProgramSession.program_id == Program.id)
        .join(Venue, ProgramSession.venue_id == Venue.id)
        .join(Organisation, Program.organisation_id == Organisation.id)
        .where(Program.status == ProgramStatus.published)
        .where(ProgramSession.status == SessionStatus.scheduled)
        .where(ProgramSession.starts_at >= now)
    )

    has_point = lat is not None and lng is not None
    distance_m = None
    if has_point:
        point = cast(func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326), Geography)
        distance_m = func.ST_Distance(Venue.location, point)
        stmt = (
            stmt.add_columns(distance_m.label("distance_m"))
            .where(Venue.location.isnot(None))
            .where(func.ST_DWithin(Venue.location, point, radius_km * 1000))
            .order_by(distance_m)
        )
    else:
        if suburb is not None:
            stmt = stmt.where(Venue.suburb.ilike(suburb))
        if postcode is not None:
            stmt = stmt.where(Venue.postcode == postcode)
        stmt = stmt.order_by(ProgramSession.starts_at)

    if date_from is not None:
        stmt = stmt.where(ProgramSession.starts_at >= _day_start(date_from))
    if date_to is not None:
        stmt = stmt.where(ProgramSession.starts_at < _day_start(date_to) + timedelta(days=1))
    if child_age is not None:
        stmt = stmt.where(
            ProgramSession.age_min <= child_age, ProgramSession.age_max >= child_age
        )
    if category is not None:
        stmt = stmt.where(Program.category == category)
    if price_max_cents is not None:
        stmt = stmt.where(ProgramSession.price_cents <= price_max_cents)
    if session_type is not None:
        stmt = stmt.where(ProgramSession.session_type == session_type)
    if days_of_week is not None and days_of_week:
        # Perth-local weekday: Postgres isodow is 1=Mon..7=Sun; our set is 0=Mon..6=Sun.
        isodow = func.extract("isodow", _perth_local(ProgramSession.starts_at))
        stmt = stmt.where(isodow.in_(sorted(d + 1 for d in days_of_week)))
    if start_after_local_hour is not None:
        local_hour = func.extract("hour", _perth_local(ProgramSession.starts_at))
        stmt = stmt.where(local_hour >= start_after_local_hour)
    if available_only:
        stmt = stmt.where(ProgramSession.seats_taken < ProgramSession.capacity)

    stmt = stmt.limit(limit).offset(offset)

    cards: list[SearchCard] = []
    for row in db.execute(stmt):
        session_obj: ProgramSession = row[0]
        program: Program = row[1]
        venue: Venue = row[2]
        org: Organisation = row[3]
        distance_km = round(row.distance_m / 1000, 1) if has_point else None
        cards.append(
            SearchCard(
                session_id=session_obj.id,
                program_id=program.id,
                title=program.title,
                category=program.category,
                organisation_name=org.name,
                venue_name=venue.name,
                suburb=venue.suburb,
                postcode=venue.postcode,
                starts_at=session_obj.starts_at,
                ends_at=session_obj.ends_at,
                price_cents=session_obj.price_cents,
                age_min=session_obj.age_min,
                age_max=session_obj.age_max,
                seats_remaining=session_obj.seats_remaining,
                session_type=session_obj.session_type.value,
                drop_off=session_obj.drop_off,
                distance_km=distance_km,
            )
        )
    events_service.record(
        db, event_type="search_performed", props={"results": len(cards)}
    )
    return cards


def this_weekend_sessions(
    db: Session,
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    suburb: str | None = None,
    postcode: str | None = None,
    child_age: int | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> list[SearchCard]:
    """"This weekend" feed (E2): bookable Sat/Sun sessions (Perth local) in the coming
    week, near the caller. Reads the live inventory projection (INV-8)."""
    now = now or datetime.now(UTC)
    horizon = (now + PERTH_OFFSET).date() + timedelta(days=FEED_HORIZON_DAYS)
    return search_sessions(
        db, lat=lat, lng=lng, radius_km=radius_km, suburb=suburb, postcode=postcode,
        child_age=child_age, category=category, date_to=horizon, days_of_week=WEEKEND,
        limit=limit, offset=offset, now=now,
    )


def after_school_this_week_sessions(
    db: Session,
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    suburb: str | None = None,
    postcode: str | None = None,
    child_age: int | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> list[SearchCard]:
    """"After school this week" feed (E2): bookable weekday sessions starting from 3pm
    Perth local, in the coming week, near the caller. Live inventory (INV-8)."""
    now = now or datetime.now(UTC)
    horizon = (now + PERTH_OFFSET).date() + timedelta(days=FEED_HORIZON_DAYS)
    return search_sessions(
        db, lat=lat, lng=lng, radius_km=radius_km, suburb=suburb, postcode=postcode,
        child_age=child_age, category=category, date_to=horizon, days_of_week=WEEKDAYS,
        start_after_local_hour=AFTER_SCHOOL_HOUR, limit=limit, offset=offset, now=now,
    )
