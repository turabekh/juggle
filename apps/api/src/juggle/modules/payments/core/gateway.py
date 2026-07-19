"""Payment gateway abstraction.

The booking flow depends on this Protocol, not on Stripe (INV-2). A ``FakeGateway``
backs local dev and tests; the real ``StripeGateway`` (separate charges & transfers —
ADR 0001: a plain charge on the platform account, NO destination charge and NO
``application_fee_amount``; the platform retains its take by not transferring it, and
pays providers via a ``Transfer`` at T+N) drops in behind the same interface, selected
in ``get_payment_gateway`` by whether a Stripe secret key is configured.

Framework-free (no FastAPI) so it stays importable from any module's ``core``.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

import stripe

from juggle.settings import get_settings


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


@dataclass(frozen=True)
class TransferReversalResult:
    id: str
    amount_cents: int


@dataclass(frozen=True)
class ConnectAccountResult:
    id: str
    charges_enabled: bool
    payouts_enabled: bool


@dataclass(frozen=True)
class AccountLinkResult:
    url: str


class PaymentGateway(Protocol):
    def create_payment_intent(
        self,
        *,
        amount_cents: int,
        application_fee_cents: int,
        currency: str,
        idempotency_key: str,
        setup_future_usage: str | None = None,
    ) -> PaymentIntentResult: ...

    def confirm(self, intent_id: str) -> PaymentConfirmResult: ...

    def cancel_payment_intent(self, intent_id: str) -> PaymentConfirmResult: ...

    def charge_saved_card(
        self, *, deposit_intent_id: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentResult: ...

    def refund(self, intent_id: str, amount_cents: int) -> RefundResult: ...

    def transfer(
        self, *, destination: str | None, amount_cents: int, idempotency_key: str | None = None
    ) -> TransferResult: ...

    def reverse_transfer(
        self, *, transfer_id: str, amount_cents: int, idempotency_key: str
    ) -> TransferReversalResult: ...

    # --- Connect Express onboarding (F-PAY-1) ---
    def create_connect_account(
        self, *, email: str | None, business_name: str
    ) -> ConnectAccountResult: ...

    def create_account_link(
        self, *, account_id: str, refresh_url: str, return_url: str
    ) -> AccountLinkResult: ...

    def retrieve_account(self, account_id: str) -> ConnectAccountResult: ...


class FakeGateway:
    """In-memory gateway for dev/tests. Deterministic and side-effect-free beyond its
    own dicts. A freshly created Connect account is NOT yet enabled; ``retrieve_account``
    reports it fully enabled, simulating a completed onboarding."""

    def __init__(self) -> None:
        self._intents: dict[str, str] = {}

    def create_payment_intent(
        self,
        *,
        amount_cents: int,
        application_fee_cents: int,
        currency: str,
        idempotency_key: str,
        setup_future_usage: str | None = None,
    ) -> PaymentIntentResult:
        intent_id = f"pi_fake_{uuid.uuid4().hex}"
        self._intents[intent_id] = "requires_confirmation"
        return PaymentIntentResult(
            id=intent_id, client_secret=f"{intent_id}_secret", status="requires_confirmation"
        )

    def confirm(self, intent_id: str) -> PaymentConfirmResult:
        self._intents[intent_id] = "succeeded"
        return PaymentConfirmResult(id=intent_id, status="succeeded", succeeded=True)

    def cancel_payment_intent(self, intent_id: str) -> PaymentConfirmResult:
        self._intents[intent_id] = "canceled"
        return PaymentConfirmResult(id=intent_id, status="canceled", succeeded=False)

    def charge_saved_card(
        self, *, deposit_intent_id: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentResult:
        intent_id = f"pi_fake_bal_{uuid.uuid4().hex}"
        self._intents[intent_id] = "succeeded"
        return PaymentIntentResult(id=intent_id, client_secret="", status="succeeded")

    def refund(self, intent_id: str, amount_cents: int) -> RefundResult:
        return RefundResult(id=f"re_fake_{uuid.uuid4().hex}", status="succeeded")

    def transfer(
        self, *, destination: str | None, amount_cents: int, idempotency_key: str | None = None
    ) -> TransferResult:
        return TransferResult(id=f"tr_fake_{uuid.uuid4().hex}", status="paid")

    def reverse_transfer(
        self, *, transfer_id: str, amount_cents: int, idempotency_key: str
    ) -> TransferReversalResult:
        return TransferReversalResult(id=f"trr_fake_{uuid.uuid4().hex}", amount_cents=amount_cents)

    def create_connect_account(
        self, *, email: str | None, business_name: str
    ) -> ConnectAccountResult:
        return ConnectAccountResult(
            id=f"acct_fake_{uuid.uuid4().hex}", charges_enabled=False, payouts_enabled=False
        )

    def create_account_link(
        self, *, account_id: str, refresh_url: str, return_url: str
    ) -> AccountLinkResult:
        return AccountLinkResult(url=f"https://connect.stripe.test/setup/{account_id}")

    def retrieve_account(self, account_id: str) -> ConnectAccountResult:
        return ConnectAccountResult(
            id=account_id, charges_enabled=True, payouts_enabled=True
        )


class StripeGateway:
    """Real Stripe Connect gateway (separate charges & transfers, ADR 0001/0005)."""

    def __init__(self, api_key: str) -> None:
        self._client = stripe.StripeClient(api_key)

    def create_payment_intent(
        self,
        *,
        amount_cents: int,
        application_fee_cents: int,
        currency: str,
        idempotency_key: str,
        setup_future_usage: str | None = None,
    ) -> PaymentIntentResult:
        # Separate charges: a plain charge on the PLATFORM account — deliberately NO
        # transfer_data.destination and NO application_fee_amount (ADR 0001). Card-only
        # so success/failure lands within the checkout window (ADR 0005). The fee is
        # internal accounting, carried as metadata only. setup_future_usage="off_session"
        # saves the card so a party balance can be charged off-session at T-7d (B3).
        params: dict[str, object] = {
            "amount": amount_cents,
            "currency": currency,
            "payment_method_types": ["card"],
            "metadata": {"application_fee_cents": str(application_fee_cents)},
        }
        if setup_future_usage is not None:
            params["setup_future_usage"] = setup_future_usage
        intent = self._client.payment_intents.create(
            params=params,  # type: ignore[arg-type]
            options={"idempotency_key": idempotency_key},
        )
        return PaymentIntentResult(
            id=intent.id,
            client_secret=intent.client_secret or "",
            status=intent.status or "requires_payment_method",
        )

    def confirm(self, intent_id: str) -> PaymentConfirmResult:
        # Read-only: the CLIENT confirms via the Payment Element; the webhook is the
        # source of truth (ADR 0005). This only reports current status.
        intent = self._client.payment_intents.retrieve(intent_id)
        return PaymentConfirmResult(
            id=intent.id, status=intent.status or "", succeeded=intent.status == "succeeded"
        )

    def cancel_payment_intent(self, intent_id: str) -> PaymentConfirmResult:
        # Terminal outcome for an abandoned checkout (ADR-0005 §1): hard-cancel the PI so
        # a late webhook can no longer succeed and strand the freed seat.
        intent = self._client.payment_intents.cancel(intent_id)
        return PaymentConfirmResult(
            id=intent.id, status=intent.status or "canceled", succeeded=False
        )

    def refund(self, intent_id: str, amount_cents: int) -> RefundResult:
        refund = self._client.refunds.create(
            params={"payment_intent": intent_id, "amount": amount_cents}
        )
        return RefundResult(id=refund.id, status=refund.status or "")

    def charge_saved_card(
        self, *, deposit_intent_id: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentResult:
        # Off-session party balance charge (ADR-0008, B3): reuse the card saved on the deposit
        # (setup_future_usage=off_session). Derive the customer + payment method from the
        # deposit PI, then confirm a new off-session PaymentIntent. Idempotency key per attempt.
        deposit = self._client.payment_intents.retrieve(deposit_intent_id)
        customer = deposit.customer
        customer_id = customer if isinstance(customer, str) else (customer.id if customer else "")
        pm = deposit.payment_method
        pm_id = pm if isinstance(pm, str) else (pm.id if pm else "")
        try:
            intent = self._client.payment_intents.create(
                params={
                    "amount": amount_cents,
                    "currency": currency,
                    "customer": customer_id,
                    "payment_method": pm_id,
                    "off_session": True,
                    "confirm": True,
                },
                options={"idempotency_key": idempotency_key},
            )
        except stripe.CardError as exc:
            # An off-session decline (insufficient funds, expired card, issuer decline, or a
            # 3DS-required "authentication_required") RAISES rather than returning a status.
            # Surface it as a non-succeeded result so the caller retries — never crash the tick.
            failed_pi = getattr(exc, "payment_intent", None)
            return PaymentIntentResult(
                id=str((failed_pi or {}).get("id", "") or ""),
                client_secret="",
                status="requires_payment_method",
            )
        return PaymentIntentResult(
            id=intent.id,
            client_secret=intent.client_secret or "",
            status=intent.status or "requires_payment_method",
        )

    def transfer(
        self, *, destination: str | None, amount_cents: int, idempotency_key: str | None = None
    ) -> TransferResult:
        if idempotency_key:
            transfer = self._client.transfers.create(
                params={
                    "amount": amount_cents,
                    "currency": "aud",
                    "destination": destination or "",
                },
                options={"idempotency_key": idempotency_key},
            )
        else:
            transfer = self._client.transfers.create(
                params={
                    "amount": amount_cents,
                    "currency": "aud",
                    "destination": destination or "",
                },
            )
        return TransferResult(id=transfer.id, status="paid")

    def reverse_transfer(
        self, *, transfer_id: str, amount_cents: int, idempotency_key: str
    ) -> TransferReversalResult:
        # Claw back money already transferred to a provider when a paid-out booking is
        # refunded (separate charges & transfers, ADR-0001/0005 §7). The idempotency key
        # makes a retry after a mid-batch failure safe (no double reversal).
        reversal = self._client.transfers.reversals.create(
            id=transfer_id,
            params={"amount": amount_cents},
            options={"idempotency_key": idempotency_key},
        )
        return TransferReversalResult(id=reversal.id, amount_cents=amount_cents)

    def create_connect_account(
        self, *, email: str | None, business_name: str
    ) -> ConnectAccountResult:
        account = self._client.accounts.create(
            params={
                "type": "express",
                "email": email or "",
                "business_profile": {"name": business_name},
                "capabilities": {
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            }
        )
        return ConnectAccountResult(
            id=account.id,
            charges_enabled=bool(account.charges_enabled),
            payouts_enabled=bool(account.payouts_enabled),
        )

    def create_account_link(
        self, *, account_id: str, refresh_url: str, return_url: str
    ) -> AccountLinkResult:
        link = self._client.account_links.create(
            params={
                "account": account_id,
                "refresh_url": refresh_url,
                "return_url": return_url,
                "type": "account_onboarding",
            }
        )
        return AccountLinkResult(url=link.url)

    def retrieve_account(self, account_id: str) -> ConnectAccountResult:
        account = self._client.accounts.retrieve(account_id)
        return ConnectAccountResult(
            id=account.id,
            charges_enabled=bool(account.charges_enabled),
            payouts_enabled=bool(account.payouts_enabled),
        )


_fake_gateway = FakeGateway()
_stripe_gateway: StripeGateway | None = None


def get_payment_gateway() -> PaymentGateway:
    """Return the real Stripe gateway when a secret key is configured, else the
    in-memory fake (so local dev and CI need no Stripe account)."""
    global _stripe_gateway
    settings = get_settings()
    if not settings.stripe_secret_key:
        return _fake_gateway
    if _stripe_gateway is None:
        _stripe_gateway = StripeGateway(settings.stripe_secret_key)
    return _stripe_gateway
