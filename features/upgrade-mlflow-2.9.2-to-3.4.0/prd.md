# Product Requirements Document: Upgrade MLflow from 2.9.2 to 3.4.0

## Objective

Upgrade the Hokusai data pipeline from MLflow 2.9.2 to MLflow 3.4.0 to take advantage of new features, bug fixes, and security patches while maintaining all existing functionality.

## Background

Hokusai currently uses MLflow 2.9.2 (released in 2023) for model tracking, registry, and serving. MLflow 3.x introduces significant improvements including the LoggedModel entity, enhanced GenAI/LLM evaluation capabilities, and improved authentication. The upgrade analysis indicates low breaking changes (2-3 areas) with high value from new features.

## Success Criteria

1. All MLflow dependencies upgraded to version 3.4.0
2. All existing tests pass without modification (unless testing deprecated features)
3. Core Hokusai functionality preserved:
   - Model registration works correctly
   - DeltaOne evaluation detects improvements
   - Authentication integration functions properly
   - MLflow proxy routes requests correctly
   - Experiment tracking operates as expected
4. No regression in performance or reliability
5. Docker images build successfully with new version
6. Services deploy and run in development environment

## Personas

- Data Scientists: Register and track models, run experiments
- ML Engineers: Deploy models, monitor performance
- API Users: Interact with model registry via hokusai-ml-platform SDK
- DevOps: Deploy and maintain MLflow infrastructure

## Technical Scope

### Files Impacted

**Requirements Files:**
- `requirements-mlflow.txt` - MLflow version specification
- `Dockerfile.mlflow` - MLflow server container
- `Dockerfile.api` - API service container (uses MLflow client)
- `requirements.txt` / `requirements-all.txt` - Consolidated dependencies

**Core Usage (128 imports across 73 files):**
- `src/services/experiment_manager.py` - Experiment tracking
- `src/evaluation/deltaone_evaluator.py` - DeltaOne detection
- `src/services/model_registry.py` - Model registration
- `hokusai-ml-platform/src/hokusai/config/mlflow_auth.py` - Authentication
- `src/integrations/mlflow_dspy.py` - DSPy integration
- All test files using MLflow mocking/fixtures

### Breaking Changes to Address

Based on MLflow 3.0 migration guide:

1. **Evaluation API** (MINOR IMPACT)
   - Removed: `baseline_model` parameter
   - Removed: `custom_metrics` parameter
   - Action: Verify ExperimentManager doesn't use deprecated parameters (preliminary check shows no usage)

2. **MetricThreshold Parameter** (LOW RISK)
   - Changed: `higher_is_better` → `greater_is_better`
   - Action: Search codebase and update if found

3. **Removed Flavors** (NO IMPACT)
   - fastai, mleap flavors removed
   - Action: Confirm not used (preliminary check shows no usage)

### Testing Strategy

**Priority 1 - Critical Path Tests:**
1. Model registration workflow (hokusai-ml-platform)
2. DeltaOne evaluation detection
3. MLflow authentication (token-based)
4. Experiment tracking and metrics logging

**Priority 2 - Integration Tests:**
1. MLflow proxy routes (`/api/2.0/mlflow/*`)
2. Health endpoints
3. Model versioning
4. Artifact storage (S3)

**Priority 3 - Unit Tests:**
1. All existing MLflow-related unit tests
2. Mock provider tests
3. Configuration tests

### Upgrade Constraints

**DO NOT in this release:**
- Implement new MLflow 3.x features (LoggedModel entity, streaming responses, etc.)
- Change existing architecture or workflows
- Modify API contracts or response formats
- Update authentication mechanisms beyond compatibility fixes

**ONLY:**
- Upgrade version numbers
- Fix compatibility issues from breaking changes
- Ensure existing functionality works identically

## Implementation Tasks

### Phase 1: Dependency Updates
1. Update `requirements-mlflow.txt` with MLflow 3.4.0
2. Update `Dockerfile.mlflow` with new version
3. Regenerate `requirements.txt` and `requirements-all.txt`
4. Update any version pins in setup.py or pyproject.toml

### Phase 2: Breaking Change Analysis
1. Search for `higher_is_better` parameter usage and replace with `greater_is_better`
2. Verify no usage of removed evaluation parameters (`baseline_model`, `custom_metrics`)
3. Confirm no fastai or mleap flavor usage
4. Check for any deprecated API usage flagged in MLflow 3.0 migration guide

### Phase 3: Test Suite Validation
1. Run full test suite locally
2. Identify and fix any test failures due to version changes
3. Update test fixtures/mocks if MLflow response formats changed
4. Validate critical path tests pass:
   - Model registration
   - DeltaOne detection
   - Authentication
   - Experiment tracking

### Phase 4: Integration Testing
1. Build Docker images locally
2. Start MLflow server container
3. Start API service container
4. Run integration tests against running services
5. Test model registration end-to-end
6. Test DeltaOne evaluation workflow
7. Validate authentication flow

### Phase 5: Documentation
1. Update CHANGELOG.md with upgrade notes
2. Document any behavioral changes discovered
3. Note any new environment variables or configuration options
4. Update deployment documentation if needed

## Risk Assessment

**Low Risk:**
- Evaluation API changes (not using deprecated parameters)
- Removed flavors (not used in codebase)
- Deployment server removal (using FastAPI, not MLflow server)

**Medium Risk:**
- Database schema migrations (MLflow may auto-migrate)
- Authentication integration (verify token-based auth still works)
- Test fixture compatibility (may need minor updates)

**Mitigation:**
- Comprehensive test coverage before upgrade
- Test in development environment first
- Database backup before running with new version
- Ability to rollback if critical issues found

## Rollback Plan

If upgrade introduces unexpected issues:
1. Revert version changes in requirements files
2. Rebuild Docker images with MLflow 2.9.2
3. Redeploy previous version
4. Document issues encountered for future upgrade attempt

## Acceptance Criteria

- [ ] MLflow 3.4.0 specified in all requirements files
- [ ] All Docker images build successfully
- [ ] 100% of existing tests pass
- [ ] Model registration works in development environment
- [ ] DeltaOne evaluation detects improvements correctly
- [ ] Authentication integration functions properly
- [ ] No performance degradation in key operations
- [ ] Services start and run without errors
- [ ] Integration tests pass end-to-end

## Timeline Estimate

- Dependency updates: 1 hour
- Breaking change fixes: 2-4 hours
- Test suite validation: 8-12 hours
- Integration testing: 4-6 hours
- Documentation: 1-2 hours

**Total: 2-3 days**

## Approval Required

Alert user if:
- More than 5 breaking changes discovered during testing
- Critical functionality cannot be preserved
- Estimated effort exceeds 5 days
- Database migration requires manual intervention
- Performance degradation > 20% in any operation
