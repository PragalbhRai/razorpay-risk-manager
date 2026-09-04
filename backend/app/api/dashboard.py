from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alert import AlertModel
from app.models.decision import DecisionModel
from app.models.merchant import MerchantModel
from app.models.transaction import TransactionModel
from app.models.window import WindowModel


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"],
)


# =========================================================
# Dashboard summary
# =========================================================

@router.get("/summary")
def dashboard_summary(
    merchant_id: str | None = Query(
        default=None,
        description="Optional merchant UUID filter",
    ),
    db: Session = Depends(get_db),
):
    """
    Return high-level fraud-risk metrics for the dashboard.
    """

    merchant_uuid = None

    if merchant_id:
        try:
            merchant_uuid = UUID(merchant_id)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="merchant_id must be a valid UUID",
            )

    # -----------------------------------------------------
    # Transaction count
    # -----------------------------------------------------

    transaction_query = db.query(
        func.count(TransactionModel.transaction_id)
    )

    if merchant_uuid:
        transaction_query = transaction_query.filter(
            TransactionModel.merchant_id == merchant_uuid
        )

    total_transactions = transaction_query.scalar() or 0

    # -----------------------------------------------------
    # Window count
    # -----------------------------------------------------

    window_query = db.query(
        func.count(WindowModel.id)
    )

    if merchant_uuid:
        window_query = window_query.filter(
            WindowModel.merchant_id == merchant_uuid
        )

    total_windows = window_query.scalar() or 0

    # -----------------------------------------------------
    # Decision classification counts
    # -----------------------------------------------------

    decision_query = db.query(
        DecisionModel.classification,
        func.count(DecisionModel.id),
    ).join(
        WindowModel,
        DecisionModel.window_id == WindowModel.id,
    )

    if merchant_uuid:
        decision_query = decision_query.filter(
            WindowModel.merchant_id == merchant_uuid
        )

    classification_rows = (
        decision_query
        .group_by(DecisionModel.classification)
        .all()
    )

    classification_counts = {
        "normal": 0,
        "watch": 0,
        "alert": 0,
    }

    for classification, count in classification_rows:
        if classification in classification_counts:
            classification_counts[classification] = count

    # -----------------------------------------------------
    # Open alerts
    # -----------------------------------------------------

    alert_query = db.query(
        func.count(AlertModel.id)
    ).filter(
        AlertModel.status == "open"
    )

    if merchant_uuid:
        alert_query = alert_query.filter(
            AlertModel.merchant_id == merchant_uuid
        )

    open_alerts = alert_query.scalar() or 0

    # -----------------------------------------------------
    # Average risk score
    # -----------------------------------------------------

    risk_query = db.query(
        func.avg(DecisionModel.risk_score)
    ).join(
        WindowModel,
        DecisionModel.window_id == WindowModel.id,
    )

    if merchant_uuid:
        risk_query = risk_query.filter(
            WindowModel.merchant_id == merchant_uuid
        )

    average_risk_score = risk_query.scalar()

    if average_risk_score is not None:
        average_risk_score = round(
            float(average_risk_score),
            2,
        )

    return {
        "total_transactions": total_transactions,
        "total_windows": total_windows,
        "normal_count": classification_counts["normal"],
        "watch_count": classification_counts["watch"],
        "alert_count": classification_counts["alert"],
        "open_alerts": open_alerts,
        "average_risk_score": average_risk_score,
    }


# =========================================================
# Risk timeline
# =========================================================

@router.get("/timeline")
def dashboard_timeline(
    merchant_id: str | None = Query(
        default=None,
        description="Optional merchant UUID filter",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
):
    """
    Return recent risk windows for charts and timeline views.
    """

    merchant_uuid = None

    if merchant_id:
        try:
            merchant_uuid = UUID(merchant_id)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="merchant_id must be a valid UUID",
            )

    query = (
        db.query(
            WindowModel,
            DecisionModel,
        )
        .outerjoin(
            DecisionModel,
            WindowModel.id == DecisionModel.window_id,
        )
    )

    if merchant_uuid:
        query = query.filter(
            WindowModel.merchant_id == merchant_uuid
        )

    results = (
        query
        .order_by(
            WindowModel.window_start.desc()
        )
        .limit(limit)
        .all()
    )

    timeline = []

    for window, decision in reversed(results):

        timeline.append({
            "window_id": str(window.id),
            "merchant_id": str(window.merchant_id),
            "window_start": (
                window.window_start.isoformat()
            ),
            "window_end": (
                window.window_end.isoformat()
            ),
            "tx_count": window.tx_count,
            "failure_rate": round(
                float(window.failure_rate),
                4,
            ),
            "amount_mean": round(
                float(window.amount_mean),
                2,
            ),
            "amount_stddev": round(
                float(window.amount_stddev),
                2,
            ),
            "baseline_deviation_score": round(
                float(
                    window.baseline_deviation_score
                ),
                4,
            ),
            "risk_score": (
                float(decision.risk_score)
                if decision
                else None
            ),
            "classification": (
                decision.classification
                if decision
                else None
            ),
        })

    return {
        "count": len(timeline),
        "timeline": timeline,
    }


# =========================================================
# Merchant overview
# =========================================================

@router.get("/merchants/{merchant_id}")
def merchant_dashboard(
    merchant_id: str,
    db: Session = Depends(get_db),
):
    """
    Return dashboard information for one merchant.
    """

    try:
        merchant_uuid = UUID(merchant_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="merchant_id must be a valid UUID",
        )

    merchant = (
        db.query(MerchantModel)
        .filter(
            MerchantModel.id == merchant_uuid
        )
        .first()
    )

    if merchant is None:
        raise HTTPException(
            status_code=404,
            detail="Merchant not found",
        )

    summary = dashboard_summary(
        merchant_id=merchant_id,
        db=db,
    )

    recent_alerts = (
        db.query(AlertModel)
        .filter(
            AlertModel.merchant_id
            == merchant_uuid
        )
        .order_by(
            AlertModel.created_at.desc()
        )
        .limit(10)
        .all()
    )

    alerts = [
        {
            "id": str(alert.id),
            "severity": alert.severity,
            "status": alert.status,
            "title": alert.title,
            "message": alert.message,
            "created_at": (
                alert.created_at.isoformat()
                if alert.created_at
                else None
            ),
        }
        for alert in recent_alerts
    ]

    return {
        "merchant": {
            "id": str(merchant.id),
            "name": merchant.name,
            "razorpay_account_id": (
                merchant.razorpay_account_id
            ),
        },
        "summary": summary,
        "recent_alerts": alerts,
    }