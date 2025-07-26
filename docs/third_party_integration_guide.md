# Third Party Integration Guide: Training and Registering Models with Hokusai

This guide shows how to integrate your applications with Hokusai to train and register models. We provide two approaches:

1. **Python SDK** (Recommended) - Simple, Pythonic interface
2. **REST API** - For non-Python environments or advanced integrations

## Prerequisites

### For Python SDK Approach
- Python 3.8+
- Install Hokusai ML Platform: `pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform`

### For REST API Approach
- Any programming language with HTTP client
- Ethereum account (for authentication) or API key
- MLflow client library (optional): `pip install mlflow`
- Hokusai API endpoint: `https://registry.hokus.ai/api`

## Approach 1: Using Python SDK (Recommended)

The Hokusai Python SDK provides a simple, high-level interface for all operations.

### Quick Example

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager, PerformanceTracker
from sklearn.ensemble import RandomForestClassifier
import pandas as pd

# Initialize Hokusai
registry = ModelRegistry("https://registry.hokus.ai/api/mlflow")
experiment_manager = ExperimentManager(registry)
performance_tracker = PerformanceTracker()

# Train and register model
with experiment_manager.start_experiment("my_model"):
    # Load data
    data = pd.read_csv("data.csv")
    X_train, y_train = data.drop("target", axis=1), data["target"]
    
    # Train model
    model = RandomForestClassifier()
    model.fit(X_train, y_train)
    
    # Register model
    result = registry.register_baseline(
        model=model,
        model_type="classification",
        metadata={"accuracy": 0.89}
    )
    
    print(f"Model registered: {result['model_id']}")
```

### Detailed SDK Usage

#### 1. Initialize Components

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager, PerformanceTracker

# Connect to Hokusai platform
registry = ModelRegistry("https://registry.hokus.ai/api/mlflow")
experiment_manager = ExperimentManager(registry)
performance_tracker = PerformanceTracker()
```

#### 2. Train Baseline Model

```python
# Start experiment tracking
with experiment_manager.start_experiment("customer_churn_baseline"):
    # Your existing training code
    model = train_your_model(baseline_data)
    metrics = evaluate_model(model, test_data)
    
    # Register as baseline
    baseline_info = registry.register_baseline(
        model=model,
        model_type="churn_prediction",
        metadata={
            "dataset": "customers_v1",
            "metrics": metrics
        }
    )
```

#### 3. Train Improved Model with Contributed Data

```python
# Train with new data
with experiment_manager.start_experiment("customer_churn_improved"):
    # Combine baseline and contributed data
    combined_data = pd.concat([baseline_data, contributed_data])
    
    # Train improved model
    improved_model = train_your_model(combined_data)
    improved_metrics = evaluate_model(improved_model, test_data)
    
    # Track improvement
    delta, attestation = performance_tracker.track_improvement(
        baseline_metrics=metrics,
        improved_metrics=improved_metrics,
        data_contribution={
            "contributor": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
            "data_size": len(contributed_data),
            "data_hash": hash_data(contributed_data)
        }
    )
    
    # Register improved model
    improved_info = registry.register_improved_model(
        baseline_model_id=baseline_info['model_id'],
        improved_model=improved_model,
        contributor_address="0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
        data_contribution={"samples": len(contributed_data)}
    )
```

#### 4. Register Model with Token

```python
# If you have a token on Hokusai platform
result = registry.register_tokenized_model(
    model_uri=f"runs:/{run_id}/model",
    model_name="CUSTOMER-CHURN",
    token_id="customer-churn",
    metric_name="f1_score",
    baseline_value=0.75,
    additional_tags={
        "environment": "production",
        "version": "2.0"
    }
)
```

## Approach 2: Using REST API

For non-Python environments or when you need direct API control.

### Authentication

#### Option A: Ethereum Signature Authentication

```python
from eth_account import Account
from eth_account.messages import encode_defunct
import requests
from datetime import datetime

class HokusaiAuth:
    def __init__(self, private_key: str):
        self.account = Account.from_key(private_key)
        self.api_base = "https://registry.hokus.ai/api"
    
    def get_auth_headers(self):
        """Generate authentication headers for API requests."""
        message = f"Hokusai API Access - {datetime.utcnow().isoformat()}"
        message_hash = encode_defunct(text=message)
        signed = self.account.sign_message(message_hash)
        
        return {
            "X-ETH-Address": self.account.address,
            "X-ETH-Message": message,
            "X-ETH-Signature": signed.signature.hex()
        }
    
    def make_request(self, method: str, endpoint: str, json=None):
        """Make authenticated API request."""
        headers = self.get_auth_headers()
        headers["Content-Type"] = "application/json"
        
        url = f"{self.api_base}{endpoint}"
        response = requests.request(method, url, headers=headers, json=json)
        response.raise_for_status()
        return response.json()
```

#### Option B: API Key Authentication

```python
headers = {
    "Authorization": f"Bearer {your_api_key}",
    "Content-Type": "application/json"
}
```

### Quick API Example

```python
import os
import mlflow

# Configure MLflow with authentication
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
# Set authentication headers
os.environ["MLFLOW_TRACKING_TOKEN"] = "your_api_key_here"

# Train model with MLflow tracking
with mlflow.start_run() as run:
    # Train your model
    model = train_model(data)
    
    # Log model with automatic registration
    mlflow.sklearn.log_model(
        model, 
        "model",
        registered_model_name="my_classifier"  # This automatically registers the model
    )
    mlflow.log_metric("accuracy", 0.89)
    
    print(f"Model registered with run ID: {run.info.run_id}")
```

### Detailed API Usage

#### Step 1: Configure MLflow Connection

```python
import mlflow
import mlflow.sklearn  # or mlflow.pytorch, mlflow.tensorflow, etc.

# Set MLflow tracking URI to Hokusai's MLflow server
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")

# Configure authentication
import os
os.environ["MLFLOW_TRACKING_TOKEN"] = your_api_key

# Set experiment name
mlflow.set_experiment("third_party_models")
```

#### Step 2: Train Your Model

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import pandas as pd
import numpy as np

def train_model(data_path: str, contributor_address: str = None):
    """Train a model with contributor data."""
    
    # Load your data
    data = pd.read_csv(data_path)
    X = data.drop('target', axis=1)
    y = data['target']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Start MLflow run
    with mlflow.start_run() as run:
        # Log parameters
        mlflow.log_param("model_type", "RandomForestClassifier")
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("max_depth", 10)
        mlflow.log_param("random_state", 42)
        
        # Log contributor if provided
        if contributor_address:
            mlflow.set_tag("contributor_address", contributor_address)
            mlflow.set_tag("data_source", "contributed")
        
        # Train model
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        model.fit(X_train, y_train)
        
        # Make predictions
        y_pred = model.predict(X_test)
        
        # Calculate and log metrics
        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, average='weighted'),
            "recall": recall_score(y_test, y_pred, average='weighted'),
            "f1_score": f1_score(y_test, y_pred, average='weighted')
        }
        
        for metric_name, metric_value in metrics.items():
            mlflow.log_metric(metric_name, metric_value)
        
        # Log model
        mlflow.sklearn.log_model(
            model, 
            "model",
            registered_model_name="third_party_classifier"
        )
        
        # Log additional artifacts
        mlflow.log_dict(metrics, "metrics.json")
        
        return {
            "run_id": run.info.run_id,
            "model_uri": f"runs:/{run.info.run_id}/model",
            "metrics": metrics
        }
```

#### Step 3: Register Model with Hokusai API

```python
def register_model_with_hokusai(mlflow_run_id: str, model_name: str):
    """Register the trained model with Hokusai through MLflow."""
    # Model registration happens through MLflow's model registry
    # The model is already registered if you used registered_model_name
    # in mlflow.sklearn.log_model()
    
    # Alternatively, create a model version:
    client = mlflow.tracking.MlflowClient()
    
    # Create registered model if it doesn't exist
    try:
        client.create_registered_model(model_name)
    except Exception:
        pass  # Model already exists
    
    # Create model version
    model_version = client.create_model_version(
        name=model_name,
        source=f"runs:/{mlflow_run_id}/model",
        run_id=mlflow_run_id
    )
    
    return {
        "model_name": model_name,
        "version": model_version.version,
        "run_id": mlflow_run_id
    }
```

## Step 5: Track Contributor Impact (if applicable)

```python
def track_contributor_impact(baseline_run_id: str, improved_run_id: str):
    """Track the impact of contributed data on model performance."""
    client = mlflow.tracking.MlflowClient()
    
    # Get metrics from both runs
    baseline_run = client.get_run(baseline_run_id)
    improved_run = client.get_run(improved_run_id)
    
    baseline_metrics = baseline_run.data.metrics
    improved_metrics = improved_run.data.metrics
    
    # Calculate improvement
    comparison = {}
    for metric_name in baseline_metrics:
        if metric_name in improved_metrics:
            baseline_value = baseline_metrics[metric_name]
            improved_value = improved_metrics[metric_name]
            comparison[metric_name] = {
                "baseline": baseline_value,
                "improved": improved_value,
                "delta": improved_value - baseline_value,
                "delta_percent": ((improved_value - baseline_value) / baseline_value) * 100
            }
    
    return comparison
```

## Step 6: Generate Attestation

```python
def generate_attestation(model_name: str, version: str, metrics: dict):
    """Generate attestation data for model improvement."""
    # Note: Full attestation generation would require Hokusai SDK
    # This is a simplified version showing the data structure
    
    from datetime import datetime
    import hashlib
    import json
    
    attestation_data = {
        "model_name": model_name,
        "model_version": version,
        "metrics": metrics,
        "timestamp": datetime.utcnow().isoformat(),
        "attestation_type": "performance_improvement"
    }
    
    # Generate hash for attestation
    data_string = json.dumps(attestation_data, sort_keys=True)
    attestation_hash = hashlib.sha256(data_string.encode()).hexdigest()
    
    return {
        "data": attestation_data,
        "hash": attestation_hash,
        "note": "For full ZK-proof attestation, use Hokusai SDK"
    }
```

## Choosing Between SDK and API

### Use the Python SDK when:
- You're working in Python
- You want the simplest integration
- You need automatic experiment tracking
- You prefer high-level abstractions

### Use the REST API when:
- You're working in non-Python languages
- You need fine-grained control
- You're building a custom integration
- You have existing MLflow infrastructure

## Complete Examples

### SDK Complete Example

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager, PerformanceTracker
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

# Initialize
registry = ModelRegistry("https://registry.hokus.ai/api/mlflow")
experiment_manager = ExperimentManager(registry)

# Full workflow
with experiment_manager.start_experiment("complete_example"):
    # Train baseline
    baseline_model = RandomForestClassifier()
    baseline_model.fit(X_train_base, y_train_base)
    baseline_metrics = {"accuracy": 0.85}
    
    baseline_id = registry.register_baseline(
        model=baseline_model,
        model_type="classification",
        metadata=baseline_metrics
    )['model_id']
    
    # Train improved model
    improved_model = RandomForestClassifier(n_estimators=200)
    improved_model.fit(X_train_combined, y_train_combined)
    improved_metrics = {"accuracy": 0.92}
    
    # Track and register improvement
    tracker = PerformanceTracker()
    delta, attestation = tracker.track_improvement(
        baseline_metrics=baseline_metrics,
        improved_metrics=improved_metrics,
        data_contribution={"contributor": "0x123...", "samples": 1000}
    )
    
    registry.register_improved_model(
        baseline_model_id=baseline_id,
        improved_model=improved_model,
        contributor_address="0x123...",
        data_contribution={"samples": 1000}
    )
```

### API Complete Example

```python
def main():
    # Configure MLflow authentication
    import os
    os.environ["MLFLOW_TRACKING_TOKEN"] = "your_api_key_here"
    mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
    
    # Step 1: Train baseline model (first time)
    print("Training baseline model...")
    baseline_result = train_model("baseline_data.csv")
    
    # Step 2: Register baseline model
    print("Registering baseline model...")
    baseline_registration = register_model_with_hokusai(
        baseline_result["run_id"],
        "third_party_classifier"
    )
    
    # Step 3: Train improved model with contributed data
    print("Training improved model with contributed data...")
    improved_result = train_model(
        "contributed_data.csv", 
        contributor_address="0x742d35Cc6634C0532925a3b844Bc9e7595f62341"
    )
    
    # Step 4: Register improved model
    print("Registering improved model...")
    improved_registration = register_model_with_hokusai(
        improved_result["run_id"],
        "third_party_classifier"
    )
    
    # Step 5: Track contributor impact
    print("Tracking contributor impact...")
    impact = track_contributor_impact(
        baseline_result["run_id"],
        improved_result["run_id"]
    )
    
    # Step 6: Generate attestation
    print("Generating attestation...")
    attestation = generate_attestation(
        "third_party_classifier",
        improved_registration["version"],
        improved_result["metrics"]
    )
    
    print(f"Model registered successfully!")
    print(f"Baseline Run ID: {baseline_result['run_id']}")
    print(f"Improved Run ID: {improved_result['run_id']}")
    print(f"Model Version: {improved_registration['version']}")
    print(f"Performance Impact: {impact}")
    print(f"Attestation Hash: {attestation['hash']}")

if __name__ == "__main__":
    main()
```

## Best Practices

1. **Start with SDK**: Unless you have specific requirements, use the Python SDK
2. **Version your models**: Use semantic versioning for model tracking
3. **Log all metrics**: Comprehensive metrics enable better comparisons
4. **Handle errors gracefully**: Both approaches support retries and fallbacks
5. **Test locally first**: Use Docker Compose for local development

## Quick Reference

### SDK Installation
```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

### SDK Usage
```python
from hokusai.core import ModelRegistry
registry = ModelRegistry("https://registry.hokus.ai/api/mlflow")
```

### API Endpoints
All model operations go through the MLflow API proxy:
- Base URL: `https://registry.hokus.ai/api/mlflow`
- Use standard MLflow REST API endpoints
- Authentication: Include API key in MLFLOW_TRACKING_TOKEN environment variable

### Rate Limits
- SDK: Handles rate limiting automatically
- API: 100 requests/minute

## Getting Help

- **Documentation**: https://docs.hokus.ai
- **SDK Examples**: See `examples/` in the repository
- **API Reference**: https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/help
- **Support**: Join our Discord at https://discord.gg/hokusai