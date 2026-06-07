from __future__ import annotations

import copy
import json
import re

import pytest
import redis

from src.evaluation.attribution.retraining_attributor import Cohort, RetrainingConfig, attribute
from src.evaluation.event_payload import EventPayloadError, make_idempotency_key
from src.events.publishers.mint_request_publisher import QUEUE_NAME
from src.events.schemas import MintRequest
from tests.integration import _gate3_fixtures as gate3_fixtures
from tests.integration._gate3_fixtures import (
    BASELINE_RUN_ID,
    CANDIDATE_RUN_ID,
    DATASET_HASH,
    MANIFEST_HASH,
    MODEL_ID,
    attribution_report,
    build_orchestrator,
    gate3_spec,
    make_decision,
    report_loader,
    seeded_per_row_frames,
)

fake_redis_client = gate3_fixtures.fake_redis_client
schema_validators = gate3_fixtures.schema_validators


def _queued_mint_requests(fake_redis_client) -> list[MintRequest]:
    return [
        MintRequest.model_validate_json(fake_redis_client.lindex(QUEUE_NAME, index))
        for index in range(fake_redis_client.llen(QUEUE_NAME))
    ]


def _weight_map(report: dict[str, object]) -> dict[str, int]:
    contributors = report["contributors"]
    assert isinstance(contributors, list)
    return {item["wallet"]: item["weight_bps"] for item in contributors}


def _loco_eval_fn(handle: dict[str, object], _eval_seed: int) -> float:
    ids = handle["ids"]
    score = 0.0
    if "A" in ids:
        score += 0.4
    if "B" in ids:
        score += 0.3
    if "C" in ids:
        score += 0.2
    return score


def _tmc_eval_fn(handle: dict[str, object], _eval_seed: int) -> float:
    ids = handle["ids"]
    return 1.0 if ids == frozenset({"A", "B", "C", "D"}) else 0.0


def _three_cohorts() -> list[Cohort]:
    return [
        Cohort("A", "0x0000000000000000000000000000000000000001", ("sub-a",), 1),
        Cohort("B", "0x0000000000000000000000000000000000000002", ("sub-b",), 1),
        Cohort("C", "0x0000000000000000000000000000000000000003", ("sub-c",), 1),
    ]


def _four_cohorts() -> list[Cohort]:
    return _three_cohorts() + [
        Cohort("D", "0x0000000000000000000000000000000000000004", ("sub-d",), 1)
    ]


def test_attribution_report_validates(schema_validators) -> None:
    report = attribution_report(seeded_per_row_frames())

    schema_validators["attribution_report"].validate(report)
    assert report["method"] == "neighbor_provenance"
    assert report["rows_improved"] == 3


class TestHappyPath:
    def test_primary_path_publishes_and_advances_score(
        self, fake_redis_client, monkeypatch, schema_validators
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(report)
        orchestrator, client, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )

        pre_tags = dict(client.tags_for(CANDIDATE_RUN_ID))
        outcome = orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)
        queued = _queued_mint_requests(fake_redis_client)

        schema_validators["attribution_report"].validate(report)
        assert report["method"] == "neighbor_provenance"
        assert report["rows_improved"] == 3
        assert sum(item["weight_bps"] for item in report["contributors"]) == 10000
        assert outcome.status == "success"
        assert outcome.canonical_score_advanced is True
        assert len(queued) == 1
        schema_validators["mint_request"].validate(queued[0].model_dump(by_alias=True))
        assert queued[0].idempotency_key == make_idempotency_key(
            int(spec["model_id_uint"]), queued[0].attestation_hash
        )
        assert "hokusai.canonical_score" not in pre_tags
        assert client.tags_for(CANDIDATE_RUN_ID)["hokusai.canonical_score"] == "0.87"


class TestAttestationCoversAttribution:
    def test_reproducible_and_sensitive_to_attribution_report(
        self, fake_redis_client, monkeypatch
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(report)

        orchestrator_1, _, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )
        outcome_1 = orchestrator_1.process_evaluation_with_spec(
            CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec
        )
        first_hash = outcome_1.attestation_hash

        fake_redis_replay = type(fake_redis_client)(decode_responses=True)
        orchestrator_2, _, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_replay,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )
        outcome_2 = orchestrator_2.process_evaluation_with_spec(
            CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec
        )
        assert first_hash == outcome_2.attestation_hash

        mutated_report = copy.deepcopy(report)
        mutated_report["contributors"][0]["raw_score"] = (
            mutated_report["contributors"][0]["raw_score"] + 0.25
        )
        fake_redis_mutated = type(fake_redis_client)(decode_responses=True)
        orchestrator_3, _, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_mutated,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(mutated_report),
        )
        outcome_3 = orchestrator_3.process_evaluation_with_spec(
            CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec
        )

        assert outcome_3.attestation_hash != first_hash


class TestSeedDeterminism:
    def test_neighbor_provenance_seeded_fixture_is_structurally_deterministic(self) -> None:
        first = attribution_report(seeded_per_row_frames(seed=1729))
        second = attribution_report(seeded_per_row_frames(seed=1729))
        third = attribution_report(seeded_per_row_frames(seed=2024))

        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        assert json.dumps(first, sort_keys=True) != json.dumps(third, sort_keys=True)
        assert _weight_map(first) == _weight_map(third)

    def test_loco_weights_stable_while_tmc_sample_plan_changes_with_seed(self) -> None:
        cohorts = _three_cohorts()
        tmc_cohorts = _four_cohorts()
        stable_1 = attribute(
            cohorts=cohorts,
            train_fn=lambda ids, seed: {"ids": ids, "seed": seed},
            eval_fn=_loco_eval_fn,
            model_id=MODEL_ID,
            baseline_run_id=BASELINE_RUN_ID,
            candidate_run_id=CANDIDATE_RUN_ID,
            created_at="2026-06-05T12:00:00Z",
            dataset_hash=DATASET_HASH,
            manifest_hash=MANIFEST_HASH,
            total_rows_evaluated=3,
            config=RetrainingConfig(rng_seed=42, budget=16, enable_add_one_in=True),
        )
        stable_2 = attribute(
            cohorts=cohorts,
            train_fn=lambda ids, seed: {"ids": ids, "seed": seed},
            eval_fn=_loco_eval_fn,
            model_id=MODEL_ID,
            baseline_run_id=BASELINE_RUN_ID,
            candidate_run_id=CANDIDATE_RUN_ID,
            created_at="2026-06-05T12:00:00Z",
            dataset_hash=DATASET_HASH,
            manifest_hash=MANIFEST_HASH,
            total_rows_evaluated=3,
            config=RetrainingConfig(rng_seed=1729, budget=16, enable_add_one_in=True),
        )
        tmc_1 = attribute(
            cohorts=tmc_cohorts,
            train_fn=lambda ids, seed: {"ids": ids, "seed": seed},
            eval_fn=_tmc_eval_fn,
            model_id=MODEL_ID,
            baseline_run_id=BASELINE_RUN_ID,
            candidate_run_id=CANDIDATE_RUN_ID,
            created_at="2026-06-05T12:00:00Z",
            dataset_hash=DATASET_HASH,
            manifest_hash=MANIFEST_HASH,
            total_rows_evaluated=4,
            config=RetrainingConfig(rng_seed=42, budget=12, enable_add_one_in=False),
        )
        tmc_2 = attribute(
            cohorts=tmc_cohorts,
            train_fn=lambda ids, seed: {"ids": ids, "seed": seed},
            eval_fn=_tmc_eval_fn,
            model_id=MODEL_ID,
            baseline_run_id=BASELINE_RUN_ID,
            candidate_run_id=CANDIDATE_RUN_ID,
            created_at="2026-06-05T12:00:00Z",
            dataset_hash=DATASET_HASH,
            manifest_hash=MANIFEST_HASH,
            total_rows_evaluated=4,
            config=RetrainingConfig(rng_seed=1729, budget=12, enable_add_one_in=False),
        )

        assert _weight_map(stable_1) == _weight_map(stable_2)
        assert tmc_1["method_details"]["sample_plan"] != tmc_2["method_details"]["sample_plan"]
        assert tmc_1["weight_bps_total"] == tmc_2["weight_bps_total"] == 10000


class TestRecoveryIdempotency:
    def test_identical_reruns_reuse_mint_idempotency_key(
        self, fake_redis_client, monkeypatch
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(report)

        orchestrator_1, _, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )
        outcome_1 = orchestrator_1.process_evaluation_with_spec(
            CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec
        )
        first_request = _queued_mint_requests(fake_redis_client)[0]

        replay_redis = type(fake_redis_client)(decode_responses=True)
        orchestrator_2, _, _, _ = build_orchestrator(
            fake_redis_client=replay_redis,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )
        outcome_2 = orchestrator_2.process_evaluation_with_spec(
            CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec
        )
        second_request = _queued_mint_requests(replay_redis)[0]

        expected = make_idempotency_key(int(spec["model_id_uint"]), first_request.attestation_hash)
        print(  # noqa: T201
            "gate3-replay",
            first_request.attestation_hash,
            first_request.idempotency_key,
        )
        assert first_request.idempotency_key == second_request.idempotency_key == expected
        assert outcome_1.attestation_hash == outcome_2.attestation_hash
        assert "sched-" not in expected
        assert "uuid" not in expected
        assert not re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            expected,
        )

        mutated = copy.deepcopy(report)
        mutated["contributors"][0]["raw_score"] = mutated["contributors"][0]["raw_score"] + 1.0
        mutated_redis = type(fake_redis_client)(decode_responses=True)
        orchestrator_3, _, _, _ = build_orchestrator(
            fake_redis_client=mutated_redis,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(mutated),
        )
        orchestrator_3.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)
        third_request = _queued_mint_requests(mutated_redis)[0]

        assert third_request.idempotency_key != first_request.idempotency_key


class TestNoPublishOnReject:
    def test_primary_reject_does_not_publish_or_advance(
        self, fake_redis_client, monkeypatch
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(report)
        orchestrator, client, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            decision=make_decision(accepted=False),
            attribution_report_loader=report_loader(report),
        )

        outcome = orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)

        assert outcome.status == "not_eligible"
        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert client.tags_for(CANDIDATE_RUN_ID).get("hokusai.canonical_score") is None

    def test_guardrail_breach_does_not_publish_or_advance(
        self, fake_redis_client, monkeypatch
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(
            report,
            guardrails=[
                {
                    "name": "safety_violation_rate",
                    "direction": "lower_is_better",
                    "threshold": 0.001,
                    "blocking": True,
                }
            ],
        )
        orchestrator, client, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )

        outcome = orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)

        assert outcome.status == "guardrail_breach"
        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert client.tags_for(CANDIDATE_RUN_ID).get("hokusai.canonical_score") is None

    def test_zero_positive_lift_contributors_abort_before_publish(
        self, fake_redis_client, monkeypatch
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        report["contributors"] = [
            {
                "wallet": report["contributors"][0]["wallet"],
                "submission_ids": ["sub-a-1729"],
                "rows_credited": 1,
                "raw_score": 0.0,
                "weight_bps": 0,
            }
        ]
        spec = gate3_spec(attribution_report(seeded_per_row_frames()))
        orchestrator, client, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )

        with pytest.raises(EventPayloadError, match="contributors"):
            orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)

        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert client.tags_for(CANDIDATE_RUN_ID).get("hokusai.canonical_score") is None


class TestLocoValidationBranch:
    def test_loco_report_validates_while_primary_path_uses_neighbor_provenance(
        self, fake_redis_client, monkeypatch, schema_validators
    ) -> None:
        loco_report = attribute(
            cohorts=_three_cohorts(),
            train_fn=lambda ids, seed: {"ids": ids, "seed": seed},
            eval_fn=_loco_eval_fn,
            model_id=MODEL_ID,
            baseline_run_id=BASELINE_RUN_ID,
            candidate_run_id=CANDIDATE_RUN_ID,
            created_at="2026-06-05T12:00:00Z",
            dataset_hash=DATASET_HASH,
            manifest_hash=MANIFEST_HASH,
            total_rows_evaluated=3,
            config=RetrainingConfig(rng_seed=42, budget=16, enable_add_one_in=True),
        )
        schema_validators["attribution_report"].validate(loco_report)
        assert loco_report["method"] == "loco_shapley"

        neighbor_report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(neighbor_report)
        orchestrator, _, _, _ = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(neighbor_report),
        )
        outcome = orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)

        assert outcome.status == "success"
        assert neighbor_report["method"] == "neighbor_provenance"
        queued_request = _queued_mint_requests(fake_redis_client)[0]
        assert queued_request.contributors[0].wallet_address.startswith("0x")


class TestCanonicalScoreOrdering:
    def test_publish_failure_prevents_canonical_score_advance(
        self, fake_redis_client, monkeypatch
    ) -> None:
        report = attribution_report(seeded_per_row_frames())
        spec = gate3_spec(report)
        orchestrator, client, _, publisher = build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            spec=spec,
            attribution_report_loader=report_loader(report),
        )

        original_publish = publisher.publish

        def fail_publish(_message):
            raise redis.RedisError("boom")

        monkeypatch.setattr(publisher, "publish", fail_publish)
        with pytest.raises(redis.RedisError):
            orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)

        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert client.tags_for(CANDIDATE_RUN_ID).get("hokusai.canonical_score") is None

        monkeypatch.setattr(publisher, "publish", original_publish)
        outcome = orchestrator.process_evaluation_with_spec(CANDIDATE_RUN_ID, BASELINE_RUN_ID, spec)

        assert outcome.status == "success"
        assert fake_redis_client.llen(QUEUE_NAME) == 1
        assert client.tags_for(CANDIDATE_RUN_ID)["hokusai.canonical_score"] == "0.87"
