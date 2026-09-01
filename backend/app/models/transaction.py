from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class TransactionModel(Base):
    __tablename__ = "transactions"
    __table_args__ = {"extend_existing": True}

    transaction_id = Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        index=True,
    )

    merchant_id = Column(
        UUID(as_uuid=True),
        index=True,
    )

    razorpay_event_id = Column(
        String,
        unique=True,
        nullable=False,
    )

    razorpay_payment_id = Column(String)

    amount = Column(
        Float,
        nullable=False,
    )

    payment_method_type = Column(
        String,
        nullable=False,
    )

    payment_method_ref_hash = Column(String)

    status = Column(
        String,
        nullable=False,
    )

    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )