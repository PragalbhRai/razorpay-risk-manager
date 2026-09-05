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
        failed_count = round(
            failure_rate * tx_count
        )

        baseline_deviation_score = 0.0

        # Relative signals are primary when a merchant baseline exists. The
        # absolute fallback keeps first-window behavior useful before history
        # has accumulated.
        if baseline_tx_count and baseline_tx_count > 0:
            volume_ratio = tx_count / baseline_tx_count

            baseline_deviation_score = min(
                max(volume_ratio - 1.0, 0.0),
                1.0,
            )

            if volume_ratio >= 3.0:
                score += 40
                reasons.append(
                    f"transaction volume is {volume_ratio:.1f}x the merchant baseline"
                )
            elif volume_ratio >= 2.0:
                score += 30
                reasons.append(
                    f"transaction volume is {volume_ratio:.1f}x the merchant baseline"
                )
            elif volume_ratio >= 1.5:
                score += 20
                reasons.append(
                    f"transaction volume is {volume_ratio:.1f}x the merchant baseline"
                )
            elif volume_ratio >= 1.25:
                score += 10
                reasons.append(
                    f"transaction volume is {volume_ratio:.1f}x the merchant baseline"
                )

        else:
            if tx_count >= 10:
                score += 30
                reasons.append("high transaction volume")
            elif tx_count >= 5:
                score += 15
                reasons.append("elevated transaction volume")

        if baseline_failure_rate is not None:
            failure_deviation = failure_rate - baseline_failure_rate

            if failure_deviation >= 0.35:
                score += 45
                reasons.append(
                    f"payment failure rate is {failure_deviation:.0%} above the merchant baseline"
                )
            elif failure_deviation >= 0.20:
                score += 35
                reasons.append(
                    f"payment failure rate is {failure_deviation:.0%} above the merchant baseline"
                )
            elif failure_deviation >= 0.10:
                score += 25
                reasons.append(
                    f"payment failure rate is {failure_deviation:.0%} above the merchant baseline"
                )
            elif failure_deviation >= 0.05:
                score += 10
                reasons.append(
                    f"payment failure rate is {failure_deviation:.0%} above the merchant baseline"
                )
        else:
            if failure_rate >= 0.50:
                score += 40
                reasons.append("very high payment failure rate")
            elif failure_rate >= 0.25:
                score += 25
                reasons.append("elevated payment failure rate")

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

        # Require enough absolute evidence before opening an alert. A high
        # failure percentage in a very small window is too noisy to treat as
        # confirmed fraud, while high-volume spikes still qualify directly.
        alert_evidence = (
            tx_count >= 10
            or failed_count >= 5
        )

        if score >= 70 and alert_evidence:
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
