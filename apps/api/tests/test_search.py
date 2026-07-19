"""Search endpoint: PostGIS radius + distance ordering and attribute filters
over published, available inventory."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from juggle.modules.search.core import service

# Perth-local (UTC+8) reference sessions (E2 day/time facets): (starts_at, ends_at) pairs.
SAT = ("2026-10-03T02:00:00Z", "2026-10-03T04:00:00Z")        # Perth Sat 10:00–12:00
SUN = ("2026-10-04T02:00:00Z", "2026-10-04T04:00:00Z")        # Perth Sun
WED_AFTER = ("2026-09-30T08:00:00Z", "2026-09-30T10:00:00Z")  # Perth Wed 16:00 (after school)
WED_BEFORE = ("2026-09-30T01:00:00Z", "2026-09-30T03:00:00Z")  # Perth Wed 09:00 (before school)
FAR_SAT = ("2026-10-10T02:00:00Z", "2026-10-10T04:00:00Z")    # Perth Sat, beyond the horizon
FEED_NOW = datetime(2026, 9, 29, tzinfo=UTC)  # Perth Tue 08:00 — the coming week has the above

# Perth CBD and a point ~11 km south (0.1° latitude).
CBD = (-31.9523, 115.8613)
SOUTH_11KM = (-32.0523, 115.8613)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"prov-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _publish_session(
    client: TestClient,
    token: str,
    *,
    coords: tuple[float, float],
    org_name: str = "Provider",
    title: str = "Camp",
    category: str = "art",
    capacity: int = 10,
    price_cents: int = 5000,
    age_min: int = 5,
    age_max: int = 12,
    starts_at: str = "2026-09-30T09:00:00Z",
    ends_at: str = "2026-09-30T15:00:00Z",
    session_type: str = "full_day",
) -> str:
    org_id = client.post(
        "/api/v1/org", headers=_auth(token), json={"name": f"{org_name} {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    lat, lng = coords
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={
            "organisation_id": org_id,
            "name": "Venue",
            "suburb": "Perth",
            "postcode": "6000",
            "latitude": lat,
            "longitude": lng,
        },
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": title, "category": category},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(token),
        json={
            "venue_id": venue_id,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "capacity": capacity,
            "price_cents": price_cents,
            "age_min": age_min,
            "age_max": age_max,
            "session_type": session_type,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(token))
    return session_id


def _search(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    resp = client.get("/api/v1/search/sessions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def test_radius_filters_and_orders_by_distance(client: TestClient) -> None:
    token = _signup(client)
    near = _publish_session(client, token, coords=CBD, title="Near Camp")
    far = _publish_session(client, token, coords=SOUTH_11KM, title="Far Camp")

    # 5 km radius from the CBD → only the near session.
    tight = _search(client, lat=CBD[0], lng=CBD[1], radius_km=5)
    ids = {c["session_id"] for c in tight}
    assert near in ids
    assert far not in ids

    # 25 km radius → both, nearest first, with sane distances.
    wide = _search(client, lat=CBD[0], lng=CBD[1], radius_km=25)
    ordered = [c["session_id"] for c in wide]
    assert ordered.index(near) < ordered.index(far)
    near_card = next(c for c in wide if c["session_id"] == near)
    far_card = next(c for c in wide if c["session_id"] == far)
    assert near_card["distance_km"] < 1
    assert 9 < far_card["distance_km"] < 13


def test_attribute_filters_narrow_results(client: TestClient) -> None:
    token = _signup(client)
    art = _publish_session(
        client, token, coords=CBD, title="Art", category="art", price_cents=4000,
        age_min=5, age_max=8,
    )
    sport = _publish_session(
        client, token, coords=CBD, title="Sport", category="sport", price_cents=9000,
        age_min=10, age_max=14,
    )

    by_cat = {c["session_id"] for c in _search(client, category="art")}
    assert art in by_cat and sport not in by_cat

    by_age = {c["session_id"] for c in _search(client, child_age=12)}
    assert sport in by_age and art not in by_age

    by_price = {c["session_id"] for c in _search(client, price_max_cents=5000)}
    assert art in by_price and sport not in by_price


def test_available_only_excludes_sold_out(client: TestClient) -> None:
    provider = _signup(client)
    guardian = _signup(client)
    session_id = _publish_session(client, provider, coords=CBD, capacity=1, title="Tiny")

    # Fill the only seat.
    hold = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    )
    assert hold.status_code == 201

    available = {c["session_id"] for c in _search(client, available_only=True)}
    assert session_id not in available

    including = {c["session_id"] for c in _search(client, available_only=False)}
    assert session_id in including
    card = next(
        c for c in _search(client, available_only=False) if c["session_id"] == session_id
    )
    assert card["seats_remaining"] == 0


def test_unpublished_sessions_are_not_searchable(client: TestClient) -> None:
    token = _signup(client)
    # Build a session but do NOT publish it.
    org_id = client.post(
        "/api/v1/org", headers=_auth(token), json={"name": f"Draft {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={"organisation_id": org_id, "name": "V", "latitude": CBD[0], "longitude": CBD[1]},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": "Secret", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(token),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": 5,
            "price_cents": 100,
            "age_min": 5,
            "age_max": 12,
        },
    ).json()["id"]

    found = {c["session_id"] for c in _search(client, lat=CBD[0], lng=CBD[1])}
    assert session_id not in found


def test_lat_without_lng_is_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/search/sessions", params={"lat": CBD[0]})
    assert resp.status_code == 422


# --- E2: any-day one-off facets + feeds (Perth-local) -----------------------

def test_when_facet_filters_by_perth_weekday_and_after_school(client: TestClient) -> None:
    token = _signup(client)
    sat = _publish_session(client, token, coords=CBD, title="Sat", starts_at=SAT[0], ends_at=SAT[1])
    wed_after = _publish_session(
        client, token, coords=CBD, title="WedPM", starts_at=WED_AFTER[0], ends_at=WED_AFTER[1]
    )
    wed_before = _publish_session(
        client, token, coords=CBD, title="WedAM", starts_at=WED_BEFORE[0], ends_at=WED_BEFORE[1]
    )

    weekend = {c["session_id"] for c in _search(client, when="weekend")}
    assert sat in weekend and wed_after not in weekend and wed_before not in weekend

    weekday = {c["session_id"] for c in _search(client, when="weekday")}
    assert wed_after in weekday and wed_before in weekday and sat not in weekday

    after_school = {c["session_id"] for c in _search(client, when="after_school")}
    assert wed_after in after_school  # weekday ≥ 3pm Perth
    assert wed_before not in after_school  # weekday but 9am
    assert sat not in after_school  # weekend excluded


def test_this_weekend_feed(client: TestClient, db: Session) -> None:
    token = _signup(client)
    sat = _publish_session(client, token, coords=CBD, title="Sat", starts_at=SAT[0], ends_at=SAT[1])
    sun = _publish_session(client, token, coords=CBD, title="Sun", starts_at=SUN[0], ends_at=SUN[1])
    wed = _publish_session(
        client, token, coords=CBD, title="Wed", starts_at=WED_AFTER[0], ends_at=WED_AFTER[1]
    )
    # A Saturday beyond the ~7-day horizon must not appear.
    far_sat = _publish_session(
        client, token, coords=CBD, title="FarSat", starts_at=FAR_SAT[0], ends_at=FAR_SAT[1]
    )

    ids = {str(c.session_id) for c in service.this_weekend_sessions(db, now=FEED_NOW)}
    assert sat in ids and sun in ids
    assert wed not in ids
    assert far_sat not in ids  # horizon bound


def test_after_school_feed(client: TestClient, db: Session) -> None:
    token = _signup(client)
    wed_after = _publish_session(
        client, token, coords=CBD, title="WedPM", starts_at=WED_AFTER[0], ends_at=WED_AFTER[1]
    )
    wed_before = _publish_session(
        client, token, coords=CBD, title="WedAM", starts_at=WED_BEFORE[0], ends_at=WED_BEFORE[1]
    )
    sat = _publish_session(client, token, coords=CBD, title="Sat", starts_at=SAT[0], ends_at=SAT[1])

    ids = {str(c.session_id) for c in service.after_school_this_week_sessions(db, now=FEED_NOW)}
    assert wed_after in ids
    assert wed_before not in ids  # before 3pm
    assert sat not in ids  # weekend
