"""Attestation service for teleprompt optimization achievements.

This service generates verifiable attestations when DSPy programs
achieve DeltaOne improvements through teleprompt optimization.
"""

import logging
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

import threading

from src.utils.attestation import generate_attestation_hash
from src.utils.eth_address_validator import validate_eth_address

logger = logging.getLogger(__name__)


@dataclass
class OptimizationAttestation:
    """Data structure for optimization attestation."""
    schema_version: str = "1.0"
    attestation_type: str = "teleprompt_optimization"
    attestation_id: str = ""
    timestamp: str = ""
    
    # Model information
    model_id: str = ""
    baseline_version: str = ""
    optimized_version: str = ""
    optimization_strategy: str = ""
    
    # Performance metrics
    deltaone_achieved: bool = False
    performance_delta: float = 0.0
    baseline_metrics: Dict[str, float] = None
    optimized_metrics: Dict[str, float] = None
    
    # Optimization details
    trace_count: int = 0
    optimization_time_seconds: float = 0.0
    outcome_metric: str = ""
    date_range: Dict[str, str] = None
    
    # Contributors
    contributors: List[Dict[str, Any]] = None
    total_contribution_weight: float = 1.0
    
    # Verification
    attestation_hash: str = ""
    signature: Optional[str] = None
    
    def __post_init__(self):
        """Initialize default values."""
        if self.baseline_metrics is None:
            self.baseline_metrics = {}
        if self.optimized_metrics is None:
            self.optimized_metrics = {}
        if self.date_range is None:
            self.date_range = {}
        if self.contributors is None:
            self.contributors = []
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        if not self.attestation_id:
            self.attestation_id = self._generate_attestation_id()
    
    def _generate_attestation_id(self) -> str:
        """Generate unique attestation ID."""
        import uuid
        # Include a random component to ensure uniqueness
        data = f"{self.model_id}-{self.optimized_version}-{self.timestamp}-{uuid.uuid4()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class OptimizationAttestationService:
    """Service for generating and managing optimization attestations."""
    
    def __init__(self):
        """Initialize attestation service."""
        self._storage: Dict[str, OptimizationAttestation] = {}
        self._lock = threading.Lock()
    
    def create_attestation(
        self,
        model_info: Dict[str, str],
        performance_data: Dict[str, Any],
        optimization_metadata: Dict[str, Any],
        contributors: List[Dict[str, Any]]
    ) -> OptimizationAttestation:
        """Create a new optimization attestation.
        
        Args:
            model_info: Model identification and version info
            performance_data: Performance metrics and delta
            optimization_metadata: Optimization process metadata
            contributors: List of contributor information
            
        Returns:
            OptimizationAttestation object
        """
        logger.info("Creating optimization attestation")
        
        # Validate contributor addresses
        validated_contributors = self._validate_contributors(contributors)
        
        # Create attestation
        attestation = OptimizationAttestation(
            model_id=model_info.get("model_id", ""),
            baseline_version=model_info.get("baseline_version", ""),
            optimized_version=model_info.get("optimized_version", ""),
            optimization_strategy=model_info.get("optimization_strategy", ""),
            deltaone_achieved=performance_data.get("deltaone_achieved", False),
            performance_delta=performance_data.get("delta", 0.0),
            baseline_metrics=performance_data.get("baseline_metrics", {}),
            optimized_metrics=performance_data.get("optimized_metrics", {}),
            trace_count=optimization_metadata.get("trace_count", 0),
            optimization_time_seconds=optimization_metadata.get("optimization_time", 0.0),
            outcome_metric=optimization_metadata.get("outcome_metric", ""),
            date_range=optimization_metadata.get("date_range", {}),
            contributors=validated_contributors,
            total_contribution_weight=sum(c["weight"] for c in validated_contributors)
        )
        
        # Generate attestation hash
        attestation.attestation_hash = self._generate_hash(attestation)
        
        # Store attestation
        with self._lock:
            self._storage[attestation.attestation_id] = attestation
        
        logger.info(f"Created attestation {attestation.attestation_id}")
        return attestation
    
    def store_attestation(self, attestation: OptimizationAttestation) -> None:
        """Store attestation in the service.
        
        Args:
            attestation: Attestation to store
        """
        with self._lock:
            self._storage[attestation.attestation_id] = attestation
            logger.info(f"Stored attestation: {attestation.attestation_id}")
    
    def verify_attestation(
        self,
        attestation: OptimizationAttestation
    ) -> bool:
        """Verify attestation integrity.
        
        Args:
            attestation: Attestation to verify
            
        Returns:
            True if attestation is valid
        """
        # Recompute hash
        expected_hash = self._generate_hash(attestation)
        
        # Compare with stored hash
        is_valid = attestation.attestation_hash == expected_hash
        
        if not is_valid:
            logger.warning(f"Attestation {attestation.attestation_id} verification failed")
        
        return is_valid
    
    def get_attestation(self, attestation_id: str) -> Optional[OptimizationAttestation]:
        """Retrieve attestation by ID.
        
        Args:
            attestation_id: Attestation ID
            
        Returns:
            Attestation object or None
        """
        with self._lock:
            return self._storage.get(attestation_id)
    
    def list_attestations(
        self,
        model_id: Optional[str] = None,
        contributor_address: Optional[str] = None,
        deltaone_only: bool = True
    ) -> List[OptimizationAttestation]:
        """List attestations with optional filtering.
        
        Args:
            model_id: Filter by model ID
            contributor_address: Filter by contributor
            deltaone_only: Only return DeltaOne achievements
            
        Returns:
            List of matching attestations
        """
        with self._lock:
            attestations = list(self._storage.values())
        
        if model_id:
            attestations = [
                a for a in attestations
                if a.model_id == model_id
            ]
        
        if contributor_address:
            attestations = [
                a for a in attestations
                if any(c["address"] == contributor_address for c in a.contributors)
            ]
        
        if deltaone_only:
            attestations = [
                a for a in attestations
                if a.deltaone_achieved
            ]
        
        return attestations
    
    def prepare_for_blockchain(
        self,
        attestation: OptimizationAttestation
    ) -> Dict[str, Any]:
        """Prepare attestation for blockchain submission.
        
        Args:
            attestation: Attestation to prepare
            
        Returns:
            Blockchain-ready attestation data
        """
        # Create compact representation for on-chain storage
        blockchain_data = {
            "attestation_id": attestation.attestation_id,
            "model_id": attestation.model_id,
            "optimized_version": attestation.optimized_version,
            "deltaone_achieved": attestation.deltaone_achieved,
            "performance_delta": int(attestation.performance_delta * 10000),  # Store as basis points
            "trace_count": attestation.trace_count,
            "timestamp": int(datetime.fromisoformat(attestation.timestamp).timestamp()),
            "contributors": [
                {
                    "address": c["address"],
                    "weight": int(c["weight"] * 10000)  # Store as basis points
                }
                for c in attestation.contributors
            ],
            "attestation_hash": attestation.attestation_hash
        }
        
        return blockchain_data
    
    def calculate_rewards(
        self,
        attestation: OptimizationAttestation,
        total_reward: float
    ) -> Dict[str, float]:
        """Calculate reward distribution for contributors.
        
        Args:
            attestation: Attestation with contributor info
            total_reward: Total reward amount
            
        Returns:
            Dictionary mapping addresses to reward amounts
        """
        if not attestation.deltaone_achieved:
            return {}
        
        rewards = {}
        
        for contributor in attestation.contributors:
            address = contributor["address"]
            weight = contributor["weight"]
            reward = total_reward * weight
            rewards[address] = round(reward, 6)
        
        # Ensure total matches (handle rounding)
        total_allocated = sum(rewards.values())
        if total_allocated != total_reward:
            # Adjust largest contributor's reward
            largest_contributor = max(rewards, key=rewards.get)
            rewards[largest_contributor] += (total_reward - total_allocated)
        
        return rewards
    
    def _validate_contributors(
        self,
        contributors: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate and normalize contributor information.
        
        Args:
            contributors: Raw contributor data
            
        Returns:
            Validated contributor list
        """
        validated = []
        
        for contrib in contributors:
            address = contrib.get("address", "")
            
            # Validate ETH address
            try:
                if not validate_eth_address(address):
                    logger.warning(f"Invalid ETH address: {address}")
                    continue
            except Exception as e:
                logger.warning(f"Invalid ETH address {address}: {e}")
                continue
            
            validated.append({
                "contributor_id": contrib.get("contributor_id", ""),
                "address": address,
                "weight": float(contrib.get("weight", 0)),
                "trace_count": int(contrib.get("trace_count", 0))
            })
        
        # Normalize weights
        total_weight = sum(c["weight"] for c in validated)
        if total_weight > 0:
            for contrib in validated:
                contrib["weight"] = contrib["weight"] / total_weight
        
        return validated
    
    def _generate_hash(self, attestation: OptimizationAttestation) -> str:
        """Generate hash for attestation.
        
        Args:
            attestation: Attestation object
            
        Returns:
            Hash string
        """
        # Create deterministic representation
        data = {
            "attestation_id": attestation.attestation_id,
            "model_id": attestation.model_id,
            "baseline_version": attestation.baseline_version,
            "optimized_version": attestation.optimized_version,
            "deltaone_achieved": attestation.deltaone_achieved,
            "performance_delta": attestation.performance_delta,
            "baseline_metrics": attestation.baseline_metrics,
            "optimized_metrics": attestation.optimized_metrics,
            "trace_count": attestation.trace_count,
            "contributors": [
                {
                    "address": c["address"],
                    "weight": c["weight"]
                }
                for c in attestation.contributors
            ]
        }
        
        # Generate hash
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()