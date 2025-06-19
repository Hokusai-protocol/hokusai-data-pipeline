"""Manifest generation for data validation results."""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd

from .exceptions import ManifestGenerationError
from . import __version__


class ManifestGenerator:
    """Generates validation manifests for data files."""
    
    SCHEMA_VERSION = "1.0"
    
    def __init__(self):
        """Initialize manifest generator."""
        pass
    
    def generate(self, 
                 file_path: str,
                 data: pd.DataFrame,
                 validation_results: Dict[str, Any],
                 data_hash: str,
                 contributor_metadata: Optional[Dict[str, Any]] = None,
                 eth_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a comprehensive manifest for the validated data.
        
        Args:
            file_path: Path to the original data file
            data: The validated DataFrame
            validation_results: Results from validation pipeline
            data_hash: SHA256 hash of the data
            contributor_metadata: Optional metadata about the contributor
            eth_address: Optional Ethereum wallet address for the contributor
            
        Returns:
            Manifest dictionary
        """
        try:
            manifest = {
                'schema_version': self.SCHEMA_VERSION,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'file_metadata': self._generate_file_metadata(file_path, data),
                'validation_results': self._prepare_validation_results(validation_results),
                'data_hash': data_hash,
                'contributor_metadata': self._generate_contributor_metadata(contributor_metadata, eth_address),
                'tool_metadata': self._generate_tool_metadata()
            }
            
            # Add manifest hash (excluding the hash field itself)
            manifest_for_hashing = manifest.copy()
            manifest_for_hashing.pop('manifest_hash', None)
            manifest['manifest_hash'] = self._hash_manifest(manifest_for_hashing)
            
            return manifest
            
        except Exception as e:
            raise ManifestGenerationError(f"Manifest generation failed: {str(e)}")
    
    def _generate_file_metadata(self, file_path: str, data: pd.DataFrame) -> Dict[str, Any]:
        """Generate metadata about the original file."""
        path = Path(file_path)
        
        # Get file stats
        file_stats = path.stat() if path.exists() else None
        
        # Detect encoding if it's a text file
        encoding = self._detect_encoding(file_path) if path.suffix.lower() in ['.csv', '.json'] else None
        
        metadata = {
            'path': str(path.absolute()),
            'name': path.name,
            'format': path.suffix.lower().lstrip('.'),
            'size': file_stats.st_size if file_stats else 0,
            'rows': len(data),
            'columns': len(data.columns),
            'column_names': list(data.columns),
            'column_types': {col: str(dtype) for col, dtype in data.dtypes.items()},
            'encoding': encoding,
            'modification_time': datetime.fromtimestamp(
                file_stats.st_mtime, tz=timezone.utc
            ).isoformat() if file_stats else None
        }
        
        return metadata
    
    def _prepare_validation_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare validation results for manifest."""
        # Clean up results to only include relevant information
        cleaned_results = {}
        
        # Schema validation
        if 'schema_valid' in results:
            cleaned_results['schema_validation'] = {
                'valid': results.get('schema_valid', False),
                'errors': results.get('schema_errors', []),
                'missing_columns': results.get('missing_columns', []),
                'type_errors': results.get('type_errors', {})
            }
        
        # PII detection
        if 'pii_found' in results:
            cleaned_results['pii_detection'] = {
                'pii_found': results.get('pii_found', False),
                'patterns_detected': results.get('pii_patterns', []),
                'flagged_fields': results.get('pii_fields', []),
                'redacted': results.get('pii_redacted', False)
            }
        
        # Data quality
        if 'quality_score' in results:
            cleaned_results['data_quality'] = {
                'quality_score': results.get('quality_score', 0.0),
                'issues': results.get('quality_issues', []),
                'missing_values': results.get('missing_values', {}),
                'outliers': len(results.get('outliers', [])),
                'duplicates': results.get('duplicates', {})
            }
        
        # Overall validation status
        cleaned_results['overall'] = {
            'valid': results.get('valid', False),
            'errors': results.get('errors', []),
            'warnings': results.get('warnings', [])
        }
        
        return cleaned_results
    
    def _generate_contributor_metadata(self, 
                                     contributor_metadata: Optional[Dict[str, Any]],
                                     eth_address: Optional[str] = None) -> Dict[str, Any]:
        """Generate contributor metadata section."""
        metadata = {
            'tool_version': __version__,
            'validation_timestamp': datetime.now(timezone.utc).isoformat(),
            'environment': {
                'python_version': self._get_python_version(),
                'pandas_version': self._get_pandas_version()
            }
        }
        
        # Add ETH address if provided
        if eth_address:
            metadata['wallet_address'] = eth_address
        
        if contributor_metadata:
            metadata.update(contributor_metadata)
        
        return metadata
    
    def _generate_tool_metadata(self) -> Dict[str, Any]:
        """Generate metadata about the validation tool."""
        return {
            'name': 'hokusai-validate',
            'version': __version__,
            'description': 'Hokusai data validation CLI',
            'validation_features': [
                'schema_validation',
                'pii_detection',
                'data_quality_checks',
                'hash_generation',
                'manifest_creation'
            ]
        }
    
    def _detect_encoding(self, file_path: str) -> Optional[str]:
        """Detect file encoding."""
        try:
            import chardet
            
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Read first 10KB
                result = chardet.detect(raw_data)
                return result.get('encoding')
        except ImportError:
            # chardet not available, use a simple heuristic
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(1000)
                return 'utf-8'
            except UnicodeDecodeError:
                return 'latin1'
        except Exception:
            return None
    
    def _get_python_version(self) -> str:
        """Get Python version."""
        import sys
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    def _get_pandas_version(self) -> str:
        """Get pandas version."""
        return pd.__version__
    
    def _hash_manifest(self, manifest: Dict[str, Any]) -> str:
        """Generate hash for the manifest itself."""
        manifest_str = json.dumps(manifest, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(manifest_str.encode('utf-8')).hexdigest()
    
    def validate_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate manifest structure and content.
        
        Args:
            manifest: Manifest to validate
            
        Returns:
            Validation result
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Check required fields
        required_fields = [
            'schema_version', 'timestamp', 'file_metadata', 
            'validation_results', 'data_hash', 'contributor_metadata'
        ]
        
        for field in required_fields:
            if field not in manifest:
                result['valid'] = False
                result['errors'].append(f"Missing required field: {field}")
        
        # Check schema version
        if manifest.get('schema_version') != self.SCHEMA_VERSION:
            result['warnings'].append(
                f"Schema version mismatch. Expected {self.SCHEMA_VERSION}, "
                f"got {manifest.get('schema_version')}"
            )
        
        # Validate hash if present
        if 'manifest_hash' in manifest:
            manifest_copy = manifest.copy()
            expected_hash = manifest_copy.pop('manifest_hash')
            actual_hash = self._hash_manifest(manifest_copy)
            
            if expected_hash != actual_hash:
                result['valid'] = False
                result['errors'].append("Manifest hash verification failed")
        
        return result
    
    def sign(self, manifest: Dict[str, Any], private_key_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Sign manifest (placeholder for future cryptographic signing).
        
        Args:
            manifest: Manifest to sign
            private_key_path: Path to private key for signing
            
        Returns:
            Signed manifest
        """
        # For now, just add a simple signature field
        # In the future, this could implement actual cryptographic signing
        signed_manifest = manifest.copy()
        
        manifest_hash = signed_manifest.get('manifest_hash')
        if not manifest_hash:
            manifest_copy = signed_manifest.copy()
            manifest_hash = self._hash_manifest(manifest_copy)
        
        # Placeholder signature - in production this would be cryptographic
        signed_manifest['signature'] = {
            'algorithm': 'placeholder',
            'signature': f"sig_{manifest_hash[:16]}",
            'signed_at': datetime.now(timezone.utc).isoformat(),
            'signer': 'hokusai-validate'
        }
        
        return signed_manifest
    
    def save(self, manifest: Dict[str, Any], output_path: str) -> str:
        """
        Save manifest to file.
        
        Args:
            manifest: Manifest to save
            output_path: Path to save the manifest
            
        Returns:
            Actual path where manifest was saved
        """
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            
            return str(path.absolute())
            
        except Exception as e:
            raise ManifestGenerationError(f"Failed to save manifest: {str(e)}")
    
    def load(self, manifest_path: str) -> Dict[str, Any]:
        """
        Load manifest from file.
        
        Args:
            manifest_path: Path to the manifest file
            
        Returns:
            Loaded manifest dictionary
        """
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            raise ManifestGenerationError(f"Failed to load manifest: {str(e)}")