import uuid

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.session import Base


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    decision_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
    )

    merchant_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    severity = Column(
        String,
        nullable=False,
    )

    status = Column(
        String,
        nullable=False,
        default="open",
    )

    title = Column(
        String,
        nullable=False,
    )

    message = Column(
        String,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    acknowledged_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )