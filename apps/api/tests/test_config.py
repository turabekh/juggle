"""Runtime config: admin-only, bounded, versioned, and actually takes effect on
the live checkout fee."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _checkout_fee(client: TestClient, provider: str, guardian: str, price_cents: int) -> int:
    org_id = client.post(
        "/api/v1/org", headers=_auth(provider), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(provider),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(provider),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(provider),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": 3,
            "price_cents": price_cents,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(provider))
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Kid", "date_of_birth": "2018-01-01"},
    ).json()["id"]
    order = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()
    return order["application_fee_cents"]


def test_config_requires_admin(client: TestClient) -> None:
    user = _signup(client)
    assert client.get("/api/v1/config", headers=_auth(user)).status_code == 403
    assert (
        client.put(
            "/api/v1/config/platform_fee_rate", headers=_auth(user), json={"value": 0.12}
        ).status_code
        == 403
    )


def test_default_fee_then_update_takes_effect(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    provider, guardian = _signup(client), _signup(client)

    # Default 10% fee.
    assert _checkout_fee(client, provider, guardian, 5000) == 500

    # Admin raises the fee to 15%; a fresh checkout reflects it — no redeploy.
    updated = client.put(
        "/api/v1/config/platform_fee_rate", headers=_auth(admin), json={"value": 0.15}
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == 0.15
    assert _checkout_fee(client, provider, guardian, 5000) == 750


def test_out_of_bounds_value_rejected(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    # Fee is bounded 0–0.20.
    resp = client.put(
        "/api/v1/config/platform_fee_rate", headers=_auth(admin), json={"value": 0.5}
    )
    assert resp.status_code == 422


def test_unknown_setting_404(client: TestClient, make_admin: Callable[[], str]) -> None:
    admin = make_admin()
    resp = client.put(
        "/api/v1/config/not_a_real_setting", headers=_auth(admin), json={"value": 1}
    )
    assert resp.status_code == 404


def test_versioning_and_audit(client: TestClient, make_admin: Callable[[], str]) -> None:
    admin = make_admin()
    client.put(
        "/api/v1/config/seat_hold_ttl_seconds",
        headers=_auth(admin),
        json={"value": 600, "note": "shorter holds"},
    )
    client.put(
        "/api/v1/config/seat_hold_ttl_seconds", headers=_auth(admin), json={"value": 300}
    )

    history = client.get(
        "/api/v1/config/seat_hold_ttl_seconds/history", headers=_auth(admin)
    ).json()
    assert [h["version"] for h in history] == [2, 1]  # newest first
    assert history[0]["is_current"] is True
    assert history[1]["is_current"] is False

    # The change is in the audit trail.
    audit = client.get(
        "/api/v1/audit", headers=_auth(admin), params={"action": "config.set"}
    ).json()
    keys = {e["entity_id"] for e in audit}
    assert "seat_hold_ttl_seconds" in keys
