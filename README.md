# Razorpay Risk Manager

## Fraud-Spike Detector

Razorpay Risk Manager is a portfolio-scale fraud-spike detection system for merchant transaction streams. It ingests payment events, groups them into deterministic five-minute merchant windows, evaluates rule-based risk signals, persists decisions, and exposes alerts through a React operations dashboard.

The project is designed to make sudden changes in transaction behavior visible: unusual volume, payment failures, baseline deviation, payment-method diversity, and unusually large transaction amounts.

## Features

- Merchant API-key authentication using `X-API-Key`
- Server-side merchant isolation across transactions, alerts, and dashboard queries
- FastAPI transaction ingestion
- Redis Streams event transport
- PostgreSQL persistence for merchants, transactions, windows, decisions, and alerts
- Deterministic five-minute aggregation
- Rule-based risk engine v2 with a low-sample alert guard
- Risk decision persistence and explanation text
- Fraud alert lifecycle: `open` -> `acknowledged` -> `resolved`
- React + Vite risk operations dashboard with auto-refresh
- Seeded transaction simulator with local ground-truth labels
- Evaluation harness for window-level TP/TN/FP/FN and classification metrics

## Architecture

```mermaid
flowchart LR
		M[Merchant / Simulator] --> API[FastAPI]
		API --> PG[(PostgreSQL)]
		API --> RS[(Redis Stream)]
		RS --> W[Risk Worker]
		W --> WIN[Deterministic 5-minute Window]
		WIN --> RE[Rule-based Risk Engine v2]
		RE --> DA[Decision + Alert]
		DA --> AA[Alert API]
		AA --> UI[React Dashboard]
```

The API stores the transaction in PostgreSQL and publishes a stream event. The worker reconstructs the complete merchant window from PostgreSQL, evaluates it, and upserts the corresponding window, decision, and alert records.

## Risk Engine

The rule-based engine scores each merchant window using:

- **Transaction volume:** 5 or more transactions adds an elevated-volume signal; 10 or more adds a high-volume signal.
- **Baseline deviation:** volume at least 1.5x or 2x the historical merchant baseline adds deviation points.
- **Payment failure rate:** rates of at least 25% or 50% add failure-rate points.
- **Baseline failure deviation:** failure rate above the historical failure baseline adds further points.
- **Payment-method diversity:** two or more methods and four or more methods add diversity points.
- **Average transaction amount:** an average amount of at least INR 10,000 adds a large-amount signal.

Scores are capped at 100:

- `alert`: score at least 70 and sufficient alert evidence
- `watch`: score at least 40 but below the alert condition
- `normal`: score below 40

Version 2 adds a low-sample alert guard. A score cannot become an `alert` unless the window has at least 10 transactions or at least 5 failed transactions. This reduces noisy alerts from very small windows while preserving obvious high-volume spikes.

## Authentication and Security

Protected API requests send:

```http
X-API-Key: <merchant-api-key>
```

The backend hashes supplied keys with SHA-256 and persists only the hash in `merchants.api_key_hash`. Plaintext keys are not stored in PostgreSQL, ground-truth JSONL, or evaluation output. Merchant ownership is derived from the authenticated key and enforced in server-side queries; client-supplied merchant IDs cannot select another merchant's data.

Never commit a real API key. Local `.env` files are ignored by Git. The checked-in `.env.example` files contain placeholders only.

## Evaluation Methodology

The simulator writes transaction-level records with local ground-truth labels. The evaluator aggregates those labels by merchant and deterministic five-minute `window_start`, marking a window fraudulent if any generated transaction in that window is labeled fraudulent.

It compares those window labels with persisted risk decisions:

- `alert` is predicted fraud
- `normal` and `watch` are predicted non-fraud

It reports:

- True positives (`TP`)
- True negatives (`TN`)
- False positives (`FP`)
- False negatives (`FN`)
- Precision, recall, F1
- False-positive rate
- Unmatched windows

## Current Results

Verified fraud-spike evaluation:

```text
Windows evaluated: 11
TP: 1
TN: 10
FP: 0
FN: 0

Precision: 1.0000
Recall: 1.0000
F1: 1.0000
False Positive Rate: 0.0000
Unmatched windows: 0
```

Broader v2 benchmark findings across the tested seeds:

- **normal:** zero false positives
- **fraud_spike:** perfect detection
- **recovery:** perfect detection
- **gradual_fraud:** conservative detection with some false negatives and zero false positives

The gradual-fraud result is expected from the current low-sample alert guard: early, lower-volume fraud stages may remain `watch` rather than opening an alert.

## Repository Structure

```text
backend/
	app/
		api/             FastAPI transaction, alert, and dashboard routes
		auth/            API-key authentication dependency
		aggregation/    Deterministic five-minute windowing
		db/              SQLAlchemy session setup
		models/          Merchant, transaction, window, decision, alert models
		risk/            Rule-based risk engine v2
		streaming/       Redis Stream worker
	scripts/           Merchant provisioning CLI
	tests/             Local pytest unit/API tests
database/migrations/ PostgreSQL schema and additive migrations
frontend/            React + Vite dashboard
simulator/
	scenarios/         Seeded transaction generator and ground truth output
	evaluation/        Ground-truth versus decision evaluator
docker-compose.yml   PostgreSQL, Redis, API, worker, and frontend services
```

## Prerequisites

- Docker Desktop with Docker Compose
- Python 3.12 or compatible Python version
- Node.js 20+ and npm for local frontend development
- A provisioned merchant API key for authenticated simulator and dashboard requests

## Local Setup

Start the complete stack:

```powershell
docker compose up -d --build
```

Services:

- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Frontend: `http://localhost:5173`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Database migrations are mounted into PostgreSQL initialization. The additive API-key migration is `database/migrations/02_add_merchant_api_key_hash.sql`.

## Provision a Merchant

From the backend directory, create a merchant and receive its plaintext key once:

```powershell
cd backend
python scripts/provision_merchant.py `
	--name "Test Merchant" `
	--razorpay-account-id acc_test_001
```

The command prints the merchant ID and API key. Store the key securely; it is not recoverable from the database after creation.

## Configure API Keys

For the simulator:

```powershell
$env:SIMULATOR_API_KEY = "<your-merchant-api-key>"
```

For the Vite dashboard, create a local `frontend/.env.local` file:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_API_KEY=<your-merchant-api-key>
```

For the Docker frontend service, set `VITE_API_KEY` in the shell before starting Compose:

```powershell
$env:VITE_API_KEY = "<your-merchant-api-key>"
docker compose up -d --build frontend
```

Do not put real keys in tracked files.

## Run the Simulator

The simulator uses seeded randomness, backdated timestamps, and naturally aligned five-minute windows. It supports `normal`, `fraud_spike`, `gradual_fraud`, and `recovery`.

Send a fraud-spike scenario:

```powershell
python simulator/scenarios/generator.py `
	--scenario fraud_spike `
	--seed 42 `
	--output $env:TEMP\risk-ground-truth.jsonl
```

Use `--dry-run` to generate JSONL without calling the API. Repeat `--merchant-id` to target multiple existing merchants. API payloads retain the merchant ID for compatibility, but ownership is enforced by the API key.

## Run Evaluation

The evaluator requires the same merchant API key to query the dashboard timeline:

```powershell
python simulator/evaluation/evaluate.py `
	--ground-truth $env:TEMP\risk-ground-truth.jsonl `
	--json-output $env:TEMP\risk-evaluation.json
```

Set `SIMULATOR_API_KEY` before running it. The evaluator fails clearly if the key is missing or reports unmatched windows instead of silently scoring incomplete data.

## Run Backend Tests

```powershell
cd backend
python -m pip install -r requirements.txt
python -m pytest -q
```

The test suite uses isolated unit fixtures and FastAPI `TestClient`; it does not require manually running PostgreSQL or Redis.

## API Overview

All routes below require `X-API-Key` unless noted otherwise.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check; returns `{"status":"ok"}` |
| `POST` | `/api/v1/transactions` | Ingest a transaction and publish it to Redis Streams |
| `GET` | `/api/v1/dashboard/summary` | Authenticated merchant summary |
| `GET` | `/api/v1/dashboard/timeline` | Authenticated merchant risk windows |
| `GET` | `/api/v1/dashboard/merchants/me` | Authenticated merchant details and recent alerts |
| `GET` | `/api/v1/dashboard/merchants/{merchant_id}` | Legacy-compatible merchant details route, restricted to the authenticated merchant |
| `GET` | `/api/v1/alerts` | Authenticated merchant alert list with filters and pagination |
| `GET` | `/api/v1/alerts/{alert_id}` | Retrieve an owned alert |
| `PATCH` | `/api/v1/alerts/{alert_id}/acknowledge` | Acknowledge an owned open alert |
| `PATCH` | `/api/v1/alerts/{alert_id}/resolve` | Resolve an owned acknowledged alert |

## Alert Lifecycle

When a risk decision is classified as `alert`, the worker creates an open alert:

```text
open --acknowledge--> acknowledged --resolve--> resolved
```

The dashboard exposes the current status and calls the acknowledge/resolve endpoints. Resolved alerts remain available in alert history but are no longer active alerts.

## Limitations and Current Status

- The system is a focused fraud-spike detector, not a general fraud decisioning platform.
- The risk engine is deterministic and rule-based; it is not an ML model.
- Gradual fraud can produce false negatives while signals accumulate.
- The current deployment is a Docker Compose development/demo stack.
- Worker idempotency, richer audit workflows, and broader automated integration coverage remain future work.
- The dashboard currently monitors the authenticated merchant configured for its API key.

## Future Scaling Direction

A production-scale direction would be:

```text
Load balancer
	-> horizontally scaled FastAPI instances
	-> Redis Streams
	-> horizontally scaled risk workers
	-> PostgreSQL and Redis
```

The current project does not claim production readiness or validation at 1M requests/sec. Those targets would require load testing, capacity planning, operational observability, high-availability data services, stronger key management, and deployment-specific reliability work.

## Technologies

- Python 3.12
- FastAPI and Uvicorn
- Pydantic
- SQLAlchemy
- PostgreSQL 15
- Redis 7 Streams
- React 19
- Vite
- Recharts
- Docker Compose
- pytest