# Model Registration Test Report

**Date**: 2025-07-21  
**API Key**: `hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL`  
**Test Status**: ❌ **FAILED** - Due to Infrastructure Issue

## Executive Summary

Model registration testing revealed that the authentication service is experiencing timeouts due to ALB routing conflicts. The root cause is that auth.hokus.ai and registry.hokus.ai share a single Application Load Balancer (ALB) without proper host-based routing rules for the auth service.

## Key Findings

### 1. Authentication Service Timeouts
- All API requests return "Authentication service timeout" after 5 seconds
- The auth service itself is healthy (confirmed via direct health check)
- Issue is with ALB routing, not the service itself

### 2. Root Cause: Missing ALB Rules
- Current ALB configuration only has host-based rules for `registry.hokus.ai`
- No specific routing rules exist for `auth.hokus.ai`
- Auth requests are being misrouted via generic path-based rules

### 3. Shared Infrastructure Conflict
- Single ALB serves both domains
- Routing rule priorities cause conflicts
- Recent changes to support registry.hokus.ai inadvertently broke auth routing

## Test Results

| Test | Result | Details |
|------|--------|---------|
| API Key Format | ✅ | Valid format `hk_live_*` |
| Auth Service Health | ✅ | Service responding at https://auth.hokus.ai/health |
| API Key Validation | ❌ | Timeout after 5 seconds |
| MLflow Registration | ❌ | Cannot authenticate |
| Bearer Token Auth | ❌ | All requests timeout |

## Solution Implemented

### Dedicated ALBs Architecture

Created Terraform configuration for separate ALBs:

1. **Auth ALB** (`auth.hokus.ai`)
   - Dedicated load balancer for authentication service
   - Simple routing rules for `/api/v1/*` and health checks
   - No conflicts with other services

2. **Registry ALB** (`registry.hokus.ai`)
   - Dedicated load balancer for MLflow and API services
   - Clear routing for `/mlflow/*` and `/api/*` paths
   - Isolated from auth service

### Benefits
- Eliminates routing conflicts permanently
- Better security isolation
- Independent scaling and maintenance
- Simplified debugging

## Files Created

1. **`infrastructure/terraform/dedicated-albs.tf`**
   - Complete Terraform configuration for both ALBs
   - Target group definitions
   - Listener rules and routing
   - DNS record configuration

2. **`DEDICATED_ALB_MIGRATION_PLAN.md`**
   - Step-by-step migration guide
   - Rollback procedures
   - Testing checklist

3. **`test_dedicated_albs.py`**
   - Comprehensive test script
   - Validates both ALBs after deployment
   - Tests domain isolation

## Next Steps

1. **Review and Approve** the dedicated ALB solution
2. **Deploy Infrastructure**:
   ```bash
   cd infrastructure/terraform
   terraform plan
   terraform apply
   ```

3. **Update DNS Records** to point to new ALBs

4. **Run Validation Tests**:
   ```bash
   export HOKUSAI_API_KEY="hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
   python test_dedicated_albs.py
   ```

5. **Re-run Model Registration** once infrastructure is deployed

## Conclusion

The model registration feature is blocked by an infrastructure issue, not a code problem. The API key provided appears valid, but cannot be validated due to ALB routing conflicts. Implementing dedicated ALBs will resolve this issue and prevent similar problems in the future.

**Estimated Time to Resolution**: 2-4 hours for deployment and testing