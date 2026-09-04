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