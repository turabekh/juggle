"""HTTP routes for the parties module (Milestone B1): provider package/slot management
and public reads. Booking + money (deposit/balance/adjustment) land in B2–B4."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.notifications.core.gateway import EmailGateway, get_email_gateway
from juggle.modules.org.core import service as org_service
from juggle.modules.parties.core import schemas, service
from juggle.modules.parties.core.models import PartyBooking
from juggle.modules.payments.core.gateway import (
    PaymentGateway,
    StripeGateway,
    get_payment_gateway,
)

router = APIRouter(prefix="/parties", tags=["parties"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]
EmailGatewayDep = Annotated[EmailGateway, Depends(get_email_gateway)]


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


@router.get("/packages/{package_id}", response_model=schemas.PackageDetailOut)
def get_package(package_id: uuid.UUID, session: SessionDep) -> schemas.PackageDetailOut:
    """Public — a single bookable package with provider + venue names for the booking page."""
    package = service.get_package(session, package_id)
    if package is None or package.status.value != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    org = org_service.get_organisation(session, package.organisation_id)
    venue = catalog_service.get_venue(session, package.venue_id)
    return schemas.PackageDetailOut(
        id=package.id,
        organisation_id=package.organisation_id,
        venue_id=package.venue_id,
        name=package.name,
        description=package.description,
        per_head_price_cents=package.per_head_price_cents,
        min_headcount=package.min_headcount,
        max_headcount=package.max_headcount,
        deposit_pct=package.deposit_pct,
        outdoor=package.outdoor,
        status=package.status.value,
        organisation_name=org.name if org else "",
        venue_name=venue.name if venue else "",
        venue_suburb=venue.suburb if venue else None,
        deposit_pct_effective=service.effective_deposit_pct(session, package),
    )


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
    return _booking_out(booking, client_secret=intent.client_secret)


def _booking_out(
    booking: PartyBooking, *, client_secret: str | None = None
) -> schemas.PartyBookingOut:
    return schemas.PartyBookingOut(
        id=booking.id,
        slot_id=booking.slot_id,
        package_id=booking.package_id,
        headcount=booking.headcount,
        total_cents=booking.total_cents,
        deposit_cents=booking.deposit_cents,
        balance_cents=booking.balance_cents,
        status=booking.status.value,
        client_secret=client_secret,
    )


@router.post("/bookings/{booking_id}/dev-confirm", response_model=schemas.PartyBookingOut)
def dev_confirm_deposit(
    booking_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.PartyBookingOut:
    """Dev/FakeGateway only: confirm the deposit synchronously (live Stripe uses the webhook)."""
    if isinstance(gateway, StripeGateway):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Deposit confirmation is webhook-driven for live payments"
        )
    try:
        booking = service.dev_confirm_deposit(
            session, booking_id=booking_id, actor_id=principal.user_id, gateway=gateway,
        )
    except service.PartyBookingNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found") from exc
    except service.NotBookingParty as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking") from exc
    return _booking_out(booking)


@router.post("/bookings/{booking_id}/adjust", response_model=schemas.PartyBookingOut)
def adjust_headcount(
    booking_id: uuid.UUID,
    body: schemas.AdjustHeadcountIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.PartyBookingOut:
    """Change the guest count until T-72h (ADR-0008); refunds any now-excess deposit."""
    try:
        booking = service.adjust_headcount(
            session, booking_id=booking_id, actor_id=principal.user_id,
            new_headcount=body.headcount, gateway=gateway,
        )
    except service.PartyBookingNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found") from exc
    except service.NotBookingParty as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking") from exc
    except service.HeadcountOutOfBand as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Headcount outside the package band"
        ) from exc
    except (
        service.BookingNotConfirmed, service.BalanceAlreadyCharged, service.AdjustmentClosed
    ) as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This booking can no longer be adjusted"
        ) from exc
    return _booking_out(booking)


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.PartyBookingOut)
def cancel_booking(
    booking_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
    email_gateway: EmailGatewayDep,
) -> schemas.PartyBookingOut:
    """Cancel a party — provider or the booking's parent (ADR-0010 refund floor + clawback)."""
    try:
        booking = service.cancel_booking(
            session, booking_id=booking_id, actor_id=principal.user_id,
            gateway=gateway, email_gateway=email_gateway,
        )
    except service.PartyBookingNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found") from exc
    except service.NotAuthorisedToCancel as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not allowed to cancel this booking"
        ) from exc
    return _booking_out(booking)
