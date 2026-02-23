"""Score transition audit trail storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from redis import Redis


class ScoreHistoryAudit:
    """Stores canonical score transitions keyed by model id."""

    def __init__(
        self: ScoreHistoryAudit, redis_client: Redis, key_prefix: str = "score:history"
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    def record_transition(
        self: ScoreHistoryAudit,
        *,
        model_id: str,
        attestation_hash: str,
        baseline_run_id: str,
        run_id: str,
        delta_percentage_points: float,
        decision_reason: str,
    ) -> None:
        """Persist one score transition linked to an attestation hash."""
        current = self._read_current_score(model_id)
        next_score = current + delta_percentage_points
        timestamp = datetime.now(timezone.utc).isoformat()

        payload = {
            "model_id": model_id,
            "attestation_hash": attestation_hash,
            "baseline_run_id": baseline_run_id,
            "run_id": run_id,
            "from_score": current,
            "to_score": next_score,
            "delta_percentage_points": delta_percentage_points,
            "reason": decision_reason,
            "recorded_at": timestamp,
        }

        pipe = self._redis.pipeline(transaction=True)
        pipe.rpush(self._history_key(model_id), json.dumps(payload, sort_keys=True))
        pipe.set(self._score_key(model_id), next_score)
        pipe.execute()

    def list_transitions(self: ScoreHistoryAudit, model_id: str) -> list[dict[str, Any]]:
        rows = self._redis.lrange(self._history_key(model_id), 0, -1)
        return [json.loads(row) for row in rows]

    def _read_current_score(self: ScoreHistoryAudit, model_id: str) -> float:
        value = self._redis.get(self._score_key(model_id))
        if value is None:
            return 0.0
        return float(value)

    def _history_key(self: ScoreHistoryAudit, model_id: str) -> str:
        return f"{self._key_prefix}:{model_id}"

    def _score_key(self: ScoreHistoryAudit, model_id: str) -> str:
        return f"{self._key_prefix}:current:{model_id}"
