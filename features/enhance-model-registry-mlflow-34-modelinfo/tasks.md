# Tasks: Enhance Model Registry with MLflow 3.4 ModelInfo

## Prerequisites

1. [ ] Verify MLflow 3.4.0 installation
   a. [ ] Check MLflow version: `pip show mlflow`
   b. [ ] Verify MLflow 3.4.0 is installed
   c. [ ] Install if needed: `pip install mlflow==3.4.0`

## Testing (Write First)

2. [ ] Create unit tests for ModelInfo capture in register_baseline()
   a. [ ] Test that ModelInfo fields are captured (model_uuid, model_uri, signature, metadata)
   b. [ ] Test that existing fields are preserved (model_id, version, model_name)
   c. [ ] Test that webhook-critical version field comes from ModelVersion
   d. [ ] Test with signature parameter
   e. [ ] Test with input_example parameter
   f. [ ] Test with code_paths parameter
   g. [ ] Test with structured metadata (no 500-char limit)

3. [ ] Create unit tests for ModelInfo capture in register_improved_model()
   a. [ ] Test that ModelInfo fields are captured
   b. [ ] Test that baseline_id is preserved
   c. [ ] Test that delta_metrics are logged correctly
   d. [ ] Test contributor attribution with ModelInfo

4. [ ] Create unit test for get_model_by_uuid() method
   a. [ ] Test successful UUID lookup
   b. [ ] Test UUID not found returns None
   c. [ ] Test that model_uuid tag is searchable
   d. [ ] Test returned data structure

5. [ ] Create unit tests for backward compatibility
   a. [ ] Test register_baseline() without new optional parameters
   b. [ ] Test that existing code paths work unchanged
   c. [ ] Test that missing optional parameters don't cause errors

6. [ ] Create unit tests for signature validation
   a. [ ] Test registration with valid ModelSignature
   b. [ ] Test signature inference from input_example
   c. [ ] Test signature string representation in result

7. [ ] Update tests/unit/test_model_registry_hooks.py
   a. [ ] Add assertions for new ModelInfo fields
   b. [ ] Verify webhook payload still contains version from ModelVersion
   c. [ ] Test that optional new fields don't break existing webhooks

8. [ ] Create integration tests for webhook integration
   a. [ ] Test end-to-end registration + webhook emission
   b. [ ] Verify webhook payload contains version from ModelVersion
   c. [ ] Verify new optional fields present in webhook
   d. [ ] Test backward compatibility of webhook payload

9. [ ] Create integration test for model UUID searchability
   a. [ ] Register multiple models
   b. [ ] Search by UUID
   c. [ ] Verify correct model retrieved
   d. [ ] Test UUID uniqueness across models

## Implementation (Dependent on Testing)

10. [ ] Update register_baseline() method signature
    a. [ ] Add signature: Optional[ModelSignature] parameter
    b. [ ] Add input_example: Optional[Any] parameter
    c. [ ] Add code_paths: Optional[list[str]] parameter
    d. [ ] Update docstring with new parameters
    e. [ ] Add type hints for new parameters

11. [ ] Enhance register_baseline() implementation
    a. [ ] Create structured metadata dictionary (not params)
    b. [ ] Capture ModelInfo from mlflow.pyfunc.log_model()
    c. [ ] Preserve mlflow.register_model() call for ModelVersion (CRITICAL)
    d. [ ] Store model_uuid as model version tag
    e. [ ] Merge ModelInfo and ModelVersion into result dictionary
    f. [ ] Add logging for model_uuid
    g. [ ] Ensure backward compatibility (all new params optional)

12. [ ] Update register_improved_model() method signature
    a. [ ] Add signature: Optional[ModelSignature] parameter
    b. [ ] Add input_example: Optional[Any] parameter
    c. [ ] Add code_paths: Optional[list[str]] parameter
    d. [ ] Update docstring

13. [ ] Enhance register_improved_model() implementation
    a. [ ] Create structured metadata dictionary
    b. [ ] Capture ModelInfo from mlflow.pyfunc.log_model()
    c. [ ] Preserve mlflow.register_model() call for ModelVersion
    d. [ ] Store model_uuid as model version tag
    e. [ ] Merge ModelInfo and ModelVersion into result
    f. [ ] Maintain baseline_id and contributor tracking

14. [ ] Implement get_model_by_uuid() method
    a. [ ] Add method signature with type hints
    b. [ ] Implement UUID tag search using MlflowClient
    c. [ ] Extract metadata from model history
    d. [ ] Return comprehensive model information
    e. [ ] Handle not found case (return None)
    f. [ ] Add error logging

15. [ ] Add necessary imports
    a. [ ] Import ModelInfo from mlflow.models
    b. [ ] Import ModelSignature from mlflow.models
    c. [ ] Import infer_signature (for documentation examples)
    d. [ ] Verify no breaking imports

16. [ ] Run all tests to verify implementation
    a. [ ] Run unit tests: `pytest tests/unit/test_model_registry.py -v`
    b. [ ] Run integration tests: `pytest tests/integration/test_model_registration_integration.py -v`
    c. [ ] Run webhook tests: `pytest tests/unit/test_model_registry_hooks.py -v`
    d. [ ] Verify all tests pass
    e. [ ] Fix any failing tests

## Documentation (Dependent on Implementation)

17. [ ] Create migration guide for existing code
    a. [ ] Document backward compatibility
    b. [ ] Provide before/after code examples
    c. [ ] Show how to use new ModelInfo fields
    d. [ ] Document signature creation with infer_signature()
    e. [ ] Document structured metadata usage

18. [ ] Document webhook payload changes
    a. [ ] Document new optional fields
    b. [ ] Emphasize backward compatibility
    c. [ ] Provide example webhook payloads
    d. [ ] Note for hokusai-site consumers

19. [ ] Update API documentation
    a. [ ] Document register_baseline() new parameters
    b. [ ] Document register_improved_model() new parameters
    c. [ ] Document get_model_by_uuid() method
    d. [ ] Add usage examples for each method

20. [ ] Create example usage documentation
    a. [ ] Basic usage without new features (backward compatible)
    b. [ ] Advanced usage with signatures
    c. [ ] Usage with structured metadata
    d. [ ] Usage with git lineage (code_paths)
    e. [ ] UUID-based model lookup examples

21. [ ] Update README.md with summary of changes
    a. [ ] Add section on MLflow 3.4 ModelInfo integration
    b. [ ] Highlight improved model tracking features
    c. [ ] Link to migration guide
    d. [ ] Note backward compatibility

## Validation and Cleanup

22. [ ] Performance validation
    a. [ ] Measure registration time before changes
    b. [ ] Measure registration time after changes
    c. [ ] Verify performance impact < 5%
    d. [ ] Document any performance considerations

23. [ ] Final integration testing
    a. [ ] Test with real models (not mocks)
    b. [ ] Verify MLflow UI shows new metadata
    c. [ ] Test webhook delivery to hokusai-site (if available)
    d. [ ] Verify backward compatibility with existing models

24. [ ] Code review preparation
    a. [ ] Run linter: `ruff check src/services/model_registry.py`
    b. [ ] Run formatter: `ruff format src/services/model_registry.py`
    c. [ ] Verify all type hints are correct
    d. [ ] Remove any debug code or comments
    e. [ ] Verify no breaking changes to public API

## Critical Reminders

- DO NOT REMOVE mlflow.register_model() call - provides ModelVersion for webhooks
- PRESERVE webhook payload schema - hokusai-site depends on it
- MAINTAIN backward compatibility - all new parameters are optional
- TEST webhook integration thoroughly - production critical
