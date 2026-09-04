ALTER TABLE merchants
ADD COLUMN IF NOT EXISTS api_key_hash VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_merchants_api_key_hash
ON merchants (api_key_hash)
WHERE api_key_hash IS NOT NULL;