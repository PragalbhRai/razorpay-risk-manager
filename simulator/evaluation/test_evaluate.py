import json

import evaluate as evaluate_module
from evaluate import calculate_metrics, calculate_run_metrics, calculate_scenario_metrics


def test_missing_fraud_prediction_is_counted_as_false_negative():
    report = calculate_metrics([
        {
            "actual_fraud": True,
            "predicted_fraud": False,
        },
    ])

    assert report["windows_evaluated"] == 1
    assert report["fn"] == 1
    assert report["recall"] == 0.0


def test_scenario_metrics_are_calculated_without_changing_global_counts():
    report = calculate_scenario_metrics([
        {"scenario": "normal", "actual_fraud": False, "predicted_fraud": False},
        {"scenario": "fraud_spike", "actual_fraud": True, "predicted_fraud": True},
    ])

    assert report["normal"]["tn"] == 1
    assert report["fraud_spike"]["tp"] == 1


def test_run_metrics_keep_scenario_and_seed_separate():
    report = calculate_run_metrics([
        {
            "scenario": "normal",
            "seed": 42,
            "actual_fraud": False,
            "predicted_fraud": False,
        },
        {
            "scenario": "normal",
            "seed": 43,
            "actual_fraud": False,
            "predicted_fraud": True,
        },
    ])

    assert report["normal:seed=42"]["tn"] == 1
    assert report["normal:seed=43"]["fp"] == 1


def test_evaluate_counts_missing_prediction_as_unmatched_false_negative(tmp_path, monkeypatch):
    ground_truth_path = tmp_path / "ground-truth.jsonl"
    ground_truth_path.write_text(
        json.dumps({
            "merchant_id": "merchant-1",
            "ground_truth": {
                "window_start": "2026-01-01T00:00:00Z",
                "is_fraud": True,
                "scenario": "fraud_spike",
            },
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluate_module, "fetch_predictions", lambda *args, **kwargs: {})

    report = evaluate_module.evaluate(
        ground_truth_path,
        "http://unused",
        limit=200,
        timeout=1,
        api_key="test-key",
    )

    assert report["windows_evaluated"] == 1
    assert report["fn"] == 1
    assert report["unmatched_count"] == 1