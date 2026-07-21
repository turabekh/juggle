"""Email gateway abstraction — mirrors the payment gateway pattern.

Transactional email depends on this Protocol, not on Postmark/SES. A
``FakeEmailGateway`` (in-memory outbox) backs dev/tests; the real provider drops
in behind the same interface, selected in ``get_email_gateway`` by environment.
Framework-free so it stays importable from any module's ``core``.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from juggle.settings import get_settings


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


@dataclass
class SmtpEmailGateway:
    """Sends real transactional email over SMTP (Postmark, Amazon SES, or any
    provider). Selected when ``JUGGLE_EMAIL_SMTP_HOST`` + ``JUGGLE_EMAIL_FROM_ADDRESS``
    are set (see ``get_email_gateway``).

    ``smtplib``/``email``/``ssl`` are stdlib and imported lazily so the app boots
    (and dev/tests run) without the email path ever being exercised — mirrors the
    Twilio gateway. A message carrying an ``ics`` is attached as ``text/calendar``
    so booking confirmations arrive as add-to-calendar invites.
    """

    host: str
    port: int
    username: str
    password: str
    from_address: str
    from_name: str
    use_starttls: bool = True

    def send(
        self, *, to: str, subject: str, body: str, ics: str | None = None
    ) -> SentMessage:
        import smtplib
        import ssl
        from email.message import EmailMessage
        from email.utils import formataddr, make_msgid

        message_id = make_msgid()
        msg = EmailMessage()
        msg["Message-ID"] = message_id
        msg["From"] = formataddr((self.from_name, self.from_address))
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if ics is not None:
            msg.add_attachment(ics, subtype="calendar", filename="invite.ics")

        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.use_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
        return SentMessage(id=message_id, to=to, subject=subject)


_fake_gateway = FakeEmailGateway()


def email_configured() -> bool:
    """True when a real SMTP email provider is fully configured."""
    s = get_settings()
    return bool(s.email_smtp_host and s.email_from_address)


def get_email_gateway() -> EmailGateway:
    """Real SMTP gateway when configured; the in-memory fake otherwise (dev/CI)."""
    settings = get_settings()
    if email_configured():
        return SmtpEmailGateway(
            host=settings.email_smtp_host,
            port=settings.email_smtp_port,
            username=settings.email_smtp_username,
            password=settings.email_smtp_password,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
            use_starttls=settings.email_smtp_starttls,
        )
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

    Used ONLY in local dev (see ``get_sms_gateway``): the sign-in code is printed
    to the server console so the flow is exercisable end to end without a real
    provider. Never selected outside ``environment == "local"``.
    """

    outbox: list[dict[str, str]] = field(default_factory=list)

    def send(self, *, to: str, body: str) -> SentSms:
        message_id = f"sms_{uuid.uuid4().hex}"
        self.outbox.append({"id": message_id, "to": to, "body": body})
        print(f"[FakeSmsGateway] -> {to}: {body}")  # noqa: T201 — local dev only
        return SentSms(id=message_id, to=to)


@dataclass
class TwilioGateway:
    """Sends real SMS via Twilio. Selected when ``JUGGLE_TWILIO_*`` is configured.

    The ``twilio`` client is imported lazily so the app boots (and dev/tests run)
    without the SMS path ever being exercised.
    """

    account_sid: str
    auth_token: str
    from_number: str

    def send(self, *, to: str, body: str) -> SentSms:
        from twilio.rest import Client

        client = Client(self.account_sid, self.auth_token)
        msg = client.messages.create(to=to, from_=self.from_number, body=body)
        return SentSms(id=msg.sid, to=to)


_fake_sms_gateway = FakeSmsGateway()


def sms_configured() -> bool:
    """True when a real SMS provider (Twilio) is fully configured."""
    s = get_settings()
    return bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number)


def sms_available() -> bool:
    """Whether SMS one-time-code sign-in can be served at all: a real provider,
    or the local-dev fake. Everywhere else it is fail-closed (see the routes)."""
    return sms_configured() or get_settings().environment == "local"


def get_sms_gateway() -> SmsGateway:
    """Real Twilio when configured; the console fake only in local dev.

    Outside local dev with Twilio unset, callers must gate on ``sms_available()``
    and refuse the request — this returns the fake purely so imports don't fail.
    """
    settings = get_settings()
    if sms_configured():
        return TwilioGateway(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_from_number,
        )
    return _fake_sms_gateway
