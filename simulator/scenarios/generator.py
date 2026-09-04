import time
import uuid
from datetime import datetime, timedelta, timezone

import requests


API_URL = "http://localhost:8000/api/v1/transactions"

MERCHANT_ID = "123e4567-e89b-12d3-a456-426614174000"

PAYMENT_METHODS = [
    "upi",
    "card",
    "netbanking",
    "wallet",
]


def send_transaction(
    occurred_at,
    amount,
    payment_method_type,
    status,
):
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "merchant_id": MERCHANT_ID,
        "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "razorpay_payment_id": f"pay_{uuid.uuid4()}",
        "amount": amount,
        "payment_method_type": payment_method_type,
        "payment_method_ref_hash": None,
        "status": status,
        "occurred_at": occurred_at.isoformat(),
    }

    response = requests.post(
        API_URL,
        json=payload,
        timeout=10,
    )

    response.raise_for_status()

    print(
        f"{status:7} | "
        f"{payment_method_type:10} | "
        f"₹{amount:8.2f} | "
        f"{occurred_at.isoformat()} | "
        f"{response.json()}",
        flush=True,
    )


def run_controlled_scenario():
    now = datetime.now(timezone.utc)

    # Align to an exact 5-minute boundary.
    anchor = now.replace(
        second=0,
        microsecond=0,
    )

    anchor -= timedelta(
        minutes=anchor.minute % 5
    )

    # ---------------------------------------------------------
    # NORMAL BASELINE
    # 8 historical 5-minute windows.
    # Each contains exactly 1 successful transaction.
    # ---------------------------------------------------------

    print("\n=== BASELINE PHASE ===\n")

    baseline_start = anchor - timedelta(
        minutes=45
    )

    for i in range(8):
        window_start = (
            baseline_start
            + timedelta(minutes=i * 5)
        )

        occurred_at = (
            window_start
            + timedelta(seconds=30)
        )

        send_transaction(
            occurred_at=occurred_at,
            amount=1000.0,
            payment_method_type="upi",
            status="SUCCESS",
        )

        time.sleep(0.2)

    # ---------------------------------------------------------
    # FRAUD SPIKE
    # 12 failed transactions inside ONE 5-minute window.
    # Uses 4 payment methods and high volume.
    # ---------------------------------------------------------

    print("\n=== FRAUD SPIKE PHASE ===\n")

    fraud_start = (
        baseline_start
        + timedelta(minutes=40)
    )

    for i in range(12):
        occurred_at = (
            fraud_start
            + timedelta(seconds=10 + i * 3)
        )

        send_transaction(
            occurred_at=occurred_at,
            amount=100.0,
            payment_method_type=(
                PAYMENT_METHODS[
                    i % len(PAYMENT_METHODS)
                ]
            ),
            status="FAILED",
        )

        time.sleep(0.2)

    print("\n=== SCENARIO COMPLETE ===\n")


if __name__ == "__main__":
    run_controlled_scenario()
