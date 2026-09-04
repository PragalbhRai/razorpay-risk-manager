import os
import time
import uuid

import redis

from app.aggregation.window import (
    build_window,
    get_window_start,
    normalize_datetime,
)
from app.db.session import SessionLocal
from app.models.alert import AlertModel
from app.models.decision import DecisionModel
from app.models.merchant import MerchantModel
from app.models.transaction import TransactionModel
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


def build_window_from_database(
    db,
    merchant_id,
    occurred_at,
):
    """
    PostgreSQL is the source of truth.

    Rebuild the complete deterministic 5-minute window
    from persisted transactions.

    This makes worker restarts and Redis message recovery
    deterministic.
    """

    window_start = get_window_start(
        occurred_at
    )

    window_end = (
        window_start
        + __import__("datetime")
        .timedelta(minutes=5)
    )

    transactions = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.merchant_id
            == merchant_id,

            TransactionModel.occurred_at
            >= window_start,

            TransactionModel.occurred_at
            < window_end,
        )
        .all()
    )

    transaction_data = [
        {
            "amount": tx.amount,
            "payment_method_type":
                tx.payment_method_type,
            "status": tx.status,
            "occurred_at": tx.occurred_at,
        }
        for tx in transactions
    ]

    window = build_window(
        transaction_data,
        window_start,
    )

    window["merchant_id"] = str(
        merchant_id
    )

    return window


def process_transaction(
    transaction_id,
    data,
):
    print(
        f"Processing transaction: {transaction_id} | "
        f"merchant={data.get('merchant_id')} | "
        f"amount={data.get('amount')} | "
        f"status={data.get('status')}",
        flush=True,
    )

    db = SessionLocal()

    try:
        merchant_id = uuid.UUID(
            data["merchant_id"]
        )

        occurred_at = normalize_datetime(
            data["occurred_at"]
        )

        # -----------------------------------------------------
        # Verify merchant
        # -----------------------------------------------------

        merchant = (
            db.query(MerchantModel)
            .filter(
                MerchantModel.id == merchant_id
            )
            .first()
        )

        if merchant is None:
            raise ValueError(
                f"Merchant not found: {merchant_id}"
            )

        # -----------------------------------------------------
        # Reconstruct complete window from PostgreSQL
        # -----------------------------------------------------

        window = build_window_from_database(
            db,
            merchant_id,
            occurred_at,
        )

        print(
            f"Window | "
            f"merchant={window['merchant_id']} | "
            f"start={window['window_start']} | "
            f"end={window['window_end']} | "
            f"transactions={window['tx_count']} | "
            f"failure_rate="
            f"{window['failure_rate']:.2f} | "
            f"methods="
            f"{window['distinct_method_count']} | "
            f"avg_amount="
            f"{window['amount_mean']:.2f}",
            flush=True,
        )

        # -----------------------------------------------------
        # Risk evaluation
        # -----------------------------------------------------

        decision, baseline_deviation_score = (
            risk_engine.evaluate(
                window,
                baseline_tx_count=(
                    merchant.baseline_tx_count
                ),
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
        # Find or create deterministic window
        # -----------------------------------------------------

        db_window = (
            db.query(WindowModel)
            .filter(
                WindowModel.merchant_id
                == merchant_id,

                WindowModel.window_start
                == window["window_start"],
            )
            .first()
        )

        if db_window is None:

            db_window = WindowModel(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                window_start=(
                    window["window_start"]
                ),
                window_end=(
                    window["window_end"]
                ),
                finalized_at=(
                    window["window_end"]
                ),
                tx_count=(
                    window["tx_count"]
                ),
                distinct_method_count=(
                    window["distinct_method_count"]
                ),
                failure_rate=(
                    window["failure_rate"]
                ),
                amount_mean=(
                    window["amount_mean"]
                ),
                amount_stddev=(
                    window["amount_stddev"]
                ),
                baseline_deviation_score=(
                    baseline_deviation_score
                ),
                late_event_count=0,
            )

            db.add(db_window)

            print(
                "Created new window.",
                flush=True,
            )

        else:

            db_window.window_end = (
                window["window_end"]
            )

            db_window.finalized_at = (
                window["window_end"]
            )

            db_window.tx_count = (
                window["tx_count"]
            )

            db_window.distinct_method_count = (
                window[
                    "distinct_method_count"
                ]
            )

            db_window.failure_rate = (
                window["failure_rate"]
            )

            db_window.amount_mean = (
                window["amount_mean"]
            )

            db_window.amount_stddev = (
                window["amount_stddev"]
            )

            db_window.baseline_deviation_score = (
                baseline_deviation_score
            )

            print(
                f"Updated existing window="
                f"{db_window.id}",
                flush=True,
            )

        db.flush()

        # -----------------------------------------------------
        # Find or create decision
        # -----------------------------------------------------

        db_decision = (
            db.query(DecisionModel)
            .filter(
                DecisionModel.window_id
                == db_window.id
            )
            .first()
        )

        if db_decision is None:

            db_decision = DecisionModel(
                id=uuid.uuid4(),
                window_id=db_window.id,
                risk_score=(
                    decision.risk_score
                ),
                classification=(
                    decision.classification
                ),
                explanation=(
                    decision.explanation
                ),
                model_version=(
                    "rule-based-v1"
                ),
            )

            db.add(db_decision)

            print(
                "Created new decision.",
                flush=True,
            )

        else:

            db_decision.risk_score = (
                decision.risk_score
            )

            db_decision.classification = (
                decision.classification
            )

            db_decision.explanation = (
                decision.explanation
            )

            db_decision.model_version = (
                "rule-based-v1"
            )

            print(
                f"Updated existing decision="
                f"{db_decision.id}",
                flush=True,
            )

        db.flush()

        # -----------------------------------------------------
        # Alert
        # -----------------------------------------------------

        if decision.classification == "alert":

            existing_alert = (
                db.query(AlertModel)
                .filter(
                    AlertModel.decision_id
                    == db_decision.id
                )
                .first()
            )

            if existing_alert is None:

                alert = AlertModel(
                    id=uuid.uuid4(),
                    decision_id=(
                        db_decision.id
                    ),
                    merchant_id=merchant_id,
                    severity="high",
                    status="open",
                    title=(
                        "Fraud spike detected"
                    ),
                    message=(
                        decision.explanation
                    ),
                )

                db.add(alert)

                print(
                    "Created new fraud alert.",
                    flush=True,
                )

            else:

                existing_alert.message = (
                    decision.explanation
                )

                print(
                    f"Updated existing alert="
                    f"{existing_alert.id}",
                    flush=True,
                )

        # -----------------------------------------------------
        # Atomic PostgreSQL commit
        # -----------------------------------------------------

        db.commit()

        print(
            f"Persisted window="
            f"{db_window.id} | "
            f"classification="
            f"{decision.classification.upper()} | "
            f"score="
            f"{decision.risk_score} | "
            f"baseline_deviation="
            f"{baseline_deviation_score}",
            flush=True,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def recover_pending_messages():

    print(
        "Checking for pending transactions...",
        flush=True,
    )

    while True:

        pending_messages = (
            redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={
                    STREAM_NAME: "0"
                },
                count=10,
            )
        )

        if not pending_messages:
            break

        processed_any = False

        for _, entries in pending_messages:

            for message_id, data in entries:

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


def main():

    print(
        "Risk worker starting...",
        flush=True,
    )

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
    # Consumer group
    # ---------------------------------------------------------

    ensure_consumer_group()

    # ---------------------------------------------------------
    # Recover pending messages
    # ---------------------------------------------------------

    recover_pending_messages()

    print(
        "Risk worker started.",
        flush=True,
    )

    # ---------------------------------------------------------
    # Consume new transactions
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