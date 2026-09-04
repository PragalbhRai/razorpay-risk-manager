"""Create a merchant and print its API key once."""

import argparse
import sys
import uuid
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.api_key import generate_api_key, hash_api_key
from app.db.session import SessionLocal
from app.models.merchant import MerchantModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--razorpay-account-id", required=True)
    args = parser.parse_args()

    api_key = generate_api_key()
    db = SessionLocal()
    try:
        merchant = MerchantModel(
            id=uuid.uuid4(),
            name=args.name,
            razorpay_account_id=args.razorpay_account_id,
            api_key_hash=hash_api_key(api_key),
        )
        db.add(merchant)
        db.commit()
        print(f"Merchant ID: {merchant.id}")
        print(f"API key (store securely; shown only now): {api_key}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()