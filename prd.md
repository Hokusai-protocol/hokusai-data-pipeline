# PRD: Define JSON Schema for ZK-Compatible Output

## Objectives

Define and implement a standardized JSON schema for Hokusai pipeline outputs that enables zero-knowledge proof generation and on-chain verification. This schema will serve as the foundation for attestation-ready results from the evaluation pipeline.

## Success Criteria

- Frozen JSON schema specification with all required fields
- Schema supports zk-proof generation workflows
- Compatible with on-chain hash verification mechanisms
- Includes dedicated field for signature/proof blob storage
- Schema validation can be performed programmatically
- Documentation explains usage for contributors and verifiers

## Personas

**Primary Users:**
- **Pipeline Operators**: Need consistent output format from evaluation runs
- **ZK Proof Generators**: Require structured data for proof creation
- **On-chain Verifiers**: Need hash-compatible format for verification

**Secondary Users:**
- **Contributors**: Will receive results in this format
- **Auditors**: Need to verify pipeline output integrity

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

1. **Research existing zk-proof JSON standards**
   - Review common attestation formats
   - Analyze blockchain verification patterns
   - Document compatibility requirements

2. **Design core schema structure**
   - Define required vs optional fields
   - Establish field naming conventions
   - Create nested object hierarchy

3. **Implement JSON Schema file**
   - Create formal JSON Schema specification
   - Add validation rules and constraints
   - Include examples and documentation

4. **Create schema validation utilities**
   - Python validation function
   - CLI tool for schema checking
   - Integration with pipeline output

5. **Add tests and documentation**
   - Unit tests for schema validation
   - Example JSON files demonstrating usage
   - Integration guide for pipeline steps

6. **Integrate with existing pipeline**
   - Update output generation in compare_and_output_delta step
   - Ensure backward compatibility
   - Add schema validation to CI/CD

## Acceptance Criteria

- [ ] JSON Schema file validates correctly
- [ ] Schema supports all required attestation fields
- [ ] Python validation utility works correctly
- [ ] Example outputs pass schema validation
- [ ] Documentation explains all fields clearly
- [ ] Integration tests pass with new schema
- [ ] ZK-proof compatibility verified
- [ ] On-chain hash verification possible

## Risk Mitigation

- **Schema Evolution**: Use semantic versioning for schema changes
- **Performance Impact**: Validate schema overhead is minimal
- **Compatibility**: Ensure existing tools continue working
- **Security**: Review schema for information leakage risks