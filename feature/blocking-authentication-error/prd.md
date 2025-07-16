# Product Requirements Document: MLflow Authentication Error Fix

## Objective

Fix the critical authentication error (403 Forbidden) that prevents third-party developers from registering models with the Hokusai ML Platform when using their API keys.

## Problem Statement

Third-party developers attempting to register models encounter a 403 authentication error when the SDK tries to connect to the MLflow tracking server. This blocks the entire model registration workflow and prevents platform adoption.

### Root Causes
1. Production MLflow server requires authentication but SDK wasn't properly passing credentials
2. Hokusai API key wasn't automatically used as MLflow authentication token
3. No fallback mechanism when production MLflow is unavailable
4. MLflow client was created with wrong tracking URI after configuration

## Solution Overview

Implement automatic authentication configuration with intelligent fallback:
1. Automatically use Hokusai API key as MLflow authentication token
2. Fall back to local MLflow server when production is unavailable
3. Provide clear error messages and debugging information
4. Ensure MLflow client uses the correct tracking URI

## Success Criteria

1. Third-party developers can register models using only their Hokusai API key
2. SDK automatically handles authentication without manual configuration
3. Development continues to work even when production MLflow is down
4. Clear error messages guide users when issues occur

## Implementation Tasks

### 1. MLflow Setup Module
- Create comprehensive MLflow configuration module with fallback logic
- Test remote connection with authentication first
- Automatically fall back to local MLflow if remote fails
- Support mock mode and optional MLflow settings

### 2. Registry Authentication Updates
- Fix bug where API key parameter wasn't properly used
- Ensure MLflow client uses correct tracking URI after configuration
- Update tracking URI based on successful connection

### 3. Testing Infrastructure
- Create test script for authenticated registration scenarios
- Test production authentication flow
- Verify fallback mechanisms work correctly
- Ensure backward compatibility

### 4. Documentation
- Create comprehensive authentication setup guide
- Document environment variables and configuration options
- Provide troubleshooting steps for common issues
- Include verification scripts

## Technical Details

### Authentication Flow
```
User provides HOKUSAI_API_KEY
    ↓
SDK attempts connection to production MLflow with token
    ↓ (if fails)
SDK falls back to local MLflow without auth
    ↓
Model registration proceeds successfully
```

### Key Components Modified
- `hokusai/config/mlflow_setup.py` - New module for MLflow configuration
- `hokusai/core/registry.py` - Fixed authentication and client initialization
- `hokusai/config/__init__.py` - Export new setup functions

## Testing Approach

1. Test authenticated registration with API key
2. Verify fallback to local MLflow
3. Test mock mode for unit tests
4. Test optional MLflow mode for production
5. Ensure error messages are helpful

## Risk Mitigation

- Backward compatibility maintained with existing code
- Fallback mechanisms ensure development isn't blocked
- Clear logging helps diagnose issues in production
- No breaking changes to public API