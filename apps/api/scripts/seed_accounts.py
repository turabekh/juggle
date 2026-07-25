"""Seed three working accounts: an admin, a parent, and a provider.

Safe to run against production. Idempotent — re-running finds the existing
accounts and only resets their password (and re-asserts admin / org ownership),
so it can be used to rotate a forgotten test password without creating clutter.

**Passwords are never stored in this file.** They come from the environment, so
nothing secret lands in the repo (INV-9):

    SEED_ADMIN_PASSWORD=... SEED_PARENT_PASSWORD=... SEED_PROVIDER_PASSWORD=... \
        uv run python scripts/seed_accounts.py

Optional overrides: SEED_ADMIN_EMAIL, SEED_PARENT_EMAIL, SEED_PROVIDER_EMAIL,
SEED_PROVIDER_ORG.

The provider account gets an organisation, and that organisation is **approved**
so the account is actually usable for listing. An approved org with nothing
published is invisible to families, so this does not put anything in front of
real users.

Creates no children, no bookings, no payments, and changes no feature flags. All
data is synthetic (INV-9).
"""

import os
import sys

from sqlalchemy import select

from juggle.db import SessionLocal
from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.models import UserAccount, UserStatus
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import Organisation, OrgRole, OrgStatus
from juggle.security import hash_password

ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@kidspots.store")
PARENT_EMAIL = os.environ.get("SEED_PARENT_EMAIL", "parent@kidspots.store")
PROVIDER_EMAIL = os.environ.get("SEED_PROVIDER_EMAIL", "provider@kidspots.store")
PROVIDER_ORG = os.environ.get("SEED_PROVIDER_ORG", "Test Provider Co")


def _require(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        sys.exit(f"{var} is required (never hardcode passwords in the repo).")
    if len(value) < 12:
        sys.exit(f"{var} is too short — use at least 12 characters.")
    return value


def _upsert(db, *, email: str, password: str, full_name: str) -> tuple[UserAccount, str]:
    """Create the account, or reset the password on an existing one."""
    user = db.scalar(select(UserAccount).where(UserAccount.email == email))
    if user is None:
        user = identity_service.create_guardian(
            db, email=email, password=password, full_name=full_name
        )
        return user, "created"
    user.password_hash = hash_password(password)
    # A seeded account should always be usable, even if it was suspended earlier.
    if user.status is UserStatus.suspended:
        user.status = UserStatus.active
    db.flush()
    return user, "password reset"


def main() -> None:
    admin_pw = _require("SEED_ADMIN_PASSWORD")
    parent_pw = _require("SEED_PARENT_PASSWORD")
    provider_pw = _require("SEED_PROVIDER_PASSWORD")

    db = SessionLocal()
    try:
        admin, admin_note = _upsert(
            db, email=ADMIN_EMAIL, password=admin_pw, full_name="Juggle Admin"
        )
        admin.is_admin = True
        db.flush()
        print(f"admin     {ADMIN_EMAIL:32} {admin_note}, is_admin=True")

        _parent, parent_note = _upsert(
            db, email=PARENT_EMAIL, password=parent_pw, full_name="Test Parent"
        )
        print(f"parent    {PARENT_EMAIL:32} {parent_note}")

        provider, provider_note = _upsert(
            db, email=PROVIDER_EMAIL, password=provider_pw, full_name="Test Provider"
        )
        org = db.scalar(select(Organisation).where(Organisation.name == PROVIDER_ORG))
        if org is None:
            org = org_service.create_organisation(
                db, name=PROVIDER_ORG, owner_user_id=provider.id
            )
            org_note = "org created"
        else:
            if org_service.get_member(db, org.id, provider.id) is None:
                org_service.add_member(
                    db, org_id=org.id, user_account_id=provider.id, role=OrgRole.owner
                )
            org_note = "org exists"
        org_service.set_status(db, org.id, OrgStatus.approved)
        db.commit()
        print(f"provider  {PROVIDER_EMAIL:32} {provider_note}, {org_note} "
              f"'{PROVIDER_ORG}' (approved, owner)")
        print("\nDone. Passwords were supplied via the environment and are not stored here.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
