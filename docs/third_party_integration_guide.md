# Third Party Integration Guide: Training and Registering Models with Hokusai API

This guide provides a step-by-step process for third party applications to train and register models using the Hokusai API.

## Prerequisites

- Python 3.8+
- MLflow client library: `pip install mlflow`
- Ethereum account (for authentication)
- Access to training data
- Hokusai API endpoint: `http://registry.hokus.ai/api`

## Step 1: Set Up Authentication

### Option A: Ethereum Signature Authentication (Recommended)

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

### Option B: API Key Authentication

```python
class HokusaiAPIKeyAuth:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_base = "http://registry.hokus.ai/api"
    
    def get_auth_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
```

## Step 2: Configure MLflow Connection

```python
import mlflow
import mlflow.sklearn  # or mlflow.pytorch, mlflow.tensorflow, etc.

# Set MLflow tracking URI to Hokusai's MLflow server
mlflow.set_tracking_uri("http://mlflow.hokus.ai/mlflow")

# Set experiment name
mlflow.set_experiment("third_party_models")
```

## Step 3: Train Your Model

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

## Step 4: Register Model with Hokusai API

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

## Complete Integration Example

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

1. **Version Control**: Always version your models with meaningful names
2. **Metadata**: Include comprehensive metadata for better tracking
3. **Metrics**: Log all relevant metrics for comparison
4. **Reproducibility**: Set random seeds and log all parameters
5. **Error Handling**: Implement proper error handling and retries
6. **Rate Limiting**: Respect API rate limits (100 requests/minute)

## API Endpoints Reference

- `POST /models/register` - Register a new model
- `GET /models` - List all models
- `GET /models/{name}/{version}` - Get specific model details
- `GET /models/compare` - Compare two models
- `POST /models/evaluate` - Evaluate model performance
- `GET /contributors/{address}/impact` - Get contributor impact metrics
- `GET /models/{name}/{version}/lineage` - Track model lineage
- `POST /models/{name}/{version}/transition` - Change model stage

## Error Handling

```python
try:
    response = auth.make_request("POST", "/models/register", json=data)
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        print("Authentication failed. Check your credentials.")
    elif e.response.status_code == 429:
        print("Rate limit exceeded. Please wait before retrying.")
    else:
        print(f"API Error: {e.response.json()}")
```

## Next Steps

1. Test with sample data
2. Integrate into your ML pipeline
3. Set up automated model registration
4. Monitor model performance over time
5. Use attestations for on-chain rewards

For support, refer to the API documentation at `/docs` endpoint or contact the Hokusai team.