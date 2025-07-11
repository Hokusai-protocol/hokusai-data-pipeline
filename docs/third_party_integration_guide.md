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
- Hokusai API endpoint: `http://registry.hokus.ai/api`

## Approach 1: Using Python SDK (Recommended)

The Hokusai Python SDK provides a simple, high-level interface for all operations.

### Quick Example

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager, PerformanceTracker
from sklearn.ensemble import RandomForestClassifier
import pandas as pd

# Initialize Hokusai
registry = ModelRegistry("http://registry.hokus.ai/mlflow")
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
registry = ModelRegistry("http://registry.hokus.ai/mlflow")
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
        self.api_base = "http://registry.hokus.ai/api"
    
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
import requests
import mlflow

# Configure MLflow
mlflow.set_tracking_uri("http://registry.hokus.ai/mlflow")

# Train model with MLflow tracking
with mlflow.start_run() as run:
    # Train your model
    model = train_model(data)
    mlflow.sklearn.log_model(model, "model")
    mlflow.log_metric("accuracy", 0.89)
    
    # Register via API
    response = requests.post(
        "http://registry.hokus.ai/api/models/register",
        headers=headers,
        json={
            "model_name": "my_classifier",
            "mlflow_run_id": run.info.run_id,
            "model_uri": f"runs:/{run.info.run_id}/model",
            "metrics": {"accuracy": 0.89}
        }
    )
    print(f"Model registered: {response.json()}")
```

### Detailed API Usage

#### Step 1: Configure MLflow Connection

```python
import mlflow
import mlflow.sklearn  # or mlflow.pytorch, mlflow.tensorflow, etc.

# Set MLflow tracking URI to Hokusai's MLflow server
mlflow.set_tracking_uri("http://registry.hokus.ai/mlflow")

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
def register_model_with_hokusai(auth: HokusaiAuth, training_result: dict):
    """Register the trained model with Hokusai API."""
    
    # Prepare registration data
    registration_data = {
        "model_name": "third_party_classifier",
        "model_type": "classification",
        "mlflow_run_id": training_result["run_id"],
        "model_uri": training_result["model_uri"],
        "metrics": training_result["metrics"],
        "metadata": {
            "framework": "scikit-learn",
            "algorithm": "RandomForest",
            "description": "Customer churn prediction model",
            "training_data_size": 10000,
            "features": ["feature1", "feature2", "feature3"]
        },
        "contributor_address": auth.account.address,
        "baseline_model_id": None  # Set if this improves an existing model
    }
    
    # Register model
    response = auth.make_request("POST", "/models/register", json=registration_data)
    return response
```

## Step 5: Track Contributor Impact (if applicable)

```python
def track_contributor_impact(auth: HokusaiAuth, improved_model_id: str, baseline_model_id: str):
    """Track the impact of contributed data on model performance."""
    
    # Compare models
    comparison_data = {
        "model1": baseline_model_id,
        "model2": improved_model_id
    }
    
    comparison = auth.make_request("GET", "/models/compare", params=comparison_data)
    
    # Get contributor impact
    contributor_impact = auth.make_request(
        "GET", 
        f"/contributors/{auth.account.address}/impact"
    )
    
    return {
        "comparison": comparison,
        "impact": contributor_impact
    }
```

## Step 6: Generate Attestation

```python
def generate_attestation(auth: HokusaiAuth, model_id: str, baseline_id: str = None):
    """Generate attestation for model improvement."""
    
    attestation_data = {
        "model_id": model_id,
        "baseline_model_id": baseline_id,
        "attestation_type": "performance_improvement",
        "metadata": {
            "timestamp": datetime.utcnow().isoformat(),
            "contributor": auth.account.address
        }
    }
    
    # This endpoint would generate a ZK-proof ready attestation
    attestation = auth.make_request(
        "POST", 
        f"/models/{model_id}/attestation", 
        json=attestation_data
    )
    
    return attestation
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
registry = ModelRegistry("http://registry.hokus.ai/mlflow")
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
    # Initialize authentication
    private_key = "0x..."  # Your Ethereum private key
    auth = HokusaiAuth(private_key)
    
    # Step 1: Train baseline model (first time)
    print("Training baseline model...")
    baseline_result = train_model("baseline_data.csv")
    
    # Step 2: Register baseline model
    print("Registering baseline model...")
    baseline_registration = register_model_with_hokusai(auth, baseline_result)
    baseline_model_id = baseline_registration["model_id"]
    
    # Step 3: Train improved model with contributed data
    print("Training improved model with contributed data...")
    improved_result = train_model(
        "contributed_data.csv", 
        contributor_address=auth.account.address
    )
    
    # Step 4: Register improved model
    print("Registering improved model...")
    improved_registration = register_model_with_hokusai(auth, improved_result)
    improved_model_id = improved_registration["model_id"]
    
    # Step 5: Track contributor impact
    print("Tracking contributor impact...")
    impact = track_contributor_impact(auth, improved_model_id, baseline_model_id)
    
    # Step 6: Generate attestation
    print("Generating attestation...")
    attestation = generate_attestation(auth, improved_model_id, baseline_model_id)
    
    print(f"Model registered successfully!")
    print(f"Baseline Model ID: {baseline_model_id}")
    print(f"Improved Model ID: {improved_model_id}")
    print(f"Performance Delta: {impact['comparison']['performance_delta']}")
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
registry = ModelRegistry("http://registry.hokus.ai/mlflow")
```

### API Endpoints
- `POST /api/models/register` - Register models
- `GET /api/models/{name}/{version}` - Get model details
- `GET /api/contributors/{address}/impact` - Track contributor impact

### Rate Limits
- SDK: Handles rate limiting automatically
- API: 100 requests/minute

## Getting Help

- **Documentation**: https://docs.hokus.ai
- **SDK Examples**: See `examples/` in the repository
- **API Reference**: http://registry.hokus.ai/api/docs
- **Support**: Join our Discord at https://discord.gg/hokusai