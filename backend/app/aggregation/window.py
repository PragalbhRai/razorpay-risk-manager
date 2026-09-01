from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev


WINDOW_MINUTES = 5


class MerchantWindowAggregator:
    """
    Maintains a rolling 5-minute transaction window per merchant.

    Handles:
    - timezone normalization
    - duplicate transaction protection
    - out-of-order transactions
    - late-event detection
    - rolling-window cleanup
    """

    def __init__(self):
        self.transactions = defaultdict(list)
        self.transaction_ids = defaultdict(set)
        self.max_seen_time = {}

    def add_transaction(self, data: dict) -> dict:
        merchant_id = data["merchant_id"]

        occurred_at = datetime.fromisoformat(
            data["occurred_at"].replace("Z", "+00:00")
        )

        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)

        transaction_id = data["transaction_id"]

        # ---------------------------------------------------------
        # Duplicate protection
        # ---------------------------------------------------------

        if transaction_id in self.transaction_ids[merchant_id]:
            current_time = self.max_seen_time.get(
                merchant_id,
                occurred_at,
            )

            return self._build_window(
                merchant_id,
                current_time,
                late_event=False,
            )

        # ---------------------------------------------------------
        # Determine the merchant watermark.
        #
        # max_seen_time represents the newest event timestamp
        # observed for this merchant.
        # ---------------------------------------------------------

        previous_max = self.max_seen_time.get(
            merchant_id
        )

        if previous_max is None or occurred_at > previous_max:
            self.max_seen_time[merchant_id] = occurred_at

        current_time = self.max_seen_time[merchant_id]

        # ---------------------------------------------------------
        # Late-event detection
        #
        # Anything older than the active 5-minute window relative
        # to the newest observed event is considered late.
        # ---------------------------------------------------------

        window_start = current_time - timedelta(
            minutes=WINDOW_MINUTES
        )

        late_event = occurred_at < window_start

        transaction = {
            "transaction_id": transaction_id,
            "merchant_id": merchant_id,
            "amount": float(data["amount"]),
            "payment_method_type": data["payment_method_type"],
            "status": data["status"],
            "occurred_at": occurred_at,
        }

        # Record the transaction so duplicate deliveries are ignored.
        self.transaction_ids[merchant_id].add(transaction_id)

        # Late events are tracked but do not contaminate the active
        # rolling window.
        if not late_event:
            self.transactions[merchant_id].append(transaction)

        return self._build_window(
            merchant_id,
            current_time,
            late_event=late_event,
        )

    def _build_window(
        self,
        merchant_id: str,
        current_time: datetime,
        late_event: bool = False,
    ) -> dict:

        window_start = current_time - timedelta(
            minutes=WINDOW_MINUTES
        )

        transactions = [
            tx
            for tx in self.transactions[merchant_id]
            if window_start <= tx["occurred_at"] <= current_time
        ]

        # Keep only transactions that belong to the active window.
        self.transactions[merchant_id] = transactions

        if not transactions:
            return {
                "merchant_id": merchant_id,
                "window_start": window_start,
                "window_end": current_time,
                "tx_count": 0,
                "distinct_method_count": 0,
                "failure_rate": 0.0,
                "amount_mean": 0.0,
                "amount_stddev": 0.0,
                "late_event_count": 1 if late_event else 0,
            }

        amounts = [
            tx["amount"]
            for tx in transactions
        ]

        failed_statuses = {
            "FAILED",
            "FAILURE",
            "DECLINED",
            "CANCELLED",
        }

        failed_count = sum(
            1
            for tx in transactions
            if tx["status"].upper() in failed_statuses
        )

        failure_rate = failed_count / len(transactions)

        return {
            "merchant_id": merchant_id,
            "window_start": window_start,
            "window_end": current_time,
            "tx_count": len(transactions),
            "distinct_method_count": len(
                {
                    tx["payment_method_type"]
                    for tx in transactions
                }
            ),
            "failure_rate": failure_rate,
            "amount_mean": mean(amounts),
            "amount_stddev": (
                pstdev(amounts)
                if len(amounts) > 1
                else 0.0
            ),
            "late_event_count": 1 if late_event else 0,
        }