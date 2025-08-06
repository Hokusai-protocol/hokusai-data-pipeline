# Service Health and Recovery Scripts

This directory contains critical scripts for diagnosing and recovering from Hokusai registry service degradation issues.

## Overview

The Hokusai registry service implements enhanced health checks with circuit breaker protection for MLflow connectivity. When MLflow becomes unavailable, the service gracefully degrades instead of failing completely, allowing core functionality to continue.

## Scripts

### 1. Service Diagnostic Script

**File**: `diagnose_service_health.py`

Comprehensive diagnostic tool that checks all service components:
- API connectivity and response times
- Health endpoint functionality  
- Circuit breaker state and metrics
- MLflow service connectivity
- Database and Redis connectivity
- AWS infrastructure (ALB, ECS, RDS)
- Service metrics and performance

**Usage**:
```bash
# Basic diagnostic
./scripts/diagnose_service_health.py

# With specific API endpoint
./scripts/diagnose_service_health.py --api-url https://data.hokus.ai

# With authentication
./scripts/diagnose_service_health.py --api-key your-api-key

# Save detailed results
./scripts/diagnose_service_health.py --output diagnostic-results.json

# Verbose logging
./scripts/diagnose_service_health.py --verbose
```

**Exit Codes**:
- `0`: Service healthy
- `1`: Service degraded or has warnings
- `2`: Service critical/unhealthy

### 2. Service Recovery Script

**File**: `recover_service.py`

Automated recovery tool that handles common failure scenarios:
- Reset MLflow circuit breaker
- Restart unhealthy ECS services
- Check and fix ALB target health
- Wait for service stabilization
- Verify recovery success

**Usage**:
```bash
# Dry run (show what would be done)
./scripts/recover_service.py --dry-run

# Full recovery
./scripts/recover_service.py

# With specific endpoint
./scripts/recover_service.py --api-url https://data.hokus.ai

# Save recovery log
./scripts/recover_service.py --output recovery-log.json
```

**Recovery Actions**:
1. **Circuit Breaker Reset**: Resets MLflow circuit breaker to allow retry
2. **ECS Service Restart**: Forces new deployment of unhealthy services
3. **ALB Health Check**: Verifies load balancer targets are healthy
4. **Stabilization Wait**: Monitors service until stable (up to 5 minutes)
5. **Recovery Verification**: Confirms service is healthy

### 3. Enhanced Health Check Tester

**File**: `test_enhanced_health_checks.py`

Test suite for validating enhanced health check functionality:
- Basic health check responses
- Detailed health information
- Readiness checks with graceful degradation
- MLflow-specific health checks
- Circuit breaker status reporting
- Service metrics availability

**Usage**:
```bash
# Test local service
./scripts/test_enhanced_health_checks.py

# Test specific endpoint
./scripts/test_enhanced_health_checks.py --api-url http://localhost:8000

# Save test results
./scripts/test_enhanced_health_checks.py --output test-results.json
```

## Circuit Breaker Behavior

The MLflow circuit breaker implements a three-state pattern:

### States

1. **CLOSED** (Normal Operation)
   - All MLflow requests are allowed
   - Tracks failure count
   - Opens on threshold failures (default: 3)

2. **OPEN** (Protection Mode)
   - MLflow requests are blocked
   - Service returns degraded status but stays available
   - Auto-transitions to HALF_OPEN after timeout (default: 30s)

3. **HALF_OPEN** (Recovery Testing)
   - Limited MLflow requests allowed
   - Requires consecutive successes to close (default: 2)
   - Returns to OPEN on any failure

### Configuration

Circuit breaker settings can be configured via environment variables:

```bash
MLFLOW_CB_FAILURE_THRESHOLD=3      # Failures before opening
MLFLOW_CB_RECOVERY_TIMEOUT=30      # Seconds before retry
MLFLOW_CB_MAX_RECOVERY_ATTEMPTS=3  # Max recovery attempts
```

## Enhanced Health Endpoints

### `/health` - Basic Health Check
```json
{
  "status": "healthy|degraded|unhealthy",
  "services": {
    "mlflow": "healthy|degraded|recovering|unhealthy",
    "redis": "healthy|unhealthy",
    "postgres": "healthy|unhealthy"
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### `/ready` - Readiness Check
```json
{
  "ready": true,
  "can_serve_traffic": true,
  "degraded_mode": false,
  "checks": [
    {
      "name": "mlflow",
      "passed": false,
      "critical": false,
      "degraded_mode": true
    }
  ]
}
```

### `/health/mlflow` - MLflow Health Check
```json
{
  "connected": false,
  "circuit_breaker_state": "OPEN",
  "circuit_breaker_details": {
    "state": "OPEN",
    "failure_count": 5,
    "time_until_retry": 15,
    "recovery_attempts": 1
  },
  "error": "Circuit breaker is OPEN - MLflow unavailable",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### `/health/status` - Comprehensive Status
```json
{
  "service_name": "hokusai-registry",
  "overall_health": "degraded",
  "mlflow": {
    "status": {...},
    "circuit_breaker": {...}
  },
  "system_info": {
    "cpu_percent": 25.5,
    "memory_percent": 60.2
  }
}
```

### `/health/mlflow/reset` - Manual Circuit Breaker Reset
```bash
curl -X POST https://data.hokus.ai/health/mlflow/reset \
  -H "Authorization: Bearer your-api-key"
```

## Graceful Degradation

The service implements graceful degradation to maintain availability:

1. **MLflow Circuit Breaker Open**:
   - Health check returns `degraded` status (not `unhealthy`)
   - Readiness check returns `200 OK` with `degraded_mode: true`
   - Core API functionality remains available
   - MLflow-dependent features are temporarily disabled

2. **Database Issues**:
   - Readiness check returns `503 Service Unavailable`
   - Health check shows `unhealthy` status
   - Service cannot serve traffic

3. **Redis Issues**:
   - Service continues with limited caching
   - Performance may be degraded but service remains available

## Monitoring Integration

These scripts integrate with monitoring systems:

- **Prometheus Metrics**: Circuit breaker state and failure counts
- **CloudWatch**: AWS infrastructure health
- **Application Logs**: Detailed error information and recovery actions

## Troubleshooting

### Common Issues

1. **MLflow Circuit Breaker Stuck Open**:
   ```bash
   # Check status
   ./scripts/diagnose_service_health.py
   
   # Manual reset
   curl -X POST https://data.hokus.ai/health/mlflow/reset
   
   # Or use recovery script
   ./scripts/recover_service.py
   ```

2. **ECS Services Not Starting**:
   ```bash
   # Check AWS infrastructure
   ./scripts/diagnose_service_health.py --verbose
   
   # Force service restart
   ./scripts/recover_service.py
   ```

3. **Service Completely Unavailable**:
   ```bash
   # Full diagnostic
   ./scripts/diagnose_service_health.py --output diagnostic.json
   
   # Attempt recovery
   ./scripts/recover_service.py --output recovery.json
   ```

### Log Analysis

Check application logs for:
- Circuit breaker state changes
- MLflow connection failures
- ECS service health changes
- Recovery attempt results

### AWS Console Checks

1. **ECS**: Check service status and task health
2. **ALB**: Verify target group health
3. **RDS**: Confirm database availability
4. **CloudWatch**: Review metrics and alarms

## Best Practices

1. **Regular Health Monitoring**:
   - Run diagnostic script in cron jobs
   - Set up alerts on degraded status
   - Monitor circuit breaker metrics

2. **Recovery Procedures**:
   - Always try diagnostic script first
   - Use dry-run mode to understand recovery actions
   - Keep recovery logs for analysis

3. **Circuit Breaker Tuning**:
   - Adjust thresholds based on MLflow stability
   - Monitor recovery success rates
   - Consider shorter timeouts for faster recovery

4. **Infrastructure Monitoring**:
   - Monitor AWS service health
   - Track ECS service stability
   - Watch database performance metrics

## Support

For issues with these scripts or service recovery:

1. Check logs in `/var/log/hokusai/`
2. Run diagnostic script with `--verbose`
3. Review AWS CloudWatch logs
4. Contact infrastructure team with diagnostic output