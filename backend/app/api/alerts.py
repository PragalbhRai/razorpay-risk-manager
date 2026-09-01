from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alert import AlertModel
from app.models.decision import DecisionModel


router = APIRouter(
    prefix="/api/v1/alerts",
    tags=["alerts"],
)


# =========================================================
# Helper: serialize alert + decision
# =========================================================

def serialize_alert(alert, decision):
    return {
        "id": str(alert.id),
        "merchant_id": str(alert.merchant_id),
        "decision_id": str(alert.decision_id),
        "severity": alert.severity,
        "status": alert.status,
        "title": alert.title,
        "message": alert.message,
        "created_at": (
            alert.created_at.isoformat()
            if alert.created_at
            else None
        ),
        "acknowledged_at": (
            alert.acknowledged_at.isoformat()
            if alert.acknowledged_at
            else None
        ),
        "resolved_at": (
            alert.resolved_at.isoformat()
            if alert.resolved_at
            else None
        ),
        "decision": {
            "risk_score": decision.risk_score,
            "classification": decision.classification,
            "explanation": decision.explanation,
            "model_version": decision.model_version,
            "decided_at": (
                decision.decided_at.isoformat()
                if decision.decided_at
                else None
            ),
        } if decision else None,
    }


# =========================================================
# Helper: get alert + decision
# =========================================================

def get_alert_with_decision(
    alert_id: str,
    db: Session,
):
    try:
        alert_uuid = UUID(alert_id)

    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="alert_id must be a valid UUID",
        )

    result = (
        db.query(
            AlertModel,
            DecisionModel,
        )
        .join(
            DecisionModel,
            AlertModel.decision_id == DecisionModel.id,
        )
        .filter(
            AlertModel.id == alert_uuid
        )
        .first()
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    return result


# =========================================================
# List alerts
# =========================================================

@router.get("")
def list_alerts(
    status: str | None = Query(
        default=None,
        description=(
            "Filter by alert status: "
            "open, acknowledged, resolved"
        ),
    ),
    merchant_id: str | None = Query(
        default=None,
        description="Filter alerts by merchant UUID",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    """
    Return fraud alerts with their associated risk decisions.
    """

    query = (
        db.query(
            AlertModel,
            DecisionModel,
        )
        .join(
            DecisionModel,
            AlertModel.decision_id == DecisionModel.id,
        )
    )

    # ---------------------------------------------------------
    # Filter by status
    # ---------------------------------------------------------

    if status:
        normalized_status = status.lower()

        allowed_statuses = {
            "open",
            "acknowledged",
            "resolved",
        }

        if normalized_status not in allowed_statuses:
            raise HTTPException(
                status_code=422,
                detail=(
                    "status must be one of: "
                    "open, acknowledged, resolved"
                ),
            )

        query = query.filter(
            AlertModel.status == normalized_status
        )

    # ---------------------------------------------------------
    # Filter by merchant
    # ---------------------------------------------------------

    if merchant_id:
        try:
            merchant_uuid = UUID(merchant_id)

        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="merchant_id must be a valid UUID",
            )

        query = query.filter(
            AlertModel.merchant_id == merchant_uuid
        )

    # ---------------------------------------------------------
    # Newest alerts first
    # ---------------------------------------------------------

    query = query.order_by(
        AlertModel.created_at.desc()
    )

    total = query.count()

    results = (
        query
        .offset(offset)
        .limit(limit)
        .all()
    )

    alerts = [
        serialize_alert(alert, decision)
        for alert, decision in results
    ]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "alerts": alerts,
    }


# =========================================================
# Get one alert
# =========================================================

@router.get("/{alert_id}")
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db),
):
    """
    Return one alert with its associated risk decision.
    """

    alert, decision = get_alert_with_decision(
        alert_id,
        db,
    )

    return serialize_alert(
        alert,
        decision,
    )


# =========================================================
# Acknowledge alert
# =========================================================

@router.patch("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
):
    """
    Mark an open alert as acknowledged.
    """

    alert, decision = get_alert_with_decision(
        alert_id,
        db,
    )

    # ---------------------------------------------------------
    # Validate current state
    # ---------------------------------------------------------

    if alert.status == "acknowledged":
        raise HTTPException(
            status_code=409,
            detail="Alert is already acknowledged",
        )

    if alert.status == "resolved":
        raise HTTPException(
            status_code=409,
            detail="Resolved alerts cannot be acknowledged",
        )

    if alert.status != "open":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Alert cannot be acknowledged "
                f"from status '{alert.status}'"
            ),
        )

    # ---------------------------------------------------------
    # Update state
    # ---------------------------------------------------------

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(alert)

    return serialize_alert(
        alert,
        decision,
    )


# =========================================================
# Resolve alert
# =========================================================

@router.patch("/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
):
    """
    Resolve an acknowledged alert.
    """

    alert, decision = get_alert_with_decision(
        alert_id,
        db,
    )

    # ---------------------------------------------------------
    # Validate current state
    # ---------------------------------------------------------

    if alert.status == "resolved":
        raise HTTPException(
            status_code=409,
            detail="Alert is already resolved",
        )

    if alert.status == "open":
        raise HTTPException(
            status_code=409,
            detail=(
                "Alert must be acknowledged "
                "before it can be resolved"
            ),
        )

    if alert.status != "acknowledged":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Alert cannot be resolved "
                f"from status '{alert.status}'"
            ),
        )

    # ---------------------------------------------------------
    # Update state
    # ---------------------------------------------------------

    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(alert)

    return serialize_alert(
        alert,
        decision,
    )