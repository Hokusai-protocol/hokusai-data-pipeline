# ZK Schema Integration Guide

This document provides instructions for integrating the ZK-compatible JSON schema into the existing Hokusai pipeline.

## Overview

The ZK-compatible schema standardizes pipeline outputs to enable zero-knowledge proof generation and on-chain verification. This integration requires updating the output generation process to conform to the new schema format.

## Current vs New Format

### Current Format
The existing pipeline generates outputs with these main sections:
- `schema_version`
- `delta_computation`
- `baseline_model`
- `new_model`
- `contributor_attribution`
- `evaluation_metadata`
- `pipeline_metadata`

### New ZK Format
The new schema restructures and enhances the output with:
- `schema_version`
- `metadata` (pipeline information)
- `evaluation_results` (metrics and benchmark data)
- `delta_computation` (improved structure)
- `models` (baseline and new model info)
- `contributor_info` (contributor data)
- `attestation` (ZK proof fields)

## Integration Steps

### Step 1: Update Output Formatter

Modify `src/utils/attestation.py` or create a new output formatter:

```python
from src.utils.schema_validator import SchemaValidator, validate_for_zk_proof
import hashlib
from datetime import datetime

class ZKCompatibleOutputFormatter:
    def __init__(self):
        self.validator = SchemaValidator()
    
    def format_output(self, pipeline_results: dict) -> dict:
        """Convert pipeline results to ZK-compatible format."""
        return {
            "schema_version": "1.0",
            "metadata": self._format_metadata(pipeline_results),
            "evaluation_results": self._format_evaluation_results(pipeline_results),
            "delta_computation": self._format_delta_computation(pipeline_results),
            "models": self._format_models(pipeline_results),
            "contributor_info": self._format_contributor_info(pipeline_results),
            "attestation": self._format_attestation(pipeline_results)
        }
    
    def _format_metadata(self, results: dict) -> dict:
        """Format pipeline metadata section."""
        pipeline_meta = results.get("pipeline_metadata", {})
        return {
            "pipeline_run_id": pipeline_meta.get("run_id"),
            "timestamp": datetime.now().isoformat() + "Z",
            "pipeline_version": "current_commit_hash",  # Get from git
            "environment": pipeline_meta.get("config", {}).get("environment", "unknown"),
            "dry_run": pipeline_meta.get("dry_run", False)
        }
    
    def _format_evaluation_results(self, results: dict) -> dict:
        """Format evaluation results section."""
        baseline_model = results.get("baseline_model", {})
        new_model = results.get("new_model", {})
        eval_meta = results.get("evaluation_metadata", {})
        
        return {
            "baseline_metrics": baseline_model.get("metrics", {}),
            "new_metrics": new_model.get("metrics", {}),
            "benchmark_metadata": {
                "size": eval_meta.get("benchmark_dataset", {}).get("size"),
                "type": eval_meta.get("benchmark_dataset", {}).get("type"),
                "dataset_hash": self._compute_benchmark_hash(eval_meta)
            },
            "evaluation_timestamp": eval_meta.get("evaluation_timestamp"),
            "evaluation_time_seconds": eval_meta.get("evaluation_time_seconds")
        }
    
    def _format_delta_computation(self, results: dict) -> dict:
        """Format delta computation section."""
        delta_comp = results.get("delta_computation", {})
        return {
            "delta_one_score": delta_comp.get("delta_one_score"),
            "metric_deltas": delta_comp.get("metric_deltas", {}),
            "computation_method": delta_comp.get("computation_method"),
            "metrics_included": delta_comp.get("metrics_included", []),
            "improved_metrics": delta_comp.get("improved_metrics", []),
            "degraded_metrics": delta_comp.get("degraded_metrics", [])
        }
    
    def _format_models(self, results: dict) -> dict:
        """Format models section."""
        baseline = results.get("baseline_model", {})
        new = results.get("new_model", {})
        
        return {
            "baseline": {
                "model_id": baseline.get("model_id"),
                "model_type": baseline.get("model_type"),
                "model_hash": self._compute_model_hash(baseline),
                "training_config_hash": self._compute_config_hash(baseline),
                "mlflow_run_id": baseline.get("mlflow_run_id"),
                "metrics": baseline.get("metrics", {})
            },
            "new": {
                "model_id": new.get("model_id"),
                "model_type": new.get("model_type"),
                "model_hash": self._compute_model_hash(new),
                "training_config_hash": self._compute_config_hash(new),
                "mlflow_run_id": new.get("mlflow_run_id"),
                "metrics": new.get("metrics", {}),
                "training_metadata": new.get("training_metadata", {})
            }
        }
    
    def _format_contributor_info(self, results: dict) -> dict:
        """Format contributor information section."""
        contrib = results.get("contributor_attribution", {})
        return {
            "contributor_id": contrib.get("contributor_id"),
            "wallet_address": contrib.get("wallet_address"),  # ETH address for on-chain verification
            "data_hash": contrib.get("data_hash"),
            "data_manifest": contrib.get("data_manifest", {}),
            "contributor_weights": contrib.get("contributor_weights"),
            "contributed_samples": contrib.get("contributed_samples"),
            "total_samples": contrib.get("total_samples"),
            "validation_status": "valid"  # Default, should be determined by validation
        }
    
    def _format_attestation(self, results: dict) -> dict:
        """Format attestation section for ZK proof generation."""
        # Compute Merkle tree root from all evaluation data
        hash_tree_root = self._compute_merkle_root(results)
        
        # Compute public inputs hash
        public_inputs = self._extract_public_inputs(results)
        public_inputs_hash = hashlib.sha256(
            str(public_inputs).encode('utf-8')
        ).hexdigest()
        
        return {
            "hash_tree_root": hash_tree_root,
            "proof_ready": True,
            "signature_blob": None,  # To be filled by proof generation
            "verification_key": None,  # To be filled by proof generation
            "proof_system": "none",  # Default, update when proof is generated
            "circuit_hash": None,  # To be filled when circuit is used
            "public_inputs_hash": public_inputs_hash
        }
    
    def _compute_model_hash(self, model_info: dict) -> str:
        """Compute SHA-256 hash of model weights/parameters."""
        # This should hash the actual model weights
        # For now, return a placeholder
        model_id = model_info.get("model_id", "unknown")
        return hashlib.sha256(model_id.encode('utf-8')).hexdigest()
    
    def _compute_config_hash(self, model_info: dict) -> str:
        """Compute SHA-256 hash of training configuration."""
        # This should hash the training configuration
        config_str = str(model_info.get("training_metadata", {}))
        return hashlib.sha256(config_str.encode('utf-8')).hexdigest()
    
    def _compute_benchmark_hash(self, eval_meta: dict) -> str:
        """Compute SHA-256 hash of benchmark dataset."""
        # This should hash the actual benchmark data
        benchmark_info = eval_meta.get("benchmark_dataset", {})
        benchmark_str = str(benchmark_info)
        return hashlib.sha256(benchmark_str.encode('utf-8')).hexdigest()
    
    def _compute_merkle_root(self, results: dict) -> str:
        """Compute Merkle tree root of all evaluation data."""
        # This should build a proper Merkle tree
        # For now, return a hash of all results
        results_str = str(results)
        return hashlib.sha256(results_str.encode('utf-8')).hexdigest()
    
    def _extract_public_inputs(self, results: dict) -> dict:
        """Extract public inputs for ZK proof."""
        return {
            "delta_one_score": results.get("delta_computation", {}).get("delta_one_score"),
            "baseline_metrics": results.get("baseline_model", {}).get("metrics", {}),
            "new_metrics": results.get("new_model", {}).get("metrics", {}),
            "contributor_hash": results.get("contributor_attribution", {}).get("data_hash")
        }
```

### Step 2: Update Pipeline Steps

Modify the `compare_and_output_delta` step in the pipeline:

```python
# In src/modules/evaluation.py or relevant module

from src.utils.schema_validator import validate_for_zk_proof

class EnhancedDeltaComparator:
    def __init__(self):
        self.output_formatter = ZKCompatibleOutputFormatter()
    
    def generate_delta_output(self, baseline_results, new_results, metadata):
        """Generate ZK-compatible delta output."""
        # Existing delta computation logic...
        
        # Format to ZK-compatible structure
        zk_output = self.output_formatter.format_output({
            "baseline_model": baseline_results,
            "new_model": new_results,
            "delta_computation": delta_computation,
            "contributor_attribution": contributor_info,
            "evaluation_metadata": evaluation_metadata,
            "pipeline_metadata": metadata
        })
        
        # Validate ZK compatibility
        is_ready, deterministic_hash, errors = validate_for_zk_proof(zk_output)
        
        if not is_ready:
            raise ValueError(f"Output not ZK-ready: {errors}")
        
        # Add deterministic hash to attestation
        zk_output["attestation"]["public_inputs_hash"] = deterministic_hash
        
        return zk_output
```

### Step 3: Update Tests

Create integration tests for the new format:

```python
# tests/integration/test_zk_schema_integration.py

import pytest
from src.utils.schema_validator import SchemaValidator
from src.pipeline.hokusai_pipeline import HokusaiPipeline

class TestZKSchemaIntegration:
    def test_pipeline_output_zk_compatible(self):
        """Test that pipeline generates ZK-compatible output."""
        pipeline = HokusaiPipeline()
        
        # Run pipeline in test mode
        results = pipeline.run(dry_run=True)
        
        # Validate ZK compatibility
        validator = SchemaValidator()
        is_valid, errors = validator.validate_output(results)
        
        assert is_valid, f"Pipeline output not ZK-compatible: {errors}"
    
    def test_deterministic_output(self):
        """Test that pipeline output is deterministic."""
        pipeline = HokusaiPipeline()
        
        # Run pipeline twice with same inputs
        results1 = pipeline.run(dry_run=True, random_seed=42)
        results2 = pipeline.run(dry_run=True, random_seed=42)
        
        # Compute deterministic hashes
        hash1 = compute_deterministic_hash(results1)
        hash2 = compute_deterministic_hash(results2)
        
        assert hash1 == hash2, "Pipeline output not deterministic"
```

### Step 4: Migration Script

Create a script to convert existing outputs:

```python
# scripts/migrate_to_zk_schema.py

import json
import glob
from pathlib import Path
from src.utils.schema_validator import SchemaValidator

def migrate_output_file(input_path: str, output_path: str):
    """Migrate a single output file to ZK-compatible format."""
    with open(input_path, 'r') as f:
        old_output = json.load(f)
    
    formatter = ZKCompatibleOutputFormatter()
    new_output = formatter.format_output(old_output)
    
    # Validate new format
    validator = SchemaValidator()
    is_valid, errors = validator.validate_output(new_output)
    
    if not is_valid:
        print(f"Migration failed for {input_path}: {errors}")
        return False
    
    with open(output_path, 'w') as f:
        json.dump(new_output, f, indent=2)
    
    print(f"Migrated {input_path} -> {output_path}")
    return True

def main():
    """Migrate all output files in the outputs directory."""
    output_files = glob.glob("outputs/*.json")
    
    for file_path in output_files:
        if "zk_compatible" not in file_path:
            new_path = file_path.replace(".json", "_zk_compatible.json")
            migrate_output_file(file_path, new_path)

if __name__ == "__main__":
    main()
```

## Deployment Plan

### Phase 1: Parallel Output Generation
1. Keep existing output format
2. Generate additional ZK-compatible output alongside
3. Validate both formats in CI/CD

### Phase 2: Gradual Migration
1. Update downstream consumers to use new format
2. Add deprecation warnings for old format
3. Update documentation

### Phase 3: Full Migration
1. Remove old format generation
2. Update all references to use new schema
3. Remove migration compatibility code

## Monitoring and Validation

### CI/CD Integration
Add schema validation to your CI/CD pipeline:

```yaml
# In your CI configuration
- name: Validate ZK Schema Compliance
  run: |
    python scripts/validate_schema.py outputs/*.json --zk-check
```

### Runtime Validation
Add validation to pipeline execution:

```python
# In pipeline execution
def save_output(output_data, file_path):
    # Validate before saving
    validator = SchemaValidator()
    is_valid, errors = validator.validate_output(output_data)
    
    if not is_valid:
        logger.error(f"Output validation failed: {errors}")
        raise ValueError("Output does not conform to ZK schema")
    
    with open(file_path, 'w') as f:
        json.dump(output_data, f, indent=2)
```

## Troubleshooting

### Common Issues

1. **Hash Format Errors**: Ensure all hash fields are exactly 64 character hex strings
2. **Missing Required Fields**: Check that all required sections are present
3. **Invalid Timestamps**: Use ISO 8601 format with UTC timezone
4. **Metric Range Errors**: Ensure all metrics are between 0 and 1

### Debugging Tools

```bash
# Validate specific output
python scripts/validate_schema.py output.json --verbose

# Check ZK readiness
python scripts/validate_schema.py output.json --zk-check

# Get deterministic hash
python scripts/validate_schema.py output.json --output-hash

# JSON format output for programmatic use
python scripts/validate_schema.py output.json --format json
```

## Next Steps

After integration:

1. **ZK Circuit Development**: Design circuits that can verify the deterministic hashes
2. **Proof Generation**: Implement proof generation using the formatted outputs
3. **On-chain Verification**: Deploy verification contracts that can validate proofs
4. **Performance Optimization**: Optimize schema validation for high-throughput scenarios