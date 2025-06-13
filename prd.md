# PRD: Implement Dry-Run and Test Mode for Hokusai Pipeline

## Objectives

Enable developers and contributors to test the Hokusai evaluation pipeline locally without requiring real data or models. This reduces development friction and allows for rapid iteration during development.

## Success Criteria

- Developers can run the complete pipeline with mock data
- All pipeline steps execute successfully in test mode
- Mock DeltaOne JSON output is generated
- Test mode is clearly distinguishable from production runs
- Documentation exists for running in test mode

## Personas

### Primary: Pipeline Developers
- Need to test pipeline changes locally
- Want to validate pipeline logic without real data/models
- Require fast feedback loops during development

### Secondary: Contributors
- Want to understand pipeline behavior before submitting real data
- Need to verify their integration works correctly

## Core Requirements

### Flag-Based Execution
- Add `--dry-run` or `--test-mode` flag to pipeline execution
- Environment variable support (e.g., `HOKUSAI_TEST_MODE=true`)
- Clear indication when running in test mode

### Mock Data and Models
- Provide dummy baseline model that mimics real model interface
- Generate sample dataset that matches expected schema
- Ensure mock data covers edge cases and various scenarios

### Mock Output Generation
- Generate realistic DeltaOne JSON output
- Include all required fields per the schema
- Populate with plausible mock values

### Pipeline Integration
- Test mode should work with existing Metaflow pipeline structure
- All pipeline steps should execute in test mode
- MLFlow tracking should still work with test runs

## Implementation Tasks

### Task 1: Add Test Mode Configuration
- Create configuration class for test mode settings
- Add command-line flag parsing for dry-run mode
- Add environment variable support
- Update pipeline initialization to detect test mode

### Task 2: Create Mock Data Generator
- Implement mock dataset generator with realistic schema
- Create sample queries, responses, and metadata
- Ensure generated data covers various test scenarios
- Make mock data deterministic for consistent testing

### Task 3: Implement Mock Baseline Model
- Create dummy model class that mimics real model interface
- Implement prediction methods that return plausible outputs
- Ensure model can be loaded and used by existing pipeline code
- Add model metadata that matches expected format

### Task 4: Update Pipeline Steps for Test Mode
- Modify `load_baseline_model` step to use mock model in test mode
- Update `integrate_contributed_data` step to use mock data
- Ensure `train_new_model` step works with mock data
- Update `evaluate_on_benchmark` step for test scenarios
- Modify `compare_and_output_delta` step to generate mock output

### Task 5: Create Mock Output Generator
- Implement DeltaOne JSON output generator
- Include all required schema fields
- Generate realistic metric values
- Add test-specific metadata to distinguish from real runs

### Task 6: Add Test Mode Documentation
- Update README with test mode usage instructions
- Document command-line flags and environment variables
- Provide examples of running in test mode
- Explain mock data and expected outputs

### Task 7: Add Integration Tests
- Create tests that verify test mode functionality
- Test each pipeline step in isolation with test mode
- Verify end-to-end pipeline execution in test mode
- Ensure mock outputs match expected schema

## Technical Considerations

### Performance
- Test mode should execute quickly (< 2 minutes for full pipeline)
- Mock data generation should be efficient
- Avoid expensive operations in test mode

### Consistency
- Mock data should be deterministic for reproducible testing
- Use fixed random seeds for consistent outputs
- Ensure test mode behavior is predictable

### Maintenance
- Mock data should be easy to update as schema evolves
- Test mode configuration should be centralized
- Clear separation between test and production code paths

## Acceptance Criteria

- [ ] Pipeline can be executed with `--dry-run` flag
- [ ] All pipeline steps complete successfully in test mode
- [ ] Mock DeltaOne JSON output is generated and valid
- [ ] Test mode is clearly indicated in logs and output
- [ ] Documentation exists and is accurate
- [ ] Integration tests pass for test mode functionality
- [ ] Test mode execution completes in under 2 minutes