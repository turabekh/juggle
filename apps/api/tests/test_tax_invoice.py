"""Provider commission tax invoice (F-PAY-6, ADR-0002 §8.4): the platform→provider taxable
supply (commission + GST) itemised per order, member-gated, using the split stored at confirm."""

import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_with_session(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs", headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": 5,
            "price_cents": 10000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return org_id, session_id


def _book_confirm(client: TestClient, guardian: str, session_id: str) -> str:
    hold_id = client.post(
        "/api/v1/inventory/holds", headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children", headers=_auth(guardian),
        json={"first_name": "Kid", "date_of_birth": "2018-01-01"},
    ).json()["id"]
    payment_id = client.post(
        "/api/v1/booking/checkout", headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))
    return payment_id


def test_provider_orders_lists_invoiceable_orders(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _org_with_session(client, owner)
    _book_confirm(client, guardian, session_id)

    orders = client.get(
        "/api/v1/booking/orders", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    assert len(orders) == 1
    o = orders[0]
    assert o["session_count"] == 1
    assert (o["gross_cents"], o["commission_cents"], o["commission_gst_cents"], o["net_cents"]) == (
        10000, 1000, 100, 8900,
    )


def test_provider_orders_requires_membership(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id, _session_id = _org_with_session(client, owner)
    resp = client.get(
        "/api/v1/booking/orders", headers=_auth(outsider), params={"organisation_id": org_id}
    )
    assert resp.status_code == 403


def test_tax_invoice_itemises_commission_and_gst(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _org_with_session(client, owner)
    payment_id = _book_confirm(client, guardian, session_id)

    inv = client.get(
        f"/api/v1/booking/orders/{payment_id}/tax-invoice",
        headers=_auth(owner), params={"organisation_id": org_id},
    )
    assert inv.status_code == 200
    body = inv.json()
    # $100 gross = $10 commission + $1 GST-on-commission + $89 net (ADR-0002).
    assert body["totals"] == {
        "gross_cents": 10000,
        "commission_cents": 1000,
        "commission_gst_cents": 100,
        "net_cents": 8900,
    }
    assert len(body["lines"]) == 1
    assert body["lines"][0]["session_title"] == "Camp"
    assert body["lines"][0]["commission_gst_cents"] == 100
    assert body["supplier"]["name"] == "Juggle Marketplace Pty Ltd"
    assert body["recipient"]["name"].startswith("Org ")
    assert body["invoice_number"].startswith("INV-")


def test_tax_invoice_requires_membership(client: TestClient) -> None:
    owner, guardian, outsider = _signup(client), _signup(client), _signup(client)
    org_id, session_id = _org_with_session(client, owner)
    payment_id = _book_confirm(client, guardian, session_id)

    resp = client.get(
        f"/api/v1/booking/orders/{payment_id}/tax-invoice",
        headers=_auth(outsider), params={"organisation_id": org_id},
    )
    assert resp.status_code == 403


def test_tax_invoice_404_when_org_has_no_line_in_the_order(client: TestClient) -> None:
    owner_a, owner_b, guardian = _signup(client), _signup(client), _signup(client)
    org_a, session_a = _org_with_session(client, owner_a)
    org_b, _session_b = _org_with_session(client, owner_b)
    payment_id = _book_confirm(client, guardian, session_a)  # order is entirely org A's

    # owner B is a member of org B but that org has no booking in this order → 404.
    resp = client.get(
        f"/api/v1/booking/orders/{payment_id}/tax-invoice",
        headers=_auth(owner_b), params={"organisation_id": org_b},
    )
    assert resp.status_code == 404


def test_tax_invoice_excludes_refunded_lines(client: TestClient, make_admin) -> None:  # noqa: ANN001
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    org_id, session_id = _org_with_session(client, owner)
    payment_id = _book_confirm(client, guardian, session_id)
    client.post(
        f"/api/v1/admin/payments/{payment_id}/refund",
        headers=_auth(admin), json={"reason": "test"},
    )
    # The only line was refunded → no standing taxable supply → 404.
    resp = client.get(
        f"/api/v1/booking/orders/{payment_id}/tax-invoice",
        headers=_auth(owner), params={"organisation_id": org_id},
    )
    assert resp.status_code == 404
