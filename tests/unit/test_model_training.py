"""Unit tests for model_training module."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from src.modules.model_training import ModelTrainer


class TestModelTrainer:
    """Test cases for ModelTrainer class."""

    def test_init_default(self):
        """Test ModelTrainer initialization with default values."""
        trainer = ModelTrainer()
        assert trainer.random_seed == 42

    def test_init_with_custom_seed(self):
        """Test ModelTrainer initialization with custom random seed."""
        custom_seed = 123
        trainer = ModelTrainer(random_seed=custom_seed)
        assert trainer.random_seed == custom_seed

    @patch('mlflow.set_tracking_uri')
    @patch('mlflow.set_experiment')
    def test_init_with_mlflow_config(self, mock_set_experiment,
                                     mock_set_tracking_uri):
        """Test ModelTrainer initialization with MLflow configuration."""
        tracking_uri = "http://localhost:5000"
        experiment_name = "test_experiment"

        ModelTrainer(
            mlflow_tracking_uri=tracking_uri,
            experiment_name=experiment_name
        )

        mock_set_tracking_uri.assert_called_once_with(tracking_uri)
        mock_set_experiment.assert_called_once_with(experiment_name)
    
    def test_prepare_training_data_default_features(self):
        """Test prepare_training_data with default feature selection."""
        trainer = ModelTrainer()

        # Create sample dataframe
        df = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50],
            'target': [0, 1, 0, 1, 0]
        })

        X_train, X_test, y_train, y_test = trainer.prepare_training_data(
            df, target_column='target', test_size=0.4
        )

        # Check shapes
        assert len(X_train) == 3  # 60% of 5 samples
        assert len(X_test) == 2   # 40% of 5 samples
        assert len(y_train) == 3
        assert len(y_test) == 2

        # Check feature columns
        expected_features = ['feature1', 'feature2']
        assert list(X_train.columns) == expected_features
        assert list(X_test.columns) == expected_features
    
    def test_prepare_training_data_custom_features(self):
        """Test prepare_training_data with custom feature selection."""
        trainer = ModelTrainer()

        df = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50],
            'feature3': [100, 200, 300, 400, 500],
            'target': [0, 1, 0, 1, 0]
        })

        feature_columns = ['feature1', 'feature3']
        X_train, X_test, y_train, y_test = trainer.prepare_training_data(
            df,
            target_column='target',
            feature_columns=feature_columns,
            test_size=0.4
        )

        assert list(X_train.columns) == feature_columns
        assert list(X_test.columns) == feature_columns
    
    def test_train_mock_model(self):
        """Test training a mock model."""
        trainer = ModelTrainer(random_seed=42)
        
        X_train = pd.DataFrame({
            'feature1': [1, 2, 3],
            'feature2': [10, 20, 30]
        })
        y_train = pd.Series([0, 1, 0])
        
        model = trainer.train_mock_model(X_train, y_train, "test_classifier")
        
        # Check model structure
        assert model["type"] == "mock_test_classifier"
        assert model["version"] == "2.0.0"
        assert model["algorithm"] == "test_classifier"
        assert model["training_samples"] == 3
        assert model["feature_count"] == 2
        
        # Check metrics are in reasonable range
        metrics = model["metrics"]
        assert 0.8 <= metrics["accuracy"] <= 0.95
        assert 0.8 <= metrics["precision"] <= 0.95
        assert 0.8 <= metrics["recall"] <= 0.95
        assert 0.8 <= metrics["f1_score"] <= 0.95
        assert 0.8 <= metrics["auroc"] <= 0.95
        
        # Check parameters
        assert model["parameters"]["random_seed"] == 42
        
        # Check feature importance
        assert len(model["feature_importance"]) == 2
        assert "feature1" in model["feature_importance"]
        assert "feature2" in model["feature_importance"]
    
    def test_train_sklearn_model_with_random_state(self):
        """Test training a sklearn model that supports random_state."""
        trainer = ModelTrainer(random_seed=42)
        
        X_train = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50]
        })
        y_train = pd.Series([0, 1, 0, 1, 0])
        
        model = trainer.train_sklearn_model(
            X_train, y_train, 
            RandomForestClassifier,
            {"n_estimators": 10}
        )
        
        assert isinstance(model, RandomForestClassifier)
        assert model.random_state == 42
        assert model.n_estimators == 10
    
    def test_train_sklearn_model_without_random_state(self):
        """Test training a sklearn model that doesn't support random_state."""
        trainer = ModelTrainer(random_seed=42)
        
        X_train = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50]
        })
        y_train = pd.Series([0, 1, 0, 1, 0])
        
        # Use a model class that doesn't have random_state
        class MockModel:
            def __init__(self, param1=None):
                self.param1 = param1
            
            def fit(self, X, y):
                pass
        
        model = trainer.train_sklearn_model(
            X_train, y_train,
            MockModel,
            {"param1": "test_value"}
        )
        
        assert isinstance(model, MockModel)
        assert model.param1 == "test_value"
    
    @patch('mlflow.start_run')
    @patch('mlflow.log_param')
    @patch('mlflow.log_metric')
    @patch('mlflow.sklearn.log_model')
    def test_log_model_to_mlflow_sklearn(self, mock_log_model, mock_log_metric,
                                         mock_log_param, mock_start_run):
        """Test logging sklearn model to MLflow."""
        # Setup mocks
        mock_run = Mock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)

        trainer = ModelTrainer()

        # Create a real sklearn model
        model = RandomForestClassifier(n_estimators=10)
        X_dummy = pd.DataFrame({'feature': [1, 2, 3]})
        y_dummy = pd.Series([0, 1, 0])
        model.fit(X_dummy, y_dummy)

        metrics = {"accuracy": 0.85, "f1_score": 0.80}
        params = {"n_estimators": 10, "random_state": 42}

        run_id = trainer.log_model_to_mlflow(
            model, "test_model", metrics, params
        )

        assert run_id == "test_run_id"

        # Check that parameters were logged
        for key, value in params.items():
            mock_log_param.assert_any_call(key, value)

        # Check that metrics were logged
        for key, value in metrics.items():
            mock_log_metric.assert_any_call(key, value)

        # Check that model was logged
        mock_log_model.assert_called_once_with(model, "test_model")
    
    @patch('mlflow.start_run')
    @patch('mlflow.log_param')
    @patch('mlflow.log_metric')
    @patch('mlflow.log_artifact')
    @patch('tempfile.NamedTemporaryFile')
    def test_log_model_to_mlflow_mock(self, mock_temp_file, mock_log_artifact,
                                      mock_log_metric, mock_log_param,
                                      mock_start_run):
        """Test logging mock model to MLflow."""
        # Setup mocks
        mock_run = Mock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)

        mock_file = Mock()
        mock_file.name = "/tmp/test_model.json"
        mock_temp_file.return_value.__enter__ = Mock(return_value=mock_file)
        mock_temp_file.return_value.__exit__ = Mock(return_value=None)

        trainer = ModelTrainer()

        # Create a mock model
        mock_model = {
            "type": "mock_classifier",
            "version": "2.0.0",
            "metrics": {"accuracy": 0.85}
        }

        metrics = {"accuracy": 0.85}
        params = {"random_seed": 42}

        run_id = trainer.log_model_to_mlflow(
            mock_model, "test_model", metrics, params
        )

        assert run_id == "test_run_id"
        mock_log_artifact.assert_called_once_with(
            "/tmp/test_model.json", artifact_path="model")
    
    def test_create_training_report_sklearn(self):
        """Test creating training report for sklearn model."""
        trainer = ModelTrainer()
        
        # Create sklearn model
        model = RandomForestClassifier()
        X_train = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50]
        })
        y_train = pd.Series([0, 1, 0, 1, 0])
        training_time = 45.5
        
        report = trainer.create_training_report(
            model, X_train, y_train, training_time
        )
        
        assert report["model_type"] == "RandomForestClassifier"
        assert report["training_samples"] == 5
        assert report["feature_count"] == 2
        assert report["training_time_seconds"] == 45.5
        assert report["feature_names"] == ["feature1", "feature2"]
        assert "timestamp" in report
    
    def test_create_training_report_mock(self):
        """Test creating training report for mock model."""
        trainer = ModelTrainer()
        
        # Create mock model
        mock_model = {
            "type": "mock_classifier",
            "version": "2.0.0"
        }
        
        X_train = pd.DataFrame({
            'feature1': [1, 2, 3],
            'feature2': [10, 20, 30]
        })
        y_train = pd.Series([0, 1, 0])
        training_time = 30.0
        
        report = trainer.create_training_report(
            mock_model, X_train, y_train, training_time
        )
        
        assert report["model_type"] == "mock_classifier"
        assert report["training_samples"] == 3
        assert report["feature_count"] == 2
        assert report["training_time_seconds"] == 30.0
    
    def test_reproducibility_with_random_seed(self):
        """Test that results are reproducible with the same random seed."""
        trainer1 = ModelTrainer(random_seed=42)
        trainer2 = ModelTrainer(random_seed=42)
        
        X_train = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50]
        })
        y_train = pd.Series([0, 1, 0, 1, 0])
        
        model1 = trainer1.train_mock_model(X_train, y_train)
        model2 = trainer2.train_mock_model(X_train, y_train)
        
        # The metrics should be similar (within some tolerance due to random generation)
        # but the random seed should be the same
        assert model1["parameters"]["random_seed"] == model2["parameters"]["random_seed"]


class TestModelTrainerIntegration:
    """Integration tests for ModelTrainer with real data flow."""
    
    def test_full_training_workflow_mock(self):
        """Test complete training workflow with mock model."""
        trainer = ModelTrainer(random_seed=42)
        
        # Create sample dataset
        df = pd.DataFrame({
            'feature1': np.random.rand(100),
            'feature2': np.random.rand(100),
            'feature3': np.random.rand(100),
            'target': np.random.randint(0, 2, 100)
        })
        
        # Prepare data
        X_train, X_test, y_train, y_test = trainer.prepare_training_data(
            df, target_column='target', test_size=0.3
        )
        
        # Train model
        model = trainer.train_mock_model(X_train, y_train, "integration_test")
        
        # Create training report
        training_report = trainer.create_training_report(
            model, X_train, y_train, training_time=25.0
        )
        
        # Verify the workflow completed successfully
        assert model["type"] == "mock_integration_test"
        assert model["training_samples"] == len(X_train)
        assert training_report["model_type"] == "mock_integration_test"
        assert training_report["training_samples"] == len(X_train)
    
    @patch('mlflow.start_run')
    @patch('mlflow.log_param')
    @patch('mlflow.log_metric')
    @patch('mlflow.sklearn.log_model')
    def test_full_training_workflow_sklearn(self, mock_log_model, mock_log_metric,
                                          mock_log_param, mock_start_run):
        """Test complete training workflow with sklearn model."""
        # Setup MLflow mocks
        mock_run = Mock()
        mock_run.info.run_id = "integration_test_run"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)
        
        trainer = ModelTrainer(random_seed=42)
        
        # Create sample dataset
        df = pd.DataFrame({
            'feature1': np.random.rand(50),
            'feature2': np.random.rand(50),
            'target': np.random.randint(0, 2, 50)
        })
        
        # Prepare data
        X_train, X_test, y_train, y_test = trainer.prepare_training_data(
            df, target_column='target', test_size=0.3
        )
        
        # Train sklearn model
        model = trainer.train_sklearn_model(
            X_train, y_train,
            LogisticRegression,
            {"max_iter": 100}
        )
        
        # Calculate some dummy metrics for testing
        from sklearn.metrics import accuracy_score
        y_pred = model.predict(X_test)
        metrics = {"accuracy": accuracy_score(y_test, y_pred)}
        params = {"max_iter": 100, "random_state": 42}
        
        # Log to MLflow
        run_id = trainer.log_model_to_mlflow(
            model, "integration_test_model", metrics, params
        )
        
        # Create training report
        training_report = trainer.create_training_report(
            model, X_train, y_train, training_time=15.0
        )
        
        # Verify workflow
        assert isinstance(model, LogisticRegression)
        assert run_id == "integration_test_run"
        assert training_report["model_type"] == "LogisticRegression"


@pytest.fixture
def sample_dataframe():
    """Fixture providing a sample dataframe for testing."""
    np.random.seed(42)
    return pd.DataFrame({
        'feature1': np.random.rand(20),
        'feature2': np.random.rand(20),
        'feature3': np.random.rand(20),
        'target': np.random.randint(0, 2, 20)
    })


@pytest.fixture
def model_trainer():
    """Fixture providing a ModelTrainer instance."""
    return ModelTrainer(random_seed=42)
