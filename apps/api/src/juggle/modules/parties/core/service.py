"""Parties service (Milestone B1): the instant-book supply side — provider packages
and their capacity-1 slots. No money here; the deposit/balance/adjustment flow (B2–B4)
lands through the ``payments`` module.

Parties sits above payments in the layering, so it composes catalog (venue) and org
(membership) through their services.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.org.core import service as org_service
from juggle.modules.parties.core.models import (
    PartyPackage,
    PartyPackageStatus,
    PartySlot,
    PartySlotStatus,
)
from juggle.modules.parties.core.schemas import PackageCreate, SlotCreate


class NotOrgMember(Exception):
    """Caller is not a member of the organisation."""


class VenueNotFound(Exception):
    """No such venue, or it does not belong to this organisation."""


class PackageNotFound(Exception):
    """No such party package."""


class InvalidHeadcountBand(Exception):
    """max_headcount is below min_headcount."""


def _require_member(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if org_service.get_member(db, org_id, actor_id) is None:
        raise NotOrgMember(str(org_id))


def create_package(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID, data: PackageCreate
) -> PartyPackage:
    _require_member(db, organisation_id, actor_id)
    if data.max_headcount < data.min_headcount:
        raise InvalidHeadcountBand(f"{data.max_headcount} < {data.min_headcount}")
    venue = catalog_service.get_venue(db, data.venue_id)
    if venue is None or venue.organisation_id != organisation_id:
        raise VenueNotFound(str(data.venue_id))
    package = PartyPackage(
        organisation_id=organisation_id,
        venue_id=data.venue_id,
        name=data.name,
        description=data.description,
        per_head_price_cents=data.per_head_price_cents,
        min_headcount=data.min_headcount,
        max_headcount=data.max_headcount,
        deposit_pct=data.deposit_pct,
        outdoor=data.outdoor,
    )
    db.add(package)
    db.flush()
    return package


def get_package(db: Session, package_id: uuid.UUID) -> PartyPackage | None:
    return db.get(PartyPackage, package_id)


def list_org_packages(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[PartyPackage]:
    """All of an org's party packages (member-gated, any status)."""
    _require_member(db, organisation_id, actor_id)
    return list(
        db.scalars(
            select(PartyPackage)
            .where(PartyPackage.organisation_id == organisation_id)
            .order_by(PartyPackage.created_at)
        )
    )


def list_active_packages(db: Session, organisation_id: uuid.UUID) -> list[PartyPackage]:
    """Public: an org's bookable party packages."""
    return list(
        db.scalars(
            select(PartyPackage)
            .where(
                PartyPackage.organisation_id == organisation_id,
                PartyPackage.status == PartyPackageStatus.active,
            )
            .order_by(PartyPackage.created_at)
        )
    )


def archive_package(
    db: Session, *, package_id: uuid.UUID, actor_id: uuid.UUID
) -> PartyPackage:
    package = db.get(PartyPackage, package_id)
    if package is None:
        raise PackageNotFound(str(package_id))
    _require_member(db, package.organisation_id, actor_id)
    package.status = PartyPackageStatus.archived
    db.flush()
    return package


def add_slots(
    db: Session, *, package_id: uuid.UUID, actor_id: uuid.UUID, slots: list[SlotCreate]
) -> list[PartySlot]:
    package = db.get(PartyPackage, package_id)
    if package is None:
        raise PackageNotFound(str(package_id))
    _require_member(db, package.organisation_id, actor_id)
    created: list[PartySlot] = []
    for spec in slots:
        slot = PartySlot(
            package_id=package_id, starts_at=spec.starts_at, ends_at=spec.ends_at
        )
        db.add(slot)
        created.append(slot)
    db.flush()
    return created


def list_slots(
    db: Session, package_id: uuid.UUID, *, available_only: bool = True,
    now: datetime | None = None,
) -> list[PartySlot]:
    """Public: a package's upcoming slots (available ones by default)."""
    moment = now or datetime.now(UTC)
    stmt = (
        select(PartySlot)
        .where(PartySlot.package_id == package_id, PartySlot.starts_at >= moment)
        .order_by(PartySlot.starts_at)
    )
    if available_only:
        stmt = stmt.where(PartySlot.status == PartySlotStatus.available)
    return list(db.scalars(stmt))
