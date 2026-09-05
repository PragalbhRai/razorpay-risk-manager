"""Run a deterministic multi-seed, multi-scenario evaluation benchmark."""

import argparse
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from simulator.evaluation.evaluate import evaluate, print_report
from simulator.evaluation.evaluate import load_ground_truth
from simulator.scenarios.generator import generate_transactions, send_transaction


SCENARIOS = ("normal", "fraud_spike", "gradual_fraud", "recovery")
DEFAULT_SEEDS = (42, 43, 44)


def parse_anchor(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def build_benchmark_transactions(merchant_id, scenarios, seeds, base_anchor, spacing_hours):
    transactions = []
    run_index = 0
    for scenario in scenarios:
        for seed in seeds:
            anchor = base_anchor + timedelta(hours=run_index * spacing_hours)
            run_transactions = list(
                generate_transactions(
                    merchant_id,
                    scenario,
                    anchor,
                    random.Random(seed),
                )
            )
            for transaction in run_transactions:
                transaction["ground_truth"]["benchmark_seed"] = seed
            transactions.extend(run_transactions)
            run_index += 1
    return transactions


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merchant-id", required=True)
    parser.add_argument("--api-key", default=os.getenv("SIMULATOR_API_KEY"))
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, dest="scenarios")
    parser.add_argument(
        "--base-anchor",
        default="2026-01-01T00:00:00Z",
        help="UTC timestamp for the first benchmark window.",
    )
    parser.add_argument("--spacing-hours", type=int, default=2)
    parser.add_argument("--settle-timeout-seconds", type=float, default=90.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("simulator/output/benchmark-ground-truth.jsonl"),
    )
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def wait_for_predictions(api_base_url, merchant_id, api_key, expected_windows, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = requests.get(
            f"{api_base_url.rstrip('/')}/api/v1/dashboard/timeline",
            params={"merchant_id": merchant_id, "limit": 200},
            headers={"X-API-Key": api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        if response.json().get("count", 0) >= expected_windows:
            return
        time.sleep(0.5)

    raise RuntimeError(
        f"Timed out waiting for {expected_windows} persisted windows"
    )


def main():
    args = parse_args()
    if not args.api_key:
        raise SystemExit("--api-key or SIMULATOR_API_KEY is required")
    if args.spacing_hours < 1:
        raise SystemExit("--spacing-hours must be at least 1")

    seeds = tuple(args.seeds or DEFAULT_SEEDS)
    scenarios = tuple(args.scenarios or SCENARIOS)
    transactions = build_benchmark_transactions(
        args.merchant_id,
        scenarios,
        seeds,
        parse_anchor(args.base_anchor),
        args.spacing_hours,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as ground_truth_file:
        for transaction in transactions:
            ground_truth_file.write(json.dumps(transaction) + "\n")

    print(f"Sending {len(transactions)} benchmark transactions...")
    for transaction in transactions:
        send_transaction(
            f"{args.api_base_url.rstrip('/')}/api/v1/transactions",
            transaction,
            args.api_key,
            timeout=10.0,
        )

    expected_windows = len(load_ground_truth(args.output))
    wait_for_predictions(
        args.api_base_url,
        args.merchant_id,
        args.api_key,
        expected_windows,
        args.settle_timeout_seconds,
    )

    report = evaluate(
        args.output,
        args.api_base_url,
        limit=200,
        timeout=10.0,
        api_key=args.api_key,
    )
    print_report(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 2 if report["unmatched_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())