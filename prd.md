# Product Requirements Document: Technical Debt Fixes

## Objectives

Address critical technical debt in the Hokusai data pipeline to improve code quality, reliability, and maintainability. This includes fixing linting issues, resolving dependency conflicts, re-enabling tests, and establishing proper dependency management.

## Personas

- **Development Team**: Engineers working on the Hokusai data pipeline who need a stable, well-tested codebase
- **DevOps Engineers**: Team members responsible for deployments who need reliable CI/CD pipelines
- **Contributors**: External developers who need clear code standards and passing tests

## Success Criteria

1. All linting rules re-enabled and code passes linting checks
2. Numpy version conflicts resolved between mlflow (<2.0) and dspy-ai (2.3.1)
3. All tests re-enabled and passing with >80% coverage
4. All dependencies pinned to specific versions
5. CI/CD pipeline runs successfully without manual interventions

## Tasks

### 1. Re-enable and Fix Linting Issues

**Objective**: Restore code quality standards by re-enabling all linting rules and fixing violations

**Requirements**:
- Review the commit that relaxed ruff linting rules
- Re-enable all original linting rules in pyproject.toml
- Fix all linting errors in the codebase
- Ensure pre-commit hooks are working

**Acceptance Criteria**:
- `ruff check src/ tests/` passes without errors
- Pre-commit hooks prevent commits with linting errors

### 2. Resolve Numpy Version Conflicts

**Objective**: Fix the dependency conflict between mlflow (requires numpy<2.0) and dspy-ai (installs numpy 2.3.1)

**Requirements**:
- Analyze current dependency tree
- Find compatible versions or use dependency groups
- Update requirements files with compatible versions
- Test both mlflow and dspy-ai functionality

**Acceptance Criteria**:
- No dependency conflicts during installation
- Both mlflow and dspy-ai features work correctly
- `pip check` shows no conflicts

### 3. Re-enable All Tests

**Objective**: Restore full test coverage by re-enabling all previously disabled tests

**Requirements**:
- Review all tests currently disabled in pytest configuration
- Fix underlying issues causing test failures
- Re-enable tests one by one
- Ensure test coverage meets 80% threshold

**Acceptance Criteria**:
- All tests in test suite are enabled
- Test coverage is ≥80%
- CI/CD test stage passes consistently

### 4. Pin Dependency Versions

**Objective**: Establish reproducible builds by pinning all dependency versions

**Requirements**:
- Generate complete dependency lock file
- Pin all direct and transitive dependencies
- Document version selection rationale for key packages
- Set up automated dependency updates

**Acceptance Criteria**:
- All dependencies in requirements.txt have exact versions
- requirements-lock.txt contains full dependency tree
- Builds are reproducible across environments
- Dependabot or similar tool configured for updates

## Technical Specifications

### Dependency Resolution Strategy

1. Create separate requirement files:
   - `requirements-core.txt`: Core dependencies without conflicts
   - `requirements-mlflow.txt`: MLflow and compatible dependencies
   - `requirements-dspy.txt`: DSPy-ai as optional dependency
   - `requirements-dev.txt`: Development dependencies

2. Use pip-tools to manage dependencies:
   - `requirements.in` files for human-edited dependencies
   - `pip-compile` to generate locked requirements

### Testing Strategy

1. Fix tests in order of importance:
   - Unit tests first
   - Integration tests second
   - End-to-end tests last

2. Address common issues:
   - Mock external dependencies properly
   - Fix import errors from dependency changes
   - Update deprecated API usage

### Linting Configuration

1. Restore original ruff configuration
2. Fix issues by category:
   - Import sorting (I)
   - Code style (E, W)
   - Docstrings (D)
   - Type annotations (ANN)
   - Security issues (S)

## Implementation Plan

1. **Phase 1**: Dependency Resolution (Day 1-2)
   - Analyze and resolve numpy conflict
   - Create modular requirements files
   - Test installation in clean environment

2. **Phase 2**: Test Fixes (Day 3-4)
   - Re-enable and fix unit tests
   - Address integration test issues
   - Achieve 80% coverage

3. **Phase 3**: Linting (Day 5)
   - Re-enable linting rules
   - Fix all violations
   - Set up pre-commit hooks

4. **Phase 4**: Documentation & CI/CD (Day 6)
   - Update contribution guidelines
   - Fix CI/CD pipeline
   - Document changes

## Risk Mitigation

- **Risk**: Breaking changes in dependencies
  - **Mitigation**: Comprehensive test suite before and after changes

- **Risk**: Incompatible dependency versions
  - **Mitigation**: Use optional dependencies or separate environments

- **Risk**: Large number of linting errors
  - **Mitigation**: Fix incrementally, category by category