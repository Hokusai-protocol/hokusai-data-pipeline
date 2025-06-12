"""Module for model evaluation."""

from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
import json


class ModelEvaluator:
    """Handles model evaluation on benchmark datasets."""
    
    def __init__(self, metrics: Optional[List[str]] = None):
        self.metrics = metrics or ["accuracy", "precision", "recall", "f1", "auroc"]
    
    def evaluate_mock_model(
        self,
        model: Dict[str, Any],
        X_test: pd.DataFrame,
        y_test: pd.Series
    ) -> Dict[str, float]:
        """Evaluate a mock model.
        
        Args:
            model: Mock model dictionary
            X_test: Test features
            y_test: Test labels
            
        Returns:
            Evaluation metrics
        """
        # For mock models, return the stored metrics with slight variation
        base_metrics = model.get("metrics", {})
        
        # Add slight random variation to simulate test set performance
        evaluated_metrics = {}
        for metric in self.metrics:
            if metric in base_metrics:
                # Add small random variation (-2% to +2%)
                variation = np.random.uniform(-0.02, 0.02)
                evaluated_metrics[metric] = max(0, min(1, base_metrics[metric] + variation))
            else:
                evaluated_metrics[metric] = np.random.uniform(0.7, 0.9)
        
        return evaluated_metrics
    
    def evaluate_sklearn_model(
        self,
        model: Any,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        threshold: float = 0.5
    ) -> Dict[str, float]:
        """Evaluate a scikit-learn model.
        
        Args:
            model: Trained sklearn model
            X_test: Test features
            y_test: Test labels
            threshold: Classification threshold
            
        Returns:
            Evaluation metrics
        """
        # Get predictions
        y_pred = model.predict(X_test)
        
        # Get probabilities if available
        y_proba = None
        if hasattr(model, "predict_proba"):
            y_proba = model.predict_proba(X_test)
            # For binary classification, use positive class probabilities
            if y_proba.shape[1] == 2:
                y_proba = y_proba[:, 1]
        
        # Calculate metrics
        metrics = {}
        
        if "accuracy" in self.metrics:
            metrics["accuracy"] = accuracy_score(y_test, y_pred)
        
        if "precision" in self.metrics:
            metrics["precision"] = precision_score(
                y_test, y_pred, average="weighted", zero_division=0
            )
        
        if "recall" in self.metrics:
            metrics["recall"] = recall_score(
                y_test, y_pred, average="weighted", zero_division=0
            )
        
        if "f1" in self.metrics:
            metrics["f1"] = f1_score(
                y_test, y_pred, average="weighted", zero_division=0
            )
        
        if "auroc" in self.metrics and y_proba is not None:
            try:
                metrics["auroc"] = roc_auc_score(
                    y_test, y_proba, average="weighted", multi_class="ovr"
                )
            except ValueError:
                # AUROC not defined for the given case
                metrics["auroc"] = None
        
        return metrics
    
    def evaluate_model(
        self,
        model: Any,
        X_test: pd.DataFrame,
        y_test: pd.Series
    ) -> Dict[str, Any]:
        """Evaluate any model type.
        
        Args:
            model: Model to evaluate
            X_test: Test features
            y_test: Test labels
            
        Returns:
            Evaluation results
        """
        # Check if mock model
        if isinstance(model, dict) and model.get("type", "").startswith("mock"):
            metrics = self.evaluate_mock_model(model, X_test, y_test)
        else:
            metrics = self.evaluate_sklearn_model(model, X_test, y_test)
        
        return {
            "metrics": metrics,
            "test_samples": len(X_test),
            "model_type": type(model).__name__ if not isinstance(model, dict) else model.get("type")
        }
    
    def compare_models(
        self,
        baseline_metrics: Dict[str, float],
        new_metrics: Dict[str, float]
    ) -> Dict[str, Dict[str, float]]:
        """Compare two models' metrics.
        
        Args:
            baseline_metrics: Baseline model metrics
            new_metrics: New model metrics
            
        Returns:
            Comparison results
        """
        comparison = {}
        
        for metric in self.metrics:
            if metric in baseline_metrics and metric in new_metrics:
                baseline_val = baseline_metrics[metric]
                new_val = new_metrics[metric]
                
                comparison[metric] = {
                    "baseline": baseline_val,
                    "new": new_val,
                    "absolute_delta": new_val - baseline_val,
                    "relative_delta": ((new_val - baseline_val) / baseline_val * 100) 
                                     if baseline_val > 0 else 0,
                    "improved": new_val > baseline_val
                }
        
        return comparison
    
    def calculate_delta_score(
        self,
        comparison: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """Calculate overall delta score.
        
        Args:
            comparison: Model comparison results
            weights: Metric weights (defaults to equal weights)
            
        Returns:
            Delta score
        """
        if not weights:
            # Default equal weights
            weights = {metric: 1.0 for metric in comparison.keys()}
        
        # Normalize weights
        total_weight = sum(weights.values())
        weights = {k: v/total_weight for k, v in weights.items()}
        
        # Calculate weighted delta
        delta_score = 0
        for metric, values in comparison.items():
            if metric in weights and values.get("absolute_delta") is not None:
                delta_score += weights[metric] * values["absolute_delta"]
        
        return delta_score
    
    def create_evaluation_report(
        self,
        baseline_results: Dict[str, Any],
        new_results: Dict[str, Any],
        comparison: Dict[str, Dict[str, float]],
        delta_score: float
    ) -> Dict[str, Any]:
        """Create comprehensive evaluation report.
        
        Args:
            baseline_results: Baseline evaluation results
            new_results: New model evaluation results
            comparison: Comparison results
            delta_score: Overall delta score
            
        Returns:
            Evaluation report
        """
        return {
            "baseline_model": {
                "metrics": baseline_results["metrics"],
                "model_type": baseline_results["model_type"],
                "test_samples": baseline_results["test_samples"]
            },
            "new_model": {
                "metrics": new_results["metrics"],
                "model_type": new_results["model_type"],
                "test_samples": new_results["test_samples"]
            },
            "comparison": comparison,
            "delta_score": delta_score,
            "summary": {
                "improved_metrics": [
                    m for m, v in comparison.items() if v.get("improved", False)
                ],
                "degraded_metrics": [
                    m for m, v in comparison.items() if not v.get("improved", True)
                ],
                "overall_improvement": delta_score > 0
            }
        }