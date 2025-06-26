"""ZK-compatible output formatter for Hokusai pipeline results."""

import hashlib
import json
from datetime import datetime
from typing import Optional
import subprocess
import os

from .schema_validator import SchemaValidator, validate_for_zk_proof


class ZKCompatibleOutputFormatter:
    """Converts pipeline results to ZK-compatible format."""
    
    def __init__(self):
        self.validator = SchemaValidator()
    
    def format_output(self, pipeline_results: dict) -> dict:
        """Convert pipeline results to ZK-compatible format.
        
        Args:
            pipeline_results: Raw pipeline results in existing format
            
        Returns:
            ZK-compatible formatted output
        """
        zk_output = {
            "schema_version": "1.0",
            "metadata": self._format_metadata(pipeline_results),
            "evaluation_results": self._format_evaluation_results(pipeline_results),
            "delta_computation": self._format_delta_computation(pipeline_results),
            "models": self._format_models(pipeline_results),
            "attestation": self._format_attestation(pipeline_results)
        }
        
        # Choose between single contributor or multiple contributors format
        contributors_data = pipeline_results.get("contributors", [])
        if contributors_data and len(contributors_data) > 1:
            # Multiple contributors
            zk_output["contributors"] = self._format_contributors(pipeline_results)
        else:
            # Single contributor (existing format)
            zk_output["contributor_info"] = self._format_contributor_info(pipeline_results)
        
        return zk_output
    
    def format_and_validate(self, pipeline_results: dict) -> tuple[dict, bool, list]:
        """Format output and validate it against ZK schema.
        
        Args:
            pipeline_results: Raw pipeline results
            
        Returns:
            Tuple of (formatted_output, is_valid, errors)
        """
        formatted_output = self.format_output(pipeline_results)
        
        # Validate against schema
        is_valid, errors = self.validator.validate_output(formatted_output)
        
        if is_valid:
            # Check ZK readiness
            is_zk_ready, deterministic_hash, zk_errors = validate_for_zk_proof(formatted_output)
            if not is_zk_ready:
                is_valid = False
                errors.extend(zk_errors)
            else:
                # Update attestation with deterministic hash
                formatted_output["attestation"]["public_inputs_hash"] = deterministic_hash
        
        return formatted_output, is_valid, errors
    
    def _format_metadata(self, results: dict) -> dict:
        """Format pipeline metadata section."""
        pipeline_meta = results.get("pipeline_metadata", {})
        
        # Get git commit hash for pipeline version
        pipeline_version = self._get_git_commit_hash()
        
        return {
            "pipeline_run_id": pipeline_meta.get("run_id", "unknown"),
            "timestamp": self._format_timestamp(pipeline_meta.get("timestamp")),
            "pipeline_version": pipeline_version,
            "environment": pipeline_meta.get("config", {}).get("environment", "unknown"),
            "dry_run": pipeline_meta.get("dry_run", False)
        }
    
    def _format_evaluation_results(self, results: dict) -> dict:
        """Format evaluation results section."""
        baseline_model = results.get("baseline_model", {})
        new_model = results.get("new_model", {})
        eval_meta = results.get("evaluation_metadata", {})
        
        # Extract benchmark metadata
        benchmark_data = eval_meta.get("benchmark_dataset", {})
        
        return {
            "baseline_metrics": baseline_model.get("metrics", {}),
            "new_metrics": new_model.get("metrics", {}),
            "benchmark_metadata": {
                "size": benchmark_data.get("size", 0),
                "type": benchmark_data.get("type", "unknown"),
                "features": benchmark_data.get("features", []),
                "dataset_hash": self._compute_benchmark_hash(benchmark_data)
            },
            "evaluation_timestamp": self._format_timestamp(eval_meta.get("evaluation_timestamp")),
            "evaluation_time_seconds": eval_meta.get("evaluation_time_seconds", 0.0)
        }
    
    def _format_delta_computation(self, results: dict) -> dict:
        """Format delta computation section."""
        delta_comp = results.get("delta_computation", {})
        
        # Transform metric deltas to new format
        metric_deltas = {}
        for metric, values in delta_comp.get("metric_deltas", {}).items():
            metric_deltas[metric] = {
                "baseline_value": values.get("baseline_value", 0.0),
                "new_value": values.get("new_value", 0.0),
                "absolute_delta": values.get("absolute_delta", 0.0),
                "relative_delta": values.get("relative_delta", 0.0),
                "improvement": values.get("improvement", False)
            }
        
        return {
            "delta_one_score": delta_comp.get("delta_one_score", 0.0),
            "metric_deltas": metric_deltas,
            "computation_method": delta_comp.get("computation_method", "weighted_average_delta"),
            "metrics_included": delta_comp.get("metrics_included", []),
            "improved_metrics": delta_comp.get("improved_metrics", []),
            "degraded_metrics": delta_comp.get("degraded_metrics", [])
        }
    
    def _format_models(self, results: dict) -> dict:
        """Format models section."""
        baseline = results.get("baseline_model", {})
        new = results.get("new_model", {})
        
        return {
            "baseline": self._format_single_model(baseline, "baseline"),
            "new": self._format_single_model(new, "new")
        }
    
    def _format_single_model(self, model_info: dict, model_type: str) -> dict:
        """Format a single model's information."""
        formatted = {
            "model_id": model_info.get("model_id", f"unknown_{model_type}"),
            "model_type": model_info.get("model_type", "unknown"),
            "model_hash": self._compute_model_hash(model_info),
            "training_config_hash": self._compute_config_hash(model_info),
            "mlflow_run_id": model_info.get("mlflow_run_id"),
            "metrics": model_info.get("metrics", {})
        }
        
        # Add training metadata for new model
        if "training_metadata" in model_info:
            training_meta = model_info["training_metadata"]
            formatted["training_metadata"] = {
                "base_samples": training_meta.get("base_samples", 0),
                "contributed_samples": training_meta.get("contributed_samples", 0),
                "contribution_ratio": training_meta.get("contribution_ratio", 0.0),
                "data_manifest": self._format_data_manifest(training_meta.get("data_manifest", {}))
            }
        
        return formatted
    
    def _format_contributor_info(self, results: dict) -> dict:
        """Format contributor information section."""
        contrib = results.get("contributor_attribution", {})
        data_manifest = contrib.get("data_manifest", {})
        
        contributor_info = {
            "data_hash": contrib.get("data_hash", self._compute_placeholder_hash("contributor_data")),
            "data_manifest": self._format_data_manifest(data_manifest),
            "contributor_weights": contrib.get("contributor_weights", 0.0),
            "contributed_samples": contrib.get("contributed_samples", 0),
            "total_samples": contrib.get("total_samples", 0),
            "validation_status": "valid"  # Default status
        }
        
        # Add ETH wallet address if provided
        wallet_address = contrib.get("wallet_address")
        if wallet_address:
            from .eth_address_validator import validate_eth_address, normalize_eth_address
            try:
                validate_eth_address(wallet_address)
                contributor_info["wallet_address"] = normalize_eth_address(wallet_address)
            except Exception as e:
                # Log warning but don't fail the pipeline
                print(f"Warning: Invalid ETH address provided: {e}")
        
        return contributor_info
    
    def _format_contributors(self, results: dict) -> list:
        """Format multiple contributors information section."""
        contributors_data = results.get("contributors", [])
        formatted_contributors = []
        
        for contributor in contributors_data:
            data_manifest = contributor.get("data_manifest", {})
            
            contributor_info = {
                "id": contributor.get("id", contributor.get("contributor_id", "unknown")),
                "data_hash": contributor.get("data_hash", self._compute_placeholder_hash("contributor_data")),
                "data_manifest": self._format_data_manifest(data_manifest),
                "weight": contributor.get("weight", contributor.get("contributor_weights", 0.0)),
                "contributed_samples": contributor.get("contributed_samples", 0),
                "validation_status": contributor.get("validation_status", "valid")
            }
            
            # Add ETH wallet address if provided
            wallet_address = contributor.get("wallet_address")
            if wallet_address:
                from .eth_address_validator import validate_eth_address, normalize_eth_address
                try:
                    validate_eth_address(wallet_address)
                    contributor_info["wallet_address"] = normalize_eth_address(wallet_address)
                except Exception as e:
                    # Log warning but don't fail the pipeline
                    print(f"Warning: Invalid ETH address for contributor {contributor_info['id']}: {e}")
            
            formatted_contributors.append(contributor_info)
        
        return formatted_contributors
    
    def _format_data_manifest(self, manifest: dict) -> dict:
        """Format data manifest section."""
        return {
            "source_path": manifest.get("source_path", "unknown"),
            "row_count": manifest.get("row_count", 0),
            "column_count": manifest.get("column_count", 0),
            "columns": manifest.get("columns", []),
            "data_hash": manifest.get("data_hash", self._compute_placeholder_hash("data_manifest")),
            "dtypes": manifest.get("dtypes", {}),
            "null_counts": manifest.get("null_counts", {}),
            "unique_counts": manifest.get("unique_counts", {})
        }
    
    def _format_attestation(self, results: dict) -> dict:
        """Format attestation section for ZK proof generation."""
        # Compute Merkle tree root from all evaluation data
        hash_tree_root = self._compute_merkle_root(results)
        
        # Extract public inputs for ZK proof
        public_inputs = self._extract_public_inputs(results)
        public_inputs_hash = self._compute_deterministic_hash(public_inputs)
        
        return {
            "hash_tree_root": hash_tree_root,
            "proof_ready": True,
            "signature_blob": None,
            "verification_key": None,
            "proof_system": "none",
            "circuit_hash": None,
            "public_inputs_hash": public_inputs_hash
        }
    
    def _compute_model_hash(self, model_info: dict) -> str:
        """Compute SHA-256 hash of model weights/parameters."""
        # For now, use model_id and metrics as proxy for model content
        model_content = {
            "model_id": model_info.get("model_id", ""),
            "model_type": model_info.get("model_type", ""),
            "metrics": model_info.get("metrics", {})
        }
        content_str = json.dumps(model_content, sort_keys=True)
        return hashlib.sha256(content_str.encode('utf-8')).hexdigest()
    
    def _compute_config_hash(self, model_info: dict) -> str:
        """Compute SHA-256 hash of training configuration."""
        config_content = model_info.get("training_metadata", {})
        config_str = json.dumps(config_content, sort_keys=True)
        return hashlib.sha256(config_str.encode('utf-8')).hexdigest()
    
    def _compute_benchmark_hash(self, benchmark_info: dict) -> str:
        """Compute SHA-256 hash of benchmark dataset."""
        # Use the dataset metadata as proxy for the actual data
        benchmark_content = {
            "size": benchmark_info.get("size", 0),
            "type": benchmark_info.get("type", ""),
            "features": benchmark_info.get("features", [])
        }
        content_str = json.dumps(benchmark_content, sort_keys=True)
        return hashlib.sha256(content_str.encode('utf-8')).hexdigest()
    
    def _compute_merkle_root(self, results: dict) -> str:
        """Compute Merkle tree root of all evaluation data."""
        # For now, compute hash of all evaluation results
        # In production, this should build a proper Merkle tree
        evaluation_data = {
            "delta_computation": results.get("delta_computation", {}),
            "baseline_model": results.get("baseline_model", {}),
            "new_model": results.get("new_model", {}),
            "evaluation_metadata": results.get("evaluation_metadata", {})
        }
        data_str = json.dumps(evaluation_data, sort_keys=True)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()
    
    def _extract_public_inputs(self, results: dict) -> dict:
        """Extract public inputs for ZK proof."""
        return {
            "delta_one_score": results.get("delta_computation", {}).get("delta_one_score", 0.0),
            "baseline_metrics": results.get("baseline_model", {}).get("metrics", {}),
            "new_metrics": results.get("new_model", {}).get("metrics", {}),
            "contributor_hash": results.get("contributor_attribution", {}).get("data_hash", "")
        }
    
    def _compute_deterministic_hash(self, data: dict) -> str:
        """Compute deterministic hash of data."""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()
    
    def _compute_placeholder_hash(self, prefix: str) -> str:
        """Compute placeholder hash for missing data."""
        content = f"{prefix}_placeholder_{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _format_timestamp(self, timestamp_str: Optional[str]) -> str:
        """Format timestamp to ISO 8601 with Z suffix."""
        if not timestamp_str:
            timestamp_str = datetime.now().isoformat()
        
        # Ensure timestamp ends with Z for UTC
        if not timestamp_str.endswith('Z'):
            if '.' in timestamp_str:
                # Remove microseconds and add Z
                timestamp_str = timestamp_str.split('.')[0] + 'Z'
            else:
                timestamp_str += 'Z'
        
        return timestamp_str
    
    def _get_git_commit_hash(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            if result.returncode == 0:
                return result.stdout.strip()[:8]  # Short hash
        except Exception:
            pass
        
        return "unknown"