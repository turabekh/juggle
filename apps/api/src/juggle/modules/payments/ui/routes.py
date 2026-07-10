"""HTTP routes for the payments module: read a payment's status."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.payments.core import schemas, service

router = APIRouter(prefix="/payments", tags=["payments"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/payouts", response_model=list[schemas.PayoutOut])
def list_payouts(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.PayoutOut]:
    """A provider's payouts for one org (member-gated)."""
    try:
        payouts = service.list_org_payouts(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return [schemas.PayoutOut.model_validate(p) for p in payouts]


@router.get("/{payment_id}", response_model=schemas.PaymentOut)
def get_payment(
    payment_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PaymentOut:
    payment = service.get_payment(session, payment_id)
    if payment is None or payment.guardian_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return schemas.PaymentOut.model_validate(payment)
