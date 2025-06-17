# PRD: Integrate ZKSchema with Existing Pipeline Output Generation

## Objectives

Integrate the existing ZK-compatible JSON schema with the Hokusai data evaluation pipeline to ensure all pipeline outputs conform to the standardized format required for zero-knowledge proof generation and on-chain verification. This task focuses on connecting the already-defined schema with the current pipeline implementation.

## Success Criteria

- Pipeline generates outputs that validate against the existing ZK schema specification
- All existing functionality remains intact while outputs use the new ZK-compatible format
- Schema validation is integrated into the pipeline execution process
- Deterministic output hashing is implemented for ZK proof compatibility
- Migration path exists for existing output files
- CLI validation tool works with pipeline-generated outputs

## Personas

**Primary User: Pipeline Developer**
- Needs pipeline to automatically generate ZK-compatible outputs
- Requires clear validation feedback when outputs don't conform
- Wants minimal changes to existing pipeline logic

**Secondary User: ZK Developer** 
- Needs standardized output format for proof generation
- Requires deterministic hashing for circuit compatibility
- Wants validated attestation fields for proof inputs

## Technical Requirements

### Core Schema Elements

The JSON schema must include:

1. **Metadata Section**
   - Pipeline execution ID
   - Timestamp (ISO 8601 format)
   - Schema version
   - Pipeline version/commit hash

2. **Model Information**
   - Baseline model ID and hash
   - New model ID and hash
   - Training configuration hash

3. **Evaluation Results**
   - DeltaOne computation result
   - Raw performance metrics (AUROC, accuracy, etc.)
   - Contributor data hashes
   - Model weights/parameters hash

4. **Attestation Fields**
   - Signature/proof blob placeholder
   - Hash of all evaluation data
   - Verification metadata

5. **Contributor Information**
   - Data submission hash
   - Contributor identifier
   - Data validation status

### Schema Validation

- JSON Schema Draft 2020-12 compliance
- Required vs optional field definitions
- Data type constraints and formats
- Range validation for numeric fields

### ZK Compatibility Requirements

- All fields must be deterministically serializable
- Hash computation must be reproducible
- Support for Merkle tree construction
- Compatible with common zk-SNARK libraries

## Implementation Tasks

### Task 1: Review Current Pipeline Output Structure
- Examine existing pipeline output generation in the compare_and_output_delta step
- Identify current output format and sections in src/modules/evaluation.py
- Map existing fields to new ZK schema requirements
- Document any missing fields required by the ZK schema

### Task 2: Implement ZK-Compatible Output Formatter
- Create ZKCompatibleOutputFormatter class in src/utils/
- Implement format_output method to convert pipeline results to ZK format
- Add helper methods for each schema section (metadata, evaluation_results, etc.)
- Implement deterministic hashing functions for models, configs, and benchmarks
- Add Merkle tree computation for hash_tree_root in attestation section

### Task 3: Update Pipeline Output Generation
- Modify compare_and_output_delta step to use new formatter
- Integrate schema validation before saving outputs
- Ensure pipeline fails gracefully if output doesn't validate
- Add ZK readiness checking to pipeline execution
- Update output file naming to indicate ZK compatibility

### Task 4: Integrate Schema Validation
- Import and use existing SchemaValidator from src/utils/schema_validator.py
- Add validation calls after output formatting
- Implement error handling for validation failures
- Add logging for validation results and errors
- Ensure validation works with both JSON schema and ZK compatibility checks

### Task 5: Create Integration Tests
- Write tests for ZK-compatible output generation in tests/integration/
- Test that pipeline outputs validate against the schema
- Verify deterministic output generation with fixed seeds
- Test error handling for invalid outputs
- Add tests for all schema sections and required fields

### Task 6: Update CLI Validation Tool
- Modify scripts/validate_schema.py to work with pipeline integration
- Add pipeline output validation commands
- Ensure CLI tool can validate newly generated outputs
- Test CLI tool with sample pipeline outputs

### Task 7: Create Migration Script
- Build script to convert existing output files to new format
- Add validation of migrated outputs in outputs/ directory
- Provide progress reporting for bulk migrations
- Handle errors gracefully during migration
- Test migration with existing output samples

### Task 8: Update Documentation
- Add integration instructions to docs/ZK_SCHEMA_INTEGRATION.md
- Document new output format structure
- Provide examples of before/after output formats
- Add troubleshooting guide for common validation errors
- Update README with new validation requirements

## Technical Requirements

- Must use existing schema/zk_output_schema.json specification
- Must integrate with existing src/utils/schema_validator.py
- Must maintain backward compatibility during transition
- All outputs must pass ZK readiness validation
- Must implement deterministic hashing for proof compatibility
- Schema validation must be performant for production use

## Dependencies

- Existing ZK schema file: schema/zk_output_schema.json
- Existing validation library: src/utils/schema_validator.py
- Existing CLI tool: scripts/validate_schema.py
- Current pipeline implementation with compare_and_output_delta step