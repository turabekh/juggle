"""Roster service: the live attendee list for a session (PRD §8.3).

Roster is a read-only, provider-facing view at the top of the layering. It
authorises via ``org`` (the caller must be a member of the session's org) and
then reads across booking + identity to assemble the list. Because it surfaces
child PII, every entry point is gated on org membership.
"""

import csv
import io
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.booking.core.models import Booking, BookingChild, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.identity.core.models import Child
from juggle.modules.org.core import service as org_service
from juggle.modules.roster.core.schemas import RosterOut, RosterRow


class SessionNotFound(Exception):
    """No such session."""


class NotOrgMember(Exception):
    """Caller is not a member of the organisation running this session."""


def _age_at(dob: date, at: datetime) -> int:
    on = at.date()
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def get_roster(db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID) -> RosterOut:
    session = catalog_service.get_session(db, session_id)
    if session is None:
        raise SessionNotFound(str(session_id))
    program = catalog_service.get_program(db, session.program_id)
    if program is None:
        raise SessionNotFound(str(session_id))
    if org_service.get_member(db, program.organisation_id, actor_id) is None:
        raise NotOrgMember(str(program.organisation_id))

    rows_stmt = (
        select(Booking.id, Child, BookingChild.form_answers)
        .join(BookingChild, BookingChild.booking_id == Booking.id)
        .join(Child, Child.id == BookingChild.child_id)
        .where(
            Booking.session_id == session_id,
            Booking.status == BookingStatus.confirmed,
        )
        .order_by(Child.first_name)
    )

    rows: list[RosterRow] = []
    for booking_id, child, form_answers in db.execute(rows_stmt):
        rows.append(
            RosterRow(
                booking_id=booking_id,
                child_first_name=child.first_name,
                age=_age_at(child.date_of_birth, session.starts_at),
                medical_notes=child.medical_notes,
                emergency_contact_name=child.emergency_contact_name,
                emergency_contact_phone=child.emergency_contact_phone,
                form_answers=form_answers,
            )
        )
    return RosterOut(session_id=session_id, count=len(rows), rows=rows)


_CSV_HEADER = [
    "child_first_name",
    "age",
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
                row.medical_notes or "",
                row.emergency_contact_name or "",
                row.emergency_contact_phone or "",
                _format_form_answers(row.form_answers),
            ]
        )
    return buffer.getvalue()


def _format_form_answers(answers: dict[str, object]) -> str:
    return "; ".join(f"{k}={v}" for k, v in sorted(answers.items()))
