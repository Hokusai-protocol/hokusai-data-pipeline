# Implementation Tasks: Local Performance Preview

## 1. [x] Set up project structure and dependencies
   a. [x] Create `src/preview/` directory for preview-specific modules
   b. [x] Add preview-related dependencies to requirements.txt (if any new ones needed)
   c. [x] Create `hokusai-preview` entry point script
   d. [x] Set up logging configuration for preview mode

## 2. [x] Implement data loading and validation module
   a. [x] Create `src/preview/data_loader.py` with support for CSV, JSON, Parquet
   b. [x] Implement file format auto-detection
   c. [x] Add data validation matching main pipeline schema
   d. [x] Implement stratified sampling for large datasets (>10k samples)
   e. [x] Add progress indicators for data loading

## 3. [x] Create baseline model management
   a. [x] Implement baseline model loader in `src/preview/model_manager.py`
   b. [x] Add support for loading from default location or custom path
   c. [x] Create mock baseline generator for test mode
   d. [x] Implement model compatibility checking

## 4. [x] Build fine-tuning module
   a. [x] Create `src/preview/fine_tuner.py` with lightweight training logic
   b. [x] Implement reduced epoch training (e.g., 5 epochs vs full pipeline's 50)
   c. [x] Add early stopping based on validation loss
   d. [x] Implement memory-efficient batch processing
   e. [x] Add training progress display with ETA

## 5. [x] Implement evaluation and delta calculation
   a. [x] Create `src/preview/evaluator.py` for model evaluation
   b. [x] Implement metric calculation (accuracy, precision, recall, F1, AUROC)
   c. [x] Create simplified DeltaOne score calculation
   d. [x] Add confidence estimation based on sample size
   e. [x] Implement comparison with baseline metrics

## 6. [x] Design output formatting system
   a. [x] Create `src/preview/output_formatter.py`
   b. [x] Implement JSON output matching main pipeline schema
   c. [x] Add preview-specific metadata fields
   d. [x] Create pretty-print console formatter
   e. [x] Add clear "PREVIEW - NON-BINDING" disclaimers

## 7. [x] Build CLI interface (Dependent on modules 2-6)
   a. [x] Create `hokusai-preview` CLI script using argparse
   b. [x] Implement argument parsing and validation
   c. [x] Add helpful error messages and usage examples
   d. [x] Implement output file writing functionality
   e. [x] Add verbose/quiet mode options

## 8. [ ] Add performance optimizations
   a. [ ] Implement data caching mechanism
   b. [ ] Add model checkpoint caching
   c. [ ] Optimize memory usage for large datasets
   d. [ ] Add performance timing and reporting

## 9. [x] Write comprehensive tests
   a. [x] Unit tests for data_loader.py
   b. [x] Unit tests for model_manager.py
   c. [x] Unit tests for fine_tuner.py
   d. [x] Unit tests for evaluator.py
   e. [x] Unit tests for output_formatter.py
   f. [x] Integration tests for full preview pipeline
   g. [x] Performance tests (<5 minute execution)
   h. [x] Accuracy tests comparing with full pipeline
   i. [x] Edge case tests (empty data, malformed files)

## 10. [ ] Create documentation (Dependent on implementation tasks 1-8)
   a. [ ] Write preview tool section in main README.md
   b. [ ] Create `docs/PREVIEW_TOOL.md` with detailed usage
   c. [ ] Add example commands and outputs
   d. [ ] Document accuracy expectations and limitations
   e. [ ] Create troubleshooting guide
   f. [ ] Add inline code documentation

## 11. [ ] Integration testing with main pipeline (Dependent on all above)
   a. [ ] Test output compatibility with main pipeline
   b. [ ] Verify delta score accuracy within ±20%
   c. [ ] Test with various dataset sizes
   d. [ ] Validate resource usage constraints
   e. [ ] End-to-end testing with real contributed data

## 12. [ ] Final validation and polish
   a. [ ] Code review and refactoring
   b. [ ] Update CLAUDE.md with preview tool information
   c. [ ] Ensure all tests pass
   d. [ ] Performance profiling and optimization
   e. [ ] User acceptance testing simulation