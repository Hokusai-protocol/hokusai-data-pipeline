"""Data loader module for preview pipeline."""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Union
import json
from sklearn.model_selection import train_test_split
import logging

logger = logging.getLogger(__name__)


class PreviewDataLoader:
    """Handles data loading and validation for the preview pipeline."""
    
    def __init__(
        self,
        max_samples: int = 10000,
        chunk_size: int = 1000,
        show_progress: bool = True,
        random_seed: int = 42
    ):
        """
        Initialize PreviewDataLoader.
        
        Args:
            max_samples: Maximum number of samples to load
            chunk_size: Chunk size for memory-efficient loading
            show_progress: Whether to show progress indicators
            random_seed: Random seed for reproducibility
        """
        self.max_samples = max_samples
        self.chunk_size = chunk_size
        self.show_progress = show_progress
        self.random_seed = random_seed
        np.random.seed(random_seed)
        
    def load_data(
        self, 
        file_path: Union[str, Path], 
        sample: bool = True
    ) -> pd.DataFrame:
        """
        Load data from file with automatic format detection.
        
        Args:
            file_path: Path to the data file
            sample: Whether to apply sampling for large datasets
            
        Returns:
            Loaded DataFrame
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is unsupported or data is invalid
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        format_type = self._detect_format(str(file_path))
        
        if self.show_progress:
            print("Loading data...")
            
        try:
            if format_type == "csv":
                data = self._load_csv(file_path)
            elif format_type == "json":
                data = self._load_json(file_path)
            elif format_type == "parquet":
                data = self._load_parquet(file_path)
            else:
                raise ValueError(f"Unsupported file format: {format_type}")
                
        except Exception as e:
            raise ValueError(f"Failed to load data: {str(e)}")
            
        if len(data) == 0:
            raise ValueError("Empty dataset")
            
        # Apply sampling if needed and requested
        if sample and len(data) > self.max_samples:
            data = self._stratified_sample(data)
            
        if self.show_progress:
            print(f"Complete. Loaded {len(data)} samples.")
            
        return data
        
    def _detect_format(self, file_path: str) -> str:
        """
        Detect file format from extension.
        
        Args:
            file_path: Path to file
            
        Returns:
            File format type
            
        Raises:
            ValueError: If format is unsupported
        """
        ext = Path(file_path).suffix.lower()
        
        if ext == ".csv":
            return "csv"
        elif ext == ".json":
            return "json"
        elif ext == ".parquet":
            return "parquet"
        else:
            raise ValueError(f"Unsupported file format: {ext}")
            
    def _load_csv(self, file_path: Path) -> pd.DataFrame:
        """Load CSV file."""
        data = pd.read_csv(file_path)
        # Convert string representation of lists to actual lists if needed
        if 'features' in data.columns:
            try:
                import ast
                data['features'] = data['features'].apply(ast.literal_eval)
            except (ValueError, SyntaxError):
                # If conversion fails, keep as strings
                pass
        return data
        
    def _load_json(self, file_path: Path) -> pd.DataFrame:
        """Load JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return pd.DataFrame(data)
        
    def _load_parquet(self, file_path: Path) -> pd.DataFrame:
        """Load Parquet file."""
        return pd.read_parquet(file_path)
        
    def validate_schema(self, data: pd.DataFrame, required_columns: Optional[list] = None):
        """
        Validate data schema.
        
        Args:
            data: DataFrame to validate
            required_columns: List of required columns
            
        Raises:
            ValueError: If schema validation fails
        """
        if required_columns is None:
            required_columns = ['query_id', 'label', 'features']
            
        missing_columns = set(required_columns) - set(data.columns)
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
            
    def _stratified_sample(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Perform stratified sampling to reduce dataset size.
        
        Args:
            data: Original DataFrame
            
        Returns:
            Sampled DataFrame preserving label distribution
        """
        if 'label' not in data.columns:
            # If no label column, do simple random sampling
            return data.sample(n=self.max_samples, random_state=self.random_seed)
            
        # Calculate sampling fraction
        sample_fraction = self.max_samples / len(data)
        
        # Perform stratified sampling
        _, sampled_data = train_test_split(
            data,
            test_size=sample_fraction,
            stratify=data['label'],
            random_state=self.random_seed
        )
        
        return sampled_data