import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.merchant import MerchantModel


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def get_current_merchant(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MerchantModel:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "API-Key"},
        )

    supplied_hash = hash_api_key(x_api_key)
    merchant = (
        db.query(MerchantModel)
        .filter(MerchantModel.api_key_hash == supplied_hash)
        .first()
    )

    if merchant is None or not hmac.compare_digest(
        merchant.api_key_hash or "",
        supplied_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "API-Key"},
        )

    return merchant