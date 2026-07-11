"""Business logic for the catalog module: venues, programs, sessions.

Cross-module note: catalog sits above org in the dependency layering, so it may
call ``org`` through its service to enforce that the actor is a member of the
organisation. It does not reach into org's models directly.
"""

import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.catalog.core.models import (
    Program,
    ProgramStatus,
    SessionStatus,
    Venue,
)
from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.catalog.core.schemas import SessionCreate, SessionDetailOut
from juggle.modules.events.core import service as events_service
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import OrgStatus


class NotOrgMember(Exception):
    """The actor is not a member of the organisation they're acting on."""


class OrgSuspended(Exception):
    """A suspended organisation cannot publish listings."""


class VenueNotFound(Exception):
    """Referenced venue does not exist or belongs to another organisation."""


class ProgramNotFound(Exception):
    """Referenced program does not exist."""


def _require_member(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if org_service.get_member(db, org_id, actor_id) is None:
        raise NotOrgMember(str(org_id))


def create_venue(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str,
    address: str | None = None,
    suburb: str | None = None,
    postcode: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Venue:
    _require_member(db, organisation_id, actor_id)
    location = None
    if latitude is not None and longitude is not None:
        location = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
    venue = Venue(
        organisation_id=organisation_id,
        name=name,
        address=address,
        suburb=suburb,
        postcode=postcode,
        location=location,
    )
    db.add(venue)
    db.flush()
    return venue


def create_program(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    actor_id: uuid.UUID,
    title: str,
    category: str,
    description: str | None = None,
) -> Program:
    _require_member(db, organisation_id, actor_id)
    program = Program(
        organisation_id=organisation_id,
        title=title,
        category=category,
        description=description,
    )
    db.add(program)
    db.flush()
    return program


def get_program(db: Session, program_id: uuid.UUID) -> Program | None:
    return db.get(Program, program_id)


def get_session(db: Session, session_id: uuid.UUID) -> ProgramSession | None:
    """Raw session lookup (no publish gate) — for provider/admin operations."""
    return db.get(ProgramSession, session_id)


def list_org_venues(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[Venue]:
    """A provider's venues for one org (member-gated)."""
    _require_member(db, organisation_id, actor_id)
    return list(
        db.scalars(
            select(Venue)
            .where(Venue.organisation_id == organisation_id)
            .order_by(Venue.created_at)
        )
    )


def get_owned_program(
    db: Session, *, program_id: uuid.UUID, actor_id: uuid.UUID
) -> Program:
    """A single program the actor may manage (member-gated)."""
    program = db.get(Program, program_id)
    if program is None:
        raise ProgramNotFound(str(program_id))
    _require_member(db, program.organisation_id, actor_id)
    return program


def list_org_programs(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[Program]:
    """A provider's programs for one org (member-gated)."""
    _require_member(db, organisation_id, actor_id)
    return list(
        db.scalars(
            select(Program)
            .where(Program.organisation_id == organisation_id)
            .order_by(Program.created_at)
        )
    )


def set_program_status(
    db: Session, *, program_id: uuid.UUID, actor_id: uuid.UUID, status: ProgramStatus
) -> Program:
    program = db.get(Program, program_id)
    if program is None:
        raise ProgramNotFound(str(program_id))
    _require_member(db, program.organisation_id, actor_id)
    if status is ProgramStatus.published:
        org = org_service.get_organisation(db, program.organisation_id)
        if org is not None and org.status is OrgStatus.suspended:
            raise OrgSuspended(str(program.organisation_id))
    program.status = status
    db.flush()
    if status is ProgramStatus.published:
        events_service.record(
            db, event_type="listing_published", props={"program_id": str(program.id)}
        )
    return program


def create_session(
    db: Session, *, program_id: uuid.UUID, actor_id: uuid.UUID, data: SessionCreate
) -> ProgramSession:
    program = db.get(Program, program_id)
    if program is None:
        raise ProgramNotFound(str(program_id))
    _require_member(db, program.organisation_id, actor_id)

    venue = db.get(Venue, data.venue_id)
    if venue is None or venue.organisation_id != program.organisation_id:
        raise VenueNotFound(str(data.venue_id))

    session = ProgramSession(
        program_id=program_id,
        venue_id=data.venue_id,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        capacity=data.capacity,
        seats_taken=0,
        price_cents=data.price_cents,
        age_min=data.age_min,
        age_max=data.age_max,
        session_type=data.session_type,
        drop_off=data.drop_off,
        what_to_bring=data.what_to_bring,
    )
    db.add(session)
    db.flush()
    return session


def create_sessions_bulk(
    db: Session, *, program_id: uuid.UUID, actor_id: uuid.UUID, items: list[SessionCreate]
) -> list[ProgramSession]:
    """Create many sessions in one transaction (PRD §8.2 bulk creation)."""
    return [create_session(db, program_id=program_id, actor_id=actor_id, data=i) for i in items]


def list_program_sessions(db: Session, program_id: uuid.UUID) -> list[ProgramSession]:
    return list(
        db.scalars(
            select(ProgramSession)
            .where(ProgramSession.program_id == program_id)
            .order_by(ProgramSession.starts_at)
        )
    )


def get_public_session(db: Session, session_id: uuid.UUID) -> ProgramSession | None:
    """A session visible to the public: it must belong to a published program."""
    session = db.get(ProgramSession, session_id)
    if session is None:
        return None
    program = db.get(Program, session.program_id)
    if program is None or program.status is not ProgramStatus.published:
        return None
    if session.status is SessionStatus.cancelled:
        return None
    return session


def published_session_refs(
    db: Session, *, now: datetime | None = None
) -> list[tuple[uuid.UUID, datetime]]:
    """(session_id, last_modified) for every indexable listing — published
    program, not cancelled, still upcoming. Powers the SEO sitemap (§7.1)."""
    if now is None:
        now = datetime.now(UTC)
    rows = db.execute(
        select(ProgramSession.id, ProgramSession.updated_at)
        .join(Program, Program.id == ProgramSession.program_id)
        .where(
            Program.status == ProgramStatus.published,
            ProgramSession.status != SessionStatus.cancelled,
            ProgramSession.starts_at > now,
        )
        .order_by(ProgramSession.starts_at)
    ).all()
    return [(session_id, updated_at) for session_id, updated_at in rows]


def get_public_session_detail(
    db: Session, session_id: uuid.UUID
) -> SessionDetailOut | None:
    """Enriched public listing detail (program + provider + venue context)."""
    session = get_public_session(db, session_id)
    if session is None:
        return None
    program = db.get(Program, session.program_id)
    venue = db.get(Venue, session.venue_id)
    if program is None or venue is None:
        return None
    events_service.record(
        db, event_type="listing_viewed", props={"session_id": str(session.id)}
    )
    org = org_service.get_organisation(db, program.organisation_id)
    return SessionDetailOut(
        id=session.id,
        program_id=session.program_id,
        venue_id=session.venue_id,
        starts_at=session.starts_at,
        ends_at=session.ends_at,
        capacity=session.capacity,
        seats_taken=session.seats_taken,
        seats_remaining=session.seats_remaining,
        price_cents=session.price_cents,
        age_min=session.age_min,
        age_max=session.age_max,
        session_type=session.session_type.value,
        drop_off=session.drop_off,
        status=session.status.value,
        title=program.title,
        category=program.category,
        description=program.description,
        organisation_name=org.name if org is not None else "",
        venue_name=venue.name,
        suburb=venue.suburb,
        postcode=venue.postcode,
    )
