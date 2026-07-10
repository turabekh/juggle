"""Schema-level tests: the tables exist and the capacity invariant is enforced
by the database, not merely by application code (PRD §12)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.catalog.core.models import Program, Venue
from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.org.core.models import Organisation

EXPECTED_TABLES = {
    "user_account", "child", "organisation", "org_member", "wwcc_record",
    "insurance_doc", "venue", "program", "session", "seat_hold", "booking",
    "booking_child", "payment", "payout", "impersonation_session",
    "platform_setting", "feature_flag", "audit_event",
}


def test_all_tables_present(engine) -> None:
    tables = set(inspect(engine).get_table_names(schema="public"))
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"


def _make_session(db: Session, *, capacity: int, seats_taken: int = 0) -> ProgramSession:
    org = Organisation(name="Acme Kids", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    venue = Venue(organisation_id=org.id, name="Main Hall")
    program = Program(organisation_id=org.id, title="Art Camp", category="art")
    db.add_all([venue, program])
    db.flush()
    start = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
    session = ProgramSession(
        program_id=program.id,
        venue_id=venue.id,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        capacity=capacity,
        seats_taken=seats_taken,
        price_cents=5500,
        age_min=5,
        age_max=12,
    )
    db.add(session)
    db.flush()
    return session


def test_session_can_fill_to_capacity(db: Session) -> None:
    session = _make_session(db, capacity=10)
    session.seats_taken = 10  # exactly full is allowed
    db.flush()
    assert session.seats_taken == 10


def test_oversell_is_rejected_by_constraint(db: Session) -> None:
    session = _make_session(db, capacity=10)
    session.seats_taken = 11  # one over capacity
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert "ck_session_no_oversell" in str(exc.value)


def test_negative_seats_rejected(db: Session) -> None:
    session = _make_session(db, capacity=10)
    session.seats_taken = -1
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert "ck_session_seats_taken_nonneg" in str(exc.value)


def test_inverted_age_range_rejected(db: Session) -> None:
    with pytest.raises(IntegrityError) as exc:
        session = _make_session(db, capacity=10)
        session.age_min = 15
        session.age_max = 8
        db.flush()
    assert "ck_session_age_range" in str(exc.value)
