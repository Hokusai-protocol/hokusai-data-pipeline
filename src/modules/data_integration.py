"""Module for integrating contributed data."""

from pathlib import Path
from typing import Optional, Tuple, List
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import hashlib
import json


class DataIntegrator:
    """Handles integration and validation of contributed datasets."""
    
    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        np.random.seed(random_seed)
    
    def load_data(self, data_path: Path) -> pd.DataFrame:
        """Load data from various formats.
        
        Args:
            data_path: Path to data file
            
        Returns:
            Loaded dataframe
        """
        if not data_path.exists():
            raise FileNotFoundError(f"Data file not found: {data_path}")
        
        suffix = data_path.suffix.lower()
        
        if suffix == ".csv":
            return pd.read_csv(data_path)
        elif suffix == ".json":
            return pd.read_json(data_path)
        elif suffix == ".parquet":
            return pd.read_parquet(data_path)
        else:
            raise ValueError(f"Unsupported data format: {suffix}")
    
    def validate_schema(self, df: pd.DataFrame, required_columns: List[str]) -> bool:
        """Validate dataframe has required columns.
        
        Args:
            df: Dataframe to validate
            required_columns: List of required column names
            
        Returns:
            True if valid, raises exception otherwise
        """
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        return True
    
    def remove_pii(self, df: pd.DataFrame, pii_columns: Optional[List[str]] = None) -> pd.DataFrame:
        """Remove or hash PII columns.
        
        Args:
            df: Input dataframe
            pii_columns: Columns containing PII
            
        Returns:
            Dataframe with PII removed/hashed
        """
        if not pii_columns:
            # Common PII column patterns
            pii_patterns = ["email", "phone", "ssn", "name", "address", "ip"]
            pii_columns = [col for col in df.columns 
                          if any(pattern in col.lower() for pattern in pii_patterns)]
        
        df_clean = df.copy()
        
        for col in pii_columns:
            if col in df_clean.columns:
                # Hash the PII data instead of removing
                df_clean[col] = df_clean[col].apply(self._hash_value)
        
        return df_clean
    
    def _hash_value(self, value: str) -> str:
        """Hash a string value."""
        if pd.isna(value):
            return value
        return hashlib.sha256(str(value).encode()).hexdigest()[:16]
    
    def deduplicate(self, df: pd.DataFrame, subset: Optional[List[str]] = None) -> pd.DataFrame:
        """Remove duplicate rows.
        
        Args:
            df: Input dataframe
            subset: Columns to consider for duplicates
            
        Returns:
            Deduplicated dataframe
        """
        return df.drop_duplicates(subset=subset, keep="first")
    
    def stratified_sample(
        self, 
        df: pd.DataFrame, 
        sample_size: int, 
        stratify_column: str
    ) -> pd.DataFrame:
        """Perform stratified sampling.
        
        Args:
            df: Input dataframe
            sample_size: Number of samples to take
            stratify_column: Column to stratify by
            
        Returns:
            Sampled dataframe
        """
        if sample_size >= len(df):
            return df
        
        # Use train_test_split for stratified sampling
        _, sampled_df = train_test_split(
            df,
            test_size=sample_size,
            stratify=df[stratify_column],
            random_state=self.random_seed
        )
        
        return sampled_df
    
    def merge_datasets(
        self, 
        base_df: pd.DataFrame, 
        contributed_df: pd.DataFrame,
        merge_strategy: str = "append"
    ) -> pd.DataFrame:
        """Merge base and contributed datasets.
        
        Args:
            base_df: Base training dataset
            contributed_df: New contributed data
            merge_strategy: How to merge ("append", "update", "replace")
            
        Returns:
            Merged dataframe
        """
        if merge_strategy == "append":
            return pd.concat([base_df, contributed_df], ignore_index=True)
        elif merge_strategy == "replace":
            return contributed_df
        elif merge_strategy == "update":
            # Update existing records and add new ones
            # This is a simplified implementation
            return pd.concat([base_df, contributed_df]).drop_duplicates(
                subset=base_df.columns.tolist(), keep="last"
            )
        else:
            raise ValueError(f"Unknown merge strategy: {merge_strategy}")
    
    def calculate_data_hash(self, df: pd.DataFrame) -> str:
        """Calculate hash of dataset for verification.
        
        Args:
            df: Dataframe to hash
            
        Returns:
            SHA256 hash of data
        """
        # Convert dataframe to string representation
        data_str = df.to_json(orient="records", sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def create_data_manifest(self, df: pd.DataFrame, data_path: Path) -> dict:
        """Create manifest for contributed data.
        
        Args:
            df: Contributed dataframe
            data_path: Original data path
            
        Returns:
            Data manifest dictionary
        """
        return {
            "source_path": str(data_path),
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": df.columns.tolist(),
            "data_hash": self.calculate_data_hash(df),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "null_counts": df.isnull().sum().to_dict(),
            "unique_counts": {col: df[col].nunique() for col in df.columns}
        }