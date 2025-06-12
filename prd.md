# PRD: Implement compare_and_output_delta Step

## Objectives

Implement the final step of the Hokusai evaluation pipeline that computes the DeltaOne metric and packages the result for verifier consumption. This step compares the performance of a newly trained model against the baseline model and outputs a structured JSON result containing the delta, contributor information, and model metadata.

## Project Summary
**[feature] Implement compare_and_output_delta step** - Compute DeltaOne and package result for verifier.

Key requirements:
* Compute delta = new - baseline
* Structure JSON output as per spec
* Include contributor hashes, weights, model ID

## Personas

**Primary User: Pipeline Operator**
- Runs the complete Hokusai evaluation pipeline
- Needs reliable delta computation between baseline and new models
- Requires structured output for downstream verification processes

**Secondary User: Verifier**
- Consumes the JSON output to validate model improvements
- Needs contributor hashes, weights, and model identifiers for attestation
- Requires standardized format for automated processing

## Success Criteria

1. **Accurate Delta Computation**: Successfully calculates delta = new_model_metrics - baseline_model_metrics
2. **Structured JSON Output**: Produces JSON output conforming to the established schema with all required fields
3. **Complete Metadata**: Includes contributor hashes, weights, model IDs, and evaluation metrics
4. **Pipeline Integration**: Seamlessly integrates as the final step in the Metaflow pipeline
5. **MLFlow Tracking**: Logs delta computation results and metadata to MLFlow for experiment tracking

## Technical Requirements

### Input Requirements
- Baseline model evaluation metrics (from previous pipeline steps)
- New model evaluation metrics (from evaluate_on_benchmark step)
- Contributor data hashes and weights (from integrate_contributed_data step)
- Model artifacts and metadata (from train_new_model step)

### Output Requirements
- JSON file containing DeltaOne metric
- Contributor attribution data (hashes, weights)
- Model identifiers and metadata
- Evaluation metrics for both baseline and new models
- Timestamp and pipeline run information

### Implementation Tasks

1. **Create compare_and_output_delta Metaflow step**
   - Add @step decorator for Metaflow integration
   - Define input parameters from previous pipeline steps
   - Implement delta computation logic

2. **Implement delta computation**
   - Calculate delta = new_model_metrics - baseline_model_metrics
   - Handle different metric types (accuracy, AUROC, F1, etc.)
   - Validate metric compatibility between models

3. **Structure JSON output**
   - Define output schema with required fields
   - Include DeltaOne value, contributor data, model metadata
   - Add timestamp and pipeline run information

4. **Add MLFlow integration**
   - Log delta computation results to MLFlow
   - Track contributor weights and model performance
   - Store output JSON as MLFlow artifact

5. **Implement error handling**
   - Validate input data completeness
   - Handle metric computation failures
   - Provide meaningful error messages

6. **Add unit tests**
   - Test delta computation with mock data
   - Verify JSON output format and completeness
   - Test error handling scenarios

7. **Integration testing**
   - Test step integration within full pipeline
   - Verify data flow from previous steps
   - Validate output consumption by downstream processes

## Dependencies

- Previous pipeline steps: load_baseline_model, train_new_model, evaluate_on_benchmark
- MLFlow for experiment tracking and artifact storage
- JSON schema validation utilities
- Metaflow framework for step definition and execution

## Acceptance Criteria

- [ ] Metaflow step successfully computes delta between baseline and new model metrics
- [ ] JSON output includes all required fields per schema specification
- [ ] Contributor hashes, weights, and model IDs are correctly included
- [ ] MLFlow tracking captures delta computation and metadata
- [ ] Unit tests achieve >90% code coverage
- [ ] Integration tests pass with full pipeline execution
- [ ] Error handling provides clear failure diagnostics