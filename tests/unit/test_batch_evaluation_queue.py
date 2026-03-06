"""Unit tests for batch evaluation queue with deduplication and debounce."""

from __future__ import annotations

import time
from unittest.mock import patch

import fakeredis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.models.evaluation_job import EvaluationJob
from src.services.evaluation_queue import EvaluationQueueConfig, EvaluationQueueManager


class TestEnqueueWithDedup:
    """Tests for enqueue_with_dedup debounce/dedup behavior."""

    def setup_method(self) -> None:
        self.redis = fakeredis.FakeRedis()
        self.config = EvaluationQueueConfig(
            max_concurrent_per_model=5,
            max_concurrent_global=20,
        )
        self.queue = EvaluationQueueManager(redis_client=self.redis, config=self.config)

    def test_first_enqueue_creates_job_and_sets_debounce_key(self) -> None:
        job_id = self.queue.enqueue_with_dedup("model-123", trigger_source="data_arrival")
        assert job_id is not None

        # Debounce key should exist in Redis
        assert self.redis.exists(self.queue._debounce_key("model-123"))

        # Job should be in queue
        job = self.queue.get_status(job_id)
        assert job is not None
        assert job.model_id == "model-123"
        assert job.trigger_source == "data_arrival"

    def test_duplicate_enqueue_within_debounce_window_returns_none(self) -> None:
        job_id_1 = self.queue.enqueue_with_dedup("model-123")
        assert job_id_1 is not None

        job_id_2 = self.queue.enqueue_with_dedup("model-123")
        assert job_id_2 is None

        # Only one job in queue
        assert self.queue.get_queue_depth("model-123") == 1

    def test_different_model_ids_enqueue_independently(self) -> None:
        job_a = self.queue.enqueue_with_dedup("model-A")
        job_b = self.queue.enqueue_with_dedup("model-B")
        assert job_a is not None
        assert job_b is not None

    def test_enqueue_after_debounce_expires_creates_new_job(self) -> None:
        self.queue._debounce_window = 1  # 1 second for testing
        job_id_1 = self.queue.enqueue_with_dedup("model-123")
        assert job_id_1 is not None

        # Wait for debounce to expire
        time.sleep(1.1)

        job_id_2 = self.queue.enqueue_with_dedup("model-123")
        assert job_id_2 is not None
        assert job_id_1 != job_id_2

    def test_debounce_key_has_correct_ttl(self) -> None:
        self.queue._debounce_window = 300
        self.queue.enqueue_with_dedup("model-123")

        ttl = self.redis.ttl(self.queue._debounce_key("model-123"))
        assert 295 <= ttl <= 300

    def test_empty_model_id_raises_value_error(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="model_id is required"):
            self.queue.enqueue_with_dedup("")

    def test_debounce_window_zero_disables_dedup(self) -> None:
        self.queue._debounce_window = 0
        job_id_1 = self.queue.enqueue_with_dedup("model-123")
        job_id_2 = self.queue.enqueue_with_dedup("model-123")
        assert job_id_1 is not None
        assert job_id_2 is not None


class TestRegularEnqueueBypassesDedup:
    """Regular enqueue should not be affected by debounce keys."""

    def setup_method(self) -> None:
        self.redis = fakeredis.FakeRedis()
        self.config = EvaluationQueueConfig()
        self.queue = EvaluationQueueManager(redis_client=self.redis, config=self.config)

    def test_regular_enqueue_works_despite_active_debounce(self) -> None:
        # Set debounce via dedup enqueue
        self.queue.enqueue_with_dedup("model-123")

        # Regular enqueue should still work
        job = EvaluationJob(
            model_id="model-123",
            eval_config={"suite": "manual"},
            trigger_source="manual",
        )
        job_id = self.queue.enqueue(job)
        assert job_id is not None
        assert self.queue.get_queue_depth("model-123") == 2


class TestBatchEnqueueDataArrivals:
    """Tests for batch_enqueue_data_arrivals."""

    def setup_method(self) -> None:
        self.redis = fakeredis.FakeRedis()
        self.config = EvaluationQueueConfig()
        self.queue = EvaluationQueueManager(redis_client=self.redis, config=self.config)

    def test_batch_deduplicates_within_single_call(self) -> None:
        result = self.queue.batch_enqueue_data_arrivals(
            ["model-A", "model-B", "model-A", "model-C", "model-B"]
        )
        assert len(result) == 3
        assert result["model-A"] is not None
        assert result["model-B"] is not None
        assert result["model-C"] is not None

    def test_batch_empty_list_returns_empty(self) -> None:
        result = self.queue.batch_enqueue_data_arrivals([])
        assert result == {}

    def test_batch_all_same_model_enqueues_once(self) -> None:
        result = self.queue.batch_enqueue_data_arrivals(["model-A", "model-A", "model-A"])
        assert len(result) == 1
        assert result["model-A"] is not None
        assert self.queue.get_queue_depth("model-A") == 1

    def test_batch_with_existing_debounce_skips_debounced_model(self) -> None:
        # Pre-debounce model-A
        self.queue.enqueue_with_dedup("model-A")

        result = self.queue.batch_enqueue_data_arrivals(["model-A", "model-B"])
        assert result["model-A"] is None
        assert result["model-B"] is not None


class TestInMemoryDebounceFallback:
    """Tests for in-memory fallback when Redis is unavailable for debounce ops."""

    def setup_method(self) -> None:
        self.redis = fakeredis.FakeRedis()
        self.config = EvaluationQueueConfig()
        self.queue = EvaluationQueueManager(redis_client=self.redis, config=self.config)

    def test_fallback_debounce_works_when_redis_exists_fails(self) -> None:
        # First enqueue succeeds normally and sets in-memory fallback
        self.queue.enqueue_with_dedup("model-123")

        # Simulate Redis failure on exists check
        original_exists = self.redis.exists

        def failing_exists(*args, **kwargs):
            raise RedisConnectionError("connection lost")

        self.redis.exists = failing_exists

        # Should fall back to in-memory and detect debounce
        result = self.queue.enqueue_with_dedup("model-123")
        assert result is None

        self.redis.exists = original_exists

    def test_stale_entries_cleaned_on_fallback_check(self) -> None:
        self.queue._debounce_window = 1
        # Manually add stale entry
        self.queue._memory_debounce["stale-model"] = time.time() - 10

        # Trigger cleanup via a Redis-failing check
        original_exists = self.redis.exists

        def failing_exists(*args, **kwargs):
            raise RedisConnectionError("connection lost")

        self.redis.exists = failing_exists

        self.queue._is_debounced("new-model")
        assert "stale-model" not in self.queue._memory_debounce

        self.redis.exists = original_exists


class TestDebounceWindowConfig:
    """Tests for configurable debounce window."""

    def test_custom_debounce_from_env(self) -> None:
        redis_client = fakeredis.FakeRedis()
        with patch.dict("os.environ", {"EVALUATION_DEBOUNCE_WINDOW_SECONDS": "60"}):
            queue = EvaluationQueueManager(redis_client=redis_client)
        assert queue._debounce_window == 60

    def test_default_debounce_window(self) -> None:
        redis_client = fakeredis.FakeRedis()
        with patch.dict("os.environ", {}, clear=True):
            queue = EvaluationQueueManager(redis_client=redis_client)
        assert queue._debounce_window == 300

    def test_negative_debounce_treated_as_zero(self) -> None:
        redis_client = fakeredis.FakeRedis()
        with patch.dict("os.environ", {"EVALUATION_DEBOUNCE_WINDOW_SECONDS": "-5"}):
            queue = EvaluationQueueManager(redis_client=redis_client)
        assert queue._debounce_window == 0
