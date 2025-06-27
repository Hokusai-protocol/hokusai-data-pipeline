"""Example of integrating token-aware registry with Metaflow pipeline"""
from metaflow import FlowSpec, step
import mlflow
from hokusai.core.registry import ModelRegistry
from hokusai.core.models import HokusaiModel


class TokenAwarePipelineFlow(FlowSpec):
    """Example pipeline using token-aware model registry"""
    
    @step
    def start(self):
        """Initialize pipeline parameters"""
        self.token_id = "msg-ai"
        self.metric_name = "reply_rate"
        self.model_name = "MSG-AI"
        self.tracking_uri = "http://localhost:5000"
        self.next(self.train_model)
    
    @step
    def train_model(self):
        """Train a model and log to MLflow"""
        import mlflow.sklearn
        from sklearn.linear_model import LogisticRegression
        from sklearn.datasets import make_classification
        
        # Set tracking URI
        mlflow.set_tracking_uri(self.tracking_uri)
        
        # Generate dummy data
        X, y = make_classification(n_samples=1000, n_features=20, random_state=42)
        
        # Train model
        with mlflow.start_run() as run:
            model = LogisticRegression()
            model.fit(X, y)
            
            # Log model
            mlflow.sklearn.log_model(model, "model")
            
            # Log metrics
            accuracy = model.score(X, y)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric(self.metric_name, 0.1342)
            
            self.run_id = run.info.run_id
            self.model_uri = f"runs:/{self.run_id}/model"
            self.baseline_value = 0.1342
        
        self.next(self.register_tokenized_model)
    
    @step
    def register_tokenized_model(self):
        """Register the model with token metadata"""
        registry = ModelRegistry(self.tracking_uri)
        
        # Register with token awareness
        result = registry.register_tokenized_model(
            model_uri=self.model_uri,
            model_name=self.model_name,
            token_id=self.token_id,
            metric_name=self.metric_name,
            baseline_value=self.baseline_value,
            additional_tags={
                "pipeline": "TokenAwarePipelineFlow",
                "experiment": "initial_baseline"
            }
        )
        
        self.registered_version = result["version"]
        print(f"Registered model {self.model_name} version {self.registered_version}")
        print(f"Token: {self.token_id}")
        print(f"Baseline {self.metric_name}: {self.baseline_value}")
        
        self.next(self.train_improved_model)
    
    @step
    def train_improved_model(self):
        """Train an improved model"""
        import mlflow.sklearn
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.datasets import make_classification
        
        mlflow.set_tracking_uri(self.tracking_uri)
        
        # Generate dummy data (same as before)
        X, y = make_classification(n_samples=1000, n_features=20, random_state=42)
        
        # Train improved model
        with mlflow.start_run() as run:
            model = RandomForestClassifier(n_estimators=100)
            model.fit(X, y)
            
            # Log model
            mlflow.sklearn.log_model(model, "model")
            
            # Log improved metrics
            accuracy = model.score(X, y)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric(self.metric_name, 0.1456)  # Improved!
            
            self.improved_run_id = run.info.run_id
            self.improved_model_uri = f"runs:/{self.improved_run_id}/model"
            self.improved_value = 0.1456
        
        self.next(self.register_improved_version)
    
    @step
    def register_improved_version(self):
        """Register the improved model version"""
        registry = ModelRegistry(self.tracking_uri)
        
        # Calculate improvement
        improvement = self.improved_value - self.baseline_value
        improvement_pct = (improvement / self.baseline_value) * 100
        
        # Register improved version
        result = registry.register_tokenized_model(
            model_uri=self.improved_model_uri,
            model_name=self.model_name,
            token_id=self.token_id,
            metric_name=self.metric_name,
            baseline_value=self.improved_value,
            additional_tags={
                "pipeline": "TokenAwarePipelineFlow",
                "experiment": "random_forest_improvement",
                "improvement": f"{improvement:.4f}",
                "improvement_pct": f"{improvement_pct:.2f}%",
                "baseline_version": self.registered_version
            }
        )
        
        self.improved_version = result["version"]
        print(f"\nRegistered improved model version {self.improved_version}")
        print(f"Improvement: {improvement:.4f} ({improvement_pct:.2f}%)")
        
        self.next(self.compare_versions)
    
    @step
    def compare_versions(self):
        """Compare model versions for the token"""
        registry = ModelRegistry(self.tracking_uri)
        
        # List all versions for this token
        models = registry.list_models_by_token(self.token_id)
        
        print(f"\nAll models for token '{self.token_id}':")
        for model in models:
            print(f"  Version {model['version']}: {model['metric_name']} = {model['baseline_value']}")
        
        # Get specific versions
        baseline = registry.get_tokenized_model(self.model_name, self.registered_version)
        improved = registry.get_tokenized_model(self.model_name, self.improved_version)
        
        print(f"\nBaseline: {baseline['baseline_value']}")
        print(f"Improved: {improved['baseline_value']}")
        print(f"Delta: {improved['baseline_value'] - baseline['baseline_value']:.4f}")
        
        self.next(self.end)
    
    @step
    def end(self):
        """Pipeline complete"""
        print("\nToken-aware pipeline complete!")
        print(f"Token '{self.token_id}' now has {self.improved_version} versions registered")


def run_existing_pipeline_integration():
    """Show how to integrate with existing pipeline steps"""
    from hokusai.core.registry import ModelRegistry
    
    print("\nIntegrating with Existing Pipeline")
    print("-" * 50)
    
    # Example of modifying the existing train_new_model step
    print("""
    # In your existing pipeline's train_new_model step:
    
    @step
    def train_new_model(self):
        # ... existing training code ...
        
        # After model is trained and logged to MLflow:
        registry = ModelRegistry()
        
        # If you have a Hokusai token associated:
        if hasattr(self, 'hokusai_token_id'):
            registry.register_tokenized_model(
                model_uri=self.model_uri,
                model_name=self.model_name,
                token_id=self.hokusai_token_id,
                metric_name=self.evaluation_metric,
                baseline_value=self.model_performance
            )
        else:
            # Fall back to existing registration
            registry.register_baseline(...)
    """)
    
    print("\nThis allows gradual migration to token-aware models")


if __name__ == "__main__":
    print("Token-Aware Pipeline Integration Example")
    print("=" * 50)
    
    # Show integration approach
    run_existing_pipeline_integration()
    
    print("\nTo run the example pipeline:")
    print("  python pipeline_integration_example.py run")
    print("\nNote: Requires MLflow tracking server running on localhost:5000")