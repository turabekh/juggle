"""Take-rate math (ADR-0002): 10% fee ex-GST + GST on the fee, per-session rounding,
with the reconciliation identity Σfee + Σgst + Σnet == order total."""

from juggle.modules.payments.core import service as payments_service

FEE = 0.10
GST = 0.10


def test_take_rate_splits_a_line_with_gst_on_the_fee() -> None:
    fee, gst, net = payments_service.take_rate(10000, FEE, GST)
    assert (fee, gst, net) == (1000, 100, 8900)


def test_parts_always_sum_to_the_line() -> None:
    for line in (1, 5, 99, 100, 5000, 5001, 12345, 999_999):
        fee, gst, net = payments_service.take_rate(line, FEE, GST)
        assert fee + gst + net == line
        assert fee >= 0 and gst >= 0 and net >= 0


def test_provider_net_subtracts_fee_and_gst() -> None:
    # $80 gross − $8 fee − $0.80 GST = $71.20.
    assert payments_service.provider_net_cents(8000, FEE, GST) == 7120


def test_fee_gst_is_gst_on_the_commission_not_the_line() -> None:
    fee = payments_service.application_fee_cents(10000, FEE)
    assert payments_service.fee_gst_cents(fee, GST) == 100  # 10% of the $10 fee, not of $100


def test_reconciliation_identity_across_a_multi_session_cart() -> None:
    lines = [5000, 3300, 7777, 101, 4999]
    order_total = sum(lines)
    fee_total = gst_total = net_total = 0
    for line in lines:
        fee, gst, net = payments_service.take_rate(line, FEE, GST)
        fee_total += fee
        gst_total += gst
        net_total += net
    assert fee_total + gst_total + net_total == order_total
