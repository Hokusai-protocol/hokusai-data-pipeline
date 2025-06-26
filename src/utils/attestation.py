"""Attestation utilities for zk-proof ready outputs."""

import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from src.utils.constants import ATTESTATION_VERSION, ATTESTATION_SCHEMA_VERSION


class AttestationGenerator:
    """Generates attestation-ready outputs for pipeline results."""
    
    def __init__(self):
        self.schema_version = ATTESTATION_SCHEMA_VERSION
        self.attestation_version = ATTESTATION_VERSION
    
    def create_attestation(
        self,
        run_id: str,
        contributor_data_hash: str,
        baseline_model_id: str,
        new_model_id: str,
        evaluation_results: Dict[str, Any],
        delta_results: Dict[str, Any],
        delta_score: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create attestation document.
        
        Args:
            run_id: Pipeline run ID
            contributor_data_hash: Hash of contributed data
            baseline_model_id: Baseline model identifier
            new_model_id: New model identifier
            evaluation_results: Evaluation metrics
            delta_results: Delta calculations
            delta_score: Overall delta score
            metadata: Additional metadata
            
        Returns:
            Attestation document
        """
        attestation = {
            "schema_version": self.schema_version,
            "attestation_version": self.attestation_version,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "run_id": run_id,
            "attestation_id": self._generate_attestation_id(run_id),
            
            "contributor": {
                "data_hash": contributor_data_hash,
                "contribution_timestamp": datetime.utcnow().isoformat() + "Z"
            },
            
            "models": {
                "baseline": {
                    "model_id": baseline_model_id,
                    "model_hash": self._hash_string(baseline_model_id)
                },
                "improved": {
                    "model_id": new_model_id,
                    "model_hash": self._hash_string(new_model_id)
                }
            },
            
            "evaluation": {
                "metrics": evaluation_results,
                "delta_results": delta_results,
                "delta_score": delta_score,
                "evaluation_timestamp": datetime.utcnow().isoformat() + "Z"
            },
            
            "proof_data": self._generate_proof_data(
                contributor_data_hash,
                baseline_model_id,
                new_model_id,
                delta_score
            ),
            
            "metadata": metadata or {},
            
            "signature_placeholder": "0x" + "0" * 64  # Placeholder for actual signature
        }
        
        # Add content hash
        attestation["content_hash"] = self._calculate_content_hash(attestation)
        
        return attestation
    
    def _generate_attestation_id(self, run_id: str) -> str:
        """Generate unique attestation ID."""
        timestamp = datetime.utcnow().isoformat()
        return self._hash_string(f"{run_id}:{timestamp}")[:16]
    
    def _hash_string(self, value: str) -> str:
        """Calculate SHA256 hash of string."""
        return hashlib.sha256(value.encode()).hexdigest()
    
    def _generate_proof_data(
        self,
        data_hash: str,
        baseline_id: str,
        new_id: str,
        delta_score: float
    ) -> Dict[str, Any]:
        """Generate proof data for zk verification.
        
        Args:
            data_hash: Contributed data hash
            baseline_id: Baseline model ID
            new_id: New model ID
            delta_score: Performance delta
            
        Returns:
            Proof data structure
        """
        # Create commitment to the evaluation
        commitment_input = f"{data_hash}:{baseline_id}:{new_id}:{delta_score:.6f}"
        commitment = self._hash_string(commitment_input)
        
        return {
            "commitment": commitment,
            "nullifier": self._hash_string(f"{commitment}:nullifier"),
            "merkle_root_placeholder": "0x" + "0" * 64,
            "proof_type": "placeholder",
            "circuit_version": "1.0.0",
            "public_inputs": {
                "delta_score": delta_score,
                "data_hash": data_hash[:16],  # Truncated for privacy
                "timestamp": int(datetime.utcnow().timestamp())
            }
        }
    
    def _calculate_content_hash(self, attestation: Dict[str, Any]) -> str:
        """Calculate hash of attestation content."""
        # Remove mutable fields
        content = attestation.copy()
        content.pop("signature_placeholder", None)
        content.pop("content_hash", None)
        
        # Serialize deterministically
        content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return self._hash_string(content_str)
    
    def validate_attestation(self, attestation: Dict[str, Any]) -> bool:
        """Validate attestation structure and content hash.
        
        Args:
            attestation: Attestation document
            
        Returns:
            True if valid
        """
        # Check required fields
        required_fields = [
            "schema_version", "attestation_version", "run_id",
            "contributor", "models", "evaluation", "proof_data"
        ]
        
        for field in required_fields:
            if field not in attestation:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate schema version
        if attestation["schema_version"] != self.schema_version:
            raise ValueError(
                f"Invalid schema version: {attestation['schema_version']}"
            )
        
        # Validate content hash
        stored_hash = attestation.get("content_hash")
        calculated_hash = self._calculate_content_hash(attestation)
        
        if stored_hash != calculated_hash:
            raise ValueError("Content hash mismatch")
        
        return True
    
    def save_attestation(
        self,
        attestation: Dict[str, Any],
        output_path: Path
    ) -> Path:
        """Save attestation to file.
        
        Args:
            attestation: Attestation document
            output_path: Output file path
            
        Returns:
            Path to saved file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(attestation, f, indent=2)
        
        return output_path
    
    def create_summary(self, attestation: Dict[str, Any]) -> Dict[str, Any]:
        """Create human-readable summary of attestation.
        
        Args:
            attestation: Attestation document
            
        Returns:
            Summary dictionary
        """
        delta_score = attestation["evaluation"]["delta_score"]
        
        return {
            "attestation_id": attestation["attestation_id"],
            "timestamp": attestation["timestamp"],
            "delta_score": delta_score,
            "improvement_percentage": delta_score * 100,
            "baseline_model": attestation["models"]["baseline"]["model_id"],
            "improved_model": attestation["models"]["improved"]["model_id"],
            "proof_commitment": attestation["proof_data"]["commitment"][:16] + "...",
            "content_hash": attestation["content_hash"][:16] + "...",
            "status": "IMPROVEMENT" if delta_score > 0 else "NO_IMPROVEMENT"
        }