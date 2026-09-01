from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.transaction import TransactionCreate
from app.models.transaction import TransactionModel
from app.streaming.redis_client import redis_client


router = APIRouter(
    prefix="/api/v1/transactions",
    tags=["transactions"],
)

TRANSACTION_STREAM = "transactions"


@router.post("", status_code=201)
def ingest_transaction(
    tx_in: TransactionCreate,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # Validate UUID fields
    # ---------------------------------------------------------

    try:
        transaction_uuid = UUID(tx_in.transaction_id)
        merchant_uuid = UUID(tx_in.merchant_id)

    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                "transaction_id and merchant_id "
                "must be valid UUIDs"
            ),
        )

    # ---------------------------------------------------------
    # Idempotency check
    #
    # Razorpay event ID is the external event identity.
    # The same webhook/event may be delivered multiple times.
    # ---------------------------------------------------------

    existing_event = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.razorpay_event_id
            == tx_in.razorpay_event_id
        )
        .first()
    )

    if existing_event:
        return {
            "status": "success",
            "transaction_id": str(
                existing_event.transaction_id
            ),
            "risk_status": existing_event.status,
            "duplicate": True,
        }

    # ---------------------------------------------------------
    # Transaction ID check
    # ---------------------------------------------------------

    existing_transaction = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.transaction_id
            == transaction_uuid
        )
        .first()
    )

    if existing_transaction:
        return {
            "status": "success",
            "transaction_id": str(
                existing_transaction.transaction_id
            ),
            "risk_status": existing_transaction.status,
            "duplicate": True,
        }

    # ---------------------------------------------------------
    # Create transaction
    # ---------------------------------------------------------

    db_tx = TransactionModel(
        transaction_id=transaction_uuid,
        merchant_id=merchant_uuid,
        razorpay_event_id=tx_in.razorpay_event_id,
        razorpay_payment_id=tx_in.razorpay_payment_id,
        amount=tx_in.amount,
        payment_method_type=tx_in.payment_method_type,
        payment_method_ref_hash=(
            tx_in.payment_method_ref_hash
        ),
        status=tx_in.status,
        occurred_at=tx_in.occurred_at,
    )

    db.add(db_tx)

    # ---------------------------------------------------------
    # Protect against concurrent duplicate requests.
    #
    # The database UNIQUE constraint on razorpay_event_id is
    # the final authority.
    # ---------------------------------------------------------

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        existing_event = (
            db.query(TransactionModel)
            .filter(
                TransactionModel.razorpay_event_id
                == tx_in.razorpay_event_id
            )
            .first()
        )

        if existing_event:
            return {
                "status": "success",
                "transaction_id": str(
                    existing_event.transaction_id
                ),
                "risk_status": existing_event.status,
                "duplicate": True,
            }

        raise HTTPException(
            status_code=409,
            detail="Transaction conflicts with an existing record",
        )

    db.refresh(db_tx)

    # ---------------------------------------------------------
    # Publish transaction to Redis Stream
    # ---------------------------------------------------------

    try:
        redis_client.xadd(
            TRANSACTION_STREAM,
            {
                "transaction_id": str(
                    db_tx.transaction_id
                ),
                "merchant_id": str(
                    db_tx.merchant_id
                ),
                "amount": str(db_tx.amount),
                "payment_method_type": (
                    db_tx.payment_method_type
                ),
                "status": db_tx.status,
                "occurred_at": (
                    db_tx.occurred_at.isoformat()
                ),
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Transaction stored but event "
                f"publishing failed: {exc}"
            ),
        )

    return {
        "status": "success",
        "transaction_id": str(
            db_tx.transaction_id
        ),
        "risk_status": db_tx.status,
        "duplicate": False,
    }