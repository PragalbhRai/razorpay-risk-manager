-- database/migrations/01_init.sql

CREATE TABLE merchants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    razorpay_account_id TEXT UNIQUE NOT NULL,
    baseline_tx_count NUMERIC,
    baseline_failure_rate NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
    id UUID PRIMARY KEY,
    merchant_id UUID REFERENCES merchants(id),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('merchant', 'analyst', 'admin')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE transactions (
    id UUID PRIMARY KEY,
    merchant_id UUID REFERENCES merchants(id),
    razorpay_event_id TEXT UNIQUE NOT NULL,
    razorpay_payment_id TEXT,
    amount NUMERIC NOT NULL,
    payment_method_type TEXT NOT NULL,
    payment_method_ref_hash TEXT,
    status TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE windows (
    id UUID PRIMARY KEY,
    merchant_id UUID REFERENCES merchants(id),
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    finalized_at TIMESTAMPTZ NOT NULL,
    tx_count INT NOT NULL,
    distinct_method_count INT NOT NULL,
    failure_rate NUMERIC NOT NULL,
    amount_mean NUMERIC NOT NULL,
    amount_stddev NUMERIC NOT NULL,
    baseline_deviation_score NUMERIC NOT NULL,
    late_event_count INT DEFAULT 0,
    UNIQUE(merchant_id, window_start)
);

CREATE TABLE decisions (
    id UUID PRIMARY KEY,
    window_id UUID REFERENCES windows(id) UNIQUE,
    risk_score NUMERIC NOT NULL,
    classification TEXT NOT NULL CHECK (classification IN ('normal','watch','alert')),
    explanation TEXT NOT NULL,
    model_version TEXT NOT NULL,
    decided_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE feedback (
    id UUID PRIMARY KEY,
    decision_id UUID REFERENCES decisions(id) UNIQUE,
    reviewer_id UUID REFERENCES users(id),
    verdict TEXT NOT NULL CHECK (verdict IN ('confirmed_fraud', 'false_positive', 'uncertain')),
    notes TEXT,
    reviewed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload JSONB NOT NULL,
    logged_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes aligned with our query patterns
CREATE INDEX idx_transactions_merchant_occurred ON transactions(merchant_id, occurred_at);
CREATE INDEX idx_windows_merchant_start ON windows(merchant_id, window_start);
CREATE INDEX idx_decisions_classification ON decisions(classification);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);