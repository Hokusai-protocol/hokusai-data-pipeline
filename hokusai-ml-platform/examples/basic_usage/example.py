"""Basic usage example for hokusai-ml-platform."""

# Import Hokusai ML Platform components
from hokusai.core import ModelRegistry, ModelVersionManager
from hokusai.core.ab_testing import ABTestConfig, ModelTrafficRouter
from hokusai.tracking import ExperimentManager, PerformanceTracker
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split


def main() -> None:
    # Initialize components
    registry = ModelRegistry()
    version_manager = ModelVersionManager(registry)
    experiment_manager = ExperimentManager(registry)  # This now works thanks to the API fix
    performance_tracker = PerformanceTracker()
    traffic_router = ModelTrafficRouter()

    # Generate sample data
    X, y = make_classification(n_samples=1000, n_features=20, n_informative=15, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Train baseline model
    print("Training baseline model...")
    with experiment_manager.start_experiment("lead_scoring_baseline"):
        baseline_model = RandomForestClassifier(n_estimators=50, random_state=42)
        baseline_model.fit(X_train, y_train)

        # Evaluate baseline
        baseline_pred = baseline_model.predict(X_test)
        baseline_accuracy = accuracy_score(y_test, baseline_pred)
        print(f"Baseline accuracy: {baseline_accuracy:.4f}")

        # Register baseline model
        baseline_version = version_manager.register_version(
            baseline_model,
            "lead_scoring",
            "1.0.0",
            metrics={"accuracy": baseline_accuracy}
        )

    # Train improved model with more trees
    print("\nTraining improved model...")
    with experiment_manager.start_experiment("lead_scoring_improved"):
        improved_model = RandomForestClassifier(n_estimators=100, random_state=42)
        improved_model.fit(X_train, y_train)

        # Evaluate improved model
        improved_pred = improved_model.predict(X_test)
        improved_accuracy = accuracy_score(y_test, improved_pred)
        print(f"Improved accuracy: {improved_accuracy:.4f}")

        # Track improvement
        delta, attestation = performance_tracker.track_improvement(
            baseline_metrics={"accuracy": baseline_accuracy},
            improved_metrics={"accuracy": improved_accuracy},
            data_contribution={"records": len(X_train), "features": X_train.shape[1]}
        )
        print(f"Performance delta: {delta}")

        # Register improved model
        improved_version = version_manager.register_version(
            improved_model,
            "lead_scoring",
            "2.0.0",
            metrics={"accuracy": improved_accuracy}
        )

    # Set up A/B test
    print("\nSetting up A/B test...")
    ab_config = ABTestConfig(
        model_a="lead_scoring/1.0.0",
        model_b="lead_scoring/2.0.0",
        traffic_split={"model_a": 0.8, "model_b": 0.2}
    )
    traffic_router.create_ab_test(ab_config)

    # Simulate inference with traffic routing
    print("\nSimulating traffic routing:")
    model_counts = {"model_a": 0, "model_b": 0}

    for i in range(100):
        selected_model = traffic_router.route_request("lead_scoring")
        model_counts[selected_model] += 1

    print(f"Traffic distribution: {model_counts}")

    # Get model lineage
    print("\nModel lineage:")
    lineage = registry.get_model_lineage("lead_scoring")
    for version_info in lineage:
        print(f"  Version: {version_info['version']}, Metrics: {version_info['metrics']}")


if __name__ == "__main__":
    main()
