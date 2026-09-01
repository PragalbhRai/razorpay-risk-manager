# backend/app/schemas/transaction.py

from datetime import datetime
from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    transaction_id: str
    merchant_id: str
    razorpay_event_id: str
    razorpay_payment_id: str | None = None
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount, must be greater than zero",
    )
    payment_method_type: str
    payment_method_ref_hash: str | None = None
    status: str = "PENDING"
    occurred_at: datetime