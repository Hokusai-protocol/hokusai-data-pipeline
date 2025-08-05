"""Event schemas for Hokusai ML Platform."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from ..utils.schema_validator import validate_json_schema


@dataclass
class ModelReadyToDeployMessage:
    """Message schema for model_ready_to_deploy events.
    
    This message is emitted when a model passes all baseline validations
    and is ready for token deployment.
    """
    
    # Required fields
    model_id: str              # Unique model identifier
    token_symbol: str          # Token symbol (e.g., "msg-ai")
    metric_name: str           # Performance metric name (e.g., "reply_rate")
    baseline_value: float      # Baseline performance value
    current_value: float       # Current model's performance value
    
    # Model metadata
    model_name: str            # Registered model name in MLflow
    model_version: str         # Model version
    mlflow_run_id: str         # MLflow run ID
    
    # Optional metadata
    improvement_percentage: Optional[float] = None
    contributor_address: Optional[str] = None
    experiment_name: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    
    # System fields (auto-populated)
    timestamp: Optional[datetime] = None
    message_version: str = "1.0"
    
    def __post_init__(self):
        """Post-initialization validation and calculations."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
            
        # Calculate improvement percentage if not provided
        if self.improvement_percentage is None and self.baseline_value > 0:
            improvement = self.current_value - self.baseline_value
            self.improvement_percentage = (improvement / self.baseline_value) * 100
            
        # Validate required fields
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.token_symbol:
            raise ValueError("token_symbol is required")
        if not isinstance(self.baseline_value, (int, float)):
            raise ValueError("baseline_value must be numeric")
        if not isinstance(self.current_value, (int, float)):
            raise ValueError("current_value must be numeric")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelReadyToDeployMessage":
        """Create instance from dictionary."""
        # Convert timestamp string back to datetime if present
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
    
    def validate(self) -> bool:
        """Validate message against schema."""
        schema = {
            "type": "object",
            "required": [
                "model_id", "token_symbol", "metric_name", 
                "baseline_value", "current_value", "model_name", 
                "model_version", "mlflow_run_id"
            ],
            "properties": {
                "model_id": {"type": "string", "minLength": 1},
                "token_symbol": {
                    "type": "string", 
                    "pattern": "^[a-z0-9-]+$",
                    "minLength": 1,
                    "maxLength": 64
                },
                "metric_name": {"type": "string", "minLength": 1},
                "baseline_value": {"type": "number"},
                "current_value": {"type": "number"},
                "model_name": {"type": "string", "minLength": 1},
                "model_version": {"type": "string", "minLength": 1},
                "mlflow_run_id": {"type": "string", "minLength": 1},
                "improvement_percentage": {"type": ["number", "null"]},
                "contributor_address": {
                    "type": ["string", "null"],
                    "pattern": "^0x[a-fA-F0-9]{40}$"
                },
                "experiment_name": {"type": ["string", "null"]},
                "tags": {
                    "type": ["object", "null"],
                    "additionalProperties": {"type": "string"}
                },
                "timestamp": {"type": "string", "format": "date-time"},
                "message_version": {"type": "string"}
            }
        }
        
        try:
            validate_json_schema(self.to_dict(), schema)
            return True
        except Exception:
            return False


@dataclass
class MessageEnvelope:
    """Generic envelope for all messages in the queue."""
    
    message_id: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    
    def to_json(self) -> str:
        """Convert to JSON for queue storage."""
        data = {
            "message_id": self.message_id,
            "message_type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "MessageEnvelope":
        """Create from JSON string."""
        data = json.loads(json_str)
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
    
    def should_retry(self) -> bool:
        """Check if message should be retried."""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> None:
        """Increment retry count."""
        self.retry_count += 1