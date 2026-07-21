"""Seed PRODUCTION with catalog-only demo data (safe for a live environment).

Unlike scripts/seed_demo.py (which is for local dev and also creates a trivial
admin, flips the party_planner flag, and injects fake families/bookings/reviews),
this script creates ONLY supply-side catalog data so the marketplace, search and
AI planner have something to show:

  - one approved, fully-verified provider org ("Sunshine Kids Co")
  - three Perth venues
  - five published programs, each with several near-future sessions
  - three bookable birthday-party packages with upcoming weekend slots

It does NOT create any admin, does NOT change feature flags, and does NOT create
any guardians/children/bookings/reviews. All data is synthetic (INV-9). The
provider login uses a random password (printed once) — it is a supply account,
not an admin. Idempotent: re-running is a no-op once the provider org exists.

Run inside the api container:
    docker compose -f docker-compose.prod.yml exec -T api python - < seed_prod_catalog.py
"""

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from juggle.db import SessionLocal
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.schemas import SessionCreate
from juggle.modules.identity.core import service as identity_service
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import OrgStatus, VerificationStatus
from juggle.modules.parties.core import service as parties_service
from juggle.modules.parties.core.schemas import PackageCreate, SlotCreate

PROVIDER_EMAIL = "demo-provider@kidspots.store"
ORG_NAME = "Sunshine Kids Co"

# (name, suburb, postcode, lat, lng)
VENUES = [
    ("Perth Cultural Centre", "Perth", "6000", -31.9483, 115.8613),
    ("Fremantle Esplanade Hall", "Fremantle", "6160", -32.0569, 115.7439),
    ("Joondalup Community Hub", "Joondalup", "6027", -31.7448, 115.7661),
]

# (title, category, description, price_cents, age_min, age_max, venue_index, day_type)
PROGRAMS = [
    ("Little Picassos Art Camp", "art",
     "A joyful day of painting, clay and collage. All materials supplied.",
     5500, 5, 10, 0, "full_day"),
    ("AllStars Soccer Clinic", "sport",
     "Small-sided games and skills with qualified coaches.",
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

# (name, description, per_head_price_cents, min, max, venue_index, outdoor, deposit_pct|None)
PARTIES = [
    ("Superhero Art Party",
     "Two hours of superhero mask-making, cape decorating and a group mural.",
     3500, 8, 20, 0, False, None),
    ("Backyard Games Party",
     "Sack races, parachute games and a mini soccer tournament run by our coaches.",
     3000, 10, 24, 1, True, 40),
    ("Junior Science Lab Party",
     "Slime, volcanoes and safe hands-on experiments — a lab coat to take home.",
     4200, 8, 16, 2, False, None),
]


def _already_seeded(db: object) -> bool:
    from sqlalchemy import select

    from juggle.modules.identity.core.models import UserAccount

    return (
        db.scalar(select(UserAccount).where(UserAccount.email == PROVIDER_EMAIL))  # type: ignore[attr-defined]
        is not None
    )


def main() -> None:
    db = SessionLocal()
    try:
        if _already_seeded(db):
            print("Catalog demo data already present — nothing to do.")
            return

        provider_pw = secrets.token_urlsafe(18)
        provider = identity_service.create_guardian(
            db, email=PROVIDER_EMAIL, password=provider_pw, full_name="Sunshine Kids Co (demo)"
        )
        org = org_service.create_organisation(db, name=ORG_NAME, owner_user_id=provider.id)
        org_service.set_status(db, org.id, OrgStatus.approved)
        org_service.set_abn(db, org.id, "51824753556")
        wwcc = org_service.add_wwcc(
            db, org_id=org.id, staff_name="Demo Coach",
            wwcc_number="WWC1234567", expiry_date=date(2030, 1, 1),
        )
        org_service.set_wwcc_status(db, wwcc.id, VerificationStatus.verified)
        insurance = org_service.add_insurance(
            db, org_id=org.id,
            file_ref="https://example.com/liability-cert.pdf", expiry_date=date(2030, 1, 1),
        )
        org_service.set_insurance_status(db, insurance.id, VerificationStatus.verified)

        venues = [
            catalog_service.create_venue(
                db, organisation_id=org.id, actor_id=provider.id,
                name=name, suburb=suburb, postcode=postcode, latitude=lat, longitude=lng,
            )
            for (name, suburb, postcode, lat, lng) in VENUES
        ]

        # 9:00am Perth (AWST, UTC+8) == 01:00 UTC, on upcoming days.
        base = datetime.now(UTC).replace(hour=1, minute=0, second=0, microsecond=0)
        # Spread each program's sessions across the next ~3 weeks (varied days).
        day_offsets = [2, 6, 11, 17]
        session_count = 0
        for i, (title, cat, desc, price, amin, amax, vidx, dtype) in enumerate(PROGRAMS):
            program = catalog_service.create_program(
                db, organisation_id=org.id, actor_id=provider.id,
                title=title, category=cat, description=desc,
            )
            hours = 3 if dtype == "half_day" else 6
            for k in day_offsets:
                start = base + timedelta(days=i + k)
                catalog_service.create_session(
                    db, program_id=program.id, actor_id=provider.id,
                    data=SessionCreate(
                        venue_id=venues[vidx].id,
                        starts_at=start, ends_at=start + timedelta(hours=hours),
                        capacity=12, price_cents=price, age_min=amin, age_max=amax,
                        session_type=dtype,  # type: ignore[arg-type]
                        drop_off=cat != "outdoor",
                    ),
                )
                session_count += 1
            catalog_service.set_program_status(
                db, program_id=program.id, actor_id=provider.id,
                status=catalog_service.ProgramStatus.published,
            )

        # Birthday-party packages (PRD §9) with upcoming weekend afternoon slots.
        party_base = datetime.now(UTC).replace(hour=2, minute=0, second=0, microsecond=0) + timedelta(days=9)
        for name, desc, price, cmin, cmax, vidx, outdoor, deposit in PARTIES:
            package = parties_service.create_package(
                db, organisation_id=org.id, actor_id=provider.id,
                data=PackageCreate(
                    venue_id=venues[vidx].id, name=name, description=desc,
                    per_head_price_cents=price, min_headcount=cmin, max_headcount=cmax,
                    deposit_pct=deposit, outdoor=outdoor,
                ),
            )
            parties_service.add_slots(
                db, package_id=package.id, actor_id=provider.id,
                slots=[
                    SlotCreate(
                        starts_at=party_base + timedelta(days=7 * w),
                        ends_at=party_base + timedelta(days=7 * w, hours=2),
                    )
                    for w in range(3)
                ],
            )

        db.commit()
        print(
            f"Seeded '{org.name}': {len(PROGRAMS)} programs / {session_count} sessions "
            f"+ {len(PARTIES)} party packages. Provider login {PROVIDER_EMAIL} "
            f"(password printed once): {provider_pw}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
