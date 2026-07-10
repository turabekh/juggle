"""HTTP routes for the config module: runtime settings console (admin only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin
from juggle.modules.config.core import schemas, service

router = APIRouter(prefix="/config", tags=["config"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[schemas.SettingItem])
def list_settings(admin: CurrentAdmin, session: SessionDep) -> list[schemas.SettingItem]:
    effective = service.effective_settings(session)
    return [
        schemas.SettingItem(
            key=spec.key,
            value=effective[spec.key],
            default=spec.default,
            minimum=spec.minimum,
            maximum=spec.maximum,
            description=spec.description,
        )
        for spec in service.REGISTRY.values()
    ]


@router.put("/{key}", response_model=schemas.SettingItem)
def update_setting(
    key: str,
    payload: schemas.SettingUpdate,
    admin: CurrentAdmin,
    session: SessionDep,
) -> schemas.SettingItem:
    try:
        service.set_value(
            session, key=key, value=payload.value, changed_by_id=admin.user_id, note=payload.note
        )
    except service.UnknownSetting as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown setting") from exc
    except service.InvalidSettingValue as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    spec = service.REGISTRY[key]
    return schemas.SettingItem(
        key=key,
        value=service.get_value(session, key),
        default=spec.default,
        minimum=spec.minimum,
        maximum=spec.maximum,
        description=spec.description,
    )


@router.get("/{key}/history", response_model=list[schemas.SettingVersion])
def setting_history(
    key: str, admin: CurrentAdmin, session: SessionDep
) -> list[schemas.SettingVersion]:
    try:
        rows = service.history(session, key)
    except service.UnknownSetting as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown setting") from exc
    return [schemas.SettingVersion.model_validate(r) for r in rows]
