"""Email gateway selection + the SMTP path.

Mirrors the Twilio/Stripe gateway pattern: the in-memory fake is used until a
real SMTP provider is configured; the SmtpEmailGateway builds a well-formed
message (with an ics attachment when given) and talks to smtplib. smtplib is
mocked so no network is touched.
"""

import smtplib

import pytest

from juggle.modules.notifications.core import gateway as gw


def test_email_gateway_defaults_to_fake() -> None:
    """With no SMTP env configured (dev/CI), sends go to the in-memory outbox."""
    assert gw.email_configured() is False
    assert isinstance(gw.get_email_gateway(), gw.FakeEmailGateway)


def test_get_email_gateway_returns_smtp_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """When host + from-address are set, the real SMTP gateway is selected."""
    settings = gw.get_settings()
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.postmarkapp.com")
    monkeypatch.setattr(settings, "email_from_address", "no-reply@kidspots.store")
    assert gw.email_configured() is True
    assert isinstance(gw.get_email_gateway(), gw.SmtpEmailGateway)


def test_smtp_gateway_sends_message_with_ics(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 0) -> None:
            captured["addr"] = (host, port)

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def starttls(self, context: object = None) -> None:
            captured["starttls"] = True

        def login(self, user: str, password: str) -> None:
            captured["login"] = (user, password)

        def send_message(self, msg: object) -> None:
            captured["msg"] = msg

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    gateway = gw.SmtpEmailGateway(
        host="smtp.postmarkapp.com", port=587, username="tok", password="tok",
        from_address="no-reply@kidspots.store", from_name="Kidspots",
    )
    sent = gateway.send(
        to="parent@example.com", subject="Your booking is confirmed",
        body="See you there!", ics="BEGIN:VCALENDAR\nEND:VCALENDAR",
    )

    assert sent.to == "parent@example.com"
    assert sent.subject == "Your booking is confirmed"
    assert captured["addr"] == ("smtp.postmarkapp.com", 587)
    assert captured["starttls"] is True
    assert captured["login"] == ("tok", "tok")

    msg = captured["msg"]
    assert msg["To"] == "parent@example.com"
    assert msg["Subject"] == "Your booking is confirmed"
    assert "Kidspots" in msg["From"] and "no-reply@kidspots.store" in msg["From"]
    content_types = {part.get_content_type() for part in msg.walk()}
    assert "text/calendar" in content_types


def test_smtp_gateway_skips_login_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some relays (e.g. an internal SES relay) take no auth — don't force login."""
    captured: dict[str, object] = {"login": None}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 0) -> None: ...
        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def starttls(self, context: object = None) -> None: ...
        def login(self, user: str, password: str) -> None:
            captured["login"] = (user, password)

        def send_message(self, msg: object) -> None: ...

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    gateway = gw.SmtpEmailGateway(
        host="relay.internal", port=25, username="", password="",
        from_address="no-reply@kidspots.store", from_name="Kidspots", use_starttls=False,
    )
    gateway.send(to="p@example.com", subject="Hi", body="Body")
    assert captured["login"] is None
