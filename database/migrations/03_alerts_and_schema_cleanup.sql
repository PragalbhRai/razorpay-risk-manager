-- Bring databases created before the final schema in line with the models.
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS users;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'windows'
          AND column_name = 'finalized_at'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'windows'
          AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE windows RENAME COLUMN finalized_at TO updated_at;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS alerts (
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

CREATE INDEX IF NOT EXISTS idx_alerts_merchant_created
    ON alerts(merchant_id, created_at);