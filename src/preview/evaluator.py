"""Evaluation module for preview pipeline."""

import warnings
from typing import Dict, Tuple, Any
import pandas as pd
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, 
    f1_score, roc_auc_score
)
import logging

logger = logging.getLogger(__name__)


class PreviewEvaluator:
    """Handles model evaluation and delta calculation for preview."""
    
    def __init__(self):
        """Initialize PreviewEvaluator."""
        pass
        
    def evaluate_model(
        self, 
        model: Any, 
        test_data: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Evaluate model performance on test data.
        
        Args:
            model: Model to evaluate
            test_data: Test dataset with features and labels
            
        Returns:
            Dictionary of evaluation metrics
        """
        # Extract features and labels
        X_test, y_true = self._prepare_test_data(test_data)
        
        # Get predictions
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)
        
        # Calculate metrics
        metrics = self.calculate_metrics(y_true, y_pred, y_proba)
        
        return metrics
        
    def calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: np.ndarray,
        multiclass: bool = False
    ) -> Dict[str, float]:
        """
        Calculate evaluation metrics.
        
        Args:
            y_true: True labels
            y_pred: Predicted labels
            y_proba: Prediction probabilities
            multiclass: Whether this is a multiclass problem
            
        Returns:
            Dictionary of metrics
            
        Raises:
            ValueError: If predictions are empty
        """
        if len(y_true) == 0:
            raise ValueError("Empty predictions")
            
        metrics = {}
        
        # Calculate basic metrics
        metrics['accuracy'] = accuracy_score(y_true, y_pred)
        
        # For binary/multiclass specific metrics
        if multiclass:
            metrics['precision'] = precision_score(y_true, y_pred, average='macro')
            metrics['recall'] = recall_score(y_true, y_pred, average='macro')
            metrics['f1'] = f1_score(y_true, y_pred, average='macro')
            # AUROC not calculated for multiclass in this simple version
        else:
            metrics['precision'] = precision_score(y_true, y_pred, average='binary')
            metrics['recall'] = recall_score(y_true, y_pred, average='binary')
            metrics['f1'] = f1_score(y_true, y_pred, average='binary')
            
            # AUROC using probability of positive class
            if y_proba.ndim > 1:
                metrics['auroc'] = roc_auc_score(y_true, y_proba[:, 1])
            else:
                metrics['auroc'] = roc_auc_score(y_true, y_proba)
                
        return metrics
        
    def calculate_delta_one_score(
        self,
        baseline_metrics: Dict[str, float],
        new_metrics: Dict[str, float]
    ) -> float:
        """
        Calculate DeltaOne score (simplified version).
        
        Args:
            baseline_metrics: Baseline model metrics
            new_metrics: New model metrics
            
        Returns:
            DeltaOne score
        """
        # Use weighted average of improvements across metrics
        weights = {
            'accuracy': 0.2,
            'precision': 0.2,
            'recall': 0.2,
            'f1': 0.2,
            'auroc': 0.2
        }
        
        delta_score = 0.0
        
        for metric, weight in weights.items():
            if metric in baseline_metrics and metric in new_metrics:
                # Calculate relative improvement
                baseline_val = baseline_metrics[metric]
                new_val = new_metrics[metric]
                
                if baseline_val > 0:
                    relative_improvement = (new_val - baseline_val) / baseline_val
                else:
                    relative_improvement = 0
                    
                delta_score += weight * relative_improvement
                
        return delta_score
        
    def compare_models(
        self,
        baseline_metrics: Dict[str, float],
        new_metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Compare baseline and new model metrics.
        
        Args:
            baseline_metrics: Baseline model metrics
            new_metrics: New model metrics
            
        Returns:
            Comparison results with deltas and improvements
        """
        # Find common metrics
        common_metrics = set(baseline_metrics.keys()) & set(new_metrics.keys())
        missing_metrics = (set(baseline_metrics.keys()) | set(new_metrics.keys())) - common_metrics
        
        if missing_metrics:
            warnings.warn(f"Missing metrics in comparison: {missing_metrics}")
            
        comparison = {
            'metric_deltas': {},
            'improved_metrics': [],
            'degraded_metrics': []
        }
        
        # Calculate deltas for each metric
        for metric in common_metrics:
            baseline_val = baseline_metrics[metric]
            new_val = new_metrics[metric]
            
            absolute_delta = new_val - baseline_val
            relative_delta = absolute_delta / baseline_val if baseline_val > 0 else 0
            
            comparison['metric_deltas'][metric] = {
                'baseline_value': baseline_val,
                'new_value': new_val,
                'absolute_delta': absolute_delta,
                'relative_delta': relative_delta,
                'improvement': absolute_delta > 0
            }
            
            # Track improvements/degradations
            if absolute_delta > 0:
                comparison['improved_metrics'].append(metric)
            elif absolute_delta < 0:
                comparison['degraded_metrics'].append(metric)
                
        # Calculate overall DeltaOne score
        comparison['delta_one_score'] = self.calculate_delta_one_score(
            baseline_metrics, new_metrics
        )
        
        return comparison
        
    def estimate_confidence(self, sample_size: int) -> float:
        """
        Estimate confidence based on sample size.
        
        Args:
            sample_size: Number of samples used
            
        Returns:
            Confidence score between 0 and 1
        """
        # Simple confidence estimation based on sample size
        # Reaches 0.9 confidence at 100k samples
        confidence = min(0.9, sample_size / 100000)
        
        # Apply a curve to make confidence grow faster initially
        confidence = np.sqrt(confidence)
        
        return confidence
        
    def _prepare_test_data(self, data: pd.DataFrame) -> Tuple[Any, np.ndarray]:
        """
        Prepare test data for evaluation.
        
        Args:
            data: Test dataframe
            
        Returns:
            Tuple of (features, labels)
        """
        # Extract labels
        y = data['label'].values
        
        # Extract features
        if 'features' in data.columns:
            # Handle case where features are stored as lists
            X = np.array(data['features'].tolist())
        else:
            # Use all columns except label and query_id as features
            feature_cols = [col for col in data.columns 
                          if col not in ['label', 'query_id']]
            X = data[feature_cols].values
            
        return X, y