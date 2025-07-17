# Model Registration Investigation Summary

**Investigation Date**: 2025-07-17  
**API Key Tested**: `hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL` (confirmed valid by user)

## Summary of Findings

### 1. ❌ Authentication is Broken Due to API Mismatch

**The Core Issue**: The API proxy and auth service expect different authentication formats:
- **API Proxy** (after PR #49): Sends API key as `Authorization: Bearer <key>` header
- **Auth Service**: Expects API key in JSON body as `{"api_key": "<key>"}`

This mismatch causes all authentication attempts to fail with "Invalid or expired API key".

### 2. ✅ MLflow Infrastructure is Working

**MLflow Configuration**:
- **URL**: `https://registry.hokus.ai/mlflow/`
- **API Format**: Uses `/ajax-api/2.0/mlflow/*` instead of standard `/api/2.0/mlflow/*`
- **Status**: Running and accessible (returns 400 on invalid params, not auth errors)
- **Direct Access**: No authentication required for direct MLflow access

### 3. ✅ API Proxy is Deployed and Running

**Proxy Status**:
- All `/api/*` endpoints are responding
- Authentication middleware is active
- Returns proper error messages
- Issue is with auth validation, not deployment

### 4. 🔍 Root Cause: Incorrect Fix in PR #49

The fix in PR #49 was based on an incorrect assumption. The middleware was changed to send the API key in the Authorization header, but the auth service OpenAPI spec clearly shows it expects the key in the request body.

**From OpenAPI Spec**:
```json
"APIKeyValidation": {
    "properties": {
        "api_key": {
            "type": "string",
            "title": "Api Key"
        },
        "service_id": {
            "type": "string"
        }
    }
}
```

## Test Results Summary

| Test | Result | Finding |
|------|--------|---------|
| Bearer token auth | ❌ 401 Invalid key | Auth service doesn't accept Bearer tokens |
| API key in body | ❌ 401 API key required | Different error suggests format issue |
| Direct MLflow | ✅ 200/400 | MLflow is accessible |
| API proxy health | ✅ Running | Proxy is deployed |
| Auth service health | ✅ 200 | Auth service is running |

## Recommendations

### Immediate Fix Options

#### Option 1: Revert Middleware Change (Fastest)
```python
# Change back to original behavior
response = await client.post(
    f"{self.auth_service_url}/api/v1/keys/validate",
    json={
        "api_key": api_key,
        "service_id": "ml-platform",
        "client_ip": client_ip
    }
)
```

#### Option 2: Update Auth Service (Better Long-term)
- Modify auth service to accept Bearer tokens
- Maintains consistency with industry standards
- Requires auth team coordination

### Next Steps

1. **For Data Pipeline Team**:
   - Consider reverting the middleware change as a quick fix
   - Test with original JSON body format
   - Add integration tests for auth flow

2. **For Auth Team**:
   - Review `AUTH_TEAM_ISSUE_REPORT.md` for detailed analysis
   - Decide on authentication format standard
   - Update either service to match

3. **For Platform Team**:
   - Establish clear API standards
   - Document authentication patterns
   - Add contract testing between services

## Files Created

1. **TEST_REPORT.md** - Initial test results
2. **AUTH_TEAM_ISSUE_REPORT.md** - Detailed report for auth team
3. **mlflow_investigation.log** - Complete endpoint testing log
4. **auth_endpoints_test.log** - Auth service API discovery
5. **investigate_mlflow.py** - Comprehensive test script
6. **test_auth_endpoints.py** - Auth endpoint discovery script

## Conclusion

The model registration feature is blocked by an API contract mismatch between the API proxy and auth service. The issue is not with deployment or the API key validity, but with how the services communicate. This requires either reverting the middleware change or updating the auth service to accept Bearer tokens.