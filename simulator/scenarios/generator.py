"""Seeded transaction-stream simulator for the risk manager.

Ground truth is written to JSONL and is deliberately not included in API
requests. Multiple merchant IDs can be supplied when those merchants exist in
the database.
"""

import argparse
import json
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


DEFAULT_API_URL = "http://localhost:8000/api/v1/transactions"
DEFAULT_MERCHANT_ID = "123e4567-e89b-12d3-a456-426614174000"
WINDOW_MINUTES = 5

PAYMENT_METHODS = ("upi", "card", "netbanking", "wallet")
NORMAL_METHOD_WEIGHTS = (0.55, 0.30, 0.10, 0.05)
FRAUD_METHOD_WEIGHTS = (0.25, 0.25, 0.25, 0.25)


@dataclass(frozen=True)
class WindowPlan:
    window_start: datetime
    transaction_count: int
    failure_rate: float
    amount_mean: float
    amount_spread: float
    payment_method_weights: tuple[float, float, float, float]
    is_fraud: bool


def aligned_anchor(now=None):
    current = now or datetime.now(timezone.utc)
    anchor = current.replace(second=0, microsecond=0)
    return anchor - timedelta(minutes=anchor.minute % WINDOW_MINUTES)


def normal_plan(window_start, rng):
    return WindowPlan(
        window_start=window_start,
        transaction_count=rng.randint(3, 7),
        failure_rate=rng.uniform(0.01, 0.06),
        amount_mean=rng.uniform(650, 1500),
        amount_spread=rng.uniform(100, 280),
        payment_method_weights=NORMAL_METHOD_WEIGHTS,
        is_fraud=False,
    )


def build_plans(scenario, anchor, rng):
    baseline_windows = 10
    plans = [
        normal_plan(
            anchor - timedelta(minutes=(baseline_windows - index) * WINDOW_MINUTES),
            rng,
        )
        for index in range(baseline_windows)
    ]

    if scenario == "normal":
        return plans

    if scenario == "fraud_spike":
        plans.append(
            WindowPlan(
                anchor,
                rng.randint(14, 18),
                rng.uniform(0.70, 0.95),
                rng.uniform(80, 240),
                rng.uniform(20, 70),
                FRAUD_METHOD_WEIGHTS,
                True,
            )
        )
        return plans

    if scenario == "gradual_fraud":
        stages = ((7, 0.18), (10, 0.32), (14, 0.55), (17, 0.78))
        for index, (count, failure_rate) in enumerate(stages):
            plans.append(
                WindowPlan(
                    anchor + timedelta(minutes=index * WINDOW_MINUTES),
                    count,
                    failure_rate,
                    rng.uniform(400, 2800),
                    rng.uniform(80, 500),
                    FRAUD_METHOD_WEIGHTS,
                    True,
                )
            )
        return plans

    if scenario == "recovery":
        plans.append(
            WindowPlan(
                anchor,
                rng.randint(14, 18),
                rng.uniform(0.70, 0.95),
                rng.uniform(80, 240),
                rng.uniform(20, 70),
                FRAUD_METHOD_WEIGHTS,
                True,
            )
        )
        recovery_stages = ((9, 0.35), (7, 0.18), (5, 0.08), (4, 0.03))
        for index, (count, failure_rate) in enumerate(recovery_stages, start=1):
            plans.append(
                WindowPlan(
                    anchor + timedelta(minutes=index * WINDOW_MINUTES),
                    count,
                    failure_rate,
                    rng.uniform(650, 1600),
                    rng.uniform(100, 300),
                    NORMAL_METHOD_WEIGHTS,
                    False,
                )
            )
        return plans

    raise ValueError(f"Unsupported scenario: {scenario}")


def generate_transactions(merchant_id, scenario, anchor, rng):
    for plan in build_plans(scenario, anchor, rng):
        for _ in range(plan.transaction_count):
            occurred_at = plan.window_start + timedelta(
                seconds=rng.randint(5, WINDOW_MINUTES * 60 - 5)
            )
            amount = max(
                1.0,
                rng.normalvariate(plan.amount_mean, plan.amount_spread),
            )
            status = "FAILED" if rng.random() < plan.failure_rate else "SUCCESS"
            payment_method = rng.choices(
                PAYMENT_METHODS,
                weights=plan.payment_method_weights,
                k=1,
            )[0]
            yield {
                "transaction_id": str(uuid.uuid4()),
                "merchant_id": merchant_id,
                "razorpay_event_id": f"evt_{uuid.uuid4().hex}",
                "razorpay_payment_id": f"pay_{uuid.uuid4().hex}",
                "amount": round(amount, 2),
                "payment_method_type": payment_method,
                "payment_method_ref_hash": None,
                "status": status,
                "occurred_at": occurred_at.isoformat(),
                "ground_truth": {
                    "is_fraud": plan.is_fraud,
                    "scenario": scenario,
                    "window_start": plan.window_start.isoformat(),
                    "window_is_fraud": plan.is_fraud,
                },
            }


def send_transaction(api_url, transaction, api_key, timeout):
    payload = {
        key: value
        for key, value in transaction.items()
        if key != "ground_truth"
    }
    response = requests.post(
        api_url,
        json=payload,
        headers={"X-API-Key": api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("normal", "fraud_spike", "gradual_fraud", "recovery"),
        default="fraud_spike",
    )
    parser.add_argument(
        "--merchant-id",
        action="append",
        dest="merchant_ids",
        default=None,
        help="Existing merchant UUID; repeat for multiple merchants.",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("RISK_API_URL", DEFAULT_API_URL),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SIMULATOR_API_KEY"),
        help="Merchant API key; defaults to SIMULATOR_API_KEY.",
    )
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("simulator/output/ground_truth.jsonl"),
    )
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    merchant_ids = args.merchant_ids or [DEFAULT_MERCHANT_ID]
    anchor = aligned_anchor() - timedelta(minutes=5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    transactions = []

    for merchant_id in merchant_ids:
        transactions.extend(
            generate_transactions(merchant_id, args.scenario, anchor, rng)
        )

    with args.output.open("w", encoding="utf-8") as ground_truth_file:
        for transaction in transactions:
            ground_truth_file.write(json.dumps(transaction) + "\n")

    if args.dry_run:
        print(f"Generated {len(transactions)} transactions in {args.output}")
        return

    if not args.api_key:
        raise SystemExit(
            "SIMULATOR_API_KEY is required when sending transactions"
        )

    print(
        f"Sending {len(transactions)} {args.scenario} transactions "
        f"for {len(merchant_ids)} merchant(s)...",
        flush=True,
    )
    for index, transaction in enumerate(transactions, start=1):
        send_transaction(args.api_url, transaction, args.api_key, args.timeout)
        if index == 1 or index == len(transactions) or index % 25 == 0:
            print(f"Accepted {index}/{len(transactions)}", flush=True)
        if args.sleep:
            time.sleep(args.sleep)

    print(f"Ground truth written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
