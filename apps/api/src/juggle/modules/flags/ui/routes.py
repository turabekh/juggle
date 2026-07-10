"""HTTP routes for the flags module: admin management + self-evaluation."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin, CurrentPrincipal
from juggle.modules.flags.core import schemas, service

router = APIRouter(prefix="/flags", tags=["flags"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[schemas.FlagOut])
def list_flags(admin: CurrentAdmin, session: SessionDep) -> list[schemas.FlagOut]:
    return [schemas.FlagOut.model_validate(f) for f in service.list_flags(session)]


@router.put("/{key}", status_code=status.HTTP_200_OK, response_model=schemas.FlagOut)
def upsert_flag(
    key: str, payload: schemas.FlagUpsert, admin: CurrentAdmin, session: SessionDep
) -> schemas.FlagOut:
    flag = service.upsert_flag(
        session,
        key=key,
        enabled=payload.enabled,
        rollout_percentage=payload.rollout_percentage,
        targeting=payload.targeting,
        description=payload.description,
        changed_by_id=admin.user_id,
    )
    return schemas.FlagOut.model_validate(flag)


@router.get("/{key}/enabled", response_model=schemas.FlagEvaluation)
def evaluate_flag(
    key: str, principal: CurrentPrincipal, session: SessionDep
) -> schemas.FlagEvaluation:
    """Evaluate a flag for the calling user (deterministic bucketing)."""
    enabled = service.is_enabled(session, key, user_id=principal.user_id)
    return schemas.FlagEvaluation(key=key, enabled=enabled)
