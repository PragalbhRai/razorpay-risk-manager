from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev

WINDOW_MINUTES = 5

FAILED_STATUSES = {
    "FAILED",
    "FAILURE",
    "DECLINED",
    "CANCELLED",
}


def normalize_datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value


def get_window_start(timestamp):
    timestamp = normalize_datetime(timestamp)

    minute = (
        timestamp.minute
        - (timestamp.minute % WINDOW_MINUTES)
    )

    return timestamp.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )


def build_window(transactions, window_start):
    window_start = normalize_datetime(
        window_start
    )

    window_end = (
        window_start
        + timedelta(minutes=WINDOW_MINUTES)
    )

    transactions = [
        tx
        for tx in transactions
        if (
            normalize_datetime(
                tx["occurred_at"]
            )
            >= window_start
        )
        and (
            normalize_datetime(
                tx["occurred_at"]
            )
            < window_end
        )
    ]

    if not transactions:
        return {
            "window_start": window_start,
            "window_end": window_end,
            "tx_count": 0,
            "distinct_method_count": 0,
            "failure_rate": 0.0,
            "amount_mean": 0.0,
            "amount_stddev": 0.0,
        }

    amounts = [
        float(tx["amount"])
        for tx in transactions
    ]

    failed_count = sum(
        1
        for tx in transactions
        if tx["status"].upper()
        in FAILED_STATUSES
    )

    tx_count = len(transactions)

    return {
        "window_start": window_start,
        "window_end": window_end,
        "tx_count": tx_count,
        "distinct_method_count": len(
            {
                tx["payment_method_type"]
                for tx in transactions
            }
        ),
        "failure_rate": (
            failed_count / tx_count
        ),
        "amount_mean": mean(amounts),
        "amount_stddev": (
            pstdev(amounts)
            if len(amounts) > 1
            else 0.0
        ),
    }