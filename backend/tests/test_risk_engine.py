from app.risk.engine import RiskEngine


def window(tx_count, failure_rate, distinct_method_count=1, amount_mean=1000.0):
    return {
        "tx_count": tx_count,
        "failure_rate": failure_rate,
        "distinct_method_count": distinct_method_count,
        "amount_mean": amount_mean,
    }


def test_normal_low_risk_window():
    decision, _ = RiskEngine().evaluate(window(3, 0.0))

    assert decision.classification == "normal"
    assert decision.risk_score == 0.0


def test_watch_classification():
    decision, _ = RiskEngine().evaluate(window(5, 0.25))

    assert decision.classification == "watch"
    assert decision.risk_score == 40.0


def test_alert_classification():
    decision, _ = RiskEngine().evaluate(window(10, 0.5, distinct_method_count=4))

    assert decision.classification == "alert"
    assert decision.risk_score == 90.0


def test_normal_baseline_behavior_has_no_deviation_signal():
    decision, baseline_score = RiskEngine().evaluate(
        window(5, 0.03, distinct_method_count=1),
        baseline_tx_count=5,
        baseline_failure_rate=0.03,
    )

    assert decision.classification == "normal"
    assert baseline_score == 0.0
    assert "baseline" not in decision.explanation


def test_large_volume_spike_uses_relative_baseline_signal():
    decision, baseline_score = RiskEngine().evaluate(
        window(15, 0.03, distinct_method_count=1),
        baseline_tx_count=5,
        baseline_failure_rate=0.03,
    )

    assert decision.classification == "watch"
    assert decision.risk_score >= 40.0
    assert baseline_score == 1.0
    assert "3.0x the merchant baseline" in decision.explanation


def test_failure_rate_spike_uses_baseline_deviation():
    decision, _ = RiskEngine().evaluate(
        window(8, 0.40, distinct_method_count=1),
        baseline_tx_count=8,
        baseline_failure_rate=0.05,
    )

    assert decision.risk_score >= 45.0
    assert "35% above the merchant baseline" in decision.explanation


def test_gradual_anomaly_becomes_alert_as_deviations_accumulate():
    early, _ = RiskEngine().evaluate(
        window(8, 0.20, distinct_method_count=2),
        baseline_tx_count=5,
        baseline_failure_rate=0.03,
    )
    late, _ = RiskEngine().evaluate(
        window(10, 0.35, distinct_method_count=4),
        baseline_tx_count=5,
        baseline_failure_rate=0.03,
    )

    assert early.classification == "watch"
    assert late.classification == "alert"
    assert late.risk_score > early.risk_score


def test_small_window_with_fewer_than_five_failures_cannot_alert():
    decision, _ = RiskEngine().evaluate(
        window(9, 4 / 9, distinct_method_count=4)
    )

    assert decision.classification == "watch"


def test_high_volume_fraud_spike_still_alerts():
    decision, _ = RiskEngine().evaluate(
        window(12, 1.0, distinct_method_count=4)
    )

    assert decision.classification == "alert"
    assert decision.risk_score >= 70.0


def test_score_and_classification_boundaries_are_stable():
    decision, _ = RiskEngine().evaluate(
        window(4, 1.0, distinct_method_count=4, amount_mean=10000),
    )

    assert 0.0 <= decision.risk_score <= 100.0
    assert decision.classification == "watch"


def test_explanation_lists_multiple_contributing_signals():
    decision, _ = RiskEngine().evaluate(
        window(12, 0.80, distinct_method_count=4, amount_mean=12000),
    )

    assert decision.classification == "alert"
    assert "high transaction volume" in decision.explanation
    assert "very high payment failure rate" in decision.explanation
    assert "unusual payment-method diversity" in decision.explanation
    assert "high average transaction amount" in decision.explanation