"""HTTP routes for the admin module: provider approval, bookings console, and
impersonation (all admin-only)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin
from juggle.modules.admin.core import schemas, service
from juggle.modules.booking.core.schemas import BookingOut, OrderOut
from juggle.modules.org.core.models import OrgStatus, VerificationStatus
from juggle.modules.org.core.schemas import InsuranceOut, WwccOut
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway
from juggle.modules.payments.core.models import PayoutStatus
from juggle.modules.payments.core.schemas import PayoutOut, PayoutRunResult

router = APIRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]


# --- Provider approval ------------------------------------------------------

@router.get("/orgs", response_model=list[schemas.OrgAdminOut])
def list_orgs(
    admin: CurrentAdmin,
    session: SessionDep,
    status_filter: Annotated[
        Literal["pending", "approved", "suspended"], Query(alias="status")
    ] = "pending",
) -> list[schemas.OrgAdminOut]:
    orgs = service.list_orgs(session, OrgStatus(status_filter))
    return [schemas.OrgAdminOut.model_validate(o) for o in orgs]


@router.get("/users", response_model=list[schemas.UserSummary])
def find_users(
    admin: CurrentAdmin,
    session: SessionDep,
    q: Annotated[str, Query(min_length=1)],
) -> list[schemas.UserSummary]:
    return [schemas.UserSummary.model_validate(u) for u in service.find_users(session, q)]


@router.get("/users/{user_id}/bookings", response_model=list[BookingOut])
def user_bookings(
    user_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> list[BookingOut]:
    """A user's booking history (support lookup, PRD §10.2)."""
    return service.user_bookings(session, user_id)


@router.post("/users/{user_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep) -> None:
    """Action an APP data-deletion request for a user (PRD §10.2)."""
    try:
        service.delete_user(session, user_id=user_id, actor_id=admin.user_id)
    except service.UserNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from exc
    except service.CannotDeleteAdmin as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Admin accounts cannot be data-deleted here"
        ) from exc


@router.post("/orgs/{org_id}/approve", response_model=schemas.OrgAdminOut)
def approve_org(
    org_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> schemas.OrgAdminOut:
    try:
        org = service.approve_org(session, org_id=org_id, actor_id=admin.user_id)
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    return schemas.OrgAdminOut.model_validate(org)


@router.post("/orgs/{org_id}/suspend", response_model=schemas.OrgAdminOut)
def suspend_org(
    org_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> schemas.OrgAdminOut:
    try:
        org = service.suspend_org(session, org_id=org_id, actor_id=admin.user_id)
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    return schemas.OrgAdminOut.model_validate(org)


# --- Provider verification review -------------------------------------------

@router.get("/orgs/{org_id}/verifications", response_model=schemas.OrgVerifications)
def org_verifications(
    org_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> schemas.OrgVerifications:
    try:
        org, wwcc, insurance = service.get_org_verifications(session, org_id)
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    return schemas.OrgVerifications(
        organisation_id=org.id,
        name=org.name,
        status=org.status.value,
        abn=org.abn,
        wwcc=[WwccOut.model_validate(r) for r in wwcc],
        insurance=[InsuranceOut.model_validate(d) for d in insurance],
    )


@router.post("/wwcc/{wwcc_id}/verify", response_model=WwccOut)
def verify_wwcc(
    wwcc_id: uuid.UUID,
    payload: schemas.VerifyRequest,
    admin: CurrentAdmin,
    session: SessionDep,
) -> WwccOut:
    try:
        record = service.verify_wwcc(
            session,
            wwcc_id=wwcc_id,
            status=VerificationStatus(payload.status),
            actor_id=admin.user_id,
        )
    except service.VerificationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found") from exc
    return WwccOut.model_validate(record)


@router.post("/insurance/{insurance_id}/verify", response_model=InsuranceOut)
def verify_insurance(
    insurance_id: uuid.UUID,
    payload: schemas.VerifyRequest,
    admin: CurrentAdmin,
    session: SessionDep,
) -> InsuranceOut:
    try:
        doc = service.verify_insurance(
            session,
            insurance_id=insurance_id,
            status=VerificationStatus(payload.status),
            actor_id=admin.user_id,
        )
    except service.VerificationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found") from exc
    return InsuranceOut.model_validate(doc)


# --- Bookings console -------------------------------------------------------

@router.post("/payments/{payment_id}/refund", response_model=OrderOut)
def refund_payment(
    payment_id: uuid.UUID,
    payload: schemas.RefundRequest,
    admin: CurrentAdmin,
    session: SessionDep,
    gateway: GatewayDep,
) -> OrderOut:
    try:
        return service.refund_payment(
            session,
            payment_id=payment_id,
            actor_id=admin.user_id,
            reason=payload.reason,
            gateway=gateway,
        )
    except service.PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc


# --- Payouts ops ------------------------------------------------------------

@router.get("/payouts", response_model=list[PayoutOut])
def list_payouts(
    admin: CurrentAdmin,
    session: SessionDep,
    status_filter: Annotated[
        Literal["scheduled", "paid", "held", "reversed"], Query(alias="status")
    ] = "scheduled",
) -> list[PayoutOut]:
    payouts = service.list_payouts(session, PayoutStatus(status_filter))
    return [PayoutOut.model_validate(p) for p in payouts]


@router.post("/payouts/run", response_model=PayoutRunResult)
def run_payouts(
    admin: CurrentAdmin, session: SessionDep, gateway: GatewayDep
) -> PayoutRunResult:
    released, total = service.run_payouts(session, actor_id=admin.user_id, gateway=gateway)
    return PayoutRunResult(released=released, total_cents=total)


@router.post("/payouts/{payout_id}/hold", response_model=PayoutOut)
def hold_payout(
    payout_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> PayoutOut:
    try:
        payout = service.set_payout_hold(
            session, payout_id=payout_id, held=True, actor_id=admin.user_id
        )
    except service.PayoutNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payout not found") from exc
    return PayoutOut.model_validate(payout)


@router.post("/payouts/{payout_id}/release", response_model=PayoutOut)
def release_payout(
    payout_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> PayoutOut:
    try:
        payout = service.set_payout_hold(
            session, payout_id=payout_id, held=False, actor_id=admin.user_id
        )
    except service.PayoutNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payout not found") from exc
    return PayoutOut.model_validate(payout)


# --- Impersonation ----------------------------------------------------------

@router.post(
    "/impersonations",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ImpersonationTokenOut,
)
def start_impersonation(
    payload: schemas.ImpersonationCreate, admin: CurrentAdmin, session: SessionDep
) -> schemas.ImpersonationTokenOut:
    try:
        session_row, token = service.start_impersonation(
            session,
            impersonator_id=admin.user_id,
            target_user_id=payload.target_user_id,
            mode=payload.mode,
            reason=payload.reason,
        )
    except service.TargetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target user not found") from exc
    except service.CannotImpersonate as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot impersonate this user"
        ) from exc
    return schemas.ImpersonationTokenOut(
        session_id=session_row.id,
        token=token,
        mode=session_row.mode.value,
        expires_at=session_row.expires_at,
    )


@router.get("/impersonations", response_model=list[schemas.ImpersonationSessionOut])
def list_active_impersonations(
    admin: CurrentAdmin, session: SessionDep
) -> list[schemas.ImpersonationSessionOut]:
    rows = service.list_active_impersonations(session)
    return [schemas.ImpersonationSessionOut.model_validate(r) for r in rows]


@router.post("/impersonations/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_impersonation(
    session_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> None:
    try:
        service.end_impersonation(session, session_id=session_id, actor_id=admin.user_id)
    except service.ImpersonationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Impersonation session not found") from exc
