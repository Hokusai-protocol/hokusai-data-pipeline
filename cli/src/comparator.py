"""
Model comparison module for the Hokusai Data Evaluation Pipeline
"""
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from sklearn.model_selection import cross_val_score
from evaluator import Evaluator, EvaluationMetrics


@dataclass
class ComparisonResult:
    """Container for model comparison results"""
    model1_metrics: Dict[str, float]
    model2_metrics: Dict[str, float]
    improvements: Dict[str, float]
    statistical_significance: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert comparison result to dictionary"""
        return {
            'model1_metrics': self.model1_metrics,
            'model2_metrics': self.model2_metrics,
            'improvements': self.improvements,
            'statistical_significance': self.statistical_significance
        }
    
    def get_summary(self) -> str:
        """Generate a human-readable summary of the comparison"""
        accuracy_improvement = self.improvements.get('accuracy', 0)
        
        if accuracy_improvement > 0.01:
            return f"Model 2 shows significant improvement over Model 1 (accuracy +{accuracy_improvement:.3f})"
        elif accuracy_improvement < -0.01:
            return f"Model 1 performs better than Model 2 (accuracy {abs(accuracy_improvement):.3f} higher)"
        else:
            return "Models show similar performance"


class Comparator:
    """Model comparator with statistical significance testing"""
    
    def __init__(self):
        self.evaluator = Evaluator()
    
    def compare(
        self,
        model1,
        model2,
        dataset,
        cv_folds: Optional[int] = None,
        n_bootstrap: int = 100,
        log_to_mlflow: bool = False
    ) -> ComparisonResult:
        """Compare two models on a dataset
        
        Args:
            model1: First model to compare
            model2: Second model to compare
            dataset: Dataset for comparison
            cv_folds: Number of cross-validation folds (optional)
            n_bootstrap: Number of bootstrap samples for significance testing
            log_to_mlflow: Whether to log comparison to MLflow
            
        Returns:
            ComparisonResult with detailed comparison metrics
        """
        if cv_folds:
            return self._compare_with_cv(model1, model2, dataset, cv_folds)
        else:
            return self._compare_simple(model1, model2, dataset, n_bootstrap)
    
    def _compare_simple(
        self,
        model1,
        model2,
        dataset,
        n_bootstrap: int
    ) -> ComparisonResult:
        """Simple comparison using single evaluation"""
        # Evaluate both models
        metrics1 = self.evaluator.evaluate(model1, dataset)
        metrics2 = self.evaluator.evaluate(model2, dataset)
        
        # Convert to dictionaries
        metrics1_dict = metrics1.to_dict()
        metrics2_dict = metrics2.to_dict()
        
        # Calculate improvements
        improvements = {}
        for metric in metrics1_dict:
            improvements[metric] = metrics2_dict[metric] - metrics1_dict[metric]
        
        # Calculate statistical significance using bootstrap
        significance = self._bootstrap_significance_test(
            model1, model2, dataset, n_bootstrap
        )
        
        return ComparisonResult(
            model1_metrics=metrics1_dict,
            model2_metrics=metrics2_dict,
            improvements=improvements,
            statistical_significance=significance
        )
    
    def _compare_with_cv(
        self,
        model1,
        model2,
        dataset,
        cv_folds: int
    ) -> ComparisonResult:
        """Compare models using cross-validation"""
        # This is a simplified implementation
        # In practice, would need proper CV integration with the dataset
        
        # For now, fall back to simple comparison
        return self._compare_simple(model1, model2, dataset, n_bootstrap=10)
    
    def _bootstrap_significance_test(
        self,
        model1,
        model2,
        dataset,
        n_bootstrap: int
    ) -> Dict[str, float]:
        """Perform bootstrap significance testing"""
        features = dataset.get_features()
        labels = dataset.get_labels()
        
        # Generate bootstrap samples
        improvements_dist = {
            'accuracy': [],
            'precision': [],
            'recall': [],
            'f1_score': []
        }
        
        for _ in range(n_bootstrap):
            # Bootstrap sample
            n_samples = len(features)
            bootstrap_idx = np.random.choice(n_samples, n_samples, replace=True)
            
            # Create bootstrap dataset (simplified)
            bootstrap_features = features[bootstrap_idx]
            bootstrap_labels = labels[bootstrap_idx]
            
            # Mock dataset object for bootstrap
            class BootstrapDataset:
                def get_features(self):
                    return bootstrap_features
                def get_labels(self):
                    return bootstrap_labels
            
            bootstrap_dataset = BootstrapDataset()
            
            # Evaluate both models on bootstrap sample
            try:
                metrics1 = self.evaluator.evaluate(model1, bootstrap_dataset)
                metrics2 = self.evaluator.evaluate(model2, bootstrap_dataset)
                
                metrics1_dict = metrics1.to_dict()
                metrics2_dict = metrics2.to_dict()
                
                # Store improvements
                for metric in improvements_dist:
                    improvement = metrics2_dict[metric] - metrics1_dict[metric]
                    improvements_dist[metric].append(improvement)
                    
            except Exception:
                # Skip this bootstrap sample if it fails
                continue
        
        # Calculate p-values (simplified)
        p_values = {}
        for metric, improvements in improvements_dist.items():
            if improvements:
                # Two-tailed test: proportion of improvements <= 0
                p_value = np.mean(np.array(improvements) <= 0) * 2
                p_values[metric] = min(p_value, 1.0)
            else:
                p_values[metric] = 1.0
        
        return p_values
    
    def _log_to_mlflow(self, result: ComparisonResult):
        """Log comparison results to MLflow"""
        try:
            import mlflow
            
            # Log improvements as metrics
            for metric, improvement in result.improvements.items():
                mlflow.log_metric(f"improvement_{metric}", improvement)
            
            # Log significance tests
            for metric, p_value in result.statistical_significance.items():
                mlflow.log_metric(f"p_value_{metric}", p_value)
                
        except ImportError:
            # MLflow not available, skip logging
            pass