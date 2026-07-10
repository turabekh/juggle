"""HTTP routes for the booking module: cart checkout and its lifecycle."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.booking.core import schemas, service
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway

router = APIRouter(prefix="/booking", tags=["booking"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]

# Maps a checkout validation failure to (status_code, detail).
_CHECKOUT_ERRORS: dict[type[Exception], tuple[int, str]] = {
    service.EmptyCart: (status.HTTP_400_BAD_REQUEST, "Cart is empty"),
    service.HoldInvalid: (status.HTTP_409_CONFLICT, "A seat hold is invalid or not yours"),
    service.HoldExpired: (status.HTTP_409_CONFLICT, "A seat hold has expired — please re-hold"),
    service.ChildCountMismatch: (
        status.HTTP_400_BAD_REQUEST,
        "Number of children must match the seats held",
    ),
    service.ChildInvalid: (status.HTTP_400_BAD_REQUEST, "A child is invalid or not yours"),
    service.AgeOutOfRange: (
        status.HTTP_400_BAD_REQUEST,
        "A child's age is outside the session's age range",
    ),
}


@router.post("/checkout", status_code=status.HTTP_201_CREATED, response_model=schemas.OrderOut)
def checkout(
    payload: schemas.CheckoutRequest,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.OrderOut:
    try:
        return service.checkout(
            session,
            guardian_id=principal.user_id,
            idempotency_key=payload.idempotency_key,
            items=payload.items,
            gateway=gateway,
        )
    except tuple(_CHECKOUT_ERRORS) as exc:
        code, detail = _CHECKOUT_ERRORS[type(exc)]
        raise HTTPException(code, detail) from exc


@router.post("/payments/{payment_id}/confirm", response_model=schemas.OrderOut)
def confirm(
    payment_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.OrderOut:
    try:
        return service.confirm(
            session, payment_id=payment_id, guardian_id=principal.user_id, gateway=gateway
        )
    except service.PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc
    except service.PaymentNotPending as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment already finalised") from exc


@router.post("/payments/{payment_id}/cancel", response_model=schemas.OrderOut)
def cancel(
    payment_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.OrderOut:
    try:
        return service.cancel(session, payment_id=payment_id, guardian_id=principal.user_id)
    except service.PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc
    except service.PaymentNotPending as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment already finalised") from exc


@router.get("/bookings", response_model=list[schemas.BookingOut])
def list_my_bookings(
    principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.BookingOut]:
    return service.list_bookings(session, principal.user_id)
