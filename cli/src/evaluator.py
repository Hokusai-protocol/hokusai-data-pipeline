"""
Model evaluation module for the Hokusai Data Evaluation Pipeline
"""
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.model_selection import StratifiedShuffleSplit


@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    
    def to_dict(self) -> Dict[str, float]:
        """Convert metrics to dictionary"""
        return {
            'accuracy': self.accuracy,
            'precision': self.precision,
            'recall': self.recall,
            'f1_score': self.f1_score
        }
    
    @classmethod
    def from_predictions(cls, y_true: np.ndarray, y_pred: np.ndarray) -> 'EvaluationMetrics':
        """Calculate metrics from prediction arrays"""
        accuracy = accuracy_score(y_true, y_pred)
        precision = precision_score(y_true, y_pred, average='weighted', zero_division=0)
        recall = recall_score(y_true, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_true, y_pred, average='weighted', zero_division=0)
        
        return cls(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1
        )


class Evaluator:
    """Model evaluator with support for sampling and batching"""
    
    def __init__(self):
        pass
    
    def evaluate(
        self,
        model,
        dataset,
        sample_size: Optional[int] = None,
        batch_size: int = 32,
        log_to_mlflow: bool = False
    ) -> EvaluationMetrics:
        """Evaluate model on dataset
        
        Args:
            model: Model to evaluate (must have predict method)
            dataset: Dataset to evaluate on (must have get_features/get_labels methods)
            sample_size: Optional size for stratified sampling
            batch_size: Batch size for evaluation
            log_to_mlflow: Whether to log metrics to MLflow
            
        Returns:
            EvaluationMetrics object with computed metrics
        """
        # Get features and labels
        features = dataset.get_features()
        labels = dataset.get_labels()
        
        # Apply stratified sampling if requested
        if sample_size and len(features) > sample_size:
            features, labels = self._stratified_sample(features, labels, sample_size)
        
        # Run inference in batches
        predictions = self._batch_predict(model, features, batch_size)
        
        # Calculate metrics
        metrics = EvaluationMetrics.from_predictions(labels, predictions)
        
        # Log to MLflow if requested
        if log_to_mlflow:
            self._log_to_mlflow(metrics)
        
        return metrics
    
    def _stratified_sample(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sample_size: int
    ) -> tuple:
        """Apply stratified sampling to reduce dataset size"""
        if len(features) <= sample_size:
            return features, labels
        
        # Use stratified sampling to maintain class distribution
        splitter = StratifiedShuffleSplit(
            n_splits=1,
            train_size=sample_size,
            random_state=42
        )
        
        sample_idx, _ = next(splitter.split(features, labels))
        return features[sample_idx], labels[sample_idx]
    
    def _batch_predict(
        self,
        model,
        features: np.ndarray,
        batch_size: int
    ) -> np.ndarray:
        """Run model predictions in batches"""
        predictions = []
        
        for i in range(0, len(features), batch_size):
            batch_features = features[i:i + batch_size]
            batch_predictions = model.predict(batch_features)
            predictions.extend(batch_predictions)
        
        return np.array(predictions)
    
    def _log_to_mlflow(self, metrics: EvaluationMetrics):
        """Log metrics to MLflow"""
        try:
            import mlflow
            mlflow.log_metrics(metrics.to_dict())
        except ImportError:
            # MLflow not available, skip logging
            pass