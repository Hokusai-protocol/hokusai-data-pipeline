"""Enhanced Hokusai evaluation pipeline with MLOps services integration."""

from metaflow import FlowSpec, step, Parameter, current
import json
import os
from datetime import datetime
from pathlib import Path
import pandas as pd

from src.utils.config import get_config, get_test_config
from src.utils.constants import *
from src.services.model_registry import HokusaiModelRegistry
from src.services.performance_tracker import PerformanceTracker
from src.services.experiment_manager import ExperimentManager


class HokusaiEvaluationPipeline(FlowSpec):
    """
    Enhanced Hokusai evaluation pipeline with integrated MLOps services.
    
    This pipeline includes:
    - Model registry integration for baseline and improved models
    - Performance tracking with attestation generation
    - Experiment management for reproducible comparisons
    - Contributor attribution throughout the workflow
    """
    
    # Pipeline parameters
    baseline_model_path = Parameter(
        "baseline-model",
        help="Path to baseline model or model ID in registry",
        default=None
    )
    
    contributed_data_path = Parameter(
        "contributed-data",
        help="Path to contributed dataset",
        required=True
    )
    
    contributor_address = Parameter(
        "contributor",
        help="Ethereum address of the data contributor",
        required=True
    )
    
    model_type = Parameter(
        "model-type",
        help="Type of model (lead_scoring, classification, etc.)",
        default="lead_scoring"
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
    
    disable_services = Parameter(
        "disable-services",
        help="Disable MLOps services for backward compatibility",
        is_flag=True
    )
    
    @step
    def start(self):
        """Initialize pipeline configuration and services."""
        self.config = get_test_config() if self.dry_run else get_config()
        
        print(f"Starting Enhanced Hokusai Pipeline")
        print(f"Environment: {self.config.environment}")
        print(f"Contributor: {self.contributor_address}")
        print(f"Model Type: {self.model_type}")
        print(f"MLOps Services: {'Disabled' if self.disable_services else 'Enabled'}")
        
        # Set random seeds for reproducibility
        import random
        import numpy as np
        random.seed(self.config.random_seed)
        np.random.seed(self.config.random_seed)
        
        # Initialize services
        if not self.disable_services:
            mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
            self.registry = HokusaiModelRegistry(tracking_uri=mlflow_uri)
            self.tracker = PerformanceTracker()
            self.experiment_manager = ExperimentManager()
        
        # Initialize run metadata
        self.run_metadata = {
            "run_id": current.run_id,
            "started_at": datetime.utcnow().isoformat(),
            "contributor_address": self.contributor_address,
            "model_type": self.model_type,
            "config": self.config.to_dict()
        }
        
        self.next(self.load_baseline_model)
    
    @step
    def load_baseline_model(self):
        """Load the baseline model from storage or registry."""
        from src.modules.baseline_loader import BaselineModelLoader
        
        loader = BaselineModelLoader(
            mlflow_tracking_uri=self.config.mlflow_config.get("tracking_uri")
        )
        
        if self.dry_run:
            # Use mock model for testing
            self.baseline_model = loader.load_from_file(
                "data/test_fixtures/mock_baseline_model.json"
            )
            self.baseline_id = "mock_baseline/1"
        else:
            if self.baseline_model_path:
                # Load from file or MLFlow
                if self.baseline_model_path.startswith("models:/"):
                    self.baseline_model = loader.load_from_mlflow(self.baseline_model_path)
                    self.baseline_id = self.baseline_model_path
                else:
                    self.baseline_model = loader.load_from_file(self.baseline_model_path)
                    self.baseline_id = f"file_{Path(self.baseline_model_path).stem}/1"
            else:
                raise ValueError("Baseline model path must be provided")
        
        self.next(self.register_baseline)
    
    @step 
    def register_baseline(self):
        """Register baseline model in the unified registry."""
        if self.disable_services or self.dry_run:
            print("Skipping baseline registration (services disabled or dry run)")
            self.baseline_registry_id = self.baseline_id
        else:
            # Register the baseline model
            registration_result = self.registry.register_baseline(
                model=self.baseline_model,
                model_type=self.model_type,
                metadata={
                    "dataset": "initial_training",
                    "version": "1.0.0",
                    "pipeline_run_id": current.run_id
                }
            )
            self.baseline_registry_id = registration_result["model_id"]
            print(f"Registered baseline model: {self.baseline_registry_id}")
        
        self.next(self.integrate_contributed_data)
    
    @step
    def integrate_contributed_data(self):
        """Integrate contributed data with training dataset."""
        from src.modules.data_integration import DataIntegrator
        
        integrator = DataIntegrator()
        
        # Load contributed data
        contributed_data = integrator.load_data(
            self.contributed_data_path,
            is_dry_run=self.dry_run
        )
        
        # For this example, we'll use the contributed data directly
        # In production, you'd merge with existing training data
        self.merged_data = contributed_data
        
        # Store contribution metadata
        self.contribution_metadata = {
            "contributor_id": f"contrib_{current.run_id[:8]}",
            "contributor_address": self.contributor_address,
            "dataset_hash": integrator._calculate_hash(contributed_data),
            "data_size": len(contributed_data),
            "contribution_timestamp": datetime.utcnow().isoformat()
        }
        
        print(f"Integrated {len(self.merged_data)} rows of contributed data")
        
        self.next(self.create_experiment)
    
    @step
    def create_experiment(self):
        """Create an experiment for tracking the improvement."""
        if self.disable_services or self.dry_run:
            print("Skipping experiment creation (services disabled or dry run)")
            self.experiment_id = f"dry_run_exp_{current.run_id[:8]}"
        else:
            # Create improvement experiment
            self.experiment_id = self.experiment_manager.create_improvement_experiment(
                baseline_model_id=self.baseline_registry_id,
                contributed_data={
                    "features": self.merged_data.values,
                    "metadata": self.contribution_metadata
                }
            )
            print(f"Created experiment: {self.experiment_id}")
        
        self.next(self.train_new_model)
    
    @step
    def train_new_model(self):
        """Train new model with contributed data."""
        from src.modules.model_training import ModelTrainer
        
        trainer = ModelTrainer(use_mlflow=not self.disable_services)
        
        # Train the model
        self.improved_model, training_metrics = trainer.train(
            train_data=self.merged_data,
            model_config=self.config.training_config,
            is_dry_run=self.dry_run
        )
        
        print(f"Model training complete. Metrics: {training_metrics}")
        
        self.next(self.evaluate_on_benchmark)
    
    @step
    def evaluate_on_benchmark(self):
        """Evaluate both models on benchmark dataset."""
        from src.modules.evaluation import ModelEvaluator
        
        evaluator = ModelEvaluator()
        
        # Load or generate test data
        if self.dry_run:
            test_data = pd.DataFrame({
                'feature1': [1, 2, 3, 4],
                'feature2': [5, 6, 7, 8],
                'label': [0, 1, 1, 0]
            })
        else:
            # Load actual benchmark dataset
            test_data = pd.read_csv(self.config.evaluation_config['benchmark_path'])
        
        # Evaluate baseline model
        self.baseline_metrics = evaluator.evaluate(
            model=self.baseline_model,
            test_data=test_data,
            model_name="baseline"
        )
        
        # Evaluate improved model
        self.improved_metrics = evaluator.evaluate(
            model=self.improved_model,
            test_data=test_data,
            model_name="improved"
        )
        
        print(f"Baseline metrics: {self.baseline_metrics}")
        print(f"Improved metrics: {self.improved_metrics}")
        
        self.next(self.track_improvement)
    
    @step
    def track_improvement(self):
        """Track performance improvement and generate attestation."""
        if self.disable_services or self.dry_run:
            # Simple delta calculation
            self.delta_metrics = {
                metric: self.improved_metrics[metric] - self.baseline_metrics[metric]
                for metric in self.baseline_metrics
            }
            self.attestation = {
                "version": "1.0",
                "delta_metrics": self.delta_metrics,
                "contributor_address": self.contributor_address,
                "generated_at": datetime.utcnow().isoformat()
            }
        else:
            # Use performance tracker service
            self.delta_metrics, self.attestation = self.tracker.track_improvement(
                baseline_metrics=self.baseline_metrics,
                improved_metrics=self.improved_metrics,
                data_contribution=self.contribution_metadata
            )
            
            # Register improved model
            registration_result = self.registry.register_improved_model(
                model=self.improved_model,
                baseline_id=self.baseline_registry_id,
                delta_metrics=self.delta_metrics,
                contributor=self.contributor_address
            )
            
            self.improved_model_id = registration_result["model_id"]
            print(f"Registered improved model: {self.improved_model_id}")
            
            # Log contributor impact
            self.tracker.log_contribution_impact(
                contributor_address=self.contributor_address,
                model_id=self.improved_model_id,
                delta=self.delta_metrics
            )
        
        print(f"Performance delta: {self.delta_metrics}")
        
        self.next(self.generate_output)
    
    @step
    def generate_output(self):
        """Generate final output with ZK-compatible format."""
        from src.utils.zk_output_formatter import ZKOutputFormatter
        
        formatter = ZKOutputFormatter()
        
        # Prepare output data
        output_data = {
            "model_id": getattr(self, 'improved_model_id', 'dry_run_model/1'),
            "baseline_score": self.baseline_metrics.get("accuracy", 0.0),
            "new_score": self.improved_metrics.get("accuracy", 0.0),
            "improvement": self.delta_metrics.get("accuracy", 0.0),
            "metric": "accuracy",
            "attestation": self.attestation,
            "contributor_info": {
                "contributor_id": self.contribution_metadata["contributor_id"],
                "wallet_address": self.contributor_address,
                "dataset_hash": self.contribution_metadata["dataset_hash"]
            }
        }
        
        # Format for ZK compatibility
        zk_output = formatter.format_output(output_data)
        
        # Save outputs
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save attestation
        attestation_file = output_path / f"attestation_{current.run_id}.json"
        with open(attestation_file, 'w') as f:
            json.dump(self.attestation, f, indent=2)
        
        # Save ZK output
        zk_output_file = output_path / f"zk_output_{current.run_id}.json"
        with open(zk_output_file, 'w') as f:
            json.dump(zk_output, f, indent=2)
        
        print(f"Outputs saved to {output_path}")
        
        self.next(self.end)
    
    @step
    def end(self):
        """Finalize pipeline and generate summary."""
        # Update run metadata
        self.run_metadata.update({
            "completed_at": datetime.utcnow().isoformat(),
            "status": "success",
            "delta_metrics": self.delta_metrics,
            "attestation_hash": self.attestation.get("attestation_hash", ""),
            "outputs": {
                "attestation": f"{self.output_dir}/attestation_{current.run_id}.json",
                "zk_output": f"{self.output_dir}/zk_output_{current.run_id}.json"
            }
        })
        
        # Print summary
        print("\n" + "="*50)
        print("PIPELINE SUMMARY")
        print("="*50)
        print(f"Run ID: {current.run_id}")
        print(f"Contributor: {self.contributor_address}")
        print(f"Model Type: {self.model_type}")
        print(f"Baseline Score: {self.baseline_metrics.get('accuracy', 0):.4f}")
        print(f"Improved Score: {self.improved_metrics.get('accuracy', 0):.4f}")
        print(f"Improvement: {self.delta_metrics.get('accuracy', 0):.4f}")
        print(f"Attestation Hash: {self.attestation.get('attestation_hash', 'N/A')}")
        print("="*50)


if __name__ == "__main__":
    HokusaiEvaluationPipeline()