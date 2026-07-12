"""HTTP routes for the parties module (Milestone B1): provider package/slot management
and public reads. Booking + money (deposit/balance/adjustment) land in B2–B4."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.parties.core import schemas, service
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway

router = APIRouter(prefix="/parties", tags=["parties"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]


@router.post(
    "/orgs/{organisation_id}/packages",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PackageOut,
)
def create_package(
    organisation_id: uuid.UUID,
    body: schemas.PackageCreate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> schemas.PackageOut:
    try:
        package = service.create_package(
            session, organisation_id=organisation_id, actor_id=principal.user_id, data=body
        )
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    except service.InvalidHeadcountBand as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "max_headcount must be ≥ min_headcount"
        ) from exc
    except service.VenueNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Venue not found for this organisation"
        ) from exc
    return schemas.PackageOut.model_validate(package)


@router.get(
    "/orgs/{organisation_id}/packages/manage", response_model=list[schemas.PackageOut]
)
def list_org_packages(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.PackageOut]:
    """Provider view — all packages (member-gated)."""
    try:
        packages = service.list_org_packages(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return [schemas.PackageOut.model_validate(p) for p in packages]


@router.get("/orgs/{organisation_id}/packages", response_model=list[schemas.PackageOut])
def list_active_packages(
    organisation_id: uuid.UUID, session: SessionDep
) -> list[schemas.PackageOut]:
    """Public — bookable packages for an org."""
    return [
        schemas.PackageOut.model_validate(p)
        for p in service.list_active_packages(session, organisation_id)
    ]


@router.post("/packages/{package_id}/archive", response_model=schemas.PackageOut)
def archive_package(
    package_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PackageOut:
    try:
        package = service.archive_package(
            session, package_id=package_id, actor_id=principal.user_id
        )
    except service.PackageNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return schemas.PackageOut.model_validate(package)


@router.post(
    "/packages/{package_id}/slots",
    status_code=status.HTTP_201_CREATED,
    response_model=list[schemas.SlotOut],
)
def add_slots(
    package_id: uuid.UUID,
    body: schemas.SlotsCreate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> list[schemas.SlotOut]:
    try:
        slots = service.add_slots(
            session, package_id=package_id, actor_id=principal.user_id, slots=body.slots
        )
    except service.PackageNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return [schemas.SlotOut.model_validate(s) for s in slots]


@router.get("/packages/{package_id}/slots", response_model=list[schemas.SlotOut])
def list_slots(package_id: uuid.UUID, session: SessionDep) -> list[schemas.SlotOut]:
    """Public — a package's upcoming available slots."""
    return [
        schemas.SlotOut.model_validate(s) for s in service.list_slots(session, package_id)
    ]


@router.post(
    "/slots/{slot_id}/book",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PartyBookingOut,
)
def book_slot(
    slot_id: uuid.UUID,
    body: schemas.BookSlotIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.PartyBookingOut:
    """Reserve a party slot and start the deposit (ADR-0007). Returns the deposit
    client_secret for the Payment Element; the booking confirms via the Stripe webhook."""
    try:
        booking, intent = service.book_slot(
            session, slot_id=slot_id, guardian_id=principal.user_id,
            headcount=body.headcount, gateway=gateway,
        )
    except service.SlotNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found") from exc
    except service.SlotUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "That slot is no longer available") from exc
    except service.HeadcountOutOfBand as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Headcount is outside the package's min/max"
        ) from exc
    return schemas.PartyBookingOut(
        id=booking.id,
        slot_id=booking.slot_id,
        package_id=booking.package_id,
        headcount=booking.headcount,
        total_cents=booking.total_cents,
        deposit_cents=booking.deposit_cents,
        balance_cents=booking.balance_cents,
        status=booking.status.value,
        client_secret=intent.client_secret,
    )
