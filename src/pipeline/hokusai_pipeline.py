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
        from src.modules.data_integration import DataIntegrator
        from pathlib import Path
        import pandas as pd
        
        print(f"Loading contributed data from: {self.contributed_data_path}")
        
        # Initialize data integrator
        integrator = DataIntegrator(random_seed=self.config.random_seed)
        
        if self.dry_run:
            # Create mock contributed data
            self.contributed_data = pd.DataFrame({
                "query_id": [f"contrib_q_{i}" for i in range(100)],
                "query_text": [f"contributed query {i}" for i in range(100)],
                "feature_1": [0.1 * i for i in range(100)],
                "feature_2": [0.2 * i for i in range(100)],
                "feature_3": [0.3 * i for i in range(100)],
                "label": [i % 2 for i in range(100)]
            })
            print(f"Created mock contributed data: {len(self.contributed_data)} samples")
            
            # Create mock base dataset for merging
            base_data = pd.DataFrame({
                "query_id": [f"base_q_{i}" for i in range(500)],
                "query_text": [f"base query {i}" for i in range(500)],
                "feature_1": [0.1 * i for i in range(500)],
                "feature_2": [0.2 * i for i in range(500)],
                "feature_3": [0.3 * i for i in range(500)],
                "label": [i % 2 for i in range(500)]
            })
            
            # Validate schema
            required_columns = ["query_id", "query_text", "feature_1", "feature_2", "feature_3", "label"]
            integrator.validate_schema(self.contributed_data, required_columns)
            
            # Remove PII (if any)
            self.contributed_data = integrator.remove_pii(self.contributed_data)
            
            # Deduplicate
            self.contributed_data = integrator.deduplicate(self.contributed_data)
            
            # Merge with base dataset
            self.integrated_data = integrator.merge_datasets(
                base_data, 
                self.contributed_data, 
                merge_strategy="append",
                run_id=current.run_id,
                metaflow_run_id=current.run_id
            )
            
            # Create data manifest
            self.data_manifest = integrator.create_data_manifest(
                self.contributed_data, 
                Path(self.contributed_data_path)
            )
            
            print(f"Integrated dataset: {len(self.integrated_data)} total samples")
            print(f"Data hash: {self.data_manifest['data_hash'][:16]}...")
            
        else:
            # Load actual contributed data
            data_path = Path(self.contributed_data_path)
            
            # Load contributed data
            self.contributed_data = integrator.load_data(
                data_path, 
                run_id=current.run_id,
                metaflow_run_id=current.run_id
            )
            
            # Validate schema (define required columns based on your needs)
            required_columns = ["query_id", "label"]  # Adjust as needed
            integrator.validate_schema(self.contributed_data, required_columns)
            
            # Clean data
            self.contributed_data = integrator.remove_pii(self.contributed_data)
            self.contributed_data = integrator.deduplicate(self.contributed_data)
            
            # TODO: Load base training dataset and merge
            # For now, just use contributed data as the training set
            self.integrated_data = self.contributed_data
            
            # Create data manifest
            self.data_manifest = integrator.create_data_manifest(
                self.contributed_data, 
                data_path
            )
            
            print(f"Loaded and validated contributed data: {len(self.contributed_data)} samples")
            print(f"Data hash: {self.data_manifest['data_hash'][:16]}...")
        
        self.next(self.train_new_model)
    
    @step
    def train_new_model(self):
        """Train new model with integrated dataset."""
        from src.modules.model_training import ModelTrainer
        from src.utils.mlflow_config import mlflow_run_context, log_step_parameters, log_step_metrics
        import time
        
        print("Training new model with integrated dataset")
        
        # Initialize MLflow tracking
        with mlflow_run_context(
            experiment_name=self.config.mlflow_experiment_name,
            run_name=f"train_new_model_{current.run_id}",
            tags={
                "pipeline.step": "train_new_model",
                "pipeline.run_id": current.run_id,
                "pipeline.timestamp": datetime.utcnow().isoformat()
            }
        ):
            # Initialize model trainer
            trainer = ModelTrainer(
                random_seed=self.config.random_seed,
                mlflow_tracking_uri=self.config.mlflow_tracking_uri,
                experiment_name=self.config.mlflow_experiment_name
            )
            
            training_start_time = time.time()
            
            if self.dry_run:
                # Simulate model training with integrated data
                training_samples = len(self.integrated_data)
                contributed_samples = len(self.contributed_data)
                
                # Prepare training data using the integrated dataset
                if 'label' in self.integrated_data.columns:
                    feature_columns = [col for col in self.integrated_data.columns if col not in ['label', 'query_id']]
                    X_train, X_test, y_train, y_test = trainer.prepare_training_data(
                        self.integrated_data,
                        target_column='label',
                        feature_columns=feature_columns,
                        test_size=0.2
                    )
                    
                    # Train mock model
                    self.new_model = trainer.train_mock_model(
                        X_train, y_train, 
                        model_type="hokusai_integrated_classifier"
                    )
                    
                    # Add integration-specific metadata
                    self.new_model.update({
                        "training_samples": training_samples,
                        "contributed_samples": contributed_samples,
                        "data_hash": self.data_manifest["data_hash"],
                        "integration_metadata": {
                            "base_samples": training_samples - contributed_samples,
                            "contributed_samples": contributed_samples,
                            "contribution_ratio": contributed_samples / training_samples,
                            "data_manifest": self.data_manifest
                        }
                    })
                    
                    training_time = time.time() - training_start_time
                    
                    # Log training parameters and metrics to MLflow
                    log_step_parameters({
                        "training_samples": training_samples,
                        "contributed_samples": contributed_samples,
                        "feature_count": len(feature_columns),
                        "model_type": "mock_hokusai_integrated_classifier",
                        "random_seed": self.config.random_seed,
                        "data_hash": self.data_manifest["data_hash"]
                    })
                    
                    log_step_metrics({
                        "training_time_seconds": training_time,
                        "training_samples": training_samples,
                        "contributed_samples": contributed_samples,
                        "feature_count": len(feature_columns),
                        **self.new_model["metrics"]
                    })
                    
                    # Log model to MLflow
                    model_run_id = trainer.log_model_to_mlflow(
                        model=self.new_model,
                        model_name="hokusai_integrated_model",
                        metrics=self.new_model["metrics"],
                        params={
                            "random_seed": self.config.random_seed,
                            "training_samples": training_samples,
                            "contributed_samples": contributed_samples,
                            "model_type": "mock_hokusai_integrated_classifier"
                        }
                    )
                    
                    self.new_model["mlflow_run_id"] = model_run_id
                    
                    print(f"Trained mock new model with {training_samples} samples ({contributed_samples} contributed)")
                    print(f"Model metrics: accuracy={self.new_model['metrics']['accuracy']:.4f}")
                    print(f"MLflow run ID: {model_run_id}")
                    
                else:
                    raise ValueError("Integrated dataset missing 'label' column for training")
                    
            else:
                # Implement actual model training with self.integrated_data
                training_samples = len(self.integrated_data)
                contributed_samples = len(self.contributed_data)
                
                if 'label' not in self.integrated_data.columns:
                    raise ValueError("Integrated dataset missing 'label' column for training")
                
                # Prepare training data
                feature_columns = [col for col in self.integrated_data.columns if col not in ['label', 'query_id']]
                X_train, X_test, y_train, y_test = trainer.prepare_training_data(
                    self.integrated_data,
                    target_column='label',
                    feature_columns=feature_columns,
                    test_size=0.2
                )
                
                # Train actual sklearn model (for now using RandomForest as example)
                from sklearn.ensemble import RandomForestClassifier
                from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
                
                model = trainer.train_sklearn_model(
                    X_train, y_train,
                    RandomForestClassifier,
                    {
                        "n_estimators": 100,
                        "max_depth": 10,
                        "min_samples_split": 5,
                        "random_state": self.config.random_seed
                    }
                )
                
                # Calculate metrics on test set
                y_pred = model.predict(X_test)
                y_pred_proba = model.predict_proba(X_test)[:, 1] if len(model.classes_) == 2 else None
                
                metrics = {
                    "accuracy": accuracy_score(y_test, y_pred),
                    "precision": precision_score(y_test, y_pred, average='weighted'),
                    "recall": recall_score(y_test, y_pred, average='weighted'),
                    "f1_score": f1_score(y_test, y_pred, average='weighted')
                }
                
                if y_pred_proba is not None:
                    metrics["auroc"] = roc_auc_score(y_test, y_pred_proba)
                
                training_time = time.time() - training_start_time
                
                # Create training report
                training_report = trainer.create_training_report(
                    model, X_train, y_train, training_time
                )
                
                # Log model to MLflow
                model_run_id = trainer.log_model_to_mlflow(
                    model=model,
                    model_name="hokusai_integrated_model",
                    metrics=metrics,
                    params={
                        "random_seed": self.config.random_seed,
                        "training_samples": training_samples,
                        "contributed_samples": contributed_samples,
                        "n_estimators": 100,
                        "max_depth": 10,
                        "min_samples_split": 5
                    }
                )
                
                # Store model information
                self.new_model = {
                    "type": "RandomForestClassifier",
                    "version": "2.0.0",
                    "training_samples": training_samples,
                    "contributed_samples": contributed_samples,
                    "data_hash": self.data_manifest["data_hash"],
                    "metrics": metrics,
                    "training_report": training_report,
                    "mlflow_run_id": model_run_id,
                    "integration_metadata": {
                        "base_samples": training_samples - contributed_samples,
                        "contributed_samples": contributed_samples,
                        "contribution_ratio": contributed_samples / training_samples,
                        "data_manifest": self.data_manifest
                    }
                }
                
                # Log training parameters and metrics to current MLflow run
                log_step_parameters({
                    "training_samples": training_samples,
                    "contributed_samples": contributed_samples,
                    "feature_count": len(feature_columns),
                    "model_type": "RandomForestClassifier",
                    "random_seed": self.config.random_seed,
                    "data_hash": self.data_manifest["data_hash"]
                })
                
                log_step_metrics({
                    "training_time_seconds": training_time,
                    "training_samples": training_samples,
                    "contributed_samples": contributed_samples,
                    "feature_count": len(feature_columns),
                    **metrics
                })
                
                print(f"Trained RandomForest model with {training_samples} samples ({contributed_samples} contributed)")
                print(f"Model metrics: accuracy={metrics['accuracy']:.4f}, f1={metrics['f1_score']:.4f}")
                print(f"MLflow run ID: {model_run_id}")
        
        self.next(self.evaluate_on_benchmark)
    
    @step
    def evaluate_on_benchmark(self):
        """Evaluate both models on standardized benchmark datasets."""
        from src.modules.evaluation import ModelEvaluator
        from src.utils.mlflow_config import mlflow_run_context, log_step_parameters, log_step_metrics
        import time
        
        print("Evaluating models on benchmark dataset")
        
        # Initialize MLflow tracking for evaluation step
        with mlflow_run_context(
            experiment_name=self.config.mlflow_experiment_name,
            run_name=f"evaluate_on_benchmark_{current.run_id}",
            tags={
                "pipeline.step": "evaluate_on_benchmark",
                "pipeline.run_id": current.run_id,
                "pipeline.timestamp": datetime.utcnow().isoformat()
            }
        ):
            # Initialize evaluator
            evaluator = ModelEvaluator(metrics=self.config.evaluation_metrics)
            evaluation_start_time = time.time()
            
            if self.dry_run:
                # Create mock benchmark dataset for testing
                import pandas as pd
                benchmark_size = 1000
                benchmark_data = pd.DataFrame({
                    "feature_1": [0.1 * i for i in range(benchmark_size)],
                    "feature_2": [0.2 * i for i in range(benchmark_size)],
                    "feature_3": [0.3 * i for i in range(benchmark_size)],
                    "label": [i % 2 for i in range(benchmark_size)]
                })
                
                # Split into features and labels
                feature_columns = ["feature_1", "feature_2", "feature_3"]
                X_benchmark = benchmark_data[feature_columns]
                y_benchmark = benchmark_data["label"]
                
                # Evaluate baseline model
                baseline_results = evaluator.evaluate_model(
                    self.baseline_model, X_benchmark, y_benchmark
                )
                
                # Evaluate new model
                new_results = evaluator.evaluate_model(
                    self.new_model, X_benchmark, y_benchmark
                )
                
                # Compare models
                comparison = evaluator.compare_models(
                    baseline_results["metrics"],
                    new_results["metrics"]
                )
                
                # Calculate delta score
                delta_score = evaluator.calculate_delta_score(comparison)
                
                # Create evaluation report
                evaluation_report = evaluator.create_evaluation_report(
                    baseline_results, new_results, comparison, delta_score
                )
                
                evaluation_time = time.time() - evaluation_start_time
                
                # Store evaluation results
                self.evaluation_results = {
                    "baseline_metrics": baseline_results["metrics"],
                    "new_metrics": new_results["metrics"],
                    "comparison": comparison,
                    "delta_score": delta_score,
                    "evaluation_report": evaluation_report,
                    "benchmark_dataset": {
                        "size": benchmark_size,
                        "features": feature_columns,
                        "type": "mock_classification_benchmark"
                    },
                    "evaluation_timestamp": datetime.utcnow().isoformat(),
                    "evaluation_time_seconds": evaluation_time
                }
                
                # Log parameters and metrics to MLflow
                log_step_parameters({
                    "benchmark_size": benchmark_size,
                    "benchmark_type": "mock_classification_benchmark",
                    "feature_count": len(feature_columns),
                    "baseline_model_type": baseline_results["model_type"],
                    "new_model_type": new_results["model_type"],
                    "evaluation_metrics": self.config.evaluation_metrics
                })
                
                log_step_metrics({
                    "evaluation_time_seconds": evaluation_time,
                    "benchmark_size": benchmark_size,
                    "delta_score": delta_score,
                    **{f"baseline_{k}": v for k, v in baseline_results["metrics"].items()},
                    **{f"new_{k}": v for k, v in new_results["metrics"].items()},
                    **{f"delta_{k}": v["absolute_delta"] for k, v in comparison.items()}
                })
                
                print(f"Completed mock evaluation in {evaluation_time:.2f} seconds")
                print(f"Baseline model performance: {baseline_results['metrics']}")
                print(f"New model performance: {new_results['metrics']}")
                print(f"Delta score: {delta_score:.4f}")
                
            else:
                # TODO: Load actual benchmark datasets
                # For now, create a simple benchmark from the test data
                if hasattr(self, 'integrated_data') and 'label' in self.integrated_data.columns:
                    # Use a subset of integrated data as benchmark (in real scenario, this would be separate)
                    benchmark_data = self.integrated_data.sample(
                        n=min(1000, len(self.integrated_data)), 
                        random_state=self.config.random_seed
                    )
                    
                    feature_columns = [col for col in benchmark_data.columns 
                                     if col not in ['label', 'query_id']]
                    X_benchmark = benchmark_data[feature_columns]
                    y_benchmark = benchmark_data["label"]
                    
                    # Evaluate baseline model
                    baseline_results = evaluator.evaluate_model(
                        self.baseline_model, X_benchmark, y_benchmark
                    )
                    
                    # Evaluate new model (load from MLflow if needed)
                    new_results = evaluator.evaluate_model(
                        self.new_model, X_benchmark, y_benchmark
                    )
                    
                    # Compare models
                    comparison = evaluator.compare_models(
                        baseline_results["metrics"],
                        new_results["metrics"]
                    )
                    
                    # Calculate delta score
                    delta_score = evaluator.calculate_delta_score(comparison)
                    
                    # Create evaluation report
                    evaluation_report = evaluator.create_evaluation_report(
                        baseline_results, new_results, comparison, delta_score
                    )
                    
                    evaluation_time = time.time() - evaluation_start_time
                    
                    # Store evaluation results
                    self.evaluation_results = {
                        "baseline_metrics": baseline_results["metrics"],
                        "new_metrics": new_results["metrics"],
                        "comparison": comparison,
                        "delta_score": delta_score,
                        "evaluation_report": evaluation_report,
                        "benchmark_dataset": {
                            "size": len(benchmark_data),
                            "features": feature_columns,
                            "type": "integrated_data_benchmark"
                        },
                        "evaluation_timestamp": datetime.utcnow().isoformat(),
                        "evaluation_time_seconds": evaluation_time
                    }
                    
                    # Log parameters and metrics to MLflow
                    log_step_parameters({
                        "benchmark_size": len(benchmark_data),
                        "benchmark_type": "integrated_data_benchmark",
                        "feature_count": len(feature_columns),
                        "baseline_model_type": baseline_results["model_type"],
                        "new_model_type": new_results["model_type"],
                        "evaluation_metrics": self.config.evaluation_metrics
                    })
                    
                    log_step_metrics({
                        "evaluation_time_seconds": evaluation_time,
                        "benchmark_size": len(benchmark_data),
                        "delta_score": delta_score,
                        **{f"baseline_{k}": v for k, v in baseline_results["metrics"].items()},
                        **{f"new_{k}": v for k, v in new_results["metrics"].items()},
                        **{f"delta_{k}": v["absolute_delta"] for k, v in comparison.items()}
                    })
                    
                    print(f"Completed evaluation in {evaluation_time:.2f} seconds")
                    print(f"Baseline model performance: {baseline_results['metrics']}")
                    print(f"New model performance: {new_results['metrics']}")
                    print(f"Delta score: {delta_score:.4f}")
                    
                else:
                    raise ValueError("No suitable benchmark data available for evaluation")
        
        self.next(self.compare_and_output_delta)
    
    @step
    def compare_and_output_delta(self):
        """Calculate performance delta between models and package results."""
        print("Calculating performance delta and packaging results")
        
        # Extract comparison results from evaluation step
        self.delta_results = self.evaluation_results["comparison"]
        self.delta_one = self.evaluation_results["delta_score"]
        
        # Create structured output for verification and downstream processing
        self.delta_output = {
            "delta_one_score": self.delta_one,
            "model_comparison": self.delta_results,
            "baseline_model": {
                "metrics": self.evaluation_results["baseline_metrics"],
                "model_id": self.baseline_model.get("version", "unknown"),
                "model_type": self.baseline_model.get("type", "unknown")
            },
            "new_model": {
                "metrics": self.evaluation_results["new_metrics"],
                "model_id": self.new_model.get("version", "unknown"),
                "model_type": self.new_model.get("type", "unknown"),
                "training_metadata": self.new_model.get("integration_metadata", {})
            },
            "evaluation_metadata": {
                "benchmark_dataset": self.evaluation_results["benchmark_dataset"],
                "evaluation_timestamp": self.evaluation_results["evaluation_timestamp"],
                "evaluation_time_seconds": self.evaluation_results["evaluation_time_seconds"],
                "metrics_calculated": list(self.delta_results.keys())
            },
            "summary": self.evaluation_results["evaluation_report"]["summary"]
        }
        
        print(f"DeltaOne score: {self.delta_one:.4f}")
        print(f"Performance summary:")
        print(f"  - Improved metrics: {self.delta_output['summary']['improved_metrics']}")
        print(f"  - Degraded metrics: {self.delta_output['summary']['degraded_metrics']}")
        print(f"  - Overall improvement: {self.delta_output['summary']['overall_improvement']}")
        
        self.next(self.generate_attestation_output)
    
    @step 
    def generate_attestation_output(self):
        """Generate attestation-ready output with all results."""
        print("Generating attestation output")
        
        # Create attestation-ready output with enhanced evaluation data
        self.attestation_output = {
            "schema_version": ATTESTATION_SCHEMA_VERSION,
            "attestation_version": ATTESTATION_VERSION,
            "run_id": self.run_metadata["run_id"],
            "timestamp": datetime.utcnow().isoformat(),
            "contributor_data_hash": self.data_manifest["data_hash"],
            "contributor_data_manifest": self.data_manifest,
            "baseline_model_id": self.baseline_model.get("version", "unknown"),
            "new_model_id": self.new_model.get("version", "unknown"),
            "evaluation_results": {
                "baseline_metrics": self.evaluation_results["baseline_metrics"],
                "new_metrics": self.evaluation_results["new_metrics"],
                "benchmark_metadata": self.evaluation_results["benchmark_dataset"],
                "evaluation_timestamp": self.evaluation_results["evaluation_timestamp"],
                "evaluation_time_seconds": self.evaluation_results["evaluation_time_seconds"]
            },
            "model_comparison": self.delta_results,
            "delta_one_score": self.delta_one,
            "delta_output": self.delta_output,
            "performance_summary": {
                "improved_metrics": self.delta_output["summary"]["improved_metrics"],
                "degraded_metrics": self.delta_output["summary"]["degraded_metrics"],
                "overall_improvement": self.delta_output["summary"]["overall_improvement"],
                "total_metrics_evaluated": len(self.delta_results)
            },
            "metadata": self.run_metadata,
            "status": STATUS_SUCCESS
        }
        
        print(f"Generated attestation output with {len(self.delta_results)} metrics evaluated")
        print(f"Evaluation completed in {self.evaluation_results['evaluation_time_seconds']:.2f} seconds")
        
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