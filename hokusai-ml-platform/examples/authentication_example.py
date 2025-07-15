"""Example of using Hokusai SDK with authentication."""

import os
from hokusai import setup, ModelRegistry, HokusaiAuth
from hokusai.auth import ProfileManager


def example_env_variable():
    """Example: Using environment variable for authentication."""
    # Set API key via environment variable
    os.environ["HOKUSAI_API_KEY"] = "hk_live_your_api_key_here"
    
    # Initialize components - auth handled automatically
    registry = ModelRegistry()
    
    # Use the registry normally
    models = registry.list_models_by_type("lead_scoring")
    print(f"Found {len(models)} lead scoring models")


def example_direct_initialization():
    """Example: Direct API key initialization."""
    # Initialize with explicit API key
    registry = ModelRegistry(api_key="hk_live_your_api_key_here")
    
    # Use the registry
    latest = registry.get_latest_model("lead_scoring")
    if latest:
        print(f"Latest model: {latest.model_id}")


def example_global_config():
    """Example: Global configuration setup."""
    # Configure globally once
    setup(
        api_key="hk_live_your_api_key_here",
        api_endpoint="https://api.hokus.ai"
    )
    
    # All components will use this configuration
    registry = ModelRegistry()  # Uses global config
    
    # Register a model via API
    entry = registry.register_baseline_via_api(
        model_type="email_classifier",
        mlflow_run_id="abc123def456",
        metadata={"author": "data_team", "framework": "sklearn"}
    )
    print(f"Registered model: {entry.model_id}")


def example_auth_object():
    """Example: Using auth object for fine-grained control."""
    # Create auth object
    auth = HokusaiAuth(
        api_key="hk_live_your_api_key_here",
        api_endpoint="https://api.hokus.ai"
    )
    
    # Pass to components
    registry = ModelRegistry(auth=auth)
    
    # Use the registry
    lineage = registry.get_model_lineage("model_123")
    print(f"Model has {len(lineage.entries)} versions in lineage")


def example_config_file():
    """Example: Using configuration file."""
    # Config file at ~/.hokusai/config:
    # [default]
    # api_key = hk_live_your_api_key_here
    # api_endpoint = https://api.hokus.ai
    
    # SDK will automatically load from config file
    registry = ModelRegistry()
    
    # Register tokenized model
    result = registry.register_tokenized_model(
        model_uri="runs:/abc123/model",
        model_name="sentiment-analyzer",
        token_id="sent-v1",
        benchmark_metric="accuracy",
        baseline_value=0.85
    )
    print(f"Registered tokenized model version {result['version']}")


def example_profile_management():
    """Example: Managing multiple profiles."""
    profiles = ProfileManager()
    
    # Add profiles
    profiles.add_profile(
        "dev",
        api_key="hk_test_dev_key_123",
        api_endpoint="http://localhost:8000"
    )
    
    profiles.add_profile(
        "prod",
        api_key="hk_live_prod_key_123",
        api_endpoint="https://api.hokus.ai"
    )
    
    # Use dev profile
    profiles.set_active("dev")
    registry = ModelRegistry()  # Uses dev profile
    
    # Switch to prod
    profiles.set_active("prod")
    registry = ModelRegistry()  # Now uses prod profile


def example_error_handling():
    """Example: Handling authentication errors."""
    from hokusai.auth.exceptions import AuthenticationError, RateLimitError
    
    try:
        registry = ModelRegistry(api_key="invalid_key")
        models = registry.list_models_by_type("test")
        
    except AuthenticationError as e:
        print(f"Authentication failed: {e}")
        # Handle invalid API key
        
    except RateLimitError as e:
        print(f"Rate limit exceeded. Retry after {e.retry_after} seconds")
        # Handle rate limiting
        
    except Exception as e:
        print(f"Unexpected error: {e}")


def example_notebook_usage():
    """Example: Common pattern for Jupyter notebooks."""
    # One-time setup at beginning of notebook
    from hokusai import setup
    setup(api_key="hk_live_notebook_key_123")
    
    # Then use normally throughout notebook
    from hokusai.core import ModelRegistry
    from hokusai.tracking import ExperimentManager
    
    registry = ModelRegistry()
    manager = ExperimentManager(registry)  # This now works thanks to the API fix
    
    # Start experiment
    with manager.start_experiment("notebook_experiment"):
        # Your ML code here
        pass


if __name__ == "__main__":
    print("Hokusai SDK Authentication Examples")
    print("===================================")
    print()
    print("See individual functions for different authentication patterns:")
    print("- example_env_variable(): Use environment variables")
    print("- example_direct_initialization(): Pass API key directly")
    print("- example_global_config(): Configure globally with setup()")
    print("- example_auth_object(): Use auth objects")
    print("- example_config_file(): Load from config file")
    print("- example_profile_management(): Manage multiple profiles")
    print("- example_error_handling(): Handle auth errors")
    print("- example_notebook_usage(): Jupyter notebook pattern")