"""Provider verification badges on the public listing (PRD §7.2): the listing
detail exposes approved / ABN-on-file / WWCC-verified / insurance-verified so
parents see trust signals before booking."""

import uuid

from fastapi.testclient import TestClient


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_and_session(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(owner),
        json={
            "venue_id": venue_id,
            "starts_at": "2030-09-30T09:00:00Z",
            "ends_at": "2030-09-30T15:00:00Z",
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return org_id, session_id


def test_badges_start_false_and_flip_as_verified(client: TestClient, make_admin) -> None:
    owner = _signup(client)
    org_id, session_id = _org_and_session(client, owner)

    before = client.get(f"/api/v1/catalog/sessions/{session_id}").json()
    assert before["provider_approved"] is False
    assert before["provider_abn"] is False
    assert before["provider_wwcc_verified"] is False
    assert before["provider_insurance_verified"] is False

    # Provider adds ABN + a WWCC record; admin verifies the WWCC and approves the org.
    client.put(f"/api/v1/org/{org_id}/abn", headers=_auth(owner), json={"abn": "51824753556"})
    wwcc = client.post(
        f"/api/v1/org/{org_id}/wwcc",
        headers=_auth(owner),
        json={"staff_name": "Jamie", "wwcc_number": "WWC1", "expiry_date": "2030-01-01"},
    ).json()
    admin = make_admin()
    client.post(
        f"/api/v1/admin/wwcc/{wwcc['id']}/verify",
        headers=_auth(admin),
        json={"status": "verified"},
    )
    client.post(f"/api/v1/admin/orgs/{org_id}/approve", headers=_auth(admin))

    after = client.get(f"/api/v1/catalog/sessions/{session_id}").json()
    assert after["provider_approved"] is True
    assert after["provider_abn"] is True
    assert after["provider_wwcc_verified"] is True
    assert after["provider_insurance_verified"] is False  # none added → stays false
