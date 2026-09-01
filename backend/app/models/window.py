import uuid

from sqlalchemy import Column, DateTime, Float, Integer
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class WindowModel(Base):
    __tablename__ = "windows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), nullable=False)

    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    finalized_at = Column(DateTime(timezone=True), nullable=False)

    tx_count = Column(Integer, nullable=False)
    distinct_method_count = Column(Integer, nullable=False)
    failure_rate = Column(Float, nullable=False)
    amount_mean = Column(Float, nullable=False)
    amount_stddev = Column(Float, nullable=False)

    baseline_deviation_score = Column(Float, nullable=False, default=0.0)
    late_event_count = Column(Integer, nullable=False, default=0)