from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.transaction import TransactionCreate


VALID_TRANSACTION = {
    "transaction_id": "123e4567-e89b-12d3-a456-426614174001",
    "merchant_id": "123e4567-e89b-12d3-a456-426614174000",
    "razorpay_event_id": "evt_test_001",
    "razorpay_payment_id": "pay_test_001",
    "amount": 1250.50,
    "payment_method_type": "upi",
    "status": "SUCCESS",
    "occurred_at": datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc),
}


def test_valid_transaction_is_accepted_by_request_schema():
    transaction = TransactionCreate(**VALID_TRANSACTION)

    assert transaction.amount == 1250.50
    assert transaction.status == "SUCCESS"


@pytest.mark.parametrize("amount", [0, -1])
def test_non_positive_amount_is_rejected(amount):
    payload = {**VALID_TRANSACTION, "amount": amount}

    with pytest.raises(ValidationError):
        TransactionCreate(**payload)


def test_required_transaction_fields_are_rejected_when_missing():
    payload = dict(VALID_TRANSACTION)
    del payload["transaction_id"]
    del payload["amount"]

    with pytest.raises(ValidationError) as error:
        TransactionCreate(**payload)

    missing_fields = {item["loc"][0] for item in error.value.errors()}
    assert missing_fields == {"transaction_id", "amount"}


def test_health_endpoint_reports_dependency_status(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return None

    monkeypatch.setattr("app.main.engine.connect", lambda: FakeConnection())
    monkeypatch.setattr("app.main.redis_client.ping", lambda: True)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }