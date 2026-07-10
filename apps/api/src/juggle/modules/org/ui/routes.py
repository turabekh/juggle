"""HTTP routes for the org module: provider organisations + membership."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.org.core import schemas, service
from juggle.modules.org.core.models import OrgRole

router = APIRouter(prefix="/org", tags=["org"])

SessionDep = Annotated[Session, Depends(get_session)]


def _require_member(session: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if service.get_member(session, org_id, user_id) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organisation")


@router.get("", response_model=list[schemas.OrgOut])
def list_my_orgs(principal: CurrentPrincipal, session: SessionDep) -> list[schemas.OrgOut]:
    orgs = service.list_user_orgs(session, principal.user_id)
    return [schemas.OrgOut.model_validate(o) for o in orgs]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=schemas.OrgOut)
def create_org(
    payload: schemas.OrgCreate, principal: CurrentPrincipal, session: SessionDep
) -> schemas.OrgOut:
    org = service.create_organisation(
        session, name=payload.name, owner_user_id=principal.user_id
    )
    return schemas.OrgOut.model_validate(org)


@router.get("/{org_id}", response_model=schemas.OrgOut)
def get_org(
    org_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.OrgOut:
    org = service.get_organisation(session, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    return schemas.OrgOut.model_validate(org)


@router.get("/{org_id}/members", response_model=list[schemas.MemberOut])
def list_members(
    org_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.MemberOut]:
    if service.get_member(session, org_id, principal.user_id) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organisation")
    members = service.list_members(session, org_id)
    return [schemas.MemberOut.model_validate(m) for m in members]


@router.post(
    "/{org_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.MemberOut,
)
def add_member(
    org_id: uuid.UUID,
    payload: schemas.MemberCreate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> schemas.MemberOut:
    actor = service.get_member(session, org_id, principal.user_id)
    if actor is None or actor.role is not OrgRole.owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an owner can add members")
    try:
        member = service.add_member(
            session,
            org_id=org_id,
            user_account_id=payload.user_account_id,
            role=OrgRole(payload.role),
        )
    except service.DuplicateMember as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member") from exc
    except service.UnknownUser as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown user_account_id") from exc
    return schemas.MemberOut.model_validate(member)


# --- Onboarding & verification (provider-facing, member-gated) --------------

@router.put("/{org_id}/abn", response_model=schemas.OrgOut)
def set_abn(
    org_id: uuid.UUID,
    payload: schemas.AbnUpdate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> schemas.OrgOut:
    _require_member(session, org_id, principal.user_id)
    org = service.set_abn(session, org_id, payload.abn)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    return schemas.OrgOut.model_validate(org)


@router.get("/{org_id}/wwcc", response_model=list[schemas.WwccOut])
def list_wwcc(
    org_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.WwccOut]:
    _require_member(session, org_id, principal.user_id)
    return [schemas.WwccOut.model_validate(r) for r in service.list_wwcc(session, org_id)]


@router.post(
    "/{org_id}/wwcc", status_code=status.HTTP_201_CREATED, response_model=schemas.WwccOut
)
def add_wwcc(
    org_id: uuid.UUID,
    payload: schemas.WwccCreate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> schemas.WwccOut:
    _require_member(session, org_id, principal.user_id)
    record = service.add_wwcc(
        session,
        org_id=org_id,
        staff_name=payload.staff_name,
        wwcc_number=payload.wwcc_number,
        expiry_date=payload.expiry_date,
    )
    return schemas.WwccOut.model_validate(record)


@router.get("/{org_id}/insurance", response_model=list[schemas.InsuranceOut])
def list_insurance(
    org_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.InsuranceOut]:
    _require_member(session, org_id, principal.user_id)
    return [schemas.InsuranceOut.model_validate(d) for d in service.list_insurance(session, org_id)]


@router.post(
    "/{org_id}/insurance", status_code=status.HTTP_201_CREATED, response_model=schemas.InsuranceOut
)
def add_insurance(
    org_id: uuid.UUID,
    payload: schemas.InsuranceCreate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> schemas.InsuranceOut:
    _require_member(session, org_id, principal.user_id)
    doc = service.add_insurance(
        session, org_id=org_id, file_ref=payload.file_ref, expiry_date=payload.expiry_date
    )
    return schemas.InsuranceOut.model_validate(doc)
