"""Example of integrating standardized metric logging with the Hokusai pipeline."""
import time
from datetime import datetime
import mlflow

from src.utils.metrics import (
    log_model_metrics,
    log_pipeline_metrics,
    log_usage_metrics,
    MetricLogger,
    STANDARD_METRICS
)


def simulate_pipeline_step(step_name: str):
    """Simulate a pipeline step with proper metric logging."""
    print(f"\n{step_name}")
    print("-" * 50)
    
    start_time = time.time()
    
    # Simulate some work
    time.sleep(0.1)
    
    # Log pipeline execution metrics
    log_pipeline_metrics({
        "duration_seconds": time.time() - start_time,
        "memory_usage_mb": 256.5,
        "success_rate": 1.0
    })
    
    print(f"✓ Logged pipeline metrics for {step_name}")


def train_model_with_metrics():
    """Simulate model training with standardized metric logging."""
    simulate_pipeline_step("Model Training")
    
    # Simulate training
    training_metrics = {
        "accuracy": 0.8934,
        "precision": 0.8821,
        "recall": 0.9012,
        "f1_score": 0.8915,
        "auroc": 0.9234
    }
    
    # Log model performance metrics
    log_model_metrics(training_metrics)
    
    # Log additional model-specific metrics
    logger = MetricLogger()
    logger.log_metric("model:latency_ms", 15.3)
    logger.log_metric("model:throughput_qps", 1000)
    
    # Log pipeline-specific training metrics
    log_pipeline_metrics({
        "training_samples": 10000,
        "feature_count": 50,
        "data_processed": 10000
    })
    
    print("✓ Logged model training metrics")
    return training_metrics


def evaluate_models_with_metrics(baseline_metrics: dict, new_metrics: dict):
    """Simulate model evaluation with proper metric logging."""
    simulate_pipeline_step("Model Evaluation")
    
    logger = MetricLogger()
    
    # Log baseline model metrics
    for metric_name, value in baseline_metrics.items():
        logger.log_metric(f"model:baseline_{metric_name}", value)
    
    # Log new model metrics
    for metric_name, value in new_metrics.items():
        logger.log_metric(f"model:new_{metric_name}", value)
    
    # Calculate and log deltas
    for metric_name in baseline_metrics:
        if metric_name in new_metrics:
            delta = new_metrics[metric_name] - baseline_metrics[metric_name]
            logger.log_metric(f"model:delta_{metric_name}", delta)
    
    print("✓ Logged model evaluation metrics with deltas")


def track_usage_metrics():
    """Simulate tracking usage metrics."""
    simulate_pipeline_step("Usage Tracking")
    
    # Simulate usage data collection
    usage_data = {
        "reply_rate": 0.1523,
        "conversion_rate": 0.0821,
        "engagement_rate": 0.2134,
        "click_through_rate": 0.0456,
        "retention_rate": 0.7823
    }
    
    # Log usage metrics
    log_usage_metrics(usage_data)
    
    print("✓ Logged usage metrics")


def compute_delta_with_metrics():
    """Simulate delta computation with standardized metrics."""
    simulate_pipeline_step("Delta Computation")
    
    logger = MetricLogger()
    
    # Log custom delta metrics
    logger.log_metrics({
        "custom:delta_one_score": 0.0234,
        "custom:metrics_compared": 5,
        "custom:improved_metrics": 4,
        "custom:degraded_metrics": 1,
        "custom:confidence_score": 0.95
    })
    
    # Log metadata about the comparison
    logger.log_metric_with_metadata(
        name="custom:delta_one_score",
        value=0.0234,
        metadata={
            "baseline_model": "v1.0.0",
            "new_model": "v2.0.0",
            "comparison_date": datetime.now().isoformat(),
            "contributor": "0xABC123..."
        }
    )
    
    print("✓ Logged delta computation metrics with metadata")


def aggregate_metrics_example():
    """Show how to aggregate metrics across multiple runs."""
    print("\nMetric Aggregation")
    print("-" * 50)
    
    logger = MetricLogger()
    
    # Simulate metrics from multiple runs
    run_metrics = [
        {"model:accuracy": 0.89, "model:f1_score": 0.87, "pipeline:duration_seconds": 120},
        {"model:accuracy": 0.91, "model:f1_score": 0.89, "pipeline:duration_seconds": 115},
        {"model:accuracy": 0.90, "model:f1_score": 0.88, "pipeline:duration_seconds": 118}
    ]
    
    # Aggregate metrics
    aggregated = logger.aggregate_metrics(run_metrics)
    
    print("Aggregated metrics across 3 runs:")
    for metric_name, stats in aggregated.items():
        print(f"  {metric_name}:")
        print(f"    - Mean: {stats['mean']:.4f}")
        print(f"    - Min: {stats['min']:.4f}")
        print(f"    - Max: {stats['max']:.4f}")


def migration_example():
    """Show how to migrate from old metric names to new convention."""
    print("\nMetric Name Migration")
    print("-" * 50)
    
    from src.utils.metrics import migrate_metric_name
    
    # Old metric names from the pipeline
    old_metrics = {
        "accuracy": 0.89,
        "f1_score": 0.87,
        "training_time_seconds": 120.5,
        "evaluation_time_seconds": 45.2,
        "delta_accuracy": 0.03
    }
    
    # Migrate to new naming convention
    logger = MetricLogger()
    for old_name, value in old_metrics.items():
        new_name = migrate_metric_name(old_name)
        
        # If name didn't change, add appropriate prefix
        if new_name == old_name:
            if "time" in old_name or "seconds" in old_name:
                new_name = f"pipeline:{old_name}"
            elif "delta" in old_name:
                new_name = f"custom:{old_name}"
            else:
                new_name = f"model:{old_name}"
        
        logger.log_metric(new_name, value, raise_on_error=False)
        print(f"  Migrated: {old_name} → {new_name}")


def main():
    """Run pipeline simulation with standardized metrics."""
    print("Hokusai Pipeline with Standardized Metric Logging")
    print("=" * 60)
    
    # Set up MLflow
    mlflow.set_tracking_uri("./mlruns")
    mlflow.set_experiment("pipeline_metrics_example")
    
    with mlflow.start_run():
        # Simulate pipeline execution
        baseline_metrics = {
            "accuracy": 0.85,
            "precision": 0.83,
            "recall": 0.87,
            "f1_score": 0.85,
            "auroc": 0.89
        }
        
        # Train new model
        new_metrics = train_model_with_metrics()
        
        # Evaluate models
        evaluate_models_with_metrics(baseline_metrics, new_metrics)
        
        # Track usage
        track_usage_metrics()
        
        # Compute delta
        compute_delta_with_metrics()
        
        # Show aggregation
        aggregate_metrics_example()
        
        # Show migration
        migration_example()
        
        # Final pipeline metrics
        log_pipeline_metrics({
            "success_rate": 1.0,
            "error_rate": 0.0
        })
    
    print("\n" + "=" * 60)
    print("Pipeline simulation completed!")
    print("\nAll metrics logged with proper categorization:")
    print("- model: performance metrics")
    print("- pipeline: execution metrics")
    print("- usage: user interaction metrics")
    print("- custom: delta and special metrics")


if __name__ == "__main__":
    main()