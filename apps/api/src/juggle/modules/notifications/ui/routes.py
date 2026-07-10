"""HTTP routes for the notifications module: the caller's own message log."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.notifications.core import service
from juggle.modules.notifications.core.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[NotificationOut])
def my_notifications(
    principal: CurrentPrincipal, session: SessionDep
) -> list[NotificationOut]:
    logs = service.list_for_user(session, principal.user_id)
    return [NotificationOut.model_validate(log) for log in logs]
