"""HTTP routes for the search module: public session discovery (PRD §7.1).

No auth — parents browse without an account.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.modules.search.core import service
from juggle.modules.search.core.schemas import SearchResults

router = APIRouter(prefix="/search", tags=["search"])

SessionDep = Annotated[Session, Depends(get_session)]

When = Literal["weekend", "weekday", "after_school"]

# Perth-local day/time facet → (days_of_week, start_after_local_hour) (E2).
_WHEN_FILTERS: dict[str, tuple[frozenset[int], int | None]] = {
    "weekend": (service.WEEKEND, None),
    "weekday": (service.WEEKDAYS, None),
    "after_school": (service.WEEKDAYS, service.AFTER_SCHOOL_HOUR),
}


@router.get("/sessions", response_model=SearchResults)
def search_sessions(
    session: SessionDep,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float, Query(gt=0, le=200)] = service.DEFAULT_RADIUS_KM,
    suburb: str | None = None,
    postcode: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    child_age: Annotated[int | None, Query(ge=0, le=18)] = None,
    category: str | None = None,
    price_max_cents: Annotated[int | None, Query(ge=0)] = None,
    session_type: Literal["half_day", "full_day"] | None = None,
    when: When | None = None,
    available_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResults:
    if (lat is None) != (lng is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "lat and lng must be provided together",
        )
    days_of_week, start_after_local_hour = _WHEN_FILTERS.get(when or "", (None, None))
    items = service.search_sessions(
        session,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        suburb=suburb,
        postcode=postcode,
        date_from=date_from,
        date_to=date_to,
        child_age=child_age,
        category=category,
        price_max_cents=price_max_cents,
        session_type=session_type,
        days_of_week=days_of_week,
        start_after_local_hour=start_after_local_hour,
        available_only=available_only,
        limit=limit,
        offset=offset,
    )
    return SearchResults(items=items, limit=limit, offset=offset)


@router.get("/feeds/this-weekend", response_model=SearchResults)
def this_weekend_feed(
    session: SessionDep,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float, Query(gt=0, le=200)] = service.DEFAULT_RADIUS_KM,
    suburb: str | None = None,
    postcode: str | None = None,
    child_age: Annotated[int | None, Query(ge=0, le=18)] = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResults:
    """"This weekend" discovery feed (E2)."""
    if (lat is None) != (lng is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "lat and lng must be provided together"
        )
    items = service.this_weekend_sessions(
        session, lat=lat, lng=lng, radius_km=radius_km, suburb=suburb, postcode=postcode,
        child_age=child_age, category=category, limit=limit, offset=offset,
    )
    return SearchResults(items=items, limit=limit, offset=offset)


@router.get("/feeds/after-school", response_model=SearchResults)
def after_school_feed(
    session: SessionDep,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float, Query(gt=0, le=200)] = service.DEFAULT_RADIUS_KM,
    suburb: str | None = None,
    postcode: str | None = None,
    child_age: Annotated[int | None, Query(ge=0, le=18)] = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResults:
    """"After school this week" discovery feed (E2)."""
    if (lat is None) != (lng is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "lat and lng must be provided together"
        )
    items = service.after_school_this_week_sessions(
        session, lat=lat, lng=lng, radius_km=radius_km, suburb=suburb, postcode=postcode,
        child_age=child_age, category=category, limit=limit, offset=offset,
    )
    return SearchResults(items=items, limit=limit, offset=offset)
