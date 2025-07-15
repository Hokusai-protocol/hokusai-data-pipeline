# Implementation Tasks: ExperimentManager API Incompatibility Fix

## 1. Analysis and Investigation
- [ ] 1.1 Locate and analyze current ExperimentManager implementation in hokusai-ml-platform
- [ ] 1.2 Find all current usage patterns of ExperimentManager in the codebase
- [ ] 1.3 Identify where the `registry` parameter expectation comes from
- [ ] 1.4 Document the current constructor signature and behavior
- [ ] 1.5 Review any existing documentation or examples that reference ExperimentManager

## 2. Constructor Logic Update
- [ ] 2.1 Modify ExperimentManager constructor to accept both `registry` and `experiment_name` parameters
- [ ] 2.2 Implement parameter validation logic
- [ ] 2.3 Add conversion logic between `registry` and `experiment_name` if needed
- [ ] 2.4 Ensure proper handling of default values for both parameters
- [ ] 2.5 Add appropriate error handling for invalid parameter combinations

## 3. Backward Compatibility
- [ ] 3.1 Ensure existing `experiment_name` usage continues to work unchanged
- [ ] 3.2 Update internal method calls that depend on constructor parameters
- [ ] 3.3 Add deprecation warnings if appropriate for old usage patterns
- [ ] 3.4 Verify no breaking changes for existing users

## 4. Documentation Updates
- [ ] 4.1 Update ExperimentManager class docstring to document both parameters
- [ ] 4.2 Add clear examples of both initialization methods in docstrings
- [ ] 4.3 Update any README or API documentation that references ExperimentManager
- [ ] 4.4 Add migration guide for developers switching between parameter types

## 5. Testing (Dependent on Implementation)
- [ ] 5.1 Write unit tests for `registry` parameter initialization
- [ ] 5.2 Write unit tests for `experiment_name` parameter initialization
- [ ] 5.3 Write unit tests for parameter validation and error cases
- [ ] 5.4 Write integration tests with registry parameter
- [ ] 5.5 Write backward compatibility tests for existing usage patterns
- [ ] 5.6 Add tests for edge cases and invalid parameter combinations

## 6. Validation and Integration
- [ ] 6.1 Run existing test suite to ensure no regressions
- [ ] 6.2 Test with real-world usage scenarios
- [ ] 6.3 Verify third-party integration works as expected
- [ ] 6.4 Run lint and type checking tools
- [ ] 6.5 Test both local and production environments

## 7. Implementation Steps (Detailed)

### 7.1 Code Changes
- [ ] 7.1.1 Update constructor signature in ExperimentManager class
- [ ] 7.1.2 Implement parameter detection and validation logic
- [ ] 7.1.3 Add conversion methods between parameter types
- [ ] 7.1.4 Update any dependent methods that reference constructor parameters

### 7.2 Error Handling
- [ ] 7.2.1 Add validation for mutually exclusive parameters
- [ ] 7.2.2 Implement clear error messages for invalid usage
- [ ] 7.2.3 Add proper exception handling for edge cases

### 7.3 Documentation
- [ ] 7.3.1 Update inline code comments
- [ ] 7.3.2 Add usage examples in docstrings
- [ ] 7.3.3 Update any external documentation references

## Dependencies
- Access to hokusai-ml-platform source code
- Existing test framework and infrastructure
- Documentation system for API reference updates

## Testing Strategy

### Unit Tests
- Test both constructor signatures work correctly
- Test parameter validation and conversion logic
- Test error handling for invalid combinations
- Test backward compatibility scenarios

### Integration Tests
- Test with actual registry objects
- Test with real experiment scenarios
- Test third-party integration patterns

### Regression Tests
- Ensure all existing tests continue to pass
- Verify no breaking changes for current users

## Acceptance Criteria Checklist
- [ ] ExperimentManager can be initialized with `registry` parameter
- [ ] ExperimentManager can still be initialized with `experiment_name` parameter
- [ ] All existing tests pass without modification
- [ ] New tests cover both initialization methods
- [ ] Documentation clearly explains both approaches
- [ ] No breaking changes for existing users
- [ ] Third-party developers can successfully integrate the updated API