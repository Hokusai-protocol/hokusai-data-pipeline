# Audit of Disabled Tests

## Overview

This document audits all tests that are currently disabled in the Hokusai data pipeline project and explains why each was disabled.

## Disabled Tests in CI/CD Pipeline

### In `.github/workflows/deploy.yml`

The following test files are ignored in the pytest run (lines 58-71):

1. **test_api_dspy.py**
   - Reason: Import issues due to dependency conflicts with dspy module
   - Impact: API DSPy integration tests not running

2. **test_api_health.py**
   - Reason: Import issues, likely missing dependencies
   - Impact: API health check tests not running

3. **test_api_models.py**
   - Reason: Import/mocking issues
   - Impact: API model endpoint tests not running

4. **test_cli_signatures.py**
   - Reason: Import issues with DSPy signatures
   - Impact: CLI signature functionality tests not running

5. **test_cli_teleprompt.py**
   - Reason: Import issues with DSPy teleprompt functionality
   - Impact: CLI teleprompt tests not running

6. **test_dspy_api.py**
   - Reason: DSPy dependency conflicts
   - Impact: DSPy API integration tests not running

7. **test_dspy_pipeline_executor.py**
   - Reason: DSPy dependency conflicts
   - Impact: DSPy pipeline execution tests not running

8. **test_dspy_signatures/** (entire directory)
   - Reason: DSPy dependency conflicts
   - Impact: All DSPy signature tests not running

9. **test_event_system.py**
   - Reason: Import or dependency issues
   - Impact: Event system tests not running

10. **test_model_registration_cli.py**
    - Reason: Import or dependency issues
    - Impact: Model registration CLI tests not running

11. **services/dspy/** (entire directory)
    - Reason: DSPy dependency conflicts
    - Impact: All DSPy service tests not running

12. **tests/integration/** (entire directory)
    - Reason: Integration test dependencies or external service requirements
    - Impact: All integration tests not running

### Additional Test Filters

The pytest command includes `-k "not dspy and not api and not event"` which further excludes:
- Any test with "dspy" in its name
- Any test with "api" in its name
- Any test with "event" in its name

### Linting Disabled

Lines 50-52 show that ruff linting is temporarily disabled with the comment:
```
# Temporarily skip linting to unblock deployment
echo "Linting temporarily disabled to unblock deployment"
# ruff check src/ tests/
```

## Dependency Installation Issues

Lines 40-45 show manual dependency installation to work around conflicts:
```python
# Install core dependencies first
pip install numpy==1.24.3 pandas==2.0.3 scikit-learn==1.3.0
```

Note: These versions differ from our resolved versions (numpy==1.26.4).

## Test Coverage Impact

With these exclusions:
- **Unit test coverage**: Significantly reduced due to multiple file exclusions
- **Integration test coverage**: 0% (all integration tests disabled)
- **DSPy functionality**: 0% coverage
- **API functionality**: Partial coverage (health, models endpoints not tested)
- **CLI functionality**: Partial coverage (signatures, teleprompt not tested)

## Required Actions

1. Update dependency versions in deploy.yml to match resolved versions
2. Re-enable tests one by one after fixing import issues
3. Re-enable ruff linting after fixing code style issues
4. Re-enable integration tests with proper test isolation
5. Update test exclusion list as tests are fixed

## Test Failure Handling

The pytest command ends with `|| echo "Tests completed with some failures"` which allows the CI to continue even if tests fail. This should be removed once tests are stable.