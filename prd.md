# PRD: Implement evaluate_on_benchmark Step

## Objective
Implement the evaluate_on_benchmark step in the Hokusai evaluation pipeline that runs standardized benchmark evaluations comparing baseline versus new model performance, logging metrics and outputting raw scores for downstream processing.

## Project Summary
**[feature] Implement evaluate_on_benchmark step** - Run evaluation using standardized benchmarks.

Key requirements:
* Compare baseline vs new model
* Log performance (e.g., AUROC, accuracy)
* Output raw scores

## Personas
- **Pipeline Engineers**: Need reliable, reproducible benchmark evaluation step
- **ML Engineers**: Require standardized evaluation metrics and model comparison
- **Data Contributors**: Want to see how their contributions impact model performance
- **Verifiers**: Need deterministic, auditable evaluation process for DeltaOne calculations

## Success Criteria
1. Evaluation step successfully integrates with existing Metaflow pipeline
2. Standardized benchmarks are applied consistently to both baseline and new models
3. Performance metrics (AUROC, accuracy, precision, recall, F1) are calculated and logged
4. Raw prediction scores are output in structured format for downstream steps
5. Evaluation process is deterministic with proper random seed handling
6. MLFlow integration captures all evaluation metadata and metrics
7. Error handling covers model loading and evaluation failures

## Technical Requirements

### Input
- Baseline model from load_baseline_model step
- New/fine-tuned model from train_new_model step
- Standardized benchmark dataset(s)
- Evaluation configuration parameters
- Random seed for reproducibility

### Output
- Performance metrics for both models (AUROC, accuracy, precision, recall, F1)
- Raw prediction scores and probabilities
- Model comparison summary with delta calculations
- MLFlow experiment logs with all metrics and artifacts
- Structured JSON output for compare_and_output_delta step

### Implementation Tasks

1. **Create Metaflow step structure**
   - Define @step decorator for evaluate_on_benchmark
   - Set up input/output data flow from previous pipeline steps
   - Initialize MLFlow tracking for evaluation runs

2. **Implement benchmark dataset handling**
   - Load standardized benchmark datasets
   - Support multiple benchmark types (classification, regression, etc.)
   - Implement data preprocessing and validation
   - Handle different data formats (JSON, CSV, parquet)

3. **Model evaluation logic**
   - Load both baseline and new models
   - Run inference on benchmark datasets
   - Calculate standard ML metrics (AUROC, accuracy, precision, recall, F1)
   - Generate prediction scores and probabilities
   - Handle different model architectures and output formats

4. **Performance comparison**
   - Compare metrics between baseline and new models
   - Calculate performance deltas
   - Generate summary statistics
   - Identify significant performance changes

5. **MLFlow integration**
   - Log evaluation metrics for both models
   - Store prediction artifacts and raw scores
   - Track benchmark dataset metadata
   - Log comparison results and deltas

6. **Output formatting**
   - Structure evaluation results for downstream processing
   - Generate JSON output compatible with compare_and_output_delta step
   - Include model metadata and evaluation parameters
   - Format raw scores for further analysis

7. **Error handling and validation**
   - Validate model compatibility with benchmark datasets
   - Handle model loading failures gracefully
   - Verify evaluation metric calculations
   - Add comprehensive logging and error reporting

8. **Testing**
   - Unit tests for evaluation metric calculations
   - Integration tests with mock models and datasets
   - End-to-end pipeline testing with real benchmark data
   - Performance regression tests

## Dependencies
- Metaflow framework for pipeline orchestration
- MLFlow for experiment tracking and model management
- Baseline model from load_baseline_model step
- New model from train_new_model step
- Standardized benchmark datasets
- Python ML libraries (scikit-learn, numpy, pandas)
- Model-specific libraries based on architecture

## Acceptance Criteria
- [ ] evaluate_on_benchmark step runs successfully in Metaflow pipeline
- [ ] Both baseline and new models are evaluated on standardized benchmarks
- [ ] All specified metrics (AUROC, accuracy, precision, recall, F1) are calculated correctly
- [ ] Raw prediction scores are output in structured format
- [ ] Evaluation process is deterministic with fixed random seeds
- [ ] MLFlow captures all evaluation metadata and results
- [ ] Performance comparison between models is accurate
- [ ] Step handles errors gracefully with informative messages
- [ ] Integration tests pass with mock models and real benchmark data
- [ ] Output format is compatible with downstream pipeline steps
- [ ] Documentation covers usage, configuration, and benchmark dataset requirements