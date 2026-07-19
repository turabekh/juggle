"""Refresh-token rotation/revocation and SMS one-time-code sign-in."""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.models import OtpChallenge, RefreshToken
from juggle.modules.notifications.core.gateway import _fake_sms_gateway
from juggle.security import hash_refresh_token
from juggle.settings import get_settings


def _signup(client: TestClient) -> dict[str, str]:
    email = f"parent-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/identity/signup",
        json={"email": email, "password": "supersecret", "full_name": "Pat Parent"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"] and body["refresh_token"] and body["expires_in"] > 0
    return body


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- refresh tokens ----------------------------------------------------------


def test_refresh_rotates_and_returns_new_pair(client: TestClient) -> None:
    tokens = _signup(client)
    resp = client.post("/api/v1/identity/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200, resp.text
    fresh = resp.json()
    # A new access token works, and a *new* refresh token is issued (rotation).
    me = client.get("/api/v1/identity/me", headers=_auth(fresh["access_token"]))
    assert me.status_code == 200
    assert fresh["refresh_token"] != tokens["refresh_token"]


def test_used_refresh_token_is_rejected_and_burns_family(client: TestClient) -> None:
    tokens = _signup(client)
    old = tokens["refresh_token"]
    rotated = client.post("/api/v1/identity/refresh", json={"refresh_token": old}).json()

    # Replaying the rotated (now-revoked) token is refused as reuse...
    replay = client.post("/api/v1/identity/refresh", json={"refresh_token": old})
    assert replay.status_code == 401
    # ...and the reuse response revokes the whole family, killing the fresh token too.
    after = client.post(
        "/api/v1/identity/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert after.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    tokens = _signup(client)
    out = client.post("/api/v1/identity/logout", json={"refresh_token": tokens["refresh_token"]})
    assert out.status_code == 204
    denied = client.post(
        "/api/v1/identity/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert denied.status_code == 401


def test_unknown_refresh_token_is_401(client: TestClient) -> None:
    assert (
        client.post("/api/v1/identity/refresh", json={"refresh_token": "nope"}).status_code == 401
    )


# --- SMS OTP sign-in ---------------------------------------------------------

_CODE = re.compile(r"\b(\d{6})\b")


def _latest_code(phone_fragment: str) -> str:
    for msg in reversed(_fake_sms_gateway.outbox):
        if phone_fragment in msg["to"]:
            match = _CODE.search(msg["body"])
            assert match, msg["body"]
            return match.group(1)
    raise AssertionError(f"no OTP sent to a number containing {phone_fragment}")


def test_otp_request_then_verify_creates_phone_first_account(client: TestClient) -> None:
    phone = "0412 345 678"
    req = client.post("/api/v1/identity/otp/request", json={"phone": phone})
    assert req.status_code == 202, req.text

    code = _latest_code("412345678")
    verify = client.post("/api/v1/identity/otp/verify", json={"phone": phone, "code": code})
    assert verify.status_code == 200, verify.text
    token = verify.json()["access_token"]

    me = client.get("/api/v1/identity/me", headers=_auth(token))
    assert me.status_code == 200
    # Normalised to E.164 and stored behind a reserved, non-registerable placeholder.
    assert me.json()["email"] == "sms-61412345678@phone.juggle.invalid"


def test_otp_signs_back_into_the_same_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A returning user signs in again later; skip the resend cooldown for the test.
    monkeypatch.setattr(get_settings(), "otp_resend_cooldown_seconds", 0)
    phone = "+61 400 000 111"
    client.post("/api/v1/identity/otp/request", json={"phone": phone})
    first = client.post(
        "/api/v1/identity/otp/verify", json={"phone": phone, "code": _latest_code("61400000111")}
    )
    first_me = client.get("/api/v1/identity/me", headers=_auth(first.json()["access_token"]))
    first_email = first_me.json()["email"]

    client.post("/api/v1/identity/otp/request", json={"phone": phone})
    second = client.post(
        "/api/v1/identity/otp/verify", json={"phone": phone, "code": _latest_code("61400000111")}
    )
    second_me = client.get("/api/v1/identity/me", headers=_auth(second.json()["access_token"]))
    assert first_email == second_me.json()["email"]  # same account, not a duplicate


def test_wrong_otp_code_is_rejected(client: TestClient) -> None:
    phone = "0412 000 999"
    client.post("/api/v1/identity/otp/request", json={"phone": phone})
    bad = client.post("/api/v1/identity/otp/verify", json={"phone": phone, "code": "000000"})
    # Vanishingly unlikely to match the real code; treat as invalid.
    assert bad.status_code == 401


def test_otp_resend_is_rate_limited(client: TestClient) -> None:
    phone = "0498 111 222"
    assert client.post("/api/v1/identity/otp/request", json={"phone": phone}).status_code == 202
    again = client.post("/api/v1/identity/otp/request", json={"phone": phone})
    assert again.status_code == 429


def test_auth_config_reports_sms_available_in_dev(client: TestClient) -> None:
    # In local dev the console fake makes SMS available.
    assert client.get("/api/v1/identity/auth-config").json()["sms_enabled"] is True


def test_otp_fails_closed_when_sms_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Outside local dev with no Twilio configured, SMS sign-in is refused, and
    # the client is told not to offer it (so the Phone tab is hidden).
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "twilio_account_sid", "")

    assert client.get("/api/v1/identity/auth-config").json()["sms_enabled"] is False
    req = client.post("/api/v1/identity/otp/request", json={"phone": "0412 000 000"})
    assert req.status_code == 503
    ver = client.post(
        "/api/v1/identity/otp/verify", json={"phone": "0412 000 000", "code": "000000"}
    )
    assert ver.status_code == 503


# --- hardening (handoff §6) --------------------------------------------------


def test_signup_ignores_phone_so_it_cannot_squat_a_number(client: TestClient) -> None:
    # A phone in the sign-up body is ignored: the account is NOT bound to it, so a
    # later OTP for that number resolves to a *separate* phone-first account.
    email = f"squatter-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/identity/signup",
        json={"email": email, "password": "supersecret", "phone": "0412 999 888"},
    )
    assert resp.status_code == 201, resp.text

    client.post("/api/v1/identity/otp/request", json={"phone": "0412 999 888"})
    verify = client.post(
        "/api/v1/identity/otp/verify",
        json={"phone": "0412 999 888", "code": _latest_code("61412999888")},
    )
    me = client.get("/api/v1/identity/me", headers=_auth(verify.json()["access_token"]))
    assert me.json()["email"] != email  # the sign-up account never claimed the number


def test_signup_rejects_reserved_placeholder_email(client: TestClient) -> None:
    # The `.invalid` phone-account namespace can't be registered (would let an
    # attacker pre-squat the address the SMS flow mints for a victim's number).
    resp = client.post(
        "/api/v1/identity/signup",
        json={"email": "sms-61412345678@phone.juggle.invalid", "password": "supersecret"},
    )
    assert resp.status_code == 422


def test_deleted_account_access_token_stops_working_immediately(client: TestClient) -> None:
    tokens = _signup(client)
    access = tokens["access_token"]
    assert client.get("/api/v1/identity/me", headers=_auth(access)).status_code == 200

    assert client.delete("/api/v1/identity/me", headers=_auth(access)).status_code == 204
    # The still-unexpired access token must not keep working past deletion.
    assert client.get("/api/v1/identity/me", headers=_auth(access)).status_code == 401


def test_otp_global_send_cap_blocks_bombing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)
    monkeypatch.setattr(settings, "otp_global_max_per_hour", 2)

    def _req(phone: str) -> int:
        return client.post("/api/v1/identity/otp/request", json={"phone": phone}).status_code

    # Distinct numbers (no per-number cooldown); the global ceiling stops the third.
    assert _req("0412000001") == 202
    assert _req("0412000002") == 202
    assert _req("0412000003") == 429


def test_otp_per_number_daily_cap(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)  # isolate the daily cap
    monkeypatch.setattr(settings, "otp_max_per_number_per_day", 1)
    phone = "0412 555 000"
    assert client.post("/api/v1/identity/otp/request", json={"phone": phone}).status_code == 202
    assert client.post("/api/v1/identity/otp/request", json={"phone": phone}).status_code == 429


def test_create_guardian_rejects_reserved_email(db: Session) -> None:
    # Defence-in-depth guard for non-HTTP callers (HTTP is already blocked by EmailStr).
    with pytest.raises(identity_service.ReservedEmail):
        identity_service.create_guardian(db, email="x@squat.invalid", password="supersecret")


def test_prune_expired_auth_drops_dead_rows_but_keeps_live_ones(db: Session) -> None:
    user = identity_service.create_guardian(
        db, email=f"prune-{uuid.uuid4().hex[:8]}@example.com", password="supersecret"
    )
    now = datetime.now(UTC)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash="dead" + uuid.uuid4().hex,
            expires_at=now - timedelta(days=1),  # already expired → prunable
        )
    )
    db.add(
        OtpChallenge(
            phone="+6199999999",
            code_hash="x",
            expires_at=now - timedelta(days=2),  # well past the OTP retention window
        )
    )
    live_raw = identity_service.issue_refresh_token(db, user_id=user.id)  # 30-day TTL, must survive
    db.flush()

    pruned = identity_service.prune_expired_auth(db, now=now)
    assert pruned >= 2
    assert (
        db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(live_raw))
        )
        is not None
    )
