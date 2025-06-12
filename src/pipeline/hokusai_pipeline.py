"""Main Hokusai evaluation pipeline using Metaflow."""

from metaflow import FlowSpec, step, Parameter, current
import json
from datetime import datetime
from pathlib import Path

from src.utils.config import get_config, get_test_config
from src.utils.constants import *


class HokusaiPipeline(FlowSpec):
    """
    Hokusai evaluation pipeline for model performance comparison.
    
    This pipeline evaluates the performance delta between a baseline model
    and a new model trained with contributed data, producing attestation-ready outputs.
    """
    
    # Pipeline parameters
    baseline_model_path = Parameter(
        "baseline-model",
        help="Path to baseline model",
        default=None
    )
    
    contributed_data_path = Parameter(
        "contributed-data",
        help="Path to contributed dataset",
        required=True
    )
    
    output_dir = Parameter(
        "output-dir",
        help="Directory for pipeline outputs",
        default="./outputs"
    )
    
    dry_run = Parameter(
        "dry-run",
        help="Run pipeline in test mode with mock data",
        is_flag=True
    )
    
    @step
    def start(self):
        """Initialize pipeline configuration and validate inputs."""
        self.config = get_test_config() if self.dry_run else get_config()
        
        print(f"Starting Hokusai pipeline")
        print(f"Environment: {self.config.environment}")
        print(f"Dry run: {self.dry_run}")
        print(f"Random seed: {self.config.random_seed}")
        
        # Set random seeds for reproducibility
        import random
        import numpy as np
        random.seed(self.config.random_seed)
        np.random.seed(self.config.random_seed)
        
        # Initialize run metadata
        self.run_metadata = {
            "run_id": current.run_id,
            "started_at": datetime.utcnow().isoformat(),
            "config": self.config.to_dict(),
            "parameters": {
                "baseline_model_path": self.baseline_model_path,
                "contributed_data_path": self.contributed_data_path,
                "output_dir": self.output_dir,
                "dry_run": self.dry_run,
            }
        }
        
        self.next(self.load_baseline_model)
    
    @step
    def load_baseline_model(self):
        """Load the baseline model from storage or registry."""
        print(f"Loading baseline model from: {self.baseline_model_path}")
        
        if self.dry_run:
            # Create mock baseline model for testing
            self.baseline_model = {
                "type": "mock_model",
                "version": "1.0.0",
                "metrics": {
                    "accuracy": 0.85,
                    "precision": 0.83,
                    "recall": 0.87,
                    "f1_score": 0.85,
                    "auroc": 0.91
                }
            }
            print("Loaded mock baseline model for dry run")
        else:
            # TODO: Implement actual model loading from MLflow or disk
            raise NotImplementedError("Model loading not yet implemented")
        
        self.next(self.integrate_contributed_data)
    
    @step
    def integrate_contributed_data(self):
        """Load and validate contributed dataset."""
        print(f"Loading contributed data from: {self.contributed_data_path}")
        
        if self.dry_run:
            # Create mock contributed data
            import pandas as pd
            self.contributed_data = pd.DataFrame({
                "query": [f"query_{i}" for i in range(100)],
                "label": [i % 2 for i in range(100)],
                "features": [[0.1 * i, 0.2 * i, 0.3 * i] for i in range(100)]
            })
            print(f"Loaded mock contributed data: {len(self.contributed_data)} samples")
        else:
            # TODO: Implement actual data loading and validation
            raise NotImplementedError("Data loading not yet implemented")
        
        self.next(self.train_new_model)
    
    @step
    def train_new_model(self):
        """Train new model with integrated dataset."""
        print("Training new model with contributed data")
        
        if self.dry_run:
            # Simulate model training
            self.new_model = {
                "type": "mock_model",
                "version": "2.0.0",
                "training_samples": len(self.contributed_data),
                "metrics": {
                    "accuracy": 0.88,  # Simulated improvement
                    "precision": 0.86,
                    "recall": 0.89,
                    "f1_score": 0.87,
                    "auroc": 0.93
                }
            }
            print("Trained mock new model for dry run")
        else:
            # TODO: Implement actual model training
            raise NotImplementedError("Model training not yet implemented")
        
        self.next(self.evaluate_on_benchmark)
    
    @step
    def evaluate_on_benchmark(self):
        """Evaluate both models on standardized benchmark."""
        print("Evaluating models on benchmark dataset")
        
        if self.dry_run:
            # Use mock evaluation results
            self.evaluation_results = {
                "baseline": self.baseline_model["metrics"],
                "new": self.new_model["metrics"],
                "benchmark_size": 1000,
                "evaluation_timestamp": datetime.utcnow().isoformat()
            }
            print("Completed mock evaluation for dry run")
        else:
            # TODO: Implement actual evaluation
            raise NotImplementedError("Model evaluation not yet implemented")
        
        self.next(self.compare_and_output_delta)
    
    @step
    def compare_and_output_delta(self):
        """Calculate performance delta between models."""
        print("Calculating performance delta")
        
        # Calculate deltas
        self.delta_results = {}
        for metric in self.config.evaluation_metrics:
            baseline_val = self.evaluation_results["baseline"].get(metric, 0)
            new_val = self.evaluation_results["new"].get(metric, 0)
            self.delta_results[metric] = {
                "baseline": baseline_val,
                "new": new_val,
                "delta": new_val - baseline_val,
                "delta_percentage": ((new_val - baseline_val) / baseline_val * 100) if baseline_val > 0 else 0
            }
        
        # Calculate overall DeltaOne score (simplified for now)
        delta_scores = [v["delta"] for v in self.delta_results.values()]
        self.delta_one = sum(delta_scores) / len(delta_scores) if delta_scores else 0
        
        print(f"DeltaOne score: {self.delta_one:.4f}")
        
        self.next(self.generate_attestation_output)
    
    @step 
    def generate_attestation_output(self):
        """Generate attestation-ready output with all results."""
        print("Generating attestation output")
        
        # Create attestation-ready output
        self.attestation_output = {
            "schema_version": ATTESTATION_SCHEMA_VERSION,
            "attestation_version": ATTESTATION_VERSION,
            "run_id": self.run_metadata["run_id"],
            "timestamp": datetime.utcnow().isoformat(),
            "contributor_data_hash": "mock_hash_" + self.contributed_data_path.replace("/", "_"),
            "baseline_model_id": self.baseline_model.get("version", "unknown"),
            "new_model_id": self.new_model.get("version", "unknown"),
            "evaluation_results": self.evaluation_results,
            "delta_results": self.delta_results,
            "delta_one_score": self.delta_one,
            "metadata": self.run_metadata,
            "status": STATUS_SUCCESS
        }
        
        self.next(self.monitor_and_log)
    
    @step
    def monitor_and_log(self):
        """Log results and monitoring information."""
        print("Logging pipeline results")
        
        # TODO: Integrate with MLflow for proper tracking
        if not self.dry_run:
            print("MLflow logging not yet implemented")
        
        self.next(self.end)
    
    @step
    def end(self):
        """Save outputs and complete pipeline."""
        print("Saving pipeline outputs")
        
        # Create output directory
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save attestation output
        attestation_file = output_path / f"attestation_{current.run_id}.json"
        with open(attestation_file, "w") as f:
            json.dump(self.attestation_output, f, indent=2)
        
        print(f"Attestation output saved to: {attestation_file}")
        print(f"Pipeline completed successfully!")
        print(f"DeltaOne score: {self.delta_one:.4f}")


if __name__ == "__main__":
    HokusaiPipeline()