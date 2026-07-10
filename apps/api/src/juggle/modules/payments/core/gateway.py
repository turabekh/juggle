"""Payment gateway abstraction.

The booking flow depends on this Protocol, not on Stripe. A ``FakeGateway`` backs
local dev and tests; the real Stripe Connect implementation (destination charges
with an application fee, PRD §8.4) drops in behind the same interface later,
selected in ``get_payment_gateway`` by environment.

Framework-free (no FastAPI) so it stays importable from any module's ``core``.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PaymentIntentResult:
    id: str
    client_secret: str
    status: str


@dataclass(frozen=True)
class PaymentConfirmResult:
    id: str
    status: str
    succeeded: bool


@dataclass(frozen=True)
class RefundResult:
    id: str
    status: str


@dataclass(frozen=True)
class TransferResult:
    id: str
    status: str


class PaymentGateway(Protocol):
    def create_payment_intent(
        self,
        *,
        amount_cents: int,
        application_fee_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> PaymentIntentResult: ...

    def confirm(self, intent_id: str) -> PaymentConfirmResult: ...

    def refund(self, intent_id: str, amount_cents: int) -> RefundResult: ...

    def transfer(self, *, destination: str | None, amount_cents: int) -> TransferResult: ...


class FakeGateway:
    """In-memory gateway for dev/tests. Confirm always succeeds; refunds always
    succeed. Deterministic and side-effect-free beyond its own dict."""

    def __init__(self) -> None:
        self._intents: dict[str, str] = {}

    def create_payment_intent(
        self,
        *,
        amount_cents: int,
        application_fee_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> PaymentIntentResult:
        intent_id = f"pi_fake_{uuid.uuid4().hex}"
        self._intents[intent_id] = "requires_confirmation"
        return PaymentIntentResult(
            id=intent_id, client_secret=f"{intent_id}_secret", status="requires_confirmation"
        )

    def confirm(self, intent_id: str) -> PaymentConfirmResult:
        self._intents[intent_id] = "succeeded"
        return PaymentConfirmResult(id=intent_id, status="succeeded", succeeded=True)

    def refund(self, intent_id: str, amount_cents: int) -> RefundResult:
        return RefundResult(id=f"re_fake_{uuid.uuid4().hex}", status="succeeded")

    def transfer(self, *, destination: str | None, amount_cents: int) -> TransferResult:
        # Real impl: Stripe transfer to the provider's connected account.
        return TransferResult(id=f"tr_fake_{uuid.uuid4().hex}", status="paid")


_fake_gateway = FakeGateway()


def get_payment_gateway() -> PaymentGateway:
    """Dependency provider. TODO(M-later): return a StripeGateway when configured."""
    return _fake_gateway
