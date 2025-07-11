# API Key Migration Guide

This guide covers how to set up the API key management system in your Hokusai deployment.

## Database Migration

### 1. Run the Migration Script

The easiest way to set up the API key tables is using the provided migration script:

```bash
# Run the migration to create tables
python scripts/migrate_api_keys.py up

# Check migration status
python scripts/migrate_api_keys.py status

# Rollback if needed
python scripts/migrate_api_keys.py down
```

### 2. Manual SQL Migration

If you prefer to run SQL directly:

```bash
# For PostgreSQL or SQLite
psql -U your_user -d your_database < scripts/create_api_key_tables.sql
```

## Environment Configuration

### Required Environment Variables

```bash
# Database connection (if not using defaults)
export DATABASE_URL=postgresql://user:pass@localhost/hokusai

# Redis connection for caching (optional)
export REDIS_URL=redis://localhost:6379

# Default user ID for CLI operations
export HOKUSAI_USER_ID=admin_user_123
```

### Optional Configuration

```bash
# API endpoint (defaults to http://localhost:8000)
export HOKUSAI_API_ENDPOINT=https://api.hokus.ai

# Cache TTL in seconds (default: 300)
export API_KEY_CACHE_TTL=600

# Default rate limit for new keys (default: 1000)
export DEFAULT_RATE_LIMIT=5000
```

## Initial Setup

### 1. Create Admin API Key

After running the migration, create your first admin API key:

```python
from src.auth.api_key_service import APIKeyService
from src.database.connection import DatabaseConnection
from src.database.operations import DatabaseOperations

# Initialize services
db = DatabaseConnection()
db_ops = DatabaseOperations(db)
service = APIKeyService(db_ops)

# Create admin key
admin_key = service.generate_api_key(
    user_id="admin",
    key_name="Admin Key",
    environment="production",
    rate_limit_per_hour=10000
)

print(f"Admin API Key: {admin_key.key}")
print(f"Key ID: {admin_key.key_id}")
```

**Important**: Save this key securely - it won't be retrievable later!

### 2. Configure Middleware

Update your FastAPI application to use the authentication middleware:

```python
from fastapi import FastAPI
from src.middleware.auth import APIKeyAuthMiddleware

app = FastAPI()

# Add authentication middleware
app.add_middleware(APIKeyAuthMiddleware)

# Your routes here...
```

### 3. Update Nginx/Load Balancer

If using a reverse proxy, ensure it forwards the necessary headers:

```nginx
# Forward authorization header
proxy_set_header Authorization $http_authorization;

# Forward client IP for IP restrictions
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP $remote_addr;
```

## Monitoring and Maintenance

### Check API Key Usage

```sql
-- Most active API keys
SELECT 
    k.name,
    k.user_id,
    COUNT(u.id) as request_count,
    AVG(u.response_time_ms) as avg_response_time
FROM api_keys k
JOIN api_key_usage u ON k.key_id = u.api_key_id
WHERE u.timestamp > NOW() - INTERVAL '24 hours'
GROUP BY k.key_id, k.name, k.user_id
ORDER BY request_count DESC
LIMIT 10;
```

### Clean Up Expired Keys

```sql
-- Deactivate expired keys
UPDATE api_keys 
SET is_active = FALSE 
WHERE expires_at < NOW() 
  AND is_active = TRUE;

-- Delete old usage data (keep 30 days)
DELETE FROM api_key_usage 
WHERE timestamp < NOW() - INTERVAL '30 days';
```

### Monitor Rate Limits

```python
# Check rate limit status for a key
from src.middleware.rate_limiter import RateLimiter

limiter = RateLimiter()
key_id = "your_key_id"

remaining = limiter.get_remaining_requests(key_id)
reset_time = limiter.get_reset_time(key_id)

print(f"Remaining requests: {remaining}")
print(f"Reset time: {reset_time}")
```

## Troubleshooting

### Migration Fails

If the migration fails:

1. Check database connectivity
2. Ensure user has CREATE TABLE permissions
3. Check for existing tables with same names
4. Review error logs in `logs/migration.log`

### Performance Issues

If API key validation is slow:

1. Ensure Redis is running and accessible
2. Check database indexes exist
3. Monitor cache hit rate
4. Consider increasing cache TTL

### Security Considerations

1. **Rotate admin keys regularly** - Every 90 days minimum
2. **Monitor for anomalies** - Unusual request patterns
3. **Implement alerting** - For failed auth attempts
4. **Regular audits** - Review active keys and permissions

## Next Steps

1. Set up monitoring dashboards
2. Configure automated key rotation
3. Implement usage analytics
4. Set up security alerts

For more details, see the [Authentication Documentation](../documentation/docs/authentication.md).