---
id: quickstart
title: Quickstart Guide
sidebar_label: Quickstart
sidebar_position: 2
---

# Quickstart Guide

Get up and running with Hokusai ML Platform in 5 minutes!

## Prerequisites

- Python 3.8+ installed
- Hokusai ML Platform installed ([Installation Guide](./installation.md))
- Basic understanding of ML concepts

## 1. Initialize Your First Project

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager

# Initialize Hokusai
registry = ModelRegistry("https://registry.hokus.ai/mlflow")
manager = ExperimentManager(registry)

print("✅ Hokusai ML Platform initialized!")
```

## 2. Register a Baseline Model

Let's register a simple model as our baseline:

```python
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import mlflow.sklearn

# Generate sample data
X, y = make_classification(n_samples=1000, n_features=20, n_informative=15, random_state=42)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train a baseline model
with mlflow.start_run(run_name="baseline_model") as run:
    # Train model
    model = RandomForestClassifier(n_estimators=50, random_state=42)
    model.fit(X_train, y_train)
    
    # Calculate metrics
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    # Log metrics and model
    mlflow.log_metric("accuracy", accuracy)
    mlflow.sklearn.log_model(model, "model")
    
    # Register as baseline with Hokusai
    model_uri = f"runs:/{run.info.run_id}/model"
    registered_model = registry.register_tokenized_model(
        model_uri=model_uri,
        name="quickstart-classifier",
        token_id="quickstart-token",
        benchmark_metric="accuracy",
        benchmark_value=str(accuracy)
    )
    
    print(f"✅ Baseline model registered with accuracy: {accuracy:.4f}")
```

## 3. Contribute Data and Improve the Model

Now let's simulate a data contribution that improves the model:

```python
# Simulate contributed data (in practice, this would come from contributors)
X_contrib, y_contrib = make_classification(
    n_samples=500, 
    n_features=20, 
    n_informative=18,  # More informative features
    random_state=123
)

# Combine with original training data
import numpy as np
X_combined = np.vstack([X_train, X_contrib])
y_combined = np.hstack([y_train, y_contrib])

# Train improved model
with mlflow.start_run(run_name="improved_model") as run:
    # Train on combined data
    improved_model = RandomForestClassifier(n_estimators=100, random_state=42)
    improved_model.fit(X_combined, y_combined)
    
    # Calculate new metrics
    y_pred_improved = improved_model.predict(X_test)
    accuracy_improved = accuracy_score(y_test, y_pred_improved)
    
    # Log everything
    mlflow.log_metric("accuracy", accuracy_improved)
    mlflow.log_param("data_contribution", "500_samples")
    mlflow.sklearn.log_model(improved_model, "model")
    
    print(f"✅ Improved model accuracy: {accuracy_improved:.4f}")
    print(f"📈 Improvement: {(accuracy_improved - accuracy) * 100:.2f} percentage points")
```

## 4. Detect DeltaOne Achievement

Check if the improvement qualifies for rewards:

```python
from hokusai.evaluation.deltaone_evaluator import detect_delta_one

# Check for DeltaOne achievement
delta_one_achieved = detect_delta_one("quickstart-classifier")

if delta_one_achieved:
    print("🎉 DeltaOne achieved! Model improved by ≥1 percentage point")
    print("💰 Contributor eligible for token rewards!")
else:
    print("📊 Model improved but didn't reach DeltaOne threshold")
```

## 5. Set Up A/B Testing

Test your improved model against the baseline:

```python
from hokusai.services.ab_testing import ModelTrafficRouter, ABTestConfig, RoutingStrategy

# Initialize traffic router
router = ModelTrafficRouter()

# Create A/B test
ab_config = ABTestConfig(
    model_a="quickstart-classifier/1",  # Baseline
    model_b="quickstart-classifier/2",  # Improved
    traffic_split={"model_a": 0.8, "model_b": 0.2},
    routing_strategy=RoutingStrategy.RANDOM
)

test_id = router.create_ab_test(ab_config)
print(f"✅ A/B test created with ID: {test_id}")

# Simulate routing decisions
for i in range(10):
    user_id = f"user_{i}"
    selected_model = router.route_request(user_id)
    print(f"User {user_id} → {selected_model}")
```

## 6. Use DSPy for Prompt Optimization

If working with language models:

```python
from hokusai.services.dspy_pipeline_executor import DSPyPipelineExecutor
from hokusai.dspy_signatures import EmailDraft

# Initialize DSPy executor
executor = DSPyPipelineExecutor()

# Use a pre-built signature
result = executor.execute_signature(
    signature_name="EmailDraft",
    inputs={
        "recipient": "John Doe",
        "subject": "Welcome to Hokusai",
        "key_points": "Platform introduction, Next steps, Support channels"
    }
)

print("📧 Generated email draft:")
print(result["email_body"])
```

## Complete Example Script

Here's everything together in one script:

```python
# quickstart.py
import mlflow
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import numpy as np

from hokusai.core import ModelRegistry
from hokusai.utils.mlflow_config import MLFlowConfig
from hokusai.evaluation.deltaone_evaluator import detect_delta_one

def main():
    # 1. Setup
    print("🚀 Starting Hokusai ML Platform Quickstart")
    config = MLFlowConfig()
    config.setup_tracking()
    registry = ModelRegistry()
    
    # 2. Generate data
    X, y = make_classification(n_samples=1000, n_features=20, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. Train baseline
    print("\n📊 Training baseline model...")
    with mlflow.start_run(run_name="baseline"):
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X_train, y_train)
        
        accuracy = accuracy_score(y_test, model.predict(X_test))
        mlflow.log_metric("accuracy", accuracy)
        mlflow.sklearn.log_model(model, "model")
        
        registry.register_tokenized_model(
            model_uri=f"runs:/{mlflow.active_run().info.run_id}/model",
            name="quickstart-model",
            token_id="QUICK-001",
            benchmark_metric="accuracy",
            benchmark_value=str(accuracy)
        )
        print(f"✅ Baseline accuracy: {accuracy:.4f}")
    
    # 4. Improve with contributed data
    print("\n🔄 Training improved model with contributed data...")
    X_contrib, y_contrib = make_classification(n_samples=500, n_features=20, n_informative=18, random_state=123)
    X_combined = np.vstack([X_train, X_contrib])
    y_combined = np.hstack([y_train, y_contrib])
    
    with mlflow.start_run(run_name="improved"):
        improved_model = RandomForestClassifier(n_estimators=100, random_state=42)
        improved_model.fit(X_combined, y_combined)
        
        accuracy_improved = accuracy_score(y_test, improved_model.predict(X_test))
        mlflow.log_metric("accuracy", accuracy_improved)
        mlflow.sklearn.log_model(improved_model, "model")
        
        improvement = (accuracy_improved - accuracy) * 100
        print(f"✅ Improved accuracy: {accuracy_improved:.4f}")
        print(f"📈 Improvement: {improvement:.2f} percentage points")
    
    # 5. Check DeltaOne
    print("\n🎯 Checking for DeltaOne achievement...")
    if detect_delta_one("quickstart-model"):
        print("🎉 DeltaOne achieved! Contributors eligible for rewards!")
    else:
        print("📊 Model improved but didn't reach DeltaOne threshold")
    
    print("\n✨ Quickstart complete! Explore more in the tutorials.")

if __name__ == "__main__":
    main()
```

## What's Next?

Congratulations! You've just:
- ✅ Registered a baseline model with token metadata
- ✅ Improved the model with contributed data
- ✅ Detected DeltaOne achievement
- ✅ Set up A/B testing
- ✅ Used DSPy for prompt optimization

### Next Steps

1. **Deep Dive Tutorials**
   - [Building Your First Hokusai Model](../tutorials/building-first-model.md)
   - [Contributing Data for Rewards](../tutorials/contributing-data.md)
   - [Advanced A/B Testing](../tutorials/ab-testing.md)

2. **Explore Core Features**
   - [Model Registry Guide](../core-features/model-registry.md)
   - [DeltaOne Detection](../core-features/deltaone-detection.md)
   - [DSPy Integration](../core-features/dspy-integration.md)

3. **Production Deployment**
   - [Configuration Guide](./configuration.md)
   - [API Reference](../api-reference/index.md)
   - [Best Practices](../guides/best-practices.md)

## Need Help?

- 📚 Check our [FAQ](../guides/faq.md)
- 💬 Join our [Discord Community](https://discord.gg/hokusai)
- 🐛 Report issues on [GitHub](https://github.com/hokusai-protocol/hokusai-data-pipeline/issues)