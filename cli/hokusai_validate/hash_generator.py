"""Hash generation utilities for deterministic data hashing."""

import hashlib
import pandas as pd
import numpy as np
from typing import Optional, Union
import io

from .exceptions import HashGenerationError


class HashGenerator:
    """Generates deterministic hashes for DataFrames."""
    
    def __init__(self, algorithm: str = 'sha256'):
        """
        Initialize hash generator.
        
        Args:
            algorithm: Hash algorithm to use (default: sha256)
        """
        self.algorithm = algorithm.lower()
        if self.algorithm not in hashlib.algorithms_available:
            raise HashGenerationError(f"Unsupported hash algorithm: {algorithm}")
    
    def generate(self, 
                 data: pd.DataFrame, 
                 normalize: bool = True, 
                 chunk_size: Optional[int] = None) -> str:
        """
        Generate deterministic hash for DataFrame.
        
        Args:
            data: DataFrame to hash
            normalize: Whether to normalize data before hashing
            chunk_size: Process data in chunks for large datasets
            
        Returns:
            Hexadecimal hash string
        """
        try:
            if chunk_size and len(data) > chunk_size:
                return self._generate_chunked_hash(data, normalize, chunk_size)
            else:
                return self._generate_single_hash(data, normalize)
                
        except Exception as e:
            raise HashGenerationError(f"Hash generation failed: {str(e)}")
    
    def _generate_single_hash(self, data: pd.DataFrame, normalize: bool) -> str:
        """Generate hash for entire DataFrame at once."""
        # Prepare data for hashing
        prepared_data = self._prepare_data_for_hashing(data, normalize)
        
        # Convert to bytes
        data_bytes = self._dataframe_to_bytes(prepared_data)
        
        # Generate hash
        hasher = hashlib.new(self.algorithm)
        hasher.update(data_bytes)
        
        return hasher.hexdigest()
    
    def _generate_chunked_hash(self, 
                              data: pd.DataFrame, 
                              normalize: bool, 
                              chunk_size: int) -> str:
        """Generate hash by processing data in chunks."""
        # For chunked hashing to be deterministic, we need to prepare the entire
        # dataset first, then process it in chunks
        prepared_data = self._prepare_data_for_hashing(data, normalize)
        
        hasher = hashlib.new(self.algorithm)
        
        # Include metadata once at the beginning
        metadata = f"COLUMNS:{','.join(prepared_data.columns)}\nDTYPES:{','.join(str(dtype) for dtype in prepared_data.dtypes)}\nDATA:\n"
        hasher.update(metadata.encode('utf-8'))
        
        # Process prepared data in chunks - only data, not metadata
        for i in range(0, len(prepared_data), chunk_size):
            chunk = prepared_data.iloc[i:i + chunk_size]
            chunk_csv = chunk.to_csv(index=False, header=False, na_rep='')
            hasher.update(chunk_csv.encode('utf-8'))
        
        return hasher.hexdigest()
    
    def _prepare_data_for_hashing(self, data: pd.DataFrame, normalize: bool) -> pd.DataFrame:
        """
        Prepare DataFrame for consistent hashing.
        
        Args:
            data: DataFrame to prepare
            normalize: Whether to normalize the data
            
        Returns:
            Prepared DataFrame
        """
        prepared = data.copy()
        
        if normalize:
            # Sort by all columns for consistent ordering
            prepared = prepared.sort_values(by=list(prepared.columns))
            
            # Reset index to ensure consistent row ordering
            prepared = prepared.reset_index(drop=True)
            
            # Handle different data types consistently
            for col in prepared.columns:
                if prepared[col].dtype == 'object':
                    # Convert to string and handle NaN consistently
                    prepared[col] = prepared[col].astype(str).replace('nan', '')
                elif prepared[col].dtype in ['float64', 'float32']:
                    # Round floats to avoid precision issues
                    prepared[col] = prepared[col].round(10)
                elif pd.api.types.is_datetime64_any_dtype(prepared[col]):
                    # Convert datetime to ISO format string
                    prepared[col] = prepared[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return prepared
    
    def _dataframe_to_bytes(self, data: pd.DataFrame) -> bytes:
        """
        Convert DataFrame to bytes for hashing.
        
        Args:
            data: DataFrame to convert
            
        Returns:
            Bytes representation of the DataFrame
        """
        # Create a string representation that includes both data and structure
        buffer = io.StringIO()
        
        # Include column names and types
        buffer.write("COLUMNS:")
        buffer.write(','.join(data.columns))
        buffer.write('\n')
        
        buffer.write("DTYPES:")
        buffer.write(','.join(str(dtype) for dtype in data.dtypes))
        buffer.write('\n')
        
        # Include data
        buffer.write("DATA:\n")
        data.to_csv(buffer, index=False, header=False, na_rep='')
        
        # Convert to bytes
        return buffer.getvalue().encode('utf-8')
    
    def verify_hash(self, 
                   data: pd.DataFrame, 
                   expected_hash: str, 
                   normalize: bool = True) -> bool:
        """
        Verify that DataFrame produces the expected hash.
        
        Args:
            data: DataFrame to verify
            expected_hash: Expected hash value
            normalize: Whether to normalize data before hashing
            
        Returns:
            True if hash matches, False otherwise
        """
        try:
            actual_hash = self.generate(data, normalize)
            return actual_hash == expected_hash
        except Exception:
            return False
    
    def hash_file_metadata(self, file_path: str) -> str:
        """
        Generate hash for file metadata (size, modification time, etc.).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Hash of file metadata
        """
        import os
        from pathlib import Path
        
        try:
            path = Path(file_path)
            if not path.exists():
                raise HashGenerationError(f"File not found: {file_path}")
            
            stat = path.stat()
            metadata = f"{path.name}:{stat.st_size}:{stat.st_mtime}".encode('utf-8')
            
            hasher = hashlib.new(self.algorithm)
            hasher.update(metadata)
            
            return hasher.hexdigest()
            
        except Exception as e:
            raise HashGenerationError(f"File metadata hashing failed: {str(e)}")
    
    def combine_hashes(self, *hashes: str) -> str:
        """
        Combine multiple hashes into a single hash.
        
        Args:
            *hashes: Hash strings to combine
            
        Returns:
            Combined hash string
        """
        try:
            hasher = hashlib.new(self.algorithm)
            
            for hash_value in sorted(hashes):  # Sort for deterministic ordering
                hasher.update(hash_value.encode('utf-8'))
            
            return hasher.hexdigest()
            
        except Exception as e:
            raise HashGenerationError(f"Hash combination failed: {str(e)}")
    
    def get_algorithm_info(self) -> dict:
        """
        Get information about the hash algorithm being used.
        
        Returns:
            Dictionary with algorithm information
        """
        hasher = hashlib.new(self.algorithm)
        
        return {
            'algorithm': self.algorithm,
            'digest_size': hasher.digest_size,
            'block_size': hasher.block_size,
            'name': hasher.name
        }