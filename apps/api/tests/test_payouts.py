"""Payouts (PRD §8.4): confirming a booking accrues the provider's net earnings
to a scheduled payout; an admin releases due payouts; hold/release works."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_with_session(
    client: TestClient, owner: str, *, price_cents: int, starts: str, ends: str
) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    # Connect onboarding: create the Express account and (via the fake gateway's
    # "completed" account) flip charges/payouts enabled so payouts can release.
    client.post(
        "/api/v1/payments/connect/onboard", headers=_auth(owner),
        json={"organisation_id": org_id},
    )
    client.post(
        "/api/v1/payments/connect/refresh", headers=_auth(owner),
        json={"organisation_id": org_id},
    )
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
            "starts_at": starts,
            "ends_at": ends,
            "capacity": 5,
            "price_cents": price_cents,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return org_id, session_id


def _book_and_pay(client: TestClient, guardian: str, session_id: str) -> None:
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
    client.post(f"/api/v1/booking/payments/{order['payment_id']}/confirm", headers=_auth(guardian))


def test_confirm_accrues_net_payout(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    # A past session so its payout is already due (ends before now).
    org_id, session_id = _org_with_session(
        client, owner, price_cents=10000, starts="2026-01-05T01:00:00Z", ends="2026-01-05T07:00:00Z"
    )
    _book_and_pay(client, guardian, session_id)

    payouts = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    )
    assert payouts.status_code == 200
    rows = payouts.json()
    assert len(rows) == 1
    # $100 gross − 10% fee ($10) − GST on the fee ($1) = $89 net (ADR-0002).
    assert rows[0]["amount_cents"] == 8900
    assert rows[0]["status"] == "scheduled"

    # Two bookings on the same session accumulate into one payout.
    _book_and_pay(client, _signup(client), session_id)
    rows = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    assert len(rows) == 1
    assert rows[0]["amount_cents"] == 17800


def test_order_reconciles_to_fee_plus_gst_plus_net(client: TestClient) -> None:
    """INV-6/ADR-0002: for a multi-session cart, amount_cents == Σfee + Σgst + Σnet, with
    per-session rounding — the platform take plus every provider payout close to the charge."""
    owner, guardian = _signup(client), _signup(client)
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
    # Two past sessions with awkward prices so rounding actually bites.
    session_ids = []
    for price in (5001, 3333):
        sid = client.post(
            f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner),
            json={
                "venue_id": venue_id,
                "starts_at": "2026-01-05T01:00:00Z",
                "ends_at": "2026-01-05T07:00:00Z",
                "capacity": 5,
                "price_cents": price,
                "age_min": 4,
                "age_max": 12,
            },
        ).json()["id"]
        session_ids.append(sid)
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))

    items = []
    for sid in session_ids:
        hold_id = client.post(
            "/api/v1/inventory/holds", headers=_auth(guardian),
            json={"session_id": sid, "quantity": 1},
        ).json()["id"]
        child_id = client.post(
            "/api/v1/identity/children", headers=_auth(guardian),
            json={"first_name": "Kid", "date_of_birth": "2018-01-01"},
        ).json()["id"]
        items.append({"hold_id": hold_id, "children": [{"child_id": child_id}]})

    order = client.post(
        "/api/v1/booking/checkout", headers=_auth(guardian),
        json={"idempotency_key": f"key-{uuid.uuid4().hex}", "items": items},
    ).json()
    client.post(f"/api/v1/booking/payments/{order['payment_id']}/confirm", headers=_auth(guardian))

    net_total = sum(
        p["amount_cents"]
        for p in client.get(
            "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
        ).json()
    )
    assert (
        order["application_fee_cents"] + order["fee_gst_cents"] + net_total
        == order["amount_cents"]
        == 5001 + 3333
    )


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


def test_refund_before_release_claws_back_scheduled_payout(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    org_id, session_id = _org_with_session(
        client, owner, price_cents=10000,
        starts="2027-12-01T01:00:00Z", ends="2027-12-01T07:00:00Z",  # future → still scheduled
    )
    payment_id = _book_confirm(client, guardian, session_id)
    scheduled = client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "scheduled"}
    ).json()
    assert any(p["amount_cents"] == 8900 for p in scheduled)

    refund = client.post(
        f"/api/v1/admin/payments/{payment_id}/refund",
        headers=_auth(admin), json={"reason": "test"},
    )
    assert refund.status_code == 200
    # The provider hadn't been paid → the scheduled payout is decremented to zero (reversed).
    assert client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "scheduled"}
    ).json() == []
    reversed_ = client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "reversed"}
    ).json()
    assert len(reversed_) == 1 and reversed_[0]["amount_cents"] == 0


def test_refund_after_release_reverses_the_transfer(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    org_id, session_id = _org_with_session(
        client, owner, price_cents=10000,
        starts="2026-01-05T01:00:00Z", ends="2026-01-05T07:00:00Z",  # past → due now
    )
    payment_id = _book_confirm(client, guardian, session_id)
    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.json() == {"released": 1, "total_cents": 8900}

    refund = client.post(
        f"/api/v1/admin/payments/{payment_id}/refund",
        headers=_auth(admin), json={"reason": "test"},
    )
    assert refund.status_code == 200
    # Already paid → the transfer is reversed and the payout zeroed.
    reversed_ = client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "reversed"}
    ).json()
    assert len(reversed_) == 1 and reversed_[0]["amount_cents"] == 0
    # A later release run does not re-pay a reversed payout.
    assert client.post("/api/v1/admin/payouts/run", headers=_auth(admin)).json()["released"] == 0


def test_session_cancel_claws_back_payout(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _org_with_session(
        client, owner, price_cents=10000,
        starts="2027-12-01T01:00:00Z", ends="2027-12-01T07:00:00Z",
    )
    _book_confirm(client, guardian, session_id)
    cancel = client.post(f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(owner))
    assert cancel.status_code == 200

    payouts = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    assert len(payouts) == 1
    assert payouts[0]["amount_cents"] == 0
    assert payouts[0]["status"] == "reversed"


def test_refund_targets_the_bookings_own_payout_not_a_sibling(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    """A session can hold two payouts (a released one + a fresh scheduled one). Refunding
    the SECOND order must reverse the second (scheduled) payout, never the first order's
    already-paid transfer (the BLOCKER the persisted booking→payout link fixes)."""
    owner, admin = _signup(client), make_admin()
    org_id, session_id = _org_with_session(
        client, owner, price_cents=10000,
        starts="2026-01-05T01:00:00Z", ends="2026-01-05T07:00:00Z",  # past → releasable
    )
    _book_confirm(client, _signup(client), session_id)  # order A → payout P1 (8900)
    assert client.post("/api/v1/admin/payouts/run", headers=_auth(admin)).json()["released"] == 1
    payment_b = _book_confirm(client, _signup(client), session_id)  # order B → fresh P2 (8900)

    client.post(
        f"/api/v1/admin/payments/{payment_b}/refund",
        headers=_auth(admin), json={"reason": "test"},
    )
    rows = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    paid = [p for p in rows if p["status"] == "paid"]
    reversed_ = [p for p in rows if p["status"] == "reversed"]
    assert len(paid) == 1 and paid[0]["amount_cents"] == 8900  # order A untouched
    assert len(reversed_) == 1 and reversed_[0]["amount_cents"] == 0  # order B clawed back


def test_clawback_is_exact_after_a_fee_config_change(
    client: TestClient, db: Session, make_admin: Callable[[], str]
) -> None:
    """The clawback uses the net PERSISTED at confirm, so raising the fee rate before the
    refund doesn't leave the provider holding money (recomputation would under-claw)."""
    from juggle.modules.config.core import service as config_service

    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    org_id, session_id = _org_with_session(
        client, owner, price_cents=10000,
        starts="2027-12-01T01:00:00Z", ends="2027-12-01T07:00:00Z",
    )
    payment_id = _book_confirm(client, guardian, session_id)  # accrued net 8900 at fee 0.10

    # Admin raises the commission to 20% AFTER confirm; a recompute would claw back only 7800.
    config_service.set_value(
        db, key=config_service.KEY_PLATFORM_FEE_RATE, value=0.20, changed_by_id=None
    )
    db.flush()

    client.post(
        f"/api/v1/admin/payments/{payment_id}/refund",
        headers=_auth(admin), json={"reason": "test"},
    )
    rows = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    # Fully clawed back (net 8900), not the recomputed 7800 that would strand 1100.
    assert len(rows) == 1 and rows[0]["amount_cents"] == 0 and rows[0]["status"] == "reversed"


def test_admin_runs_due_payouts(client: TestClient, make_admin: Callable[[], str]) -> None:
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    _, session_id = _org_with_session(
        client, owner, price_cents=8000, starts="2026-01-05T01:00:00Z", ends="2026-01-05T07:00:00Z"
    )
    _book_and_pay(client, guardian, session_id)

    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.status_code == 200
    assert run.json()["released"] == 1
    assert run.json()["total_cents"] == 7120  # 8000 − 10% fee − GST on the fee (ADR-0002)

    # Now it's paid, not scheduled.
    scheduled = client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "scheduled"}
    ).json()
    assert scheduled == []
    paid = client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "paid"}
    ).json()
    assert any(p["amount_cents"] == 7120 for p in paid)


def test_future_payout_not_released(client: TestClient, make_admin: Callable[[], str]) -> None:
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    # Session far in the future → payout not yet due.
    _, session_id = _org_with_session(
        client, owner, price_cents=5000, starts="2027-12-01T01:00:00Z", ends="2027-12-01T07:00:00Z"
    )
    _book_and_pay(client, guardian, session_id)
    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.json()["released"] == 0


def test_hold_blocks_release(client: TestClient, make_admin: Callable[[], str]) -> None:
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    _, session_id = _org_with_session(
        client, owner, price_cents=6000, starts="2026-01-05T01:00:00Z", ends="2026-01-05T07:00:00Z"
    )
    _book_and_pay(client, guardian, session_id)
    scheduled = client.get(
        "/api/v1/admin/payouts", headers=_auth(admin), params={"status": "scheduled"}
    ).json()
    payout_id = scheduled[0]["id"]

    client.post(f"/api/v1/admin/payouts/{payout_id}/hold", headers=_auth(admin))
    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.json()["released"] == 0  # held payouts aren't paid

    client.post(f"/api/v1/admin/payouts/{payout_id}/release", headers=_auth(admin))
    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.json()["released"] == 1


def test_payouts_require_membership(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id, _ = _org_with_session(
        client, owner, price_cents=5000, starts="2026-01-05T01:00:00Z", ends="2026-01-05T07:00:00Z"
    )
    resp = client.get(
        "/api/v1/payments/payouts", headers=_auth(outsider), params={"organisation_id": org_id}
    )
    assert resp.status_code == 403
