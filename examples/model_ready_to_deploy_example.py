"""Example: Model Ready to Deploy Event Emission.

This example demonstrates how models that meet baseline requirements
automatically trigger model_ready_to_deploy events for token deployment.
"""

import os
import time
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Set up authentication
os.environ["HOKUSAI_API_KEY"] = os.getenv("HOKUSAI_API_KEY", "hk_live_your_key_here")
os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5000"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from src.services.enhanced_model_registry import EnhancedModelRegistry
from src.events.publishers.redis_publisher import RedisPublisher
import mlflow


def train_improved_model():
    """Train a model that beats the baseline."""
    # Generate synthetic data
    X, y = make_classification(
        n_samples=1000,
        n_features=20,
        n_informative=15,
        n_redundant=5,
        random_state=42
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Train model
    model = RandomForestClassifier(
        n_estimators=100,  # More trees for better performance
        max_depth=10,
        random_state=42
    )
    model.fit(X_train, y_train)
    
    # Evaluate
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    return model, accuracy


def main():
    """Demonstrate model registration with automatic event emission."""
    
    print("=" * 60)
    print("Model Ready to Deploy Event Example")
    print("=" * 60)
    
    # Initialize enhanced registry with event emission
    registry = EnhancedModelRegistry(
        tracking_uri="http://localhost:5000"
    )
    
    # Define baseline requirements
    TOKEN_ID = "msg-ai"
    METRIC_NAME = "accuracy"
    BASELINE_VALUE = 0.75  # Model must achieve >75% accuracy
    
    print(f"\nToken: {TOKEN_ID}")
    print(f"Metric: {METRIC_NAME}")
    print(f"Baseline Requirement: {BASELINE_VALUE:.2%}")
    
    # Train a model
    print("\nTraining improved model...")
    model, current_accuracy = train_improved_model()
    print(f"Model Accuracy: {current_accuracy:.2%}")
    
    # Check if model meets baseline
    if current_accuracy < BASELINE_VALUE:
        print(f"\n❌ Model does not meet baseline ({current_accuracy:.2%} < {BASELINE_VALUE:.2%})")
        print("No event will be emitted.")
        return
    
    print(f"\n✅ Model meets baseline! ({current_accuracy:.2%} >= {BASELINE_VALUE:.2%})")
    
    # Start MLflow run to log the model
    with mlflow.start_run() as run:
        # Log model and metrics
        mlflow.sklearn.log_model(model, "model")
        mlflow.log_metric(METRIC_NAME, current_accuracy)
        
        # Register model with event emission
        print("\nRegistering model with automatic event emission...")
        result = registry.register_tokenized_model_with_events(
            model_uri=f"runs:/{run.info.run_id}/model",
            model_name=f"msg-ai-model",
            token_id=TOKEN_ID,
            metric_name=METRIC_NAME,
            baseline_value=BASELINE_VALUE,
            current_value=current_accuracy,
            additional_tags={
                "framework": "sklearn",
                "algorithm": "random_forest"
            },
            contributor_address="0x1234567890123456789012345678901234567890",
            experiment_name="baseline-improvements"
        )
    
    # Check if event was emitted
    if result.get("event_emitted"):
        print("\n🚀 SUCCESS: model_ready_to_deploy event emitted!")
        print(f"Model ID: {result.get('model_name')}/v{result.get('version')}")
        print(f"Improvement: {((current_accuracy - BASELINE_VALUE) / BASELINE_VALUE * 100):.2f}%")
        
        # Demonstrate consuming the message
        print("\n" + "=" * 60)
        print("Consuming Messages from Queue")
        print("=" * 60)
        
        publisher = RedisPublisher()
        
        def process_deployment_message(payload):
            """Process a model_ready_to_deploy message."""
            print("\n📨 Received model_ready_to_deploy message:")
            print(f"  Model ID: {payload['model_id']}")
            print(f"  Token: {payload['token_symbol']}")
            print(f"  Metric: {payload['metric_name']}")
            print(f"  Performance: {payload['current_value']:.2%} (baseline: {payload['baseline_value']:.2%})")
            print(f"  Improvement: {payload['improvement_percentage']:.2f}%")
            print(f"  MLflow Run: {payload['mlflow_run_id']}")
            
            # Here you would trigger token deployment
            print("\n🔄 Triggering token deployment process...")
            time.sleep(1)  # Simulate deployment
            print("✅ Token deployment initiated!")
            
            return True
        
        # Check queue depth
        queue_depth = publisher.get_queue_depth("hokusai:model_ready_queue")
        print(f"\nMessages in queue: {queue_depth}")
        
        if queue_depth > 0:
            print("Processing message...")
            publisher.consume_messages(
                process_callback=process_deployment_message,
                timeout=5  # Wait up to 5 seconds
            )
        
    else:
        print(f"\n❌ Event emission failed: {result.get('event_error', 'Unknown error')}")
    
    print("\n" + "=" * 60)
    print("Example Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()