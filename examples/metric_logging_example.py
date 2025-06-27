"""Example usage of the standardized metric logging convention."""
import mlflow
from src.utils.metrics import (
    MetricLogger,
    log_usage_metrics,
    log_model_metrics,
    log_pipeline_metrics,
    STANDARD_METRICS,
    MetricCategory
)


def basic_metric_logging():
    """Demonstrate basic metric logging."""
    print("Basic Metric Logging")
    print("-" * 50)
    
    # Create logger instance
    logger = MetricLogger()
    
    # Log individual metrics
    logger.log_metric("usage:reply_rate", 0.1523)
    logger.log_metric("model:accuracy", 0.8934)
    logger.log_metric("pipeline:duration_seconds", 45.2)
    
    print("✓ Logged individual metrics with proper prefixes")
    
    # Log batch of metrics
    metrics = {
        "usage:conversion_rate": 0.0821,
        "usage:engagement_rate": 0.2134,
        "model:f1_score": 0.8756,
        "model:latency_ms": 23.5
    }
    logger.log_metrics(metrics)
    
    print("✓ Logged batch of metrics")


def convenience_functions():
    """Demonstrate convenience functions for metric categories."""
    print("\nConvenience Functions")
    print("-" * 50)
    
    # Log usage metrics (automatically prefixed)
    usage_metrics = {
        "reply_rate": 0.1523,
        "conversion_rate": 0.0821,
        "engagement_rate": 0.2134
    }
    log_usage_metrics(usage_metrics)
    print("✓ Logged usage metrics with automatic prefixing")
    
    # Log model metrics
    model_metrics = {
        "accuracy": 0.8934,
        "precision": 0.8821,
        "recall": 0.9012,
        "f1_score": 0.8915
    }
    log_model_metrics(model_metrics)
    print("✓ Logged model metrics with automatic prefixing")
    
    # Log pipeline metrics
    pipeline_metrics = {
        "data_processed": 10000,
        "success_rate": 0.98,
        "duration_seconds": 120.5,
        "memory_usage_mb": 512.3
    }
    log_pipeline_metrics(pipeline_metrics)
    print("✓ Logged pipeline metrics with automatic prefixing")


def metadata_logging():
    """Demonstrate logging metrics with metadata."""
    print("\nMetric Logging with Metadata")
    print("-" * 50)
    
    logger = MetricLogger()
    
    # Log metric with additional context
    logger.log_metric_with_metadata(
        name="usage:reply_rate",
        value=0.1523,
        metadata={
            "model_version": "2.0.1",
            "experiment": "baseline_comparison",
            "dataset": "customer_interactions_v3",
            "environment": "production"
        }
    )
    
    print("✓ Logged metric with metadata (stored as MLflow parameters)")


def validation_examples():
    """Demonstrate metric validation."""
    print("\nMetric Validation")
    print("-" * 50)
    
    logger = MetricLogger()
    
    # Valid metric names
    valid_names = [
        "usage:reply_rate",
        "model:accuracy",
        "custom:special_metric",
        "simple_metric"
    ]
    
    print("Valid metric names:")
    for name in valid_names:
        try:
            logger.log_metric(name, 0.5, raise_on_error=True)
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
    
    # Invalid metric names
    invalid_names = [
        "metric with spaces",
        "UPPERCASE_METRIC",
        "metric-with-dashes",
        "123_starts_with_number"
    ]
    
    print("\nInvalid metric names:")
    for name in invalid_names:
        try:
            logger.log_metric(name, 0.5, raise_on_error=True)
            print(f"  ✗ {name} (should have failed)")
        except Exception as e:
            print(f"  ✓ {name}: Correctly rejected - {e}")


def legacy_support():
    """Demonstrate backward compatibility with legacy metrics."""
    print("\nLegacy Metric Support")
    print("-" * 50)
    
    # Create logger that allows legacy names
    logger = MetricLogger(allow_legacy_names=True)
    
    # These would normally be invalid but are allowed in legacy mode
    legacy_metrics = {
        "my-old-metric": 0.75,
        "AnotherOldMetric": 0.82,
        "metric with spaces": 0.91
    }
    
    for name, value in legacy_metrics.items():
        logger.log_metric(name, value, raise_on_error=False)
        print(f"✓ Logged legacy metric: {name}")


def show_standard_metrics():
    """Display all standard metrics."""
    print("\nStandard Metrics Reference")
    print("-" * 50)
    
    # Group metrics by category
    categories = {}
    for metric_name, description in STANDARD_METRICS.items():
        category, _ = metric_name.split(':', 1) if ':' in metric_name else ('custom', metric_name)
        if category not in categories:
            categories[category] = []
        categories[category].append((metric_name, description))
    
    # Display by category
    for category in sorted(categories.keys()):
        print(f"\n{category.upper()} Metrics:")
        for metric_name, description in sorted(categories[category]):
            print(f"  • {metric_name}: {description}")


def pipeline_integration_example():
    """Show how to integrate with a pipeline."""
    print("\nPipeline Integration Example")
    print("-" * 50)
    
    # Simulate a pipeline run
    with mlflow.start_run():
        # Pipeline start
        pipeline_start_time = 0
        
        # Log pipeline metrics throughout execution
        log_pipeline_metrics({
            "data_processed": 5000,
            "memory_usage_mb": 256
        })
        
        # Simulate model training
        log_model_metrics({
            "accuracy": 0.89,
            "f1_score": 0.87,
            "latency_ms": 15.2
        })
        
        # Log usage metrics
        log_usage_metrics({
            "reply_rate": 0.152,
            "conversion_rate": 0.082
        })
        
        # Final pipeline metrics
        log_pipeline_metrics({
            "duration_seconds": 120.5,
            "success_rate": 1.0
        })
        
        print("✓ Logged all pipeline metrics with proper categorization")


def main():
    """Run all examples."""
    print("Hokusai Metric Logging Convention Examples")
    print("=" * 60)
    
    # Set up MLflow tracking (use local directory for example)
    mlflow.set_tracking_uri("./mlruns")
    mlflow.set_experiment("metric_logging_examples")
    
    # Run examples
    basic_metric_logging()
    convenience_functions()
    metadata_logging()
    validation_examples()
    legacy_support()
    show_standard_metrics()
    pipeline_integration_example()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("\nTo view metrics in MLflow UI, run:")
    print("  mlflow ui")
    print("\nThen open http://localhost:5000 in your browser")


if __name__ == "__main__":
    main()