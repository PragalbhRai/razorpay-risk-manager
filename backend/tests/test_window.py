from datetime import datetime, timezone

from app.aggregation.window import build_window, get_window_start


def test_timestamp_is_bucketed_to_deterministic_five_minute_window():
    timestamp = datetime(2026, 9, 5, 12, 17, 42, tzinfo=timezone.utc)

    assert get_window_start(timestamp) == datetime(
        2026, 9, 5, 12, 15, tzinfo=timezone.utc
    )


def test_window_boundaries_are_start_inclusive_and_end_exclusive():
    window_start = datetime(2026, 9, 5, 12, 15, tzinfo=timezone.utc)
    transactions = [
        {
            "amount": 100,
            "payment_method_type": "upi",
            "status": "SUCCESS",
            "occurred_at": "2026-09-05T12:15:00+00:00",
        },
        {
            "amount": 200,
            "payment_method_type": "card",
            "status": "FAILED",
            "occurred_at": "2026-09-05T12:19:59+00:00",
        },
        {
            "amount": 300,
            "payment_method_type": "wallet",
            "status": "FAILED",
            "occurred_at": "2026-09-05T12:20:00+00:00",
        },
    ]

    result = build_window(transactions, window_start)

    assert result["tx_count"] == 2
    assert result["failure_rate"] == 0.5
    assert result["distinct_method_count"] == 2


def test_exact_five_minute_boundary_starts_the_next_window():
    assert get_window_start("2026-09-05T12:20:00Z") == datetime(
        2026, 9, 5, 12, 20, tzinfo=timezone.utc
    )