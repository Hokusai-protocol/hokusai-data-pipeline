# Getting Started with Hokusai ML Platform

This guide will help you get started with Hokusai in just a few minutes. We'll focus on the simplest path to train, register, and evaluate your models.

## Installation

Install the Hokusai ML Platform package:

```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

That's it! You're ready to use Hokusai.

## Quick Start: Train and Register a Model

Here's a complete example to get you started:

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# 1. Initialize Hokusai
registry = ModelRegistry("http://registry.hokus.ai/mlflow")
experiment_manager = ExperimentManager(registry)

# 2. Load your data
data = pd.read_csv("your_data.csv")
X = data.drop("target", axis=1)
y = data["target"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# 3. Train your model
with experiment_manager.start_experiment("my_first_model"):
    # Train model
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train, y_train)
    
    # Evaluate
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    # Register model
    model_info = registry.register_baseline(
        model=model,
        model_type="classification",
        metadata={
            "accuracy": accuracy,
            "dataset": "my_dataset_v1"
        }
    )
    
    print(f"Model registered! ID: {model_info['model_id']}")
    print(f"Accuracy: {accuracy:.3f}")
```

## Common Tasks

### 1. Register a Model with Token Association

If you have a token created on the Hokusai platform:

```python
# Register model with token
result = registry.register_tokenized_model(
    model_uri=f"runs:/{run_id}/model",
    model_name="MY-TOKEN-MODEL",
    token_id="my-token",
    metric_name="accuracy",
    baseline_value=0.85
)
```

### 2. Track Model Improvements

When you have new data to improve your model:

```python
from hokusai.tracking import PerformanceTracker

performance_tracker = PerformanceTracker()

# Train improved model with new data
improved_model = RandomForestClassifier(n_estimators=200)
improved_model.fit(X_train_new, y_train_new)

# Track the improvement
delta, attestation = performance_tracker.track_improvement(
    baseline_metrics={"accuracy": 0.85},
    improved_metrics={"accuracy": 0.92},
    data_contribution={
        "contributor": "your_address",
        "data_size": len(X_train_new)
    }
)

print(f"Improvement: {delta['accuracy']['absolute_delta']:.3f}")
```

### 3. Run Inference

```python
from hokusai.core.inference import HokusaiInferencePipeline, InferenceRequest

# Initialize inference pipeline
inference_pipeline = HokusaiInferencePipeline(registry=registry)

# Make predictions
request = InferenceRequest(
    model_type="classification",
    data={"features": [0.5, 0.3, 0.8, 0.2]}
)

response = await inference_pipeline.predict(request)
print(f"Prediction: {response.prediction}")
```

## Working with DSPy Models

Hokusai supports DSPy (Declarative Self-Prompting) models:

```python
from hokusai.core.dspy import DSPyModelWrapper
import dspy

# Load a DSPy signature
class EmailAssistant(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought("context -> email")
    
    def forward(self, context):
        return self.generate(context=context)

# Wrap and register the DSPy model
dspy_model = DSPyModelWrapper(EmailAssistant())
registry.register_baseline(
    model=dspy_model,
    model_type="dspy_email_assistant",
    metadata={"version": "1.0"}
)
```

## Local Development Setup

For local development and testing:

```bash
# 1. Clone the repository
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline

# 2. Start local services (MLflow, Redis, etc.)
docker compose -f docker-compose.minimal.yml up -d

# 3. Set environment variable
export MLFLOW_TRACKING_URI=http://localhost:5001

# 4. Now use the local registry
registry = ModelRegistry("http://localhost:5001")
```

## Next Steps

- **Need to integrate with existing code?** See our [Integration Guide](./integration_guide.md)
- **Want to use the REST API instead?** Check the [API Documentation](./api_documentation.md)
- **Setting up production infrastructure?** Read the [Deployment Guide](./deployment_guide.md)

## Getting Help

- **Documentation**: https://docs.hokus.ai
- **Examples**: See the `examples/` directory in the repository
- **Support**: Join our Discord at https://discord.gg/hokusai

Remember: Start simple, then add complexity as needed. The basic workflow above will cover most use cases!