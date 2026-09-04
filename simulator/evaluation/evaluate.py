"""Compare simulator window ground truth with persisted risk decisions."""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests


DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_TIMELINE_LIMIT = 200


def normalize_window_start(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def load_ground_truth(path):
    windows = {}
    with path.open("r", encoding="utf-8") as ground_truth_file:
        for line_number, line in enumerate(ground_truth_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                ground_truth = record["ground_truth"]
                merchant_id = record["merchant_id"]
                window_start = normalize_window_start(
                    ground_truth["window_start"]
                )
                is_fraud = ground_truth["is_fraud"]
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Invalid ground-truth record at line {line_number}: {exc}"
                ) from exc

            if not isinstance(is_fraud, bool):
                raise ValueError(
                    f"ground_truth.is_fraud must be boolean at line {line_number}"
                )

            key = (merchant_id, window_start)
            windows[key] = windows.get(key, False) or is_fraud

    return windows


def fetch_predictions(api_base_url, merchant_ids, limit, timeout):
    api_key = os.getenv("SIMULATOR_API_KEY")
    if not api_key:
        raise ValueError(
            "SIMULATOR_API_KEY environment variable is required for evaluation"
        )

    predictions = {}
    for merchant_id in merchant_ids:
        response = requests.get(
            f"{api_base_url.rstrip('/')}/api/v1/dashboard/timeline",
            params={"merchant_id": merchant_id, "limit": limit},
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        for item in body.get("timeline", []):
            key = (
                item["merchant_id"],
                normalize_window_start(item["window_start"]),
            )
            predictions[key] = item
    return predictions


def calculate_metrics(results):
    true_positive = sum(
        result["actual_fraud"] and result["predicted_fraud"]
        for result in results
    )
    true_negative = sum(
        not result["actual_fraud"] and not result["predicted_fraud"]
        for result in results
    )
    false_positive = sum(
        not result["actual_fraud"] and result["predicted_fraud"]
        for result in results
    )
    false_negative = sum(
        result["actual_fraud"] and not result["predicted_fraud"]
        for result in results
    )

    precision = safe_ratio(true_positive, true_positive + false_positive)
    recall = safe_ratio(true_positive, true_positive + false_negative)
    f1 = safe_ratio(2 * precision * recall, precision + recall)
    false_positive_rate = safe_ratio(
        false_positive,
        false_positive + true_negative,
    )

    return {
        "windows_evaluated": len(results),
        "tp": true_positive,
        "tn": true_negative,
        "fp": false_positive,
        "fn": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": false_positive_rate,
    }


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def evaluate(ground_truth_path, api_base_url, limit, timeout):
    ground_truth = load_ground_truth(ground_truth_path)
    merchant_ids = sorted({merchant_id for merchant_id, _ in ground_truth})
    predictions = fetch_predictions(api_base_url, merchant_ids, limit, timeout)

    results = []
    unmatched = []
    for key, actual_fraud in sorted(ground_truth.items()):
        prediction = predictions.get(key)
        if prediction is None or prediction.get("classification") is None:
            unmatched.append(
                {
                    "merchant_id": key[0],
                    "window_start": key[1].isoformat(),
                    "reason": "persisted window or decision not found",
                }
            )
            continue

        classification = prediction["classification"].lower()
        if classification not in {"normal", "watch", "alert"}:
            unmatched.append(
                {
                    "merchant_id": key[0],
                    "window_start": key[1].isoformat(),
                    "reason": f"unsupported classification: {classification}",
                }
            )
            continue

        results.append(
            {
                "merchant_id": key[0],
                "window_start": key[1].isoformat(),
                "actual_fraud": actual_fraud,
                "classification": classification,
                "predicted_fraud": classification == "alert",
            }
        )

    report = calculate_metrics(results)
    report["ground_truth_windows"] = len(ground_truth)
    report["unmatched_windows"] = unmatched
    report["unmatched_count"] = len(unmatched)
    return report


def print_report(report):
    print("## Evaluation Results")
    print(f"Windows evaluated: {report['windows_evaluated']}")
    print(f"TP: {report['tp']}")
    print(f"TN: {report['tn']}")
    print(f"FP: {report['fp']}")
    print(f"FN: {report['fn']}")
    print()
    print(f"Precision: {report['precision']:.4f}")
    print(f"Recall: {report['recall']:.4f}")
    print(f"F1: {report['f1']:.4f}")
    print(f"False Positive Rate: {report['false_positive_rate']:.4f}")
    print(f"Unmatched windows: {report['unmatched_count']}")
    if report["unmatched_windows"]:
        for item in report["unmatched_windows"]:
            print(
                f"  {item['merchant_id']} {item['window_start']}: "
                f"{item['reason']}"
            )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL for the running FastAPI service.",
    )
    parser.add_argument(
        "--timeline-limit",
        type=int,
        default=DEFAULT_TIMELINE_LIMIT,
        help="Maximum persisted windows fetched per merchant.",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for a machine-readable JSON report.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.timeline_limit < 1 or args.timeline_limit > 200:
        raise SystemExit("--timeline-limit must be between 1 and 200")

    try:
        report = evaluate(
            args.ground_truth,
            args.api_base_url,
            args.timeline_limit,
            args.timeout,
        )
    except (OSError, requests.RequestException, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )

    return 2 if report["unmatched_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
