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
