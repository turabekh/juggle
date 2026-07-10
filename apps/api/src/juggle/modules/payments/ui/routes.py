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


@router.get("/{payment_id}", response_model=schemas.PaymentOut)
def get_payment(
    payment_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PaymentOut:
    payment = service.get_payment(session, payment_id)
    if payment is None or payment.guardian_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return schemas.PaymentOut.model_validate(payment)
