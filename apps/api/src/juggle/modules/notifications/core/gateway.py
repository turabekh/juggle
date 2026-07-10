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
