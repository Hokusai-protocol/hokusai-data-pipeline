# Hokusai ZK-Compatible Output Schema

This directory contains the JSON Schema specification for Hokusai pipeline outputs that are compatible with zero-knowledge proof generation and on-chain verification.

## Files

- `zk_output_schema.json` - The main JSON Schema specification
- `examples/` - Example JSON files demonstrating valid and invalid outputs
- `README.md` - This documentation file

## Schema Overview

The schema defines a standardized format for Hokusai evaluation pipeline outputs that enables:

1. **Zero-Knowledge Proof Generation** - All fields are deterministically serializable
2. **On-Chain Verification** - Hash-compatible format for blockchain verification
3. **Attestation Support** - Dedicated fields for signatures and proof blobs
4. **Reproducible Results** - Consistent structure across pipeline runs

## Required Sections

### 1. Schema Metadata
```json
{
  "schema_version": "1.0"
}
```

### 2. Pipeline Metadata
```json
{
  "metadata": {
    "pipeline_run_id": "unique_run_identifier",
    "timestamp": "2025-06-16T10:30:00.000Z",
    "pipeline_version": "git_commit_hash",
    "environment": "production|staging|test|development",
    "dry_run": false
  }
}
```

### 3. Evaluation Results
```json
{
  "evaluation_results": {
    "baseline_metrics": {
      "accuracy": 0.85,
      "precision": 0.82,
      "recall": 0.88,
      "f1": 0.84,
      "auroc": 0.90
    },
    "new_metrics": {
      "accuracy": 0.88,
      "precision": 0.85,
      "recall": 0.91,
      "f1": 0.89,
      "auroc": 0.93
    },
    "benchmark_metadata": {
      "size": 10000,
      "type": "benchmark_name",
      "dataset_hash": "sha256_hash_of_benchmark_data"
    }
  }
}
```

### 4. Delta Computation
```json
{
  "delta_computation": {
    "delta_one_score": 0.033,
    "metric_deltas": {
      "accuracy": {
        "baseline_value": 0.85,
        "new_value": 0.88,
        "absolute_delta": 0.03,
        "relative_delta": 0.035,
        "improvement": true
      }
    },
    "computation_method": "weighted_average_delta",
    "metrics_included": ["accuracy", "precision", "recall", "f1", "auroc"],
    "improved_metrics": ["accuracy", "precision", "recall", "f1", "auroc"],
    "degraded_metrics": []
  }
}
```

### 5. Model Information
```json
{
  "models": {
    "baseline": {
      "model_id": "baseline_v1.0.0",
      "model_type": "transformer_classifier",
      "model_hash": "sha256_hash_of_model_weights",
      "training_config_hash": "sha256_hash_of_training_config",
      "metrics": { /* same as evaluation_results.baseline_metrics */ }
    },
    "new": {
      "model_id": "enhanced_v1.1.0",
      "model_type": "transformer_classifier_enhanced",
      "model_hash": "sha256_hash_of_model_weights",
      "training_config_hash": "sha256_hash_of_training_config",
      "metrics": { /* same as evaluation_results.new_metrics */ }
    }
  }
}
```

### 6. Contributor Information

The schema supports two formats for contributor information:

#### Single Contributor Format
```json
{
  "contributor_info": {
    "contributor_id": "optional_contributor_identifier",
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    "data_hash": "sha256_hash_of_contributed_data",
    "data_manifest": {
      "source_path": "/path/to/data/file",
      "data_hash": "sha256_hash_of_data",
      "row_count": 5000,
      "column_count": 5,
      "columns": ["feature_1", "feature_2", "feature_3", "feature_4", "label"]
    },
    "contributor_weights": 0.091,
    "contributed_samples": 5000,
    "total_samples": 55000,
    "validation_status": "valid|invalid|pending|unknown"
  }
}
```

#### Multiple Contributors Format
```json
{
  "contributors": [
    {
      "id": "contributor_xyz789",
      "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
      "data_hash": "sha256_hash_of_contributed_data",
      "weight": 0.7,
      "contributed_samples": 5600,
      "validation_status": "valid",
      "data_manifest": { /* same structure as above */ }
    },
    {
      "id": "contributor_abc456",
      "wallet_address": "0x6C3e007f281f6948b37c511a11E43c8026d2F069",
      "data_hash": "sha256_hash_of_contributed_data",
      "weight": 0.3,
      "contributed_samples": 2400,
      "validation_status": "valid",
      "data_manifest": { /* same structure as above */ }
    }
  ]
}
```

**ETH Address Requirements:**
- Must follow Ethereum address format: `0x` followed by 40 hexadecimal characters
- Pattern: `^0[xX][a-fA-F0-9]{40}$`
- Used for on-chain verification and contributor reward distribution
- Each contributor must have a unique ETH address

### 7. Attestation Fields
```json
{
  "attestation": {
    "hash_tree_root": "merkle_tree_root_hash",
    "proof_ready": true,
    "signature_blob": "base64_encoded_signature_or_proof",
    "verification_key": "public_key_or_verification_parameters",
    "proof_system": "groth16|plonk|stark|ecdsa|none",
    "circuit_hash": "sha256_hash_of_zk_circuit",
    "public_inputs_hash": "sha256_hash_of_public_inputs"
  }
}
```

## Hash Requirements

All hash fields must be valid SHA-256 hashes (64 character hexadecimal strings matching the pattern `^[a-f0-9]{64}$`).

Examples of valid hashes:
- `abcd567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`
- `0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`

## Deterministic Serialization

For ZK proof generation, the output must be deterministically serializable. This means:

1. All dictionary keys are sorted recursively
2. JSON serialization uses consistent formatting (`separators=(',', ':'), sort_keys=True`)
3. No optional fields with `null` values should be included unless explicitly required
4. Numeric values should have consistent precision

## Validation

### CLI Tool
Use the provided CLI tool to validate outputs:

```bash
# Basic validation
python scripts/validate_schema.py output.json

# Validate with ZK proof readiness check
python scripts/validate_schema.py output.json --zk-check

# Get deterministic hash
python scripts/validate_schema.py output.json --output-hash

# Verbose output
python scripts/validate_schema.py output.json --verbose
```

### Python API
```python
from src.utils.schema_validator import SchemaValidator, validate_for_zk_proof

# Basic validation
validator = SchemaValidator()
is_valid, errors = validator.validate_output(output_data)

# ZK proof readiness
is_ready, deterministic_hash, errors = validate_for_zk_proof(output_data)
```

## Integration with Pipeline

To integrate this schema with the existing pipeline:

1. Update the `compare_and_output_delta` step to generate outputs in this format
2. Add schema validation to the output generation process
3. Include attestation field population in the final step
4. Update tests to validate against the new schema

## Schema Evolution

The schema uses semantic versioning:
- **Major version changes** (e.g., 1.0 → 2.0): Breaking changes requiring migration
- **Minor version changes** (e.g., 1.0 → 1.1): Backward-compatible additions

When updating the schema:
1. Update the `schema_version` field in the JSON Schema
2. Update the `$id` field with the new version
3. Document migration requirements for breaking changes
4. Update validation utilities if needed

## ZK Proof Generation Workflow

1. **Pipeline Execution**: Run the Hokusai evaluation pipeline
2. **Schema Validation**: Validate output against this schema
3. **Deterministic Hash**: Compute the deterministic hash of the output
4. **Merkle Tree**: Build Merkle tree from evaluation data
5. **Circuit Input**: Use the deterministic hash and Merkle root as circuit inputs
6. **Proof Generation**: Generate ZK proof using chosen proof system
7. **Verification**: On-chain verification using public inputs and proof

## Examples

See the `examples/` directory for:
- `valid_zk_output.json` - Complete valid example with single contributor including ETH address
- `valid_zk_output_multiple_contributors.json` - Valid example with multiple contributors and ETH addresses
- `invalid_example.json` - Example with validation errors

These examples demonstrate proper usage, ETH address formatting, and common validation errors.