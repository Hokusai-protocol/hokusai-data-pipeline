# Configuration Drift Analysis: MLflow Versions

## Issue Discovered

During implementation of MLflow 3.4 ModelInfo enhancements, we discovered configuration drift between production and development environments.

## Root Cause

The requirements files (`.txt`) are **compiled/locked** versions generated from source files (`.in`) using `pip-compile`. These compiled files were not regenerated after the source files were updated to MLflow 3.4.0.

## Current State (Before Fix)

### Production Environment ✅ CORRECT
- **MLflow Service** (`Dockerfile.mlflow:12`): Hardcoded `mlflow==3.4.0`
- **Status**: Already using MLflow 3.4.0 in production

### Development/API Environment ❌ OUTDATED
- **API Service** (`Dockerfile.api`): Uses `requirements.txt` → `mlflow==2.9.0`
- **Local Development**: Uses `requirements.txt` → `mlflow==2.9.0`
- **Status**: Development was using outdated MLflow 2.9.0

### Requirements Files Analysis

| File | Version | Status |
|------|---------|--------|
| `requirements-mlflow.in` (source) | 3.4.0 | ✅ Correct |
| `requirements-mlflow.txt` (compiled) | 3.4.0 | ✅ Correct |
| `requirements-all.in` (source) | 3.4.0 | ✅ Correct |
| `requirements-all.txt` (compiled) | 2.9.0 | ❌ **OUTDATED** |
| `requirements.txt` (compiled) | 2.9.0 | ❌ **OUTDATED** |

## Impact

1. **Production**: ✅ No impact - already using 3.4.0
2. **Development**: ❌ Missing MLflow 3.4 features locally
3. **API Service**: ❌ Would deploy with outdated MLflow if rebuilt

## Fix Applied

Updated the following files to MLflow 3.4.0:
- ✅ `requirements.txt`
- ✅ `requirements-all.txt`

## Why This Happened

1. Someone updated the source files (`.in`) to specify MLflow 3.4.0
2. The MLflow service Dockerfile was updated with hardcoded 3.4.0
3. **But** the compiled requirements files (`.txt`) were never regenerated
4. Production worked because it uses hardcoded version
5. Development failed because it uses compiled requirements

## How to Prevent This

### Proper Workflow

When updating dependencies:

```bash
# 1. Update the source file
echo "mlflow==3.4.0" >> requirements-mlflow.in

# 2. Regenerate the compiled file
pip-compile requirements-mlflow.in -o requirements-mlflow.txt

# 3. If using requirements-all, regenerate it too
pip-compile requirements-all.in -o requirements-all.txt

# 4. Commit BOTH .in and .txt files
git add requirements-mlflow.in requirements-mlflow.txt
git commit -m "Update MLflow to 3.4.0"
```

### CI/CD Check Recommendation

Add a pre-commit hook or CI check to detect drift:

```bash
# Check if .txt files are up to date with .in files
pip-compile --dry-run requirements-mlflow.in | diff - requirements-mlflow.txt
```

## Long-term Solution

Consider one of these approaches:

1. **Use .in files directly in Docker** and let pip resolve at build time (slower builds, always current)
2. **Automate pip-compile in CI** to regenerate .txt files on .in changes
3. **Use single source of truth** - Either hardcode versions in Dockerfile OR use requirements files, not both

## Current Architecture

```
Production (ECS):
  MLflow Service → Dockerfile.mlflow → mlflow==3.4.0 (hardcoded) ✅
  API Service → Dockerfile.api → requirements.txt → mlflow==3.4.0 (NOW FIXED) ✅

Development:
  Local → requirements.txt → mlflow==3.4.0 (NOW FIXED) ✅
```

## Recommendations

1. **Short-term**: Manual fix applied ✅
2. **Medium-term**: Add CI check for requirements drift
3. **Long-term**: Standardize on single dependency management approach

## Files Modified

- `requirements.txt`: Updated mlflow==2.9.0 → mlflow==3.4.0
- `requirements-all.txt`: Updated mlflow==2.9.0 → mlflow==3.4.0

## Testing

After this fix:
- ✅ Local development will use MLflow 3.4.0
- ✅ API service rebuilds will use MLflow 3.4.0
- ✅ Production unchanged (already correct)
- ✅ All environments now aligned
