# LSCOR Model Registration Bug Investigation Plan

## Bug Summary

**Third-party user attempting to register the LSCOR lead scoring model encountered multiple critical blocking issues that prevent successful model registration with the Hokusai platform.**

### Reported Issues:
1. **Missing Tracking Module Components** - hokusai.tracking module appears empty despite documentation referencing ExperimentManager and PerformanceTracker
2. **ModelRegistry Constructor Mismatch** - Documentation shows no-parameter constructor but SDK expects tracking_uri parameter
3. **API Authentication Error (403 Forbidden)** - MLflow API authentication fails when using MLFLOW_TRACKING_TOKEN
4. **register_tokenized_model Method Missing** - Method referenced in docs doesn't appear to exist in SDK (only register_baseline found)

### User Environment:
- Python 3.11.8
- hokusai-ml-platform: Latest from GitHub (commit b1698a58)
- MLflow 2.9.0
- API Key: hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN

## Impact Analysis

### Severity: **CRITICAL**
- **User Impact**: Complete blockage of model registration workflow for third-party developers
- **Business Impact**: Prevents external users from successfully onboarding models to the platform
- **Platform Integrity**: Documentation-code mismatch undermines user trust and platform reliability

### Affected User Journey:
1. User follows official documentation at https://hokus.ai/explore-models/21
2. Attempts to import required components from hokusai.tracking module
3. Tries to instantiate ModelRegistry following documented pattern
4. Attempts authentication with provided API key
5. Calls register_tokenized_model method as shown in documentation
6. **FAILURE AT MULTIPLE STEPS**

## Affected Components/Services

### Primary Components:
- **hokusai-ml-platform SDK** (`/hokusai-ml-platform/src/hokusai/`)
  - `tracking/__init__.py` - Module export configuration
  - `core/registry.py` - ModelRegistry class and registration methods
  - `auth/client.py` - Authentication client
  - `config/mlflow_auth.py` - MLflow authentication setup

### External Services:
- **MLflow Tracking Server** - https://registry.hokus.ai/mlflow
- **Hokusai Auth Service** - https://auth.hokus.ai
- **Hokusai API Gateway** - Authentication proxy and routing

### Documentation:
- **Hokusai Website** - https://hokus.ai/explore-models/21 (model registration guide)

## Investigation Status - Initial Observations

### ✅ VERIFIED ISSUES:

#### 1. Tracking Module Components - **ISSUE RESOLVED**
**Status**: FALSE POSITIVE - Components exist and are properly exported
- `ExperimentManager` exists in `/hokusai-ml-platform/src/hokusai/tracking/experiments.py`
- `PerformanceTracker` exists in `/hokusai-ml-platform/src/hokusai/tracking/performance.py`
- Both are correctly exported in `/hokusai-ml-platform/src/hokusai/tracking/__init__.py`
- **Possible causes**: Import path issues, package installation problems, or version mismatch

#### 2. ModelRegistry Constructor - **ISSUE CONFIRMED**
**Status**: DOCUMENTATION BUG CONFIRMED
- Documentation shows: `registry = ModelRegistry()` (no parameters)
- Actual constructor: `ModelRegistry(tracking_uri=None, api_key=None, api_endpoint=None, auth=None, **kwargs)`
- Constructor handles None parameters with defaults, so no-param call should work
- **Root cause**: Documentation may be showing simplified usage but not explaining parameter options

#### 3. register_tokenized_model Method - **ISSUE RESOLVED**
**Status**: FALSE POSITIVE - Method exists and is fully implemented
- Method exists at line 435 in `/hokusai-ml-platform/src/hokusai/core/registry.py`
- Full implementation with proper parameter validation and MLflow integration
- **Possible causes**: Import issues, incorrect SDK version, or module loading problems

#### 4. API Authentication (403 Forbidden) - **ISSUE NEEDS INVESTIGATION**
**Status**: REQUIRES DEEP DIVE
- MLflow authentication configuration appears complex with multiple fallback mechanisms
- Could be related to token format, endpoint configuration, or authentication proxy setup
- May involve multiple authentication layers (API key → MLflow token conversion)

### 🔍 INVESTIGATION FINDINGS:

1. **SDK Code Quality**: All reported missing components actually exist and appear well-implemented
2. **Authentication Complexity**: Multiple authentication mechanisms and fallback strategies suggest this is the most likely failure point
3. **Documentation Gap**: Mismatch between simplified documentation examples and actual implementation requirements

## Reproduction Steps

### Step 1: Environment Setup
```bash
# Create clean Python environment
python3.11 -m venv test_env
source test_env/bin/activate
pip install mlflow==2.9.0

# Install hokusai-ml-platform from latest commit
git clone https://github.com/hokusai-tech/hokusai-data-pipeline.git
cd hokusai-data-pipeline
git checkout b1698a58
cd hokusai-ml-platform
pip install -e .
```

### Step 2: Test Component Imports
```python
# Test 1: Verify tracking module imports
try:
    from hokusai.tracking import ExperimentManager, PerformanceTracker
    print("✅ Tracking components imported successfully")
except ImportError as e:
    print(f"❌ Import failed: {e}")

# Test 2: Verify ModelRegistry import and instantiation
try:
    from hokusai.core import ModelRegistry
    registry = ModelRegistry()  # No parameters as per docs
    print("✅ ModelRegistry instantiated successfully")
except Exception as e:
    print(f"❌ ModelRegistry instantiation failed: {e}")
```

### Step 3: Test Authentication
```python
# Test 3: API key authentication
import os
os.environ["HOKUSAI_API_KEY"] = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"

registry = ModelRegistry(api_key="hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN")

# Test MLflow connectivity
import mlflow
try:
    mlflow.set_tracking_uri("https://registry.hokus.ai/mlflow")
    experiments = mlflow.search_experiments(max_results=1)
    print("✅ MLflow connection successful")
except Exception as e:
    print(f"❌ MLflow connection failed: {e}")
```

### Step 4: Test Model Registration
```python
# Test 4: register_tokenized_model method
try:
    # Check if method exists
    assert hasattr(registry, 'register_tokenized_model'), "Method does not exist"
    print("✅ register_tokenized_model method found")

    # Test method call with mock data
    result = registry.register_tokenized_model(
        model_uri="runs:/test123/model",
        model_name="LSCOR_Test_Model",
        token_id="LSCOR",
        metric_name="accuracy",
        baseline_value=0.92
    )
    print("✅ Model registration successful")
except Exception as e:
    print(f"❌ Model registration failed: {e}")
```

## Investigation Approach

### Phase 1: Component Verification (Priority: HIGH)
- [ ] Verify all components exist in the installed package
- [ ] Test import statements in clean environment
- [ ] Check for package installation integrity issues
- [ ] Verify SDK version matches documentation

### Phase 2: Authentication Deep Dive (Priority: CRITICAL)
- [ ] Trace authentication flow from API key to MLflow token
- [ ] Test different authentication methods (basic auth, token auth, API key)
- [ ] Verify MLflow server accessibility and authentication requirements
- [ ] Check authentication proxy configuration in API gateway
- [ ] Validate API key format and permissions

### Phase 3: Documentation Validation (Priority: MEDIUM)
- [ ] Compare documentation examples with actual SDK signatures
- [ ] Verify all code examples can be executed successfully
- [ ] Document any simplifications or missing context in examples
- [ ] Test against multiple Python/MLflow versions

### Phase 4: Integration Testing (Priority: HIGH)
- [ ] End-to-end testing of complete registration workflow
- [ ] Test with multiple model types and token IDs
- [ ] Verify webhook notifications and status updates
- [ ] Test rollback and error recovery scenarios

## Monitoring and Logging Analysis

### Key Log Locations:
- **ECS Service Logs**: `/ecs/hokusai-mlflow-development`, `/ecs/hokusai-api-development`
- **Application Logs**: SDK logging output from authentication and registry operations
- **MLflow Server Logs**: Authentication and API access logs
- **API Gateway Logs**: Request routing and authentication proxy logs

### Monitoring Commands:
```bash
# Check MLflow service health
aws logs tail /ecs/hokusai-mlflow-development --follow --filter "ERROR"

# Check API service authentication
aws logs tail /ecs/hokusai-api-development --follow --filter "403"

# Test endpoint accessibility
curl -H "Authorization: Bearer hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN" \
     https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search

# Check service discovery resolution
nslookup mlflow.hokusai-development.local
```

## Next Steps

### Immediate Actions (Within 24 hours):
1. **Execute reproduction steps** to confirm each reported issue
2. **Analyze authentication logs** for the specific API key provided
3. **Test alternative authentication methods** (basic auth, different token formats)
4. **Verify documentation accuracy** against current SDK implementation

### Short-term Fixes (Within 1 week):
1. **Fix authentication issues** - highest priority as this blocks all operations
2. **Update documentation** with correct usage examples and parameter explanations
3. **Improve error messaging** to guide users through common issues
4. **Add comprehensive integration tests** to prevent regression

### Long-term Improvements (Within 1 month):
1. **Enhance SDK robustness** with better error handling and fallback mechanisms
2. **Implement automated documentation testing** to prevent code-documentation drift
3. **Add user onboarding validation** to catch issues before they reach production
4. **Create troubleshooting guide** for common authentication and setup issues

## Risk Assessment

### High Risk Areas:
- **Authentication Infrastructure**: Multiple failure points in authentication chain
- **Documentation Maintenance**: Manual process prone to drift from implementation
- **Third-party Integration**: External dependencies (MLflow, auth service) create additional complexity

### Mitigation Strategies:
- Implement automated testing of all documentation code examples
- Add comprehensive error messages with troubleshooting guidance
- Create simplified authentication setup for common use cases
- Add health checks for all dependent services

---

**Investigation Owner**: Claude Code Assistant
**Created**: 2025-09-15
**Status**: INVESTIGATION IN PROGRESS
**Next Review**: Daily until resolution