"""Data models for evaluation queue jobs."""
# ruff: noqa: ANN101, ANN102

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvaluationJobStatus(Enum):
    """Lifecycle states for evaluation jobs."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class EvaluationJobPriority(Enum):
    """Priority constants for evaluation jobs."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


@dataclass
class EvaluationJob:
    """Serializable evaluation job payload stored in Redis."""

    model_id: str
    eval_config: dict[str, Any]
    priority: int = EvaluationJobPriority.NORMAL.value
    status: EvaluationJobStatus = EvaluationJobStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # noqa: A003
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    timeout_seconds: int = 1800
    result: dict[str, Any] | None = None
    error_message: str | None = None
    next_retry_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the job into a JSON-safe dictionary."""
        return {
            "id": self.id,
            "model_id": self.model_id,
            "eval_config": self.eval_config,
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "timeout_seconds": self.timeout_seconds,
            "result": self.result,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
        }

    def to_redis_hash(self, queue_score: float) -> dict[str, str]:
        """Convert the job into Redis hash fields."""
        payload = self.to_dict()
        payload["queue_score"] = queue_score
        return {
            "id": payload["id"],
            "model_id": payload["model_id"],
            "eval_config": json.dumps(payload["eval_config"], sort_keys=True),
            "priority": str(payload["priority"]),
            "status": payload["status"],
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
            "started_at": payload["started_at"] or "",
            "completed_at": payload["completed_at"] or "",
            "attempt_count": str(payload["attempt_count"]),
            "max_attempts": str(payload["max_attempts"]),
            "timeout_seconds": str(payload["timeout_seconds"]),
            "result": json.dumps(payload["result"], sort_keys=True) if payload["result"] else "",
            "error_message": payload["error_message"] or "",
            "metadata": json.dumps(payload["metadata"], sort_keys=True),
            "next_retry_at": payload["next_retry_at"] or "",
            "queue_score": str(payload["queue_score"]),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationJob:
        """Create a job object from dictionary payload."""
        return cls(
            id=data["id"],
            model_id=data["model_id"],
            eval_config=data.get("eval_config") or {},
            priority=int(data.get("priority", EvaluationJobPriority.NORMAL.value)),
            status=EvaluationJobStatus(data.get("status", EvaluationJobStatus.PENDING.value)),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            attempt_count=int(data.get("attempt_count", 0)),
            max_attempts=int(data.get("max_attempts", 3)),
            timeout_seconds=int(data.get("timeout_seconds", 1800)),
            result=data.get("result"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata") or {},
            next_retry_at=(
                datetime.fromisoformat(data["next_retry_at"]) if data.get("next_retry_at") else None
            ),
        )

    @classmethod
    def from_redis_hash(cls, mapping: dict[Any, Any]) -> EvaluationJob:
        """Create a job object from Redis hash mapping."""
        normalized = {k.decode() if isinstance(k, bytes) else k: v for k, v in mapping.items()}
        parsed = {
            key: value.decode() if isinstance(value, bytes) else value
            for key, value in normalized.items()
        }
        payload: dict[str, Any] = {
            "id": parsed["id"],
            "model_id": parsed["model_id"],
            "eval_config": json.loads(parsed["eval_config"]) if parsed.get("eval_config") else {},
            "priority": int(parsed.get("priority", EvaluationJobPriority.NORMAL.value)),
            "status": parsed.get("status", EvaluationJobStatus.PENDING.value),
            "created_at": parsed["created_at"],
            "updated_at": parsed["updated_at"],
            "started_at": parsed.get("started_at") or None,
            "completed_at": parsed.get("completed_at") or None,
            "attempt_count": int(parsed.get("attempt_count", 0)),
            "max_attempts": int(parsed.get("max_attempts", 3)),
            "timeout_seconds": int(parsed.get("timeout_seconds", 1800)),
            "result": json.loads(parsed["result"]) if parsed.get("result") else None,
            "error_message": parsed.get("error_message") or None,
            "metadata": json.loads(parsed["metadata"]) if parsed.get("metadata") else {},
            "next_retry_at": parsed.get("next_retry_at") or None,
        }
        return cls.from_dict(payload)
