"""Roster service: the live attendee list for a session + check-in (PRD §8.3).

Provider-facing, at the top of the layering. It authorises via ``org`` (the
caller must be a member of the session's org) and reads across booking + identity
to assemble the list. Because it surfaces child PII, every entry point is gated on
org membership. ``Attendance`` is the one piece of state roster owns — the
morning-of check-in mark for each child on the session.
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.booking.core.models import Booking, BookingChild, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.identity.core.models import Child
from juggle.modules.org.core import service as org_service
from juggle.modules.roster.core.models import Attendance
from juggle.modules.roster.core.schemas import (
    AttendanceOut,
    RosterOut,
    RosterRow,
)


class SessionNotFound(Exception):
    """No such session."""


class NotOrgMember(Exception):
    """Caller is not a member of the organisation running this session."""


class NotOnRoster(Exception):
    """No confirmed booking-child with that id on this session."""


def _age_at(dob: date, at: datetime) -> int:
    on = at.date()
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _require_org_session(
    db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID
) -> ProgramSession:
    session = catalog_service.get_session(db, session_id)
    if session is None:
        raise SessionNotFound(str(session_id))
    program = catalog_service.get_program(db, session.program_id)
    if program is None:
        raise SessionNotFound(str(session_id))
    if org_service.get_member(db, program.organisation_id, actor_id) is None:
        raise NotOrgMember(str(program.organisation_id))
    return session


def get_roster(db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID) -> RosterOut:
    session = _require_org_session(db, session_id=session_id, actor_id=actor_id)

    rows_stmt = (
        select(
            Booking.id,
            BookingChild.id,
            Child,
            BookingChild.form_answers,
            Attendance.attended_at,
        )
        .join(BookingChild, BookingChild.booking_id == Booking.id)
        .join(Child, Child.id == BookingChild.child_id)
        .outerjoin(Attendance, Attendance.booking_child_id == BookingChild.id)
        .where(
            Booking.session_id == session_id,
            Booking.status == BookingStatus.confirmed,
        )
        .order_by(Child.first_name)
    )

    rows: list[RosterRow] = []
    attended_count = 0
    for booking_id, booking_child_id, child, form_answers, attended_at in db.execute(rows_stmt):
        if attended_at is not None:
            attended_count += 1
        rows.append(
            RosterRow(
                booking_id=booking_id,
                booking_child_id=booking_child_id,
                child_first_name=child.first_name,
                age=_age_at(child.date_of_birth, session.starts_at),
                medical_notes=child.medical_notes,
                emergency_contact_name=child.emergency_contact_name,
                emergency_contact_phone=child.emergency_contact_phone,
                form_answers=form_answers,
                attended=attended_at is not None,
                attended_at=attended_at,
            )
        )
    return RosterOut(
        session_id=session_id, count=len(rows), attended_count=attended_count, rows=rows
    )


def mark_attendance(
    db: Session,
    *,
    session_id: uuid.UUID,
    booking_child_id: uuid.UUID,
    actor_id: uuid.UUID,
    attended: bool,
) -> AttendanceOut:
    """Check a child in (or undo it) on the morning-of roster (PRD §8.3)."""
    _require_org_session(db, session_id=session_id, actor_id=actor_id)

    on_roster = db.scalar(
        select(BookingChild.id)
        .join(Booking, Booking.id == BookingChild.booking_id)
        .where(
            BookingChild.id == booking_child_id,
            Booking.session_id == session_id,
            Booking.status == BookingStatus.confirmed,
        )
    )
    if on_roster is None:
        raise NotOnRoster(str(booking_child_id))

    record = db.scalar(
        select(Attendance).where(Attendance.booking_child_id == booking_child_id)
    )
    if record is None:
        record = Attendance(session_id=session_id, booking_child_id=booking_child_id)
        db.add(record)
    record.attended_at = datetime.now(UTC) if attended else None
    record.marked_by_id = actor_id
    db.flush()

    audit_service.record(
        db,
        action="roster.attendance_marked",
        actor_id=actor_id,
        entity_type="attendance",
        entity_id=str(record.id),
        detail={"session_id": str(session_id), "attended": attended},
    )
    return AttendanceOut(
        booking_child_id=booking_child_id,
        attended=record.attended_at is not None,
        attended_at=record.attended_at,
    )


_CSV_HEADER = [
    "child_first_name",
    "age",
    "attended",
    "medical_notes",
    "emergency_contact_name",
    "emergency_contact_phone",
    "form_answers",
]


def roster_csv(db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID) -> str:
    roster = get_roster(db, session_id=session_id, actor_id=actor_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_HEADER)
    for row in roster.rows:
        writer.writerow(
            [
                row.child_first_name,
                row.age,
                "yes" if row.attended else "no",
                row.medical_notes or "",
                row.emergency_contact_name or "",
                row.emergency_contact_phone or "",
                _format_form_answers(row.form_answers),
            ]
        )
    return buffer.getvalue()


def _format_form_answers(answers: dict[str, object]) -> str:
    return "; ".join(f"{k}={v}" for k, v in sorted(answers.items()))
