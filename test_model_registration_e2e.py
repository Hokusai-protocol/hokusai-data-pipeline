#!/usr/bin/env python3
"""End-to-end test for model registration using Hokusai API key.
Tests the complete flow as a third-party user would experience it.
"""

import os

import mlflow
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

# Configuration
HOKUSAI_API_KEY = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
MLFLOW_TRACKING_URI = "https://registry.hokus.ai"

# Set up MLflow with Hokusai authentication
os.environ["MLFLOW_TRACKING_TOKEN"] = HOKUSAI_API_KEY
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def test_model_registration():
    """Test registering a model with Hokusai using API key authentication."""
    print("=" * 60)
    print("Hokusai Model Registration E2E Test")
    print("=" * 60)
    print(f"\nMLflow Tracking URI: {MLFLOW_TRACKING_URI}")
    print(f"API Key: {HOKUSAI_API_KEY[:10]}...")

    # Step 1: Create a simple model
    print("\n[1/5] Creating test model...")
    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = LogisticRegression(max_iter=200, random_state=42)
    model.fit(X_train, y_train)
    accuracy = model.score(X_test, y_test)
    print(f"   ✓ Model trained with accuracy: {accuracy:.2%}")

    # Step 2: Create/Get experiment
    print("\n[2/5] Setting up MLflow experiment...")
    experiment_name = "hokusai-e2e-test"
    try:
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            experiment_id = mlflow.create_experiment(experiment_name)
            print(f"   ✓ Created new experiment: {experiment_name} (ID: {experiment_id})")
        else:
            experiment_id = experiment.experiment_id
            print(f"   ✓ Using existing experiment: {experiment_name} (ID: {experiment_id})")
    except Exception as e:
        print(f"   ✗ Failed to set up experiment: {e}")
        return False

    # Step 3: Log model to MLflow
    print("\n[3/5] Logging model to MLflow...")
    try:
        with mlflow.start_run(experiment_id=experiment_id) as run:
            mlflow.log_param("max_iter", 200)
            mlflow.log_param("random_state", 42)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.sklearn.log_model(model, "model")
            run_id = run.info.run_id
            print(f"   ✓ Model logged to run: {run_id}")
    except Exception as e:
        print(f"   ✗ Failed to log model: {e}")
        return False

    # Step 4: Register model
    print("\n[4/5] Registering model...")
    model_name = "hokusai-test-iris-classifier"
    try:
        model_uri = f"runs:/{run_id}/model"
        registered_model = mlflow.register_model(model_uri, model_name)
        print(f"   ✓ Model registered: {model_name}")
        print(f"     Version: {registered_model.version}")
    except Exception as e:
        print(f"   ✗ Failed to register model: {e}")
        return False

    # Step 5: Verify model in registry
    print("\n[5/5] Verifying model in registry...")
    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient()

        # Get registered model
        registered_model_details = client.get_registered_model(model_name)
        print("   ✓ Model found in registry")
        print(f"     Name: {registered_model_details.name}")
        print(f"     Creation time: {registered_model_details.creation_timestamp}")
        print(f"     Latest versions: {len(registered_model_details.latest_versions)}")

        # Get specific version
        model_version = client.get_model_version(model_name, registered_model.version)
        print("   ✓ Model version details:")
        print(f"     Version: {model_version.version}")
        print(f"     Stage: {model_version.current_stage}")
        print(f"     Run ID: {model_version.run_id}")

    except Exception as e:
        print(f"   ✗ Failed to verify model: {e}")
        return False

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED - Model registration successful!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = test_model_registration()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
