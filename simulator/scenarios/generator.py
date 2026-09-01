import random
import time
import requests
from datetime import datetime, timezone

API_URL = "http://localhost:8000/api/v1/transactions"

MERCHANT_IDS = ["mer_val_101", "mer_lux_202", "mer_elec_303", "mer_Apparel_404"]
CUSTOMER_EMAILS = ["test.user1@gmail.com", "fraudster99@riskmail.io", "priya.sharma@yahoo.com", "alex.smith@outlook.com"]
PAYMENT_METHODS = ["upi", "card", "netbanking", "wallet"]
CURRENCIES = ["INR", "USD"]

def generate_random_transaction():
    is_suspicious = random.random() < 0.15
    amount = round(random.uniform(500.0, 150000.0), 2) if is_suspicious else round(random.uniform(100.0, 5000.0), 2)
    
    payload = {
        "transaction_id": f"txn_{random.randint(10000000, 99999999)}",
        "merchant_id": random.choice(MERCHANT_IDS),
        "customer_email": random.choice(CUSTOMER_EMAILS),
        "amount": amount,
        "currency": "INR",
        "payment_method": random.choice(PAYMENT_METHODS),
        "ip_address": f"192.168.{random.randint(0, 255)}.{random.randint(0, 255)}",
        "device_fingerprint": f"dev_fp_{random.randint(1000, 9999)}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return payload

if __name__ == "__main__":
    print("Starting Live Transaction Ingestion Stream... Press Ctrl+C to stop.")
    while True:
        tx = generate_random_transaction()
        try:
            response = requests.post(API_URL, json=tx)
            if response.status_code == 201:
                print(f"Successfully ingested: {tx['transaction_id']} | Amount: {tx['amount']} INR | Status: {response.json().get('risk_status')}")
            else:
                print(f"Failed to ingest {tx['transaction_id']}: {response.text}")
        except Exception as e:
            print(f"Connection error: {e}")
        
        time.sleep(2.0)