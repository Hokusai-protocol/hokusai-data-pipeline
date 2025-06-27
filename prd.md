# DeltaOne Detector Product Requirements Document

## Objectives

Implement an automated system that compares the latest model version against a baseline model and triggers a flag when performance improvements of 1 percentage point or greater are detected. This enables automatic identification of significant model improvements for potential tokenization.

## Target Personas

1. **ML Engineers**: Need automated detection of meaningful model improvements
2. **Data Scientists**: Want to track performance deltas across model versions
3. **Platform Users**: Require reliable signals for model tokenization decisions

## Success Criteria

1. Accurate detection of ≥1 percentage point improvements in model metrics
2. Automated comparison between latest and baseline model versions
3. Integration with MLflow model registry for version tracking
4. Clear logging and webhook notifications for DeltaOne achievements
5. Support for multiple metric types (accuracy, reply_rate, etc.)

## Implementation Tasks

### Core Module Development
- Create deltaone_evaluator.py module in src/evaluation/
- Implement detect_delta_one() function with model comparison logic
- Add support for retrieving and sorting model versions from MLflow
- Implement metric extraction and comparison functionality

### MLflow Integration
- Enhance model registry integration for version queries
- Ensure proper tag reading for benchmark metrics and values
- Add validation for required model metadata

### Notification System
- Implement MLflow metric logging for DeltaOne achievements
- Create webhook trigger mechanism for Hokusai minting service
- Add configurable notification endpoints

### Testing and Validation
- Create unit tests for delta calculation logic
- Add integration tests with MLflow model registry
- Test edge cases (missing metrics, invalid versions, etc.)
- Validate percentage point calculation accuracy

### Documentation
- Document DeltaOne detection API and usage
- Add examples for different metric types
- Include integration guide for minting service webhook