---
id: model-registration-guide
title: Complete Model Registration Guide
sidebar_label: Model Registration Guide
sidebar_position: 3
---

# Complete Model Registration Guide

This guide provides step-by-step instructions for registering your machine learning models with Hokusai. Whether you're a data scientist looking to tokenize your model or a third-party developer integrating with Hokusai, this guide covers everything you need to know.

## Overview

Hokusai provides two main approaches for model registration:

1. **Using the Hokusai ML Platform SDK** (Recommended) - Full integration with model versioning, A/B testing, and performance tracking
2. **Direct MLflow API** - Lightweight approach for basic model registration

## Prerequisites

Before you begin, ensure you have:

1. **Python 3.8 or higher** installed on your system
2. **A trained machine learning model** or the ability to train one
3. **Performance metrics** for your model (accuracy, F1 score, etc.)
4. **Hokusai API credentials** (obtain from https://hokus.ai/settings/api)

## Step 1: Install the Hokusai ML Platform

### Option A: Install from GitHub (Recommended)

```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

### Option B: Install for Development

```bash
# Clone the repository
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline/hokusai-ml-platform

# Install in editable mode
pip install -e .
```

## Step 2: Set Up Your Environment

### Configure API Credentials

Set your Hokusai API key as an environment variable:

```bash
export HOKUSAI_API_KEY="your-api-key-here"
```

You can obtain your API key from:
1. Log in to https://hokus.ai
2. Navigate to Settings → API Keys
3. Click "Generate New Key"
4. Copy the key and store it securely

### Verify Installation

Test that everything is set up correctly:

```python
from hokusai.core import ModelRegistry
import os

# Verify API key is set
if not os.getenv("HOKUSAI_API_KEY"):
    raise ValueError("Please set HOKUSAI_API_KEY environment variable")

# This should not raise any errors
registry = ModelRegistry()
print("✅ Hokusai ML Platform installed successfully!")
```

## Step 3: Train and Register Your Model

### Option A: Complete Example with Hokusai ML Platform SDK

This approach provides full integration with Hokusai's features including version management, A/B testing, and performance tracking:

```python
#!/usr/bin/env python3
"""
Complete example: Train and register a model with Hokusai ML Platform
"""

import os
import mlflow
from hokusai.core import ModelRegistry, ModelVersionManager
from hokusai.tracking import ExperimentManager, PerformanceTracker
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score
import joblib

def main():
    # 1. Initialize Hokusai components
    print("🚀 Initializing Hokusai ML Platform...")
    registry = ModelRegistry()
    version_manager = ModelVersionManager(registry)
    experiment_manager = ExperimentManager(registry)
    performance_tracker = PerformanceTracker()
    
    # 2. Prepare your data
    print("\n📊 Preparing data...")
    X, y = make_classification(
        n_samples=1000, 
        n_features=20, 
        n_informative=15, 
        n_classes=2,
        random_state=42
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # 3. Train your model within an experiment
    print("\n🔬 Training model...")
    with experiment_manager.start_experiment("customer_churn_prediction"):
        # Train model
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Calculate metrics
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        
        print(f"  Accuracy: {accuracy:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        
        # Save model locally
        model_path = "churn_predictor.pkl"
        joblib.dump(model, model_path)
        
        # 4. Register with Hokusai
        print("\n📝 Registering model with Hokusai...")
        
        # Configure MLflow
        mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
        os.environ["MLFLOW_TRACKING_TOKEN"] = os.getenv("HOKUSAI_API_KEY")
        
        # Log to MLflow
        with mlflow.start_run() as run:
            # Log model
            mlflow.sklearn.log_model(
                model, 
                "model",
                registered_model_name="customer-churn-predictor"
            )
            
            # Log metrics
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("f1_score", f1)
            mlflow.log_metric("training_samples", len(X_train))
            
            # Log parameters
            mlflow.log_param("model_type", "RandomForest")
            mlflow.log_param("n_estimators", 100)
            mlflow.log_param("feature_count", X.shape[1])
            
            # Register with token metadata
            model_uri = f"runs:/{run.info.run_id}/model"
            registered_model = registry.register_tokenized_model(
                model_uri=model_uri,
                name="customer-churn-predictor",
                token_id="CHURN-001",
                benchmark_metric="accuracy",
                benchmark_value=str(accuracy),
                tags={
                    "author": "data-science-team",
                    "use_case": "customer_retention",
                    "industry": "telecom",
                    "framework": "scikit-learn",
                    "data_version": "v2.1"
                }
            )
            
            # Register version for version management
            model_version = version_manager.register_version(
                model,
                "customer_churn",
                "1.0.0",
                metrics={"accuracy": accuracy, "f1_score": f1}
            )
            
            print(f"\n✅ Model registered successfully!")
            print(f"   Name: {registered_model.name}")
            print(f"   Version: {registered_model.version}")
            print(f"   Token ID: CHURN-001")
            print(f"   MLflow Run ID: {run.info.run_id}")

if __name__ == "__main__":
    main()
```

### Option B: Simple Registration with Direct MLflow

For a simpler approach using MLflow directly:

```python
import os
import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Set up MLflow
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
os.environ["MLFLOW_TRACKING_TOKEN"] = os.getenv("HOKUSAI_API_KEY")

# Train your model
X, y = make_classification(n_samples=1000, n_features=20, random_state=42)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Calculate metrics
accuracy = accuracy_score(y_test, model.predict(X_test))

# Register with MLflow
with mlflow.start_run() as run:
    # Log model with Hokusai metadata
    mlflow.sklearn.log_model(
        model, 
        "model",
        registered_model_name="my-classifier"
    )
    
    # Required Hokusai tags
    mlflow.set_tag("hokusai_token_id", "CLASS-001")
    mlflow.set_tag("benchmark_metric", "accuracy")
    mlflow.set_tag("benchmark_value", str(accuracy))
    
    # Log metrics
    mlflow.log_metric("accuracy", accuracy)
    
    print(f"✅ Model registered with run ID: {run.info.run_id}")
```

## Step 4: Register Model Improvements

When you improve your model, register the new version to track progress:

```python
# Assuming you have an improved model with better performance
improved_accuracy = 0.95  # 3% improvement!

with experiment_manager.start_experiment("customer_churn_improved"):
    # Train improved model (e.g., with more data or better features)
    improved_model = train_improved_model()  # Your training code
    
    # Track the improvement
    delta, attestation = performance_tracker.track_improvement(
        baseline_metrics={"accuracy": 0.92},
        improved_metrics={"accuracy": improved_accuracy},
        data_contribution={
            "contributor": "0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1",
            "additional_samples": 5000,
            "improvement_method": "active_learning"
        }
    )
    
    # Register new version
    with mlflow.start_run() as run:
        mlflow.sklearn.log_model(improved_model, "model")
        mlflow.log_metric("accuracy", improved_accuracy)
        
        model_uri = f"runs:/{run.info.run_id}/model"
        improved_version = registry.register_tokenized_model(
            model_uri=model_uri,
            name="customer-churn-predictor",
            token_id="CHURN-001",
            benchmark_metric="accuracy",
            benchmark_value=str(improved_accuracy),
            tags={
                "previous_version": "1",
                "improvement": "3_percent",
                "deltaone_achieved": "true" if delta["accuracy"] >= 0.01 else "false"
            }
        )
    
    print(f"✅ Improved model registered as version {improved_version.version}")
    print(f"🎯 DeltaOne achieved: {delta['accuracy'] >= 0.01}")
```

## Step 5: Set Up A/B Testing (Optional)

Test your improved model against the baseline:

```python
from hokusai.core.ab_testing import ABTestConfig, ModelTrafficRouter

# Initialize traffic router
traffic_router = ModelTrafficRouter()

# Configure A/B test
ab_config = ABTestConfig(
    test_id="churn-v2-test",
    model_a="customer-churn-predictor/1",  # Baseline
    model_b="customer-churn-predictor/2",  # Improved
    traffic_split={"model_a": 0.9, "model_b": 0.1},  # 10% to new model
    duration_hours=24
)

# Start A/B test
traffic_router.create_ab_test(ab_config)
print("✅ A/B test configured - 10% of traffic will use the improved model")
```

## Step 6: Monitor and Retrieve Models

### Check Model Status

```python
# Get model information
model = registry.get_tokenized_model("customer-churn-predictor")
print(f"Latest version: {model.version}")
print(f"Token ID: {model.tags['hokusai_token_id']}")
print(f"Performance: {model.tags['benchmark_value']}")

# List all versions
versions = registry.list_models_by_token("CHURN-001")
for v in versions:
    print(f"Version {v.version}: {v.tags['benchmark_value']}")
```

### View Model Lineage

```python
# Get complete model history
lineage = registry.get_model_lineage("customer-churn-predictor")
for version in lineage:
    print(f"Version {version['version']}:")
    print(f"  - Metric: {version['metrics']['accuracy']}")
    print(f"  - Created: {version['created_at']}")
    print(f"  - Contributor: {version.get('contributor', 'N/A')}")
```

## Working with Different ML Frameworks

### TensorFlow/Keras

```python
import tensorflow as tf
import mlflow.tensorflow

# Train your model
model = tf.keras.Sequential([
    tf.keras.layers.Dense(128, activation='relu', input_shape=(20,)),
    tf.keras.layers.Dropout(0.2),
    tf.keras.layers.Dense(1, activation='sigmoid')
])
model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
model.fit(X_train, y_train, epochs=10, validation_split=0.2)

# Register with MLflow
with mlflow.start_run() as run:
    mlflow.tensorflow.log_model(
        model, 
        "model",
        registered_model_name="nn-classifier"
    )
    mlflow.set_tag("hokusai_token_id", "NN-001")
    mlflow.set_tag("benchmark_metric", "accuracy")
    mlflow.set_tag("benchmark_value", "0.89")
```

### PyTorch

```python
import torch
import mlflow.pytorch

# Your PyTorch model
class BinaryClassifier(torch.nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.fc1 = torch.nn.Linear(input_dim, 128)
        self.fc2 = torch.nn.Linear(128, 1)
        self.sigmoid = torch.nn.Sigmoid()
    
    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = self.sigmoid(self.fc2(x))
        return x

# Train and register
model = BinaryClassifier(20)
# ... training code ...

with mlflow.start_run() as run:
    mlflow.pytorch.log_model(
        model, 
        "model",
        registered_model_name="pytorch-classifier"
    )
    mlflow.set_tag("hokusai_token_id", "TORCH-001")
    mlflow.set_tag("benchmark_metric", "accuracy")
    mlflow.set_tag("benchmark_value", "0.91")
```

### XGBoost

```python
import xgboost as xgb
import mlflow.xgboost

# Train XGBoost model
dtrain = xgb.DMatrix(X_train, label=y_train)
params = {'objective': 'binary:logistic', 'eval_metric': 'auc'}
model = xgb.train(params, dtrain, num_boost_round=100)

# Register
with mlflow.start_run() as run:
    mlflow.xgboost.log_model(
        model, 
        "model",
        registered_model_name="xgb-classifier"
    )
    mlflow.set_tag("hokusai_token_id", "XGB-001")
    mlflow.set_tag("benchmark_metric", "auc")
    mlflow.set_tag("benchmark_value", "0.94")
```

## Best Practices

### 1. Comprehensive Metadata

Always include detailed metadata for better tracking:

```python
tags = {
    # Required Hokusai fields
    "hokusai_token_id": "MODEL-001",
    "benchmark_metric": "accuracy",
    "benchmark_value": "0.92",
    
    # Recommended metadata
    "dataset_version": "v2.1",
    "dataset_size": "50000",
    "preprocessing": "standard_scaler",
    "feature_engineering": "polynomial_features",
    "cross_validation": "5_fold",
    "hardware": "gpu_a100",
    "training_time_hours": "2.5",
    "framework_version": "sklearn_1.3.0"
}
```

### 2. Consistent Metric Names

Use standardized metric names:

```python
CLASSIFICATION_METRICS = ["accuracy", "precision", "recall", "f1_score", "auc", "auroc"]
REGRESSION_METRICS = ["mse", "rmse", "mae", "r2_score", "mape"]
NLP_METRICS = ["perplexity", "bleu_score", "rouge_score", "exact_match"]
```

### 3. Version Management

Follow semantic versioning:
- **Major version (1.0.0)**: Breaking changes or significant architecture changes
- **Minor version (1.1.0)**: New features or improvements
- **Patch version (1.1.1)**: Bug fixes or minor adjustments

### 4. Reproducibility

Ensure your models are reproducible:

```python
# Set random seeds
import random
import numpy as np

random.seed(42)
np.random.seed(42)

# For deep learning frameworks
tf.random.set_seed(42)  # TensorFlow
torch.manual_seed(42)    # PyTorch

# Log environment
mlflow.log_param("python_version", sys.version)
mlflow.log_param("numpy_version", np.__version__)
mlflow.log_param("sklearn_version", sklearn.__version__)
```

## Troubleshooting

### Common Issues

#### Authentication Error
```
Error: 401 Unauthorized
```
**Solution**: Verify your API key:
```bash
echo $HOKUSAI_API_KEY  # Should show your key
curl -H "Authorization: Bearer $HOKUSAI_API_KEY" https://registry.hokus.ai/api/health
```

#### Model Too Large
```
Error: Request entity too large
```
**Solution**: For models > 100MB, consider:
- Model compression techniques
- Uploading to cloud storage and registering the URI
- Contact support for enterprise limits

#### Invalid Token ID
```
Error: Token ID format invalid
```
**Solution**: Use uppercase letters with hyphens:
- ✅ Good: `MODEL-001`, `SENT-AI`, `IMG-DETECT`
- ❌ Bad: `model_001`, `sentai`, `img detect`

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Also for MLflow
import mlflow
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
```

## API Reference

### Core Methods

#### `register_tokenized_model()`
```python
registry.register_tokenized_model(
    model_uri: str,           # MLflow model URI
    name: str,                # Model name
    token_id: str,            # Hokusai token ID
    benchmark_metric: str,    # Metric name
    benchmark_value: str,     # Baseline value
    tags: Dict[str, str]      # Additional metadata
)
```

#### `get_tokenized_model()`
```python
model = registry.get_tokenized_model(
    name: str,                # Model name
    version: Optional[str]    # Specific version (default: latest)
)
```

#### `list_models_by_token()`
```python
models = registry.list_models_by_token(
    token_id: str            # Token ID to filter by
)
```

## Next Steps

- **Automate Registration**: Integrate model registration into your CI/CD pipeline
- **Monitor Performance**: Track model performance in production
- **Join Community**: Connect with other developers at https://discord.gg/hokusai
- **Explore Advanced Features**: Learn about DeltaOne detection and reward distribution

## Support

- **Documentation**: https://docs.hokus.ai
- **API Reference**: https://registry.hokus.ai/api/docs
- **GitHub Issues**: https://github.com/Hokusai-protocol/hokusai-data-pipeline/issues
- **Email**: support@hokus.ai