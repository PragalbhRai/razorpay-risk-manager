import uuid

from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.session import Base


class MerchantModel(Base):
    __tablename__ = "merchants"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    razorpay_account_id = Column(
        String,
        unique=True,
        nullable=False,
    )

    baseline_tx_count = Column(
        Float,
        nullable=True,
    )

    baseline_failure_rate = Column(
        Float,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
