-- Database schema for API key management
-- Compatible with PostgreSQL and SQLite

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    key_id VARCHAR(36) PRIMARY KEY,
    key_hash VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    rate_limit_per_hour INTEGER DEFAULT 1000,
    allowed_ips TEXT, -- JSON array
    environment VARCHAR(20) DEFAULT 'production',
    
    -- Indexes
    INDEX idx_key_hash (key_hash),
    INDEX idx_user_id (user_id),
    INDEX idx_is_active (is_active),
    INDEX idx_expires_at (expires_at)
);

-- API Key Usage table for analytics
CREATE TABLE IF NOT EXISTS api_key_usage (
    id SERIAL PRIMARY KEY,
    api_key_id VARCHAR(36) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    response_time_ms INTEGER,
    status_code INTEGER,
    
    -- Foreign key
    FOREIGN KEY (api_key_id) REFERENCES api_keys(key_id) ON DELETE CASCADE,
    
    -- Indexes
    INDEX idx_api_key_id (api_key_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_endpoint (endpoint)
);

-- Create indexes for PostgreSQL (if not using SQLite)
-- Note: SQLite creates indexes automatically with CREATE INDEX in table definition

-- For PostgreSQL, you might want these additional indexes:
-- CREATE INDEX CONCURRENTLY idx_api_keys_hash ON api_keys USING btree (key_hash);
-- CREATE INDEX CONCURRENTLY idx_api_keys_user ON api_keys USING btree (user_id) WHERE is_active = true;
-- CREATE INDEX CONCURRENTLY idx_usage_key_time ON api_key_usage USING btree (api_key_id, timestamp DESC);

-- Add comments for documentation
COMMENT ON TABLE api_keys IS 'Stores API keys for authentication';
COMMENT ON COLUMN api_keys.key_hash IS 'BCrypt hash of the API key';
COMMENT ON COLUMN api_keys.key_prefix IS 'Visible prefix for key identification (e.g., hk_live_abc)';
COMMENT ON COLUMN api_keys.allowed_ips IS 'JSON array of allowed IP addresses';

COMMENT ON TABLE api_key_usage IS 'Tracks API key usage for analytics and rate limiting';
COMMENT ON COLUMN api_key_usage.response_time_ms IS 'Response time in milliseconds';

-- Sample data for testing (DO NOT USE IN PRODUCTION)
-- INSERT INTO api_keys (key_id, key_hash, key_prefix, user_id, name, created_at, rate_limit_per_hour)
-- VALUES (
--     'test-key-123',
--     '$2b$12$K.0D7Ov7VYqVzMKYHhqy3.8sJ3J3J3J3J3J3J3J3J3J3J3J3J3J3J',
--     'hk_test_abc',
--     'test_user_123',
--     'Test API Key',
--     NOW(),
--     100
-- );