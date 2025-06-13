# PRD: Build CLI for Contributor-Side Data Validation

## Objectives

Build a command-line interface tool that allows contributors to validate, hash, and preview their data locally before submission to the Hokusai pipeline. This empowers contributors to ensure data quality and compatibility while maintaining privacy by performing validation on their local machines.

## Project Summary

**[feature] Build CLI for contributor-side data validation** - Allow contributors to validate, hash, and preview their data locally.

Key requirements:
* Accept .json, .csv, .parquet file formats
* Redact/check for PII (Personally Identifiable Information)
* Output manifest + SHA256 hash for data integrity verification

## Personas

**Primary User: Data Contributor**
- Has datasets they want to contribute to model training
- Needs assurance their data is properly formatted and free of PII
- Wants to preview what will be submitted without exposing raw data
- Requires proof of contribution via data hash

**Secondary User: Pipeline Operator**
- Needs to verify contributed data meets requirements
- Wants consistent data format and quality across contributors
- Requires cryptographic proof of data integrity

## Success Criteria

1. **Multi-format Support**: CLI accepts and validates .json, .csv, and .parquet files
2. **PII Detection**: Automatically detects and flags potential PII in datasets
3. **Data Validation**: Validates schema, data types, and required fields
4. **Hash Generation**: Generates SHA256 hash of validated data for integrity verification
5. **Manifest Creation**: Produces detailed manifest with metadata about the validated dataset
6. **User-Friendly Interface**: Clear command-line interface with helpful error messages
7. **Local Execution**: All validation happens locally without sending data externally

## Technical Requirements

### Input Requirements
- Support for .json, .csv, and .parquet file formats
- Configurable schema validation rules
- Customizable PII detection patterns

### Output Requirements
- Data validation report (pass/fail with details)
- PII detection results with flagged fields
- SHA256 hash of the validated dataset
- JSON manifest containing:
  - File metadata (size, format, row count, column count)
  - Schema information
  - Validation results
  - Data hash
  - Timestamp

### Core Features

1. **File Format Detection and Loading**
   - Auto-detect file format from extension
   - Load data using appropriate parser
   - Handle large files efficiently

2. **Schema Validation**
   - Validate required columns exist
   - Check data types match expected schema
   - Verify data ranges and constraints
   - Support custom validation rules

3. **PII Detection**
   - Scan for common PII patterns (SSN, email, phone, etc.)
   - Support custom PII patterns via configuration
   - Option to automatically redact detected PII
   - Generate PII scan report

4. **Data Quality Checks**
   - Check for missing values
   - Identify outliers
   - Validate data consistency
   - Generate quality metrics

5. **Hash Generation**
   - Generate deterministic SHA256 hash
   - Include option to hash normalized data
   - Support chunked hashing for large files

6. **Manifest Generation**
   - Create comprehensive JSON manifest
   - Include all validation results
   - Add contributor metadata (optional)
   - Sign manifest with data hash

## Implementation Plan

### CLI Structure
```
hokusai-validate [OPTIONS] <input_file>

Options:
  --schema       Path to schema definition file
  --output-dir   Directory for output files (default: current directory)
  --no-pii-scan  Skip PII detection
  --redact-pii   Automatically redact detected PII
  --verbose      Show detailed validation progress
  --format       Force specific file format (auto-detected by default)
```

### Dependencies
- Click for CLI framework
- Pandas for data manipulation
- PyArrow for Parquet support
- Presidio or similar for PII detection
- JSON Schema for validation
- Rich for enhanced CLI output

## User Experience

### Success Flow
1. Contributor runs: `hokusai-validate mydata.csv`
2. CLI loads and analyzes the data
3. Performs schema validation
4. Scans for PII
5. Generates hash and manifest
6. Outputs results with clear success message

### Error Handling
- Clear error messages for validation failures
- Suggestions for fixing common issues
- Option to output detailed error report
- Non-zero exit codes for automation

## Security Considerations

- All processing happens locally
- No data transmission over network
- Secure hash generation
- Optional PII redaction
- No storage of sensitive data

## Acceptance Criteria

- [ ] CLI successfully validates files in all three formats (.json, .csv, .parquet)
- [ ] PII detection correctly identifies common PII patterns
- [ ] Schema validation catches type mismatches and missing fields
- [ ] SHA256 hash generation is deterministic and verifiable
- [ ] Manifest contains all required metadata
- [ ] Clear documentation and help text
- [ ] Comprehensive error handling with helpful messages
- [ ] Unit tests achieve >90% code coverage
- [ ] Integration tests cover all major use cases
- [ ] Performance: Can process 1GB file in under 60 seconds