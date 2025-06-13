"""Module for integrating contributed data."""

from pathlib import Path
from typing import Optional, Tuple, List
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import hashlib
import json
import time
from ..utils.mlflow_config import mlflow_run_context, log_step_parameters, log_step_metrics, log_dataset_info
import logging

logger = logging.getLogger(__name__)


class DataIntegrator:
    """Handles integration and validation of contributed datasets."""
    
    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        np.random.seed(random_seed)
    
    def load_data(self, data_path: Path, run_id: str = "data_load", 
                 metaflow_run_id: str = "") -> pd.DataFrame:
        """Load data from various formats with tracking.
        
        Args:
            data_path: Path to data file
            run_id: Unique run identifier
            metaflow_run_id: Metaflow run identifier
            
        Returns:
            Loaded dataframe
        """
        start_time = time.time()
        run_name = f"data_load_{run_id}"
        
        with mlflow_run_context(
            run_name=run_name, 
            tags={
                "pipeline.step": "integrate_contributed_data",
                "pipeline.run_id": run_id,
                "metaflow.run_id": metaflow_run_id
            }
        ):
            try:
                if not data_path.exists():
                    raise FileNotFoundError(f"Data file not found: {data_path}")
                
                suffix = data_path.suffix.lower()
                
                # Log parameters
                log_step_parameters({
                    "data_path": str(data_path),
                    "data_format": suffix,
                    "file_size_bytes": data_path.stat().st_size
                })
                
                if suffix == ".csv":
                    df = pd.read_csv(data_path)
                elif suffix == ".json":
                    df = pd.read_json(data_path)
                elif suffix == ".parquet":
                    df = pd.read_parquet(data_path)
                else:
                    raise ValueError(f"Unsupported data format: {suffix}")
                
                # Calculate and log dataset hash
                data_hash = self.calculate_data_hash(df)
                
                # Log dataset information
                log_dataset_info(str(data_path), data_hash, len(df), len(df.columns))
                
                # Log metrics
                load_time = time.time() - start_time
                log_step_metrics({
                    "load_time_seconds": load_time,
                    "data_loaded": 1,
                    "memory_usage_mb": df.memory_usage(deep=True).sum() / 1024 / 1024
                })
                
                logger.info(f"Successfully loaded data from {data_path}: {len(df)} rows, {len(df.columns)} columns")
                return df
                
            except Exception as e:
                log_step_metrics({"data_loaded": 0})
                logger.error(f"Failed to load data: {e}")
                raise
    
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
        merge_strategy: str = "append",
        run_id: str = "data_merge",
        metaflow_run_id: str = ""
    ) -> pd.DataFrame:
        """Merge base and contributed datasets with tracking.
        
        Args:
            base_df: Base training dataset
            contributed_df: New contributed data
            merge_strategy: How to merge ("append", "update", "replace")
            run_id: Unique run identifier
            metaflow_run_id: Metaflow run identifier
            
        Returns:
            Merged dataframe
        """
        start_time = time.time()
        run_name = f"data_merge_{run_id}"
        
        with mlflow_run_context(
            run_name=run_name, 
            tags={
                "pipeline.step": "integrate_contributed_data",
                "pipeline.run_id": run_id,
                "metaflow.run_id": metaflow_run_id
            }
        ):
            try:
                # Log parameters
                log_step_parameters({
                    "merge_strategy": merge_strategy,
                    "base_rows": len(base_df),
                    "base_columns": len(base_df.columns),
                    "contributed_rows": len(contributed_df),
                    "contributed_columns": len(contributed_df.columns)
                })
                
                if merge_strategy == "append":
                    merged_df = pd.concat([base_df, contributed_df], ignore_index=True)
                elif merge_strategy == "replace":
                    merged_df = contributed_df
                elif merge_strategy == "update":
                    # Update existing records and add new ones
                    merged_df = pd.concat([base_df, contributed_df]).drop_duplicates(
                        subset=base_df.columns.tolist(), keep="last"
                    )
                else:
                    raise ValueError(f"Unknown merge strategy: {merge_strategy}")
                
                # Log metrics
                merge_time = time.time() - start_time
                log_step_metrics({
                    "merge_time_seconds": merge_time,
                    "final_rows": len(merged_df),
                    "final_columns": len(merged_df.columns),
                    "rows_added": len(merged_df) - len(base_df),
                    "merge_success": 1
                })
                
                logger.info(f"Successfully merged datasets: {len(merged_df)} total rows")
                return merged_df
                
            except Exception as e:
                log_step_metrics({"merge_success": 0})
                logger.error(f"Failed to merge datasets: {e}")
                raise
    
    def calculate_data_hash(self, df: pd.DataFrame) -> str:
        """Calculate hash of dataset for verification.
        
        Args:
            df: Dataframe to hash
            
        Returns:
            SHA256 hash of data
        """
        # Convert dataframe to string representation (sorted for consistency)
        data_str = df.sort_index().sort_index(axis=1).to_json(orient="records")
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