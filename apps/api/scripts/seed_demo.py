"""Seed the local database with demo marketplace data.

Creates one approved provider with a handful of published programs/sessions
across Perth suburbs and categories, so the frontend shows a populated,
realistic marketplace during development.

Run once:  uv run python scripts/seed_demo.py   (idempotent — skips if present)
"""

from datetime import UTC, datetime, timedelta

from juggle.db import SessionLocal
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.schemas import SessionCreate
from juggle.modules.identity.core import service as identity_service
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import OrgStatus

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

        db.commit()
        print(f"Seeded {len(PROGRAMS)} programs / {session_count} sessions for '{org.name}'.")
    finally:
        db.close()


def _already_seeded(db: object) -> bool:
    from sqlalchemy import select

    from juggle.modules.identity.core.models import UserAccount

    return (
        db.scalar(select(UserAccount).where(UserAccount.email == PROVIDER_EMAIL))  # type: ignore[attr-defined]
        is not None
    )


if __name__ == "__main__":
    _seed()
