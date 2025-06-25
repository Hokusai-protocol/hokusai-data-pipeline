# Basic Usage Example

This example demonstrates the core features of the hokusai-ml-platform package.

## What This Example Does

1. **Model Training**: Trains two versions of a Random Forest classifier
2. **Model Registration**: Registers both models in the Model Registry
3. **Performance Tracking**: Tracks the performance improvement between versions
4. **A/B Testing**: Sets up an A/B test to gradually roll out the new model
5. **Traffic Routing**: Simulates traffic routing between model versions
6. **Model Lineage**: Displays the complete model history

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Example

```bash
python example.py
```

## Expected Output

```
Training baseline model...
Baseline accuracy: 0.8750

Training improved model...
Improved accuracy: 0.8850
Performance delta: {'accuracy': 0.01}

Setting up A/B test...

Simulating traffic routing:
Traffic distribution: {'model_a': 82, 'model_b': 18}

Model lineage:
  Version: 1.0.0, Metrics: {'accuracy': 0.875}
  Version: 2.0.0, Metrics: {'accuracy': 0.885}
```

## Key Concepts Demonstrated

- **Model Registry**: Central storage for all model versions
- **Version Management**: Semantic versioning for models
- **Experiment Tracking**: Automatic tracking of experiments
- **Performance Tracking**: Quantifying model improvements
- **A/B Testing**: Gradual rollout of new models
- **Traffic Routing**: Intelligent request routing

## Next Steps

- Modify the traffic split to test different rollout strategies
- Add more metrics beyond accuracy
- Try different model types
- Integrate with your own ML pipeline