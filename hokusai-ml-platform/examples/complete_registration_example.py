"""Complete example of model registration with Hokusai SDK.

This example demonstrates:
- MLflow authentication setup
- Model registration with proper error handling
- Using ModelVersionManager
- Batch predictions with HokusaiInferencePipeline
- Performance tracking
"""

import os
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Hokusai SDK components
from hokusai import (
    configure,
    setup_mlflow_auth,
    ModelRegistry,
    ModelVersionManager,
    ExperimentManager,
    PerformanceTracker,
    HokusaiInferencePipeline,
    HokusaiModel,
    MLflowAuthenticationError,
    MLflowConnectionError
)
from hokusai.core.ab_testing import ModelTrafficRouter

def setup_authentication():
    """Setup authentication for Hokusai SDK."""
    # Option 1: Basic configuration
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        raise ValueError("HOKUSAI_API_KEY environment variable not set")
    
    # Configure global authentication
    configure(
        api_key=api_key,
        api_endpoint=os.getenv("HOKUSAI_API_ENDPOINT", "https://api.hokus.ai")
    )
    
    # Option 2: Setup MLflow authentication if needed
    try:
        setup_mlflow_auth(
            tracking_uri=os.getenv("MLFLOW_TRACKING_URI"),
            username=os.getenv("MLFLOW_TRACKING_USERNAME"),
            password=os.getenv("MLFLOW_TRACKING_PASSWORD"),
            token=os.getenv("MLFLOW_TRACKING_TOKEN"),
            validate=True  # Validate connection
        )
        logger.info("MLflow authentication configured successfully")
    except MLflowAuthenticationError as e:
        logger.warning(f"MLflow authentication failed: {e}")
        logger.info("Continuing with optional MLflow mode")
        os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"


def register_model_example():
    """Example of registering a model."""
    # Create registry instance
    registry = ModelRegistry()
    
    # Create a mock model for demonstration
    model = HokusaiModel(
        model_id="example-model-001",
        model_type="lead_scoring",
        version="1.0.0"
    )
    
    # Set some mock metrics
    model._metrics = {
        "accuracy": 0.92,
        "precision": 0.89,
        "recall": 0.94,
        "f1_score": 0.91
    }
    
    try:
        # Method 1: Using original signature
        entry = registry.register_baseline(
            model=model,
            model_type="lead_scoring",
            metadata={
                "dataset": "customer_data_v2",
                "training_date": "2024-01-15"
            }
        )
        logger.info(f"Model registered successfully: {entry.model_id}")
        
        # Method 2: Using model_name parameter (backward compatibility)
        entry2 = registry.register_baseline(
            model_name="lead_scoring",  # This works too!
            model=model,
            metadata={
                "variant": "alternative_method"
            }
        )
        logger.info(f"Model registered with model_name: {entry2.model_id}")
        
    except Exception as e:
        logger.error(f"Failed to register model: {e}")


def version_management_example():
    """Example of using ModelVersionManager."""
    registry = ModelRegistry()
    version_manager = ModelVersionManager(registry)
    
    try:
        # Get latest version
        latest_version = version_manager.get_latest_version("lead_scoring")
        logger.info(f"Latest version: {latest_version}")
        
        # List all versions
        all_versions = version_manager.list_versions("lead_scoring")
        logger.info(f"All versions: {all_versions}")
        
        # Register a new version with auto-increment
        model = HokusaiModel(
            model_id="example-model-002",
            model_type="lead_scoring"
        )
        
        new_entry = version_manager.register_version(
            model=model,
            model_type="lead_scoring",
            auto_increment="patch",  # Will increment to 1.0.1
            metadata={"improvement": "feature_engineering"}
        )
        logger.info(f"New version registered: {new_entry.version}")
        
    except Exception as e:
        logger.error(f"Version management error: {e}")


def batch_prediction_example():
    """Example of batch predictions."""
    registry = ModelRegistry()
    version_manager = ModelVersionManager(registry)
    traffic_router = ModelTrafficRouter()
    
    # Create inference pipeline
    pipeline = HokusaiInferencePipeline(
        registry=registry,
        version_manager=version_manager,
        traffic_router=traffic_router
    )
    
    # Sample batch data
    batch_data = [
        {"feature1": 0.5, "feature2": 1.2, "feature3": 0.8},
        {"feature1": 0.7, "feature2": 0.9, "feature3": 1.1},
        {"feature1": 0.3, "feature2": 1.5, "feature3": 0.6},
    ]
    
    try:
        # Run batch prediction
        predictions = pipeline.predict_batch(
            data=batch_data,
            model_name="lead_scoring",
            model_version="1.0.0"  # Optional - uses latest if not specified
        )
        
        logger.info(f"Batch predictions: {predictions}")
        
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}")


def performance_tracking_example():
    """Example of tracking performance metrics."""
    tracker = PerformanceTracker()
    
    # Track some inference metrics
    inference_metrics = {
        "model_id": "example-model-001",
        "model_version": "1.0.0",
        "latency_ms": 45.2,
        "confidence": 0.89,
        "input_size": 3,
        "user_id": "user123",
        "request_id": "req-456"
    }
    
    try:
        tracker.track_inference(inference_metrics)
        logger.info("Inference metrics tracked successfully")
        
    except Exception as e:
        logger.error(f"Failed to track metrics: {e}")


def experiment_example():
    """Example of using ExperimentManager."""
    try:
        # Method 1: Initialize with experiment name
        exp_manager = ExperimentManager(
            experiment_name="lead_scoring_improvements"
        )
        
        # Method 2: Initialize with registry (backward compatibility)
        registry = ModelRegistry()
        exp_manager2 = ExperimentManager(registry)
        
        # Create an improvement experiment
        experiment_id = exp_manager.create_improvement_experiment(
            baseline_model_id="example-model-001",
            contributed_data={
                "features": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
                "metadata": {
                    "dataset_hash": "abc123",
                    "contributor_id": "contributor-001"
                }
            }
        )
        
        logger.info(f"Created experiment: {experiment_id}")
        
    except MLflowConnectionError as e:
        logger.warning(f"MLflow not available: {e}")
        logger.info("Continuing in mock mode")
        os.environ["HOKUSAI_MOCK_MODE"] = "true"
        # Retry in mock mode
        exp_manager = ExperimentManager("lead_scoring_improvements")


def main():
    """Run all examples."""
    logger.info("Starting Hokusai SDK examples...")
    
    # Setup authentication
    setup_authentication()
    
    # Run examples
    logger.info("\n=== Model Registration Example ===")
    register_model_example()
    
    logger.info("\n=== Version Management Example ===")
    version_management_example()
    
    logger.info("\n=== Batch Prediction Example ===")
    batch_prediction_example()
    
    logger.info("\n=== Performance Tracking Example ===")
    performance_tracking_example()
    
    logger.info("\n=== Experiment Manager Example ===")
    experiment_example()
    
    logger.info("\nAll examples completed!")


if __name__ == "__main__":
    main()