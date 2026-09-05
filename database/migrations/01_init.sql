-- database/migrations/01_init.sql

CREATE TABLE merchants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    razorpay_account_id TEXT UNIQUE NOT NULL,
    baseline_tx_count NUMERIC,
    baseline_failure_rate NUMERIC,
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
    updated_at TIMESTAMPTZ NOT NULL,
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

CREATE TABLE alerts (
    id UUID PRIMARY KEY,
    decision_id UUID NOT NULL UNIQUE REFERENCES decisions(id),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
);

-- Indexes aligned with our query patterns
CREATE INDEX idx_transactions_merchant_occurred ON transactions(merchant_id, occurred_at);
CREATE INDEX idx_windows_merchant_start ON windows(merchant_id, window_start);
CREATE INDEX idx_decisions_classification ON decisions(classification);
CREATE INDEX idx_alerts_merchant_created ON alerts(merchant_id, created_at);