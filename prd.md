# Product Requirements Document: ExperimentManager API Incompatibility Fix

## Objectives

Fix the ExperimentManager constructor signature mismatch in the hokusai-ml-platform package that prevents proper initialization when following expected patterns. The current implementation expects an `experiment_name` parameter but documentation and usage examples suggest a `registry` parameter should be used.

## Problem Statement

Third-party developers attempting to use the ExperimentManager class encounter initialization failures due to constructor signature mismatch:

- **Expected Usage**: `ExperimentManager(registry)`
- **Actual Implementation**: `ExperimentManager(experiment_name='hokusai_model_improvements')`

This discrepancy prevents developers from successfully initializing the ExperimentManager and blocks adoption of the hokusai-ml-platform package.

## Target Personas

- **Third-party developers** integrating hokusai-ml-platform into their projects
- **Data scientists** using the Hokusai platform for experiment tracking
- **ML engineers** building applications on top of the Hokusai ecosystem

## Success Criteria

1. ExperimentManager constructor accepts both `registry` and `experiment_name` parameters
2. Backward compatibility is maintained for existing usage patterns
3. Clear documentation explains both initialization methods
4. All existing tests continue to pass
5. New tests validate both constructor signatures work correctly

## Technical Requirements

### Constructor Signature Update
- Modify ExperimentManager to accept both parameter types
- Implement parameter validation and conversion logic
- Maintain backward compatibility with existing `experiment_name` usage

### Documentation Updates
- Update docstrings to reflect supported parameters
- Provide clear examples of both initialization methods
- Update any relevant README or API documentation

### Testing Requirements
- Add unit tests for both constructor signatures
- Verify backward compatibility with existing code
- Test error handling for invalid parameter combinations

## Implementation Tasks

1. **Analyze Current Implementation**
   - Review existing ExperimentManager constructor
   - Identify all current usage patterns in codebase
   - Document current behavior and expected changes

2. **Update Constructor Logic**
   - Modify constructor to accept both `registry` and `experiment_name`
   - Implement parameter validation
   - Add conversion logic between parameter types if needed

3. **Maintain Backward Compatibility**
   - Ensure existing `experiment_name` usage continues to work
   - Add deprecation warnings if appropriate
   - Update internal method calls as needed

4. **Update Documentation**
   - Modify class docstrings and method documentation
   - Update usage examples in code comments
   - Ensure API documentation reflects changes

5. **Add Comprehensive Tests**
   - Test both constructor signatures
   - Test parameter validation and error cases
   - Test backward compatibility scenarios
   - Add integration tests with registry parameter

6. **Validate Changes**
   - Run existing test suite to ensure no regressions
   - Test with real-world usage scenarios
   - Verify third-party integration works as expected

## Acceptance Criteria

- [ ] ExperimentManager can be initialized with `registry` parameter
- [ ] ExperimentManager can still be initialized with `experiment_name` parameter
- [ ] All existing tests pass without modification
- [ ] New tests cover both initialization methods
- [ ] Documentation clearly explains both approaches
- [ ] No breaking changes for existing users
- [ ] Third-party developers can successfully integrate the updated API

## Dependencies

- Access to hokusai-ml-platform source code
- Existing test suite and testing infrastructure
- Documentation system for API reference updates

## Timeline

This is a focused API compatibility fix that should be completed as a single cohesive update to prevent further integration issues for third-party developers.

---

# Analysis: Model Registration Without MLflow

## Problem Statement

When MLflow integration fails, there's no clear fallback mechanism for model registration. The platform should support model registration even when MLflow is unavailable or misconfigured.

## Current State Analysis

### Existing Fallback Mechanisms
- **Mock Mode**: `HOKUSAI_MOCK_MODE` environment variable bypasses MLflow entirely
- **API Registration**: `register_baseline_via_api()` method provides alternative path
- **Retry Logic**: Basic retry mechanisms for transient connection errors
- **Error Handling**: Generic exception handling with logging

### MLflow Dependencies
- **Core Registration**: `ModelRegistry` class heavily depends on `MlflowClient`
- **Experiment Tracking**: `ExperimentManager` requires MLflow connection
- **Metrics Storage**: Performance metrics stored in MLflow
- **Artifact Management**: Model artifacts managed through MLflow

## Options Analysis

### Option 1: High Availability MLflow (Recommended)
**Approach**: Focus on making MLflow itself highly available rather than building fallback systems.

**Pros**:
- Simpler architecture - one source of truth
- Existing MLflow ecosystem and tooling
- No data consistency issues
- Lower development and maintenance cost

**Implementation**:
- **MLflow HA Setup**: Multi-instance MLflow with load balancer
- **Database Redundancy**: PostgreSQL with replication
- **Monitoring**: Health checks and alerting
- **Backup/Recovery**: Automated backups and disaster recovery

**Estimated Effort**: 2-3 weeks
**Estimated Cost**: $500-1000/month for infrastructure

### Option 2: Lightweight Fallback System
**Approach**: Build minimal fallback using existing database infrastructure.

**Pros**:
- Provides resilience during MLflow outages
- Uses existing PostgreSQL database
- Minimal additional infrastructure

**Implementation**:
- **Simple Registry Table**: Store basic model metadata in existing DB
- **Queue System**: Queue registrations for MLflow sync when available
- **Health Monitoring**: Simple MLflow availability checks

**Estimated Effort**: 3-4 weeks
**Estimated Cost**: Minimal additional infrastructure cost

### Option 3: Full Fallback System (Not Recommended)
**Approach**: Complete mirror of MLflow functionality in local database.

**Cons**:
- High complexity and maintenance burden
- Data consistency challenges
- Duplicate infrastructure
- Feature parity challenges with MLflow updates

**Estimated Effort**: 8-12 weeks
**Estimated Cost**: Significant ongoing maintenance

## Recommendation

**Choose Option 1: High Availability MLflow**

### Rationale
1. **Simplicity**: One system to maintain rather than two
2. **Reliability**: MLflow is mature and battle-tested
3. **Cost-Effective**: Infrastructure costs are lower than development time
4. **Future-Proof**: Leverages MLflow's ongoing development

### Implementation Plan
1. **Week 1**: Set up MLflow HA infrastructure
2. **Week 2**: Implement monitoring and alerting
3. **Week 3**: Add backup/recovery procedures and testing

### Quick Wins (Immediate)
While setting up HA infrastructure, improve current error handling:
- **Better Retry Logic**: Exponential backoff for transient failures
- **Circuit Breaker**: Fail fast when MLflow is definitively down
- **User Feedback**: Clear error messages about MLflow status

## Success Metrics
- **Uptime**: Target 99.9% MLflow availability
- **MTTR**: Mean time to recovery < 5 minutes
- **Error Rate**: Reduce MLflow-related errors by 90%

## Decision Required
Should we proceed with Option 1 (High Availability MLflow) or do you prefer a different approach?