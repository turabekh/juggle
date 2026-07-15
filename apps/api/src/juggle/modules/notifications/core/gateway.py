"""Email gateway abstraction — mirrors the payment gateway pattern.

Transactional email depends on this Protocol, not on Postmark/SES. A
``FakeEmailGateway`` (in-memory outbox) backs dev/tests; the real provider drops
in behind the same interface, selected in ``get_email_gateway`` by environment.
Framework-free so it stays importable from any module's ``core``.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SentMessage:
    id: str
    to: str
    subject: str


class EmailGateway(Protocol):
    def send(
        self, *, to: str, subject: str, body: str, ics: str | None = None
    ) -> SentMessage: ...


@dataclass
class FakeEmailGateway:
    """Records messages to an in-memory outbox instead of sending them."""

    outbox: list[dict[str, str | None]] = field(default_factory=list)

    def send(
        self, *, to: str, subject: str, body: str, ics: str | None = None
    ) -> SentMessage:
        message_id = f"msg_{uuid.uuid4().hex}"
        self.outbox.append(
            {"id": message_id, "to": to, "subject": subject, "body": body, "ics": ics}
        )
        return SentMessage(id=message_id, to=to, subject=subject)


_fake_gateway = FakeEmailGateway()


def get_email_gateway() -> EmailGateway:
    """Dependency provider. TODO(prod): return a PostmarkGateway when configured."""
    return _fake_gateway


# --- SMS (one-time-code sign-in, PRD §7.2) -----------------------------------


@dataclass(frozen=True)
class SentSms:
    id: str
    to: str


class SmsGateway(Protocol):
    def send(self, *, to: str, body: str) -> SentSms: ...


@dataclass
class FakeSmsGateway:
    """Records SMS to an in-memory outbox and logs them, instead of sending.

    In dev/CI the sign-in code is printed to the server console so the flow is
    exercisable end to end without a real SMS provider. A ``TwilioGateway`` drops
    in behind this same Protocol once ``JUGGLE_TWILIO_*`` is configured.
    """

    outbox: list[dict[str, str]] = field(default_factory=list)

    def send(self, *, to: str, body: str) -> SentSms:
        message_id = f"sms_{uuid.uuid4().hex}"
        self.outbox.append({"id": message_id, "to": to, "body": body})
        # Dev convenience: surface the code in the API logs. Never do this in prod.
        print(f"[FakeSmsGateway] -> {to}: {body}")  # noqa: T201
        return SentSms(id=message_id, to=to)


_fake_sms_gateway = FakeSmsGateway()


def get_sms_gateway() -> SmsGateway:
    """Dependency provider. TODO(prod): return a TwilioGateway when configured."""
    return _fake_sms_gateway
