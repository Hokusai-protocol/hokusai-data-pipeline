"""Example usage of the Token-Aware MLflow Model Registry"""
import mlflow
from hokusai.core.registry import ModelRegistry


def main():
    """Demonstrate token-aware model registration"""
    
    # Initialize the registry
    registry = ModelRegistry("http://localhost:5000")
    
    # Example 1: Register a new tokenized model
    print("Example 1: Registering a tokenized model")
    print("-" * 50)
    
    try:
        # In a real scenario, you would have trained a model and logged it to MLflow
        # For this example, we'll use a dummy model URI
        result = registry.register_tokenized_model(
            model_uri="runs:/abc123def456/model",
            model_name="MSG-AI",
            token_id="msg-ai",
            metric_name="reply_rate",
            baseline_value=0.1342,
            additional_tags={
                "dataset": "customer_interactions_v2",
                "environment": "production",
                "team": "messaging"
            }
        )
        
        print(f"Successfully registered model: {result['model_name']}")
        print(f"Version: {result['version']}")
        print(f"Token ID: {result['token_id']}")
        print(f"Metric: {result['metric_name']} = {result['baseline_value']}")
        print()
        
    except Exception as e:
        print(f"Registration failed: {e}")
        print()
    
    # Example 2: Retrieve a tokenized model
    print("Example 2: Retrieving a tokenized model")
    print("-" * 50)
    
    try:
        model = registry.get_tokenized_model("MSG-AI", "1")
        print(f"Retrieved model: {model['model_name']} v{model['version']}")
        print(f"Token: {model['token_id']}")
        print(f"Performance: {model['metric_name']} = {model['baseline_value']}")
        print()
        
    except Exception as e:
        print(f"Retrieval failed: {e}")
        print()
    
    # Example 3: List all models for a token
    print("Example 3: Listing models by token")
    print("-" * 50)
    
    try:
        models = registry.list_models_by_token("msg-ai")
        print(f"Found {len(models)} models for token 'msg-ai':")
        for model in models:
            print(f"  - {model['model_name']} v{model['version']}: "
                  f"{model['metric_name']} = {model['baseline_value']}")
        print()
        
    except Exception as e:
        print(f"Listing failed: {e}")
        print()
    
    # Example 4: Update model tags
    print("Example 4: Updating model tags")
    print("-" * 50)
    
    try:
        registry.update_model_tags(
            "MSG-AI", 
            "1",
            {
                "benchmark_value": "0.1456",  # Updated performance
                "last_evaluated": "2024-01-15"
            }
        )
        print("Successfully updated model tags")
        print()
        
    except Exception as e:
        print(f"Update failed: {e}")
        print()
    
    # Example 5: Integration with existing model registration
    print("Example 5: Integration with standard MLflow")
    print("-" * 50)
    
    # You can still use the existing register_baseline and register_improved_model methods
    # alongside the new tokenized model functionality
    print("The token-aware registry extends the existing functionality")
    print("You can use both approaches as needed for your use case")


def validate_token_examples():
    """Show token ID validation examples"""
    from hokusai.core.registry import ModelRegistry
    
    registry = ModelRegistry()
    
    print("\nToken ID Validation Examples")
    print("-" * 50)
    
    valid_tokens = [
        "msg-ai",
        "lead-scorer",
        "churn-predictor-v2",
        "recommendation-engine-prod"
    ]
    
    invalid_tokens = [
        "MSG AI",           # Contains space
        "token@special",    # Contains special character
        "",                 # Empty
        "a" * 65,          # Too long
        "-token",          # Starts with hyphen
        "token-"           # Ends with hyphen
    ]
    
    print("Valid token IDs:")
    for token in valid_tokens:
        try:
            registry.validate_token_id(token)
            print(f"  ✓ {token}")
        except ValueError:
            print(f"  ✗ {token}")
    
    print("\nInvalid token IDs:")
    for token in invalid_tokens:
        try:
            registry.validate_token_id(token)
            print(f"  ✗ {token} (should have failed)")
        except ValueError as e:
            print(f"  ✓ {token} - {e}")


if __name__ == "__main__":
    print("Token-Aware MLflow Model Registry Examples")
    print("=" * 50)
    print()
    
    # Run main examples
    main()
    
    # Show validation examples
    validate_token_examples()