"""Seed the local database with demo marketplace data.

Creates one approved provider with a handful of published programs/sessions
across Perth suburbs and categories, so the frontend shows a populated,
realistic marketplace during development.

Run once:  uv run python scripts/seed_demo.py   (idempotent — skips if present)
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from juggle.db import SessionLocal
from juggle.modules.booking.core import service as booking_service
from juggle.modules.booking.core.schemas import CheckoutChild, CheckoutItem
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.schemas import SessionCreate
from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.schemas import ChildCreate
from juggle.modules.inventory.core import service as inventory_service
from juggle.modules.notifications.core.gateway import get_email_gateway
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import OrgStatus, VerificationStatus
from juggle.modules.payments.core import service as payments_service
from juggle.modules.payments.core.gateway import get_payment_gateway
from juggle.modules.payments.core.models import PayoutStatus
from juggle.modules.reviews.core import service as reviews_service
from juggle.modules.waitlist.core import service as waitlist_service

PROVIDER_EMAIL = "demo-provider@juggle.test"

# (name, suburb, postcode, lat, lng)
VENUES = [
    ("Perth Cultural Centre", "Perth", "6000", -31.9483, 115.8613),
    ("Fremantle Esplanade Hall", "Fremantle", "6160", -32.0569, 115.7439),
    ("Joondalup Community Hub", "Joondalup", "6027", -31.7448, 115.7661),
]

# (title, category, description, price_cents, age_min, age_max, venue_index, day_type)
PROGRAMS = [
    ("Little Picassos Art Camp", "art",
     "A joyful week of painting, clay and collage. All materials supplied.",
     5500, 5, 10, 0, "full_day"),
    ("AllStars Soccer Clinic", "sport",
     "Small-sided games and skills with FFA-qualified coaches.",
     4000, 6, 12, 1, "half_day"),
    ("Junior Robotics Lab", "stem",
     "Build and program LEGO robots to complete fun challenges.",
     6500, 8, 13, 2, "full_day"),
    ("Stage & Spotlight Drama", "drama",
     "Improv, scripts and a mini-performance for families on the last day.",
     4800, 7, 12, 0, "full_day"),
    ("Bushrangers Nature Adventure", "outdoor",
     "Guided bush walks, shelter-building and creek exploring. Parent-stays.",
     3800, 5, 11, 1, "half_day"),
]


def _seed() -> None:
    db = SessionLocal()
    try:
        if _already_seeded(db):
            print("Demo data already present — nothing to do.")
            return

        admin = identity_service.create_guardian(
            db, email="admin@example.com", password="supersecret", full_name="Ops Admin"
        )
        admin.is_admin = True

        provider = identity_service.create_guardian(
            db, email=PROVIDER_EMAIL, password="supersecret", full_name="Demo Provider"
        )
        org = org_service.create_organisation(
            db, name="Sunshine Kids Co", owner_user_id=provider.id
        )
        org_service.set_status(db, org.id, OrgStatus.approved)
        # A fully-verified provider so the §7.2 trust badges show on listings.
        org_service.set_abn(db, org.id, "51824753556")
        wwcc = org_service.add_wwcc(
            db,
            org_id=org.id,
            staff_name="Demo Coach",
            wwcc_number="WWC1234567",
            expiry_date=date(2030, 1, 1),
        )
        org_service.set_wwcc_status(db, wwcc.id, VerificationStatus.verified)
        insurance = org_service.add_insurance(
            db,
            org_id=org.id,
            file_ref="https://example.com/liability-cert.pdf",
            expiry_date=date(2030, 1, 1),
        )
        org_service.set_insurance_status(db, insurance.id, VerificationStatus.verified)

        venues = [
            catalog_service.create_venue(
                db,
                organisation_id=org.id,
                actor_id=provider.id,
                name=name,
                suburb=suburb,
                postcode=postcode,
                latitude=lat,
                longitude=lng,
            )
            for (name, suburb, postcode, lat, lng) in VENUES
        ]

        # 9:00am Perth (AWST, UTC+8) == 01:00 UTC. Stored in UTC; the frontend
        # renders in the viewer's local time.
        base = datetime(2026, 9, 29, 1, 0, tzinfo=UTC)  # WA spring holidays
        session_count = 0
        for i, (title, category, desc, price, amin, amax, vidx, dtype) in enumerate(PROGRAMS):
            program = catalog_service.create_program(
                db,
                organisation_id=org.id,
                actor_id=provider.id,
                title=title,
                category=category,
                description=desc,
            )
            hours = 3 if dtype == "half_day" else 6
            for day in range(3):  # three days each
                start = base + timedelta(days=i + day)
                catalog_service.create_session(
                    db,
                    program_id=program.id,
                    actor_id=provider.id,
                    data=SessionCreate(
                        venue_id=venues[vidx].id,
                        starts_at=start,
                        ends_at=start + timedelta(hours=hours),
                        capacity=12,
                        price_cents=price,
                        age_min=amin,
                        age_max=amax,
                        session_type=dtype,  # type: ignore[arg-type]
                        drop_off=category != "outdoor",
                    ),
                )
                session_count += 1
            catalog_service.set_program_status(
                db,
                program_id=program.id,
                actor_id=provider.id,
                status=catalog_service.ProgramStatus.published,
            )

        review_count = _seed_reviews(
            db, org_id=org.id, provider_id=provider.id, admin_id=admin.id, venue_id=venues[0].id
        )
        _seed_waitlist(db, org_id=org.id, provider_id=provider.id, venue_id=venues[1].id)

        db.commit()
        print(
            f"Seeded {len(PROGRAMS)} programs / {session_count} sessions "
            f"+ {review_count} published reviews + a sold-out session with a waitlist "
            f"for '{org.name}'."
        )
    finally:
        db.close()


# (guardian first name, child first name, rating, body, provider_reply | None)
DEMO_REVIEWS = [
    ("Amara", "Mika", 5,
     "Absolutely brilliant week — the coaches were warm and my kid came home buzzing "
     "every day. Booking took two minutes.",
     "Thank you Amara! We loved having them — see you next holidays."),
    ("Ben", "Theo", 4,
     "Really well organised and great value. Drop-off was smooth. Would have loved a "
     "little more shade at pickup, but a small thing.",
     None),
    ("Priya", "Anaya", 5,
     "The best holiday program we've tried in Perth. Communication was clear and the "
     "kids were genuinely engaged the whole time.",
     None),
]


def _seed_reviews(
    db: Session,
    *,
    org_id: uuid.UUID,
    provider_id: uuid.UUID,
    admin_id: uuid.UUID,
    venue_id: uuid.UUID,
) -> int:
    """A completed 'last holidays' program with confirmed bookings + published
    reviews, so the reviews UI (PRD §7.6) is populated on first run."""
    payment_gateway = get_payment_gateway()
    email_gateway = get_email_gateway()

    program = catalog_service.create_program(
        db,
        organisation_id=org_id,
        actor_id=provider_id,
        title="Autumn Explorers Art Camp",
        category="art",
        description="Our last-holidays art camp — messy, joyful and much loved.",
    )
    # A session that has already finished, so its bookings are reviewable.
    start = datetime.now(UTC) - timedelta(days=30)
    session = catalog_service.create_session(
        db,
        program_id=program.id,
        actor_id=provider_id,
        data=SessionCreate(
            venue_id=venue_id,
            starts_at=start,
            ends_at=start + timedelta(hours=6),
            capacity=20,
            price_cents=5500,
            age_min=5,
            age_max=12,
            session_type="full_day",
            drop_off=True,
        ),
    )
    catalog_service.set_program_status(
        db,
        program_id=program.id,
        actor_id=provider_id,
        status=catalog_service.ProgramStatus.published,
    )

    count = 0
    for i, (guardian_name, child_name, rating, body, reply) in enumerate(DEMO_REVIEWS):
        guardian = identity_service.create_guardian(
            db,
            email=f"parent{i + 1}@example.com",
            password="supersecret",
            full_name=f"{guardian_name} Demo",
        )
        child = identity_service.add_child(
            db,
            guardian_id=guardian.id,
            data=ChildCreate(first_name=child_name, date_of_birth=date(2016, 6, 1)),
        )
        hold, _ = inventory_service.hold_seats(
            db, session_id=session.id, held_by_id=guardian.id, quantity=1
        )
        order = booking_service.checkout(
            db,
            guardian_id=guardian.id,
            idempotency_key=f"seed-{uuid.uuid4().hex}",
            items=[CheckoutItem(hold_id=hold.id, children=[CheckoutChild(child_id=child.id)])],
            gateway=payment_gateway,
        )
        booking_service.confirm(
            db,
            payment_id=order.payment_id,
            guardian_id=guardian.id,
            gateway=payment_gateway,
            email_gateway=email_gateway,
        )
        review = reviews_service.submit_review(
            db,
            booking_id=order.bookings[0].id,
            author_id=guardian.id,
            rating=rating,
            body=body,
        )
        reviews_service.moderate(
            db, review_id=review.id, moderator_id=admin_id, approve=True
        )
        if reply is not None:
            reviews_service.provider_reply(
                db, review_id=review.id, actor_id=provider_id, reply=reply
            )
        count += 1

    # This is a completed last-cycle program, so its payouts are already settled.
    # Marking them paid also keeps these seeded rows out of the global
    # "run due payouts" admin operation exercised by the payout tests.
    for payout in payments_service.list_org_payouts(
        db, organisation_id=org_id, actor_id=provider_id
    ):
        if payout.status is PayoutStatus.scheduled:
            payments_service.set_payout_status(db, payout.id, PayoutStatus.paid)

    return count


def _seed_waitlist(
    db: Session, *, org_id: uuid.UUID, provider_id: uuid.UUID, venue_id: uuid.UUID
) -> None:
    """A high-demand, single-seat future session — sold out, with one family
    waiting — so the waitlist UI (PRD §7.7) has something to show on first run."""
    payment_gateway = get_payment_gateway()
    email_gateway = get_email_gateway()

    program = catalog_service.create_program(
        db,
        organisation_id=org_id,
        actor_id=provider_id,
        title="Sold-Out Slime Lab",
        category="stem",
        description="Our most popular one — a single small-group session that fills fast.",
    )
    start = datetime.now(UTC) + timedelta(days=20)
    session = catalog_service.create_session(
        db,
        program_id=program.id,
        actor_id=provider_id,
        data=SessionCreate(
            venue_id=venue_id,
            starts_at=start,
            ends_at=start + timedelta(hours=3),
            capacity=1,
            price_cents=4500,
            age_min=5,
            age_max=12,
            session_type="half_day",
            drop_off=True,
        ),
    )
    catalog_service.set_program_status(
        db,
        program_id=program.id,
        actor_id=provider_id,
        status=catalog_service.ProgramStatus.published,
    )

    # One family takes the only seat (→ sold out).
    holder = identity_service.create_guardian(
        db, email="parent-booked@example.com", password="supersecret", full_name="Sam Demo"
    )
    child = identity_service.add_child(
        db,
        guardian_id=holder.id,
        data=ChildCreate(first_name="Frankie", date_of_birth=date(2016, 6, 1)),
    )
    hold, _ = inventory_service.hold_seats(
        db, session_id=session.id, held_by_id=holder.id, quantity=1
    )
    order = booking_service.checkout(
        db,
        guardian_id=holder.id,
        idempotency_key=f"seed-wl-{uuid.uuid4().hex}",
        items=[CheckoutItem(hold_id=hold.id, children=[CheckoutChild(child_id=child.id)])],
        gateway=payment_gateway,
    )
    booking_service.confirm(
        db,
        payment_id=order.payment_id,
        guardian_id=holder.id,
        gateway=payment_gateway,
        email_gateway=email_gateway,
    )
    # Settle the accrued payout so this demo row stays out of the global
    # "scheduled payouts" assertions in the payout tests (see _seed_reviews).
    for payout in payments_service.list_org_payouts(
        db, organisation_id=org_id, actor_id=provider_id
    ):
        if payout.status is PayoutStatus.scheduled:
            payments_service.set_payout_status(db, payout.id, PayoutStatus.paid)

    # Another family joins the waitlist for the now sold-out session.
    waiter = identity_service.create_guardian(
        db, email="parent-waiting@example.com", password="supersecret", full_name="Alex Demo"
    )
    identity_service.add_child(
        db,
        guardian_id=waiter.id,
        data=ChildCreate(first_name="Charlie", date_of_birth=date(2017, 3, 1)),
    )
    waitlist_service.join_waitlist(db, session_id=session.id, guardian_id=waiter.id)


def _already_seeded(db: object) -> bool:
    from sqlalchemy import select

    from juggle.modules.identity.core.models import UserAccount

    return (
        db.scalar(select(UserAccount).where(UserAccount.email == PROVIDER_EMAIL))  # type: ignore[attr-defined]
        is not None
    )


if __name__ == "__main__":
    _seed()
