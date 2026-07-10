"""Provider onboarding + admin verification (PRD §8.1): a provider submits ABN,
WWCC and insurance; an admin reviews and verifies/rejects each (audited)."""

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


def _org(client: TestClient, token: str) -> str:
    return client.post("/api/v1/org", headers=_auth(token), json={"name": "Verify Co"}).json()["id"]


def test_provider_submits_and_admin_verifies(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    provider = _signup(client)
    admin = make_admin()
    org_id = _org(client, provider)

    # Provider fills in compliance details.
    assert client.put(
        f"/api/v1/org/{org_id}/abn", headers=_auth(provider), json={"abn": "12345678901"}
    ).status_code == 200
    wwcc = client.post(
        f"/api/v1/org/{org_id}/wwcc",
        headers=_auth(provider),
        json={"staff_name": "Alex Coach", "wwcc_number": "WWC1234", "expiry_date": "2027-06-30"},
    )
    assert wwcc.status_code == 201
    assert wwcc.json()["status"] == "pending"
    ins = client.post(
        f"/api/v1/org/{org_id}/insurance",
        headers=_auth(provider),
        json={"file_ref": "https://example.com/cert.pdf", "expiry_date": "2027-01-01"},
    )
    assert ins.status_code == 201

    # Admin reviews the whole package.
    review = client.get(f"/api/v1/admin/orgs/{org_id}/verifications", headers=_auth(admin))
    assert review.status_code == 200
    body = review.json()
    assert body["abn"] == "12345678901"
    assert len(body["wwcc"]) == 1
    assert len(body["insurance"]) == 1

    # Admin verifies the WWCC, rejects the insurance.
    v = client.post(
        f"/api/v1/admin/wwcc/{wwcc.json()['id']}/verify",
        headers=_auth(admin),
        json={"status": "verified"},
    )
    assert v.status_code == 200 and v.json()["status"] == "verified"
    r = client.post(
        f"/api/v1/admin/insurance/{ins.json()['id']}/verify",
        headers=_auth(admin),
        json={"status": "rejected"},
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"

    # The decisions are audited.
    audit = client.get(
        "/api/v1/audit", headers=_auth(admin), params={"action": "admin.wwcc.verify"}
    ).json()
    assert any(e["entity_id"] == wwcc.json()["id"] for e in audit)


def test_verification_submission_is_member_gated(client: TestClient) -> None:
    owner = _signup(client)
    outsider = _signup(client)
    org_id = _org(client, owner)
    resp = client.post(
        f"/api/v1/org/{org_id}/wwcc",
        headers=_auth(outsider),
        json={"staff_name": "X", "wwcc_number": "Y", "expiry_date": "2027-06-30"},
    )
    assert resp.status_code == 403


def test_verification_review_requires_admin(client: TestClient) -> None:
    owner = _signup(client)
    org_id = _org(client, owner)
    assert (
        client.get(f"/api/v1/admin/orgs/{org_id}/verifications", headers=_auth(owner)).status_code
        == 403
    )
