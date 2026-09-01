from dataclasses import dataclass
from typing import Tuple


@dataclass
class RiskDecision:
    risk_score: float
    classification: str
    explanation: str


class RiskEngine:
    """
    Rule-based fraud-spike detector.

    Evaluates the current merchant window using:
    - transaction volume
    - deviation from merchant baseline volume
    - failure rate
    - deviation from merchant baseline failure rate
    - payment-method diversity
    - average transaction amount
    """

    def evaluate(
        self,
        window: dict,
        baseline_tx_count: float | None = None,
        baseline_failure_rate: float | None = None,
    ) -> Tuple[RiskDecision, float]:

        score = 0.0
        reasons = []

        tx_count = window["tx_count"]
        failure_rate = window["failure_rate"]
        distinct_methods = window["distinct_method_count"]
        amount_mean = window["amount_mean"]

        # ---------------------------------------------------------
        # 1. Transaction volume
        # ---------------------------------------------------------

        if tx_count >= 10:
            score += 30
            reasons.append("high transaction volume")
        elif tx_count >= 5:
            score += 15
            reasons.append("elevated transaction volume")

        # ---------------------------------------------------------
        # 2. Baseline transaction-volume deviation
        # ---------------------------------------------------------

        baseline_deviation_score = 0.0

        if baseline_tx_count and baseline_tx_count > 0:
            volume_ratio = tx_count / baseline_tx_count

            if volume_ratio >= 2.0:
                score += 25
                baseline_deviation_score = 1.0
                reasons.append(
                    "transaction volume is at least 2x the merchant baseline"
                )

            elif volume_ratio >= 1.5:
                score += 15
                baseline_deviation_score = 0.5
                reasons.append(
                    "transaction volume is significantly above the merchant baseline"
                )

        # ---------------------------------------------------------
        # 3. Failure rate
        # ---------------------------------------------------------

        if failure_rate >= 0.50:
            score += 40
            reasons.append("very high payment failure rate")

        elif failure_rate >= 0.25:
            score += 25
            reasons.append("elevated payment failure rate")

        # ---------------------------------------------------------
        # 4. Baseline failure-rate deviation
        # ---------------------------------------------------------

        if baseline_failure_rate is not None:

            failure_deviation = failure_rate - baseline_failure_rate

            if failure_deviation >= 0.20:
                score += 25
                reasons.append(
                    "payment failure rate is significantly above the merchant baseline"
                )

            elif failure_deviation >= 0.10:
                score += 15
                reasons.append(
                    "payment failure rate is above the merchant baseline"
                )

        # ---------------------------------------------------------
        # 5. Payment-method diversity
        # ---------------------------------------------------------

        if distinct_methods >= 4:
            score += 20
            reasons.append("unusual payment-method diversity")

        elif distinct_methods >= 2:
            score += 10
            reasons.append("multiple payment methods")

        # ---------------------------------------------------------
        # 6. Large average transaction
        # ---------------------------------------------------------

        if amount_mean >= 10000:
            score += 10
            reasons.append("high average transaction amount")

        # ---------------------------------------------------------
        # Final score
        # ---------------------------------------------------------

        score = min(score, 100.0)

        if score >= 70:
            classification = "alert"

        elif score >= 40:
            classification = "watch"

        else:
            classification = "normal"

        if reasons:
            explanation = "Risk indicators: " + ", ".join(reasons) + "."
        else:
            explanation = "No significant fraud-spike indicators detected."

        return (
            RiskDecision(
                risk_score=score,
                classification=classification,
                explanation=explanation,
            ),
            baseline_deviation_score,
        )
