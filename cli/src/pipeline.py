"""
Main pipeline orchestration for the Hokusai Data Evaluation Pipeline
"""
import yaml
import random
import numpy as np
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    """Configuration for the evaluation pipeline"""
    model_path: str
    dataset_path: str
    output_dir: str = '/tmp/hokusai_output'
    batch_size: int = 32
    random_seed: int = 42
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'PipelineConfig':
        """Create config from dictionary"""
        # Validate required fields
        if 'model_path' not in config_dict:
            raise ValueError("model_path is required")
        if 'dataset_path' not in config_dict:
            raise ValueError("dataset_path is required")
        
        return cls(**config_dict)
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'PipelineConfig':
        """Load config from YAML file"""
        with open(yaml_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        return cls.from_dict(config_dict)


class Pipeline:
    """Main pipeline orchestrator"""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = 'initialized'
        self.completed_steps: List[str] = []
    
    def run(self) -> Dict[str, Any]:
        """Run the complete evaluation pipeline"""
        try:
            self.state = 'running'
            self._set_random_seeds()
            self._start_mlflow_run()
            
            # Step 1: Load data
            data = self._load_data()
            self._mark_step_complete('data_loading')
            
            # Step 2: Load model
            model = self._load_model()
            self._mark_step_complete('model_loading')
            
            # Step 3: Run evaluation
            results = self._evaluate_model(model, data)
            self._mark_step_complete('evaluation')
            
            self.state = 'completed'
            return results
            
        except Exception as e:
            self.state = 'error'
            raise e
    
    def _set_random_seeds(self):
        """Set random seeds for reproducibility"""
        random.seed(self.config.random_seed)
        np.random.seed(self.config.random_seed)
    
    def _start_mlflow_run(self):
        """Start MLflow tracking run"""
        try:
            import mlflow
            mlflow.start_run()
            mlflow.log_params({
                'batch_size': self.config.batch_size,
                'random_seed': self.config.random_seed
            })
        except ImportError:
            # MLflow not available, skip tracking
            pass
    
    def _load_data(self):
        """Load and prepare dataset"""
        from data_loader import DataLoader
        loader = DataLoader()
        return loader.load(self.config.dataset_path)
    
    def _load_model(self):
        """Load the model for evaluation"""
        from model_loader import ModelLoader
        loader = ModelLoader()
        return loader.load(self.config.model_path)
    
    def _evaluate_model(self, model, data):
        """Evaluate the model on the dataset"""
        from evaluator import Evaluator
        evaluator = Evaluator()
        return evaluator.evaluate(model, data)
    
    def _mark_step_complete(self, step_name: str):
        """Mark a pipeline step as completed"""
        self.completed_steps.append(step_name)