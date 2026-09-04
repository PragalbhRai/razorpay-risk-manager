from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.api import transactions as transactions_api
from app.auth.api_key import get_current_merchant, hash_api_key
from app.db.session import get_db
from app.main import app
from app.models.alert import AlertModel
from app.models.decision import DecisionModel
from app.models.merchant import MerchantModel
from app.models.transaction import TransactionModel
from app.models.window import WindowModel


MERCHANT_A_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
MERCHANT_B_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
API_KEY_A = "merchant-a-development-key"
API_KEY_B = "merchant-b-development-key"


def merchant(merchant_id, api_key):
    return MerchantModel(
        id=merchant_id,
        name=f"Merchant {merchant_id}",
        razorpay_account_id=f"acc_{merchant_id}",
        api_key_hash=hash_api_key(api_key),
    )


class FakeQuery:
    def __init__(self, records):
        self.records = list(records)

    def filter(self, *criteria):
        for criterion in criteria:
            field = getattr(criterion.left, "name", None)
            expected = getattr(criterion.right, "value", criterion.right)
            self.records = [
                record
                for record in self.records
                if self._value(record, field) == expected
            ]
        return self

    def join(self, *_args):
        return self

    @staticmethod
    def _value(record, field):
        if isinstance(record, tuple):
            for item in record:
                if hasattr(item, field):
                    return getattr(item, field)
            return None
        return getattr(record, field, None)

    def first(self):
        return self.records[0] if self.records else None

    def all(self):
        return self.records

    def order_by(self, *_args):
        return self

    def limit(self, _value):
        return self

    def offset(self, _value):
        return self

    def count(self):
        return len(self.records)


class FakeSession:
    def __init__(self, records=()):
        self.records = list(records)
        self.added = []

    def query(self, *models):
        if TransactionModel in models:
            return FakeQuery([record for record in self.records if isinstance(record, TransactionModel)])
        if AlertModel in models:
            return FakeQuery([record for record in self.records if isinstance(record, tuple)])
        if WindowModel in models:
            return FakeQuery([record for record in self.records if isinstance(record, tuple)])
        if MerchantModel in models:
            return FakeQuery([record for record in self.records if isinstance(record, MerchantModel)])
        return FakeQuery([])

    def add(self, item):
        self.added.append(item)

    def commit(self):
        return None

    def refresh(self, _item):
        return None

    def rollback(self):
        return None


def override_db(fake_db):
    app.dependency_overrides[get_db] = lambda: fake_db


def clear_overrides():
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def dependency_cleanup():
    yield
    clear_overrides()


def test_missing_api_key_returns_401():
    override_db(FakeSession())

    response = TestClient(app).get("/api/v1/dashboard/summary")

    assert response.status_code == 401


def test_invalid_api_key_returns_401():
    override_db(FakeSession())

    response = TestClient(app).get(
        "/api/v1/dashboard/summary",
        headers={"X-API-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_unauthenticated_transaction_post_returns_401():
    override_db(FakeSession())
    payload = {
        "transaction_id": str(uuid4()),
        "merchant_id": str(MERCHANT_A_ID),
        "razorpay_event_id": "evt_missing_api_key",
        "amount": 100,
        "payment_method_type": "upi",
        "status": "SUCCESS",
        "occurred_at": "2026-09-05T12:00:00+00:00",
    }

    response = TestClient(app).post(
        "/api/v1/transactions",
        json=payload,
    )

    assert response.status_code == 401


def test_invalid_api_key_transaction_post_returns_401():
    override_db(FakeSession())
    payload = {
        "transaction_id": str(uuid4()),
        "merchant_id": str(MERCHANT_A_ID),
        "razorpay_event_id": "evt_invalid_api_key",
        "amount": 100,
        "payment_method_type": "upi",
        "status": "SUCCESS",
        "occurred_at": "2026-09-05T12:00:00+00:00",
    }

    response = TestClient(app).post(
        "/api/v1/transactions",
        headers={"X-API-Key": "wrong-key"},
        json=payload,
    )

    assert response.status_code == 401


def test_valid_api_key_authenticates_correct_merchant():
    merchant_a = merchant(MERCHANT_A_ID, API_KEY_A)
    db = FakeSession([merchant_a])

    authenticated = get_current_merchant(API_KEY_A, db)

    assert authenticated.id == MERCHANT_A_ID
    assert authenticated.id != MERCHANT_B_ID


def test_merchant_a_cannot_access_merchant_b_alert():
    merchant_a = merchant(MERCHANT_A_ID, API_KEY_A)
    alert_b = AlertModel(
        id=uuid4(),
        decision_id=uuid4(),
        merchant_id=MERCHANT_B_ID,
        severity="high",
        status="open",
        title="B alert",
        message="B only",
    )
    decision_b = DecisionModel(
        id=alert_b.decision_id,
        window_id=uuid4(),
        risk_score=90,
        classification="alert",
        explanation="B only",
        model_version="rule-based-v2",
    )
    override_db(FakeSession([(alert_b, decision_b)]))
    app.dependency_overrides[get_current_merchant] = lambda: merchant_a

    response = TestClient(app).get(f"/api/v1/alerts/{alert_b.id}")

    assert response.status_code == 404


def test_merchant_a_cannot_query_merchant_b_dashboard_data():
    merchant_a = merchant(MERCHANT_A_ID, API_KEY_A)
    override_db(FakeSession())
    app.dependency_overrides[get_current_merchant] = lambda: merchant_a

    response = TestClient(app).get(
        "/api/v1/dashboard/timeline",
        params={"merchant_id": str(MERCHANT_B_ID)},
    )

    assert response.status_code == 403


def test_transaction_cannot_be_submitted_for_another_merchant():
    merchant_a = merchant(MERCHANT_A_ID, API_KEY_A)
    db = FakeSession()
    override_db(db)
    app.dependency_overrides[get_current_merchant] = lambda: merchant_a

    payload = {
        "transaction_id": str(uuid4()),
        "merchant_id": str(MERCHANT_B_ID),
        "razorpay_event_id": "evt_other_merchant",
        "amount": 100,
        "payment_method_type": "upi",
        "status": "SUCCESS",
        "occurred_at": "2026-09-05T12:00:00+00:00",
    }

    response = TestClient(app).post(
        "/api/v1/transactions",
        json=payload,
    )

    assert response.status_code == 403
    assert db.added == []


def test_valid_transaction_for_authenticated_merchant_succeeds(monkeypatch):
    merchant_a = merchant(MERCHANT_A_ID, API_KEY_A)
    db = FakeSession()
    override_db(db)
    app.dependency_overrides[get_current_merchant] = lambda: merchant_a
    monkeypatch.setattr(transactions_api.redis_client, "xadd", lambda *_args, **_kwargs: "1-0")

    payload = {
        "transaction_id": str(uuid4()),
        "merchant_id": str(MERCHANT_A_ID),
        "razorpay_event_id": "evt_authenticated_merchant",
        "amount": 100,
        "payment_method_type": "upi",
        "status": "SUCCESS",
        "occurred_at": "2026-09-05T12:00:00+00:00",
    }

    response = TestClient(app).post(
        "/api/v1/transactions",
        json=payload,
    )

    assert response.status_code == 201
    assert response.json()["duplicate"] is False
    assert db.added[0].merchant_id == MERCHANT_A_ID
