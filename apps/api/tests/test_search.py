"""Search endpoint: PostGIS radius + distance ordering and attribute filters
over published, available inventory."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

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
