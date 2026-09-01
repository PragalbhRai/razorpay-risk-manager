import os
import time
import uuid

import redis

from app.aggregation.window import MerchantWindowAggregator
from app.db.session import SessionLocal
from app.models.alert import AlertModel
from app.models.decision import DecisionModel
from app.models.merchant import MerchantModel
from app.models.window import WindowModel
from app.risk.engine import RiskEngine


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

STREAM_NAME = "transactions"
CONSUMER_GROUP = "risk-workers"
CONSUMER_NAME = "risk-worker-1"


redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
)

aggregator = MerchantWindowAggregator()
risk_engine = RiskEngine()


def ensure_consumer_group():
    try:
        redis_client.xgroup_create(
            STREAM_NAME,
            CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )

        print(
            f"Created consumer group '{CONSUMER_GROUP}' "
            f"for stream '{STREAM_NAME}'.",
            flush=True,
        )

    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def process_transaction(transaction_id, data):
    print(
        f"Processing transaction: {transaction_id} | "
        f"merchant={data.get('merchant_id')} | "
        f"amount={data.get('amount')} | "
        f"status={data.get('status')}",
        flush=True,
    )

    # ---------------------------------------------------------
    # Build rolling merchant window
    # ---------------------------------------------------------

    window = aggregator.add_transaction(data)

    print(
        f"Window | merchant={window['merchant_id']} | "
        f"transactions={window['tx_count']} | "
        f"failure_rate={window['failure_rate']:.2f} | "
        f"methods={window['distinct_method_count']} | "
        f"avg_amount={window['amount_mean']:.2f} | "
        f"late_events={window['late_event_count']}",
        flush=True,
    )

    # ---------------------------------------------------------
    # Load merchant baseline
    # ---------------------------------------------------------

    db = SessionLocal()

    try:
        merchant = (
            db.query(MerchantModel)
            .filter(
                MerchantModel.id
                == uuid.UUID(window["merchant_id"])
            )
            .first()
        )

        if merchant is None:
            raise ValueError(
                f"Merchant not found: {window['merchant_id']}"
            )

        # -----------------------------------------------------
        # Risk evaluation
        # -----------------------------------------------------

        decision, baseline_deviation_score = (
            risk_engine.evaluate(
                window,
                baseline_tx_count=merchant.baseline_tx_count,
                baseline_failure_rate=(
                    merchant.baseline_failure_rate
                ),
            )
        )

        print(
            f"RISK DECISION | "
            f"score={decision.risk_score} | "
            f"classification="
            f"{decision.classification.upper()} | "
            f"explanation={decision.explanation}",
            flush=True,
        )

        # -----------------------------------------------------
        # Create window record
        # -----------------------------------------------------

        window_id = uuid.uuid4()

        db_window = WindowModel(
            id=window_id,
            merchant_id=uuid.UUID(
                window["merchant_id"]
            ),
            window_start=window["window_start"],
            window_end=window["window_end"],
            finalized_at=window["window_end"],
            tx_count=window["tx_count"],
            distinct_method_count=(
                window["distinct_method_count"]
            ),
            failure_rate=window["failure_rate"],
            amount_mean=window["amount_mean"],
            amount_stddev=window["amount_stddev"],
            baseline_deviation_score=(
                baseline_deviation_score
            ),
            late_event_count=(
                window["late_event_count"]
            ),
        )

        # -----------------------------------------------------
        # Create decision record
        # -----------------------------------------------------

        db_decision = DecisionModel(
            id=uuid.uuid4(),
            window_id=window_id,
            risk_score=decision.risk_score,
            classification=decision.classification,
            explanation=decision.explanation,
            model_version="rule-based-v1",
        )

        # -----------------------------------------------------
        # Persist window first
        # -----------------------------------------------------

        db.add(db_window)

        # Ensure windows.id exists before decisions.window_id
        # references it.
        db.flush()

        # -----------------------------------------------------
        # Persist decision
        # -----------------------------------------------------

        db.add(db_decision)

        # IMPORTANT:
        # Ensure decisions.id exists before alerts.decision_id
        # references it.
        db.flush()

        # -----------------------------------------------------
        # Create alert for high-risk decisions
        # -----------------------------------------------------

        if decision.classification == "alert":
            alert = AlertModel(
                id=uuid.uuid4(),
                decision_id=db_decision.id,
                merchant_id=uuid.UUID(
                    window["merchant_id"]
                ),
                severity="high",
                status="open",
                title="Fraud spike detected",
                message=decision.explanation,
            )

            db.add(alert)

        # -----------------------------------------------------
        # Commit window, decision, and optional alert together
        # -----------------------------------------------------

        db.commit()

        print(
            f"Persisted window={window_id} | "
            f"classification="
            f"{decision.classification.upper()} | "
            f"score={decision.risk_score} | "
            f"baseline_deviation="
            f"{baseline_deviation_score}",
            flush=True,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def main():
    print(
        "Risk worker starting...",
        flush=True,
    )
        # ---------------------------------------------------------
    # Recover previously pending messages
    # ---------------------------------------------------------

    print(
        "Checking for pending transactions...",
        flush=True,
    )

    while True:
        pending_messages = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={
                STREAM_NAME: "0"
            },
            count=10,
        )

        if not pending_messages:
            break

        processed_any = False

        for _, entries in pending_messages:
            for message_id, data in entries:

                # Redis returns an empty entry once this consumer
                # has no more pending messages.
                if not data:
                    continue

                processed_any = True

                transaction_id = data.get(
                    "transaction_id"
                )

                try:
                    process_transaction(
                        transaction_id,
                        data,
                    )

                    redis_client.xack(
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        message_id,
                    )

                    print(
                        f"Recovered and acknowledged: "
                        f"{message_id}",
                        flush=True,
                    )

                except Exception as exc:
                    print(
                        f"Error recovering "
                        f"{message_id}: {exc}",
                        flush=True,
                    )

        if not processed_any:
            break
    # ---------------------------------------------------------
    # Wait for Redis
    # ---------------------------------------------------------

    while True:
        try:
            redis_client.ping()
            break

        except redis.exceptions.ConnectionError:
            print(
                "Waiting for Redis...",
                flush=True,
            )
            time.sleep(2)

    # ---------------------------------------------------------
    # Ensure Redis consumer group exists
    # ---------------------------------------------------------

    ensure_consumer_group()

    print(
        "Risk worker started.",
        flush=True,
    )

    # ---------------------------------------------------------
    # Consume transactions
    # ---------------------------------------------------------

    while True:
        try:
            messages = redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={
                    STREAM_NAME: ">"
                },
                count=10,
                block=5000,
            )

            if not messages:
                continue

            for _, entries in messages:

                for message_id, data in entries:

                    transaction_id = data.get(
                        "transaction_id"
                    )

                    try:
                        process_transaction(
                            transaction_id,
                            data,
                        )

                        # Acknowledge only after successful
                        # PostgreSQL commit.
                        redis_client.xack(
                            STREAM_NAME,
                            CONSUMER_GROUP,
                            message_id,
                        )

                        print(
                            f"Transaction acknowledged: "
                            f"{message_id}",
                            flush=True,
                        )

                    except Exception as exc:
                        print(
                            f"Error processing "
                            f"{message_id}: {exc}",
                            flush=True,
                        )

        except redis.exceptions.TimeoutError:
            continue

        except redis.exceptions.ConnectionError:
            print(
                "Redis connection lost. Retrying...",
                flush=True,
            )
            time.sleep(2)


if __name__ == "__main__":
    main()