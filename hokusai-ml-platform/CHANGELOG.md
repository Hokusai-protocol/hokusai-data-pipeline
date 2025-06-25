# Changelog

All notable changes to the hokusai-ml-platform package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Package installation support via pip from GitHub
- Comprehensive installation documentation
- GitHub Actions workflow for automated package building and publishing
- Support for Python 3.8, 3.9, 3.10, and 3.11
- Package metadata enhancements for PyPI discoverability

## [1.0.0] - 2024-12-25

### Added
- Initial release of hokusai-ml-platform
- Core ML infrastructure components
  - Model Registry for centralized model management
  - Model Version Manager for version control
  - A/B Testing framework for model comparison
  - Inference Pipeline with caching support
- MLOps tracking capabilities
  - Experiment Manager for tracking ML experiments
  - Performance Tracker for model metrics
  - Model lineage tracking
- API clients for programmatic access
- Comprehensive test suite
- Documentation and examples

### Dependencies
- MLflow >= 2.8.1 for experiment tracking
- Metaflow >= 2.10.6 for pipeline orchestration
- Redis >= 5.0.1 for caching
- FastAPI >= 0.104.1 for API server
- Pydantic >= 2.5.0 for data validation

[Unreleased]: https://github.com/Hokusai-protocol/hokusai-data-pipeline/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Hokusai-protocol/hokusai-data-pipeline/releases/tag/v1.0.0