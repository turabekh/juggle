"""HTTP routes for the booking module: cart checkout and its lifecycle."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.booking.core import schemas, service
from juggle.modules.notifications.core.gateway import EmailGateway, get_email_gateway
from juggle.modules.payments.core import service as payments_service
from juggle.modules.payments.core.gateway import (
    PaymentGateway,
    StripeGateway,
    get_payment_gateway,
)
from juggle.settings import get_settings

router = APIRouter(prefix="/booking", tags=["booking"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]
EmailGatewayDep = Annotated[EmailGateway, Depends(get_email_gateway)]

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
    email_gateway: EmailGatewayDep,
) -> schemas.OrderOut:
    # Synchronous confirm is a FakeGateway/dev convenience only. With real Stripe live,
    # confirmation MUST come from the verified payment_intent.succeeded webhook — otherwise
    # a guardian could confirm + accrue a provider payout with no charge (ADR-0005 §5).
    if isinstance(gateway, StripeGateway):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Confirmation is webhook-driven for live payments"
        )
    try:
        return service.confirm(
            session,
            payment_id=payment_id,
            guardian_id=principal.user_id,
            email_gateway=email_gateway,
        )
    except service.PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc
    except service.PaymentNotPending as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment already finalised") from exc


@router.post("/stripe/webhook", response_model=schemas.WebhookAck)
async def stripe_webhook(
    request: Request,
    session: SessionDep,
    gateway: GatewayDep,
    email_gateway: EmailGatewayDep,
) -> schemas.WebhookAck:
    """The single Stripe webhook sink (account.updated + payment_intent.*). Signature is
    verified against the RAW body before any parsing (INV-2); handlers are idempotent via
    the stripe_event ledger. Hosted here because settlement orchestrates booking."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    secret = get_settings().stripe_webhook_secret
    try:
        result = service.handle_stripe_webhook(
            session,
            payload=payload,
            sig_header=sig_header,
            secret=secret,
            gateway=gateway,
            email_gateway=email_gateway,
        )
    except payments_service.WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from exc
    return schemas.WebhookAck(status=result)


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


@router.get("/payments/{payment_id}/calendar.ics")
def order_calendar(
    payment_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> Response:
    """Download the order's sessions as an .ics (add to calendar)."""
    try:
        ics = service.order_calendar(
            session, payment_id=payment_id, guardian_id=principal.user_id
        )
    except service.PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from exc
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="juggle-bookings.ics"'},
    )


@router.post(
    "/sessions/{session_id}/cancel", response_model=schemas.SessionCancelResult
)
def cancel_session(
    session_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
    email_gateway: EmailGatewayDep,
) -> schemas.SessionCancelResult:
    """Provider cancels a session — refunds families and releases all seats."""
    try:
        return service.cancel_session(
            session,
            session_id=session_id,
            actor_id=principal.user_id,
            gateway=gateway,
            email_gateway=email_gateway,
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotSessionOwner as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an owner can cancel this session"
        ) from exc
