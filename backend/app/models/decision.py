import uuid

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.session import Base


class DecisionModel(Base):
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    window_id = Column(UUID(as_uuid=True), nullable=False, unique=True)

    risk_score = Column(Float, nullable=False)
    classification = Column(String, nullable=False)
    explanation = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    decided_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )