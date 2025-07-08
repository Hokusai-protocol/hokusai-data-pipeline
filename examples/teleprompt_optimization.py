"""Example implementation of Teleprompt Fine-tuning Pipeline.

This example demonstrates how to use the teleprompt fine-tuning pipeline
to optimize DSPy programs based on usage logs and generate attestations
for DeltaOne achievements.
"""

import json
from datetime import datetime, timedelta

from src.dspy_signatures import DraftText, EmailDraft
from src.services.optimization_attestation import OptimizationAttestationService
from src.services.teleprompt_finetuner import (
    OptimizationConfig,
    OptimizationStrategy,
    TelepromptFinetuner,
)


def run_basic_optimization() -> None:
    """Run basic teleprompt optimization example."""
    print("=== Basic Teleprompt Optimization ===\n")

    # Configure optimization
    config = OptimizationConfig(
        strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT,
        min_traces=100,  # Lower for demo
        optimization_rounds=2,
        deltaone_threshold=0.01  # 1% improvement threshold
    )

    # Create finetuner
    finetuner = TelepromptFinetuner(config)

    # Use EmailDraft signature as example
    program = EmailDraft()

    # Run optimization (using last 7 days of traces)
    print("Running optimization...")
    result = finetuner.run_optimization(
        program=program,
        start_date=datetime.now() - timedelta(days=7),
        end_date=datetime.now(),
        outcome_metric="reply_rate"
    )

    if result.success:
        print(f"✓ Optimization successful!")
        print(f"  - Traces used: {result.trace_count}")
        print(f"  - Optimization time: {result.optimization_time:.2f}s")
        print(f"  - Strategy: {result.strategy}")
        print(f"  - Contributors: {len(result.contributors)}")
    else:
        print(f"✗ Optimization failed: {result.error_message}")
        return

    # Evaluate DeltaOne
    print("\nEvaluating DeltaOne improvement...")
    deltaone_result = finetuner.evaluate_deltaone(result)

    print(f"  - Performance delta: {deltaone_result['delta']:.2%}")
    print(f"  - DeltaOne achieved: {deltaone_result['deltaone_achieved']}")

    if deltaone_result["deltaone_achieved"]:
        print("\n🎉 DeltaOne threshold reached! Generating attestation...")

        # Generate attestation
        attestation = finetuner.generate_attestation(result, deltaone_result)

        print("\nAttestation Summary:")
        print(f"  - ID: {attestation['attestation_hash'][:16]}...")
        print(f"  - Model: {attestation['model_info']['optimized_version']}")
        print(f"  - Improvement: {attestation['performance']['performance_delta']:.2%}")
        print(f"  - Contributors: {len(attestation['contributors'])}")

        # Save optimized model
        print("\nSaving optimized model to MLflow...")
        model_info = finetuner.save_optimized_model(
            result,
            model_name="EmailDraft-Optimized",
            tags={"deltaone": "true"}
        )
        print(f"  - Model saved: {model_info['model_name']} v{model_info['version']}")


def run_scheduled_optimization() -> None:
    """Example of scheduled optimization pipeline."""
    print("\n=== Scheduled Optimization Pipeline ===\n")

    # Configuration for production use
    config = OptimizationConfig(
        strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT_RANDOM,
        min_traces=5000,
        max_traces=50000,
        min_quality_score=0.8,
        optimization_rounds=5,
        num_candidates=20,
        enable_deltaone_check=True
    )

    # Programs to optimize
    programs = [
        ("EmailDraft", EmailDraft(), "reply_rate"),
        ("ContentDraft", DraftText(), "engagement_score")
    ]

    # Attestation service
    attestation_service = OptimizationAttestationService()

    # Run optimization for each program
    for program_name, program, metric in programs:
        print(f"\nOptimizing {program_name}...")

        finetuner = TelepromptFinetuner(config)

        # Run optimization
        result = finetuner.run_optimization(
            program=program,
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now(),
            outcome_metric=metric
        )

        if not result.success:
            print(f"  ✗ Failed: {result.error_message}")
            continue

        print(f"  ✓ Optimized using {result.trace_count} traces")

        # Check DeltaOne
        deltaone_result = finetuner.evaluate_deltaone(result)
        print(f"  - Delta: {deltaone_result['delta']:.2%}")

        if deltaone_result["deltaone_achieved"]:
            # Create attestation through service
            attestation = attestation_service.create_attestation(
                model_info={
                    "model_id": program_name,
                    "baseline_version": "1.0.0",
                    "optimized_version": result.model_version,
                    "optimization_strategy": result.strategy
                },
                performance_data=deltaone_result,
                optimization_metadata={
                    "trace_count": result.trace_count,
                    "optimization_time": result.optimization_time,
                    "outcome_metric": metric,
                    "date_range": result.metadata.get("date_range", {})
                },
                contributors=[
                    {
                        "contributor_id": cid,
                        "address": info["address"],
                        "weight": info["weight"],
                        "trace_count": info["trace_count"]
                    }
                    for cid, info in result.contributors.items()
                ]
            )

            print(f"  ✓ Attestation created: {attestation.attestation_id}")

            # Calculate rewards
            rewards = attestation_service.calculate_rewards(
                attestation,
                total_reward=1000.0  # Example reward amount
            )

            print(f"  - Reward distribution:")
            for address, amount in list(rewards.items())[:3]:
                print(f"    {address[:10]}...: {amount:.2f}")


def demonstrate_contributor_attribution() -> None:
    """Demonstrate contributor attribution in optimization."""
    print("\n=== Contributor Attribution Example ===\n")

    # Simulate optimization result with multiple contributors
    from src.services.teleprompt_finetuner import OptimizationResult

    result = OptimizationResult(
        success=True,
        optimized_program=EmailDraft(),
        baseline_program=EmailDraft(),
        trace_count=10000,
        optimization_time=120.0,
        strategy="bootstrap_fewshot",
        contributors={
            "alice": {
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
                "weight": 0.45,
                "trace_count": 4500,
                "avg_score": 0.92
            },
            "bob": {
                "address": "0x5aAeb6053f3E94C9b9A09f33669435E7Ef1BeAed",
                "weight": 0.35,
                "trace_count": 3500,
                "avg_score": 0.88
            },
            "charlie": {
                "address": "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
                "weight": 0.20,
                "trace_count": 2000,
                "avg_score": 0.85
            }
        }
    )

    print("Contributors to optimization:")
    print(f"{'Contributor':<12} {'Address':<20} {'Weight':<8} {'Traces':<8} {'Avg Score'}")
    print("-" * 70)

    for contrib_id, info in result.contributors.items():
        print(
            f"{contrib_id:<12} "
            f"{info['address'][:16]}... "
            f"{info['weight']:<8.2%} "
            f"{info['trace_count']:<8} "
            f"{info['avg_score']:.3f}"
        )

    # Show reward calculation
    print("\nReward calculation (1000 tokens total):")
    total_reward = 1000

    for contrib_id, info in result.contributors.items():
        reward = total_reward * info["weight"]
        print(f"  {contrib_id}: {reward:.2f} tokens ({info['weight']:.1%})")


def show_attestation_verification() -> None:
    """Demonstrate attestation verification process."""
    print("\n=== Attestation Verification ===\n")

    attestation_service = OptimizationAttestationService()

    # Create example attestation
    attestation = attestation_service.create_attestation(
        model_info={
            "model_id": "EmailDraft",
            "baseline_version": "1.0.0",
            "optimized_version": "1.0.0-opt-bfs-20240115120000",
            "optimization_strategy": "bootstrap_fewshot"
        },
        performance_data={
            "deltaone_achieved": True,
            "delta": 0.023,  # 2.3% improvement
            "baseline_metrics": {"reply_rate": 0.134, "click_rate": 0.089},
            "optimized_metrics": {"reply_rate": 0.157, "click_rate": 0.095}
        },
        optimization_metadata={
            "trace_count": 15000,
            "optimization_time": 180.5,
            "outcome_metric": "reply_rate",
            "date_range": {
                "start": "2024-01-01T00:00:00",
                "end": "2024-01-15T00:00:00"
            }
        },
        contributors=[
            {
                "contributor_id": "contrib_001",
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
                "weight": 0.7,
                "trace_count": 10500
            },
            {
                "contributor_id": "contrib_002",
                "address": "0x5aAeb6053f3E94C9b9A09f33669435E7Ef1BeAed",
                "weight": 0.3,
                "trace_count": 4500
            }
        ]
    )

    print("Attestation created:")
    print(f"  ID: {attestation.attestation_id}")
    print(f"  Hash: {attestation.attestation_hash[:32]}...")

    # Verify attestation
    is_valid = attestation_service.verify_attestation(attestation)
    print(f"\nVerification: {'✓ VALID' if is_valid else '✗ INVALID'}")

    # Prepare for blockchain
    print("\nBlockchain representation:")
    blockchain_data = attestation_service.prepare_for_blockchain(attestation)
    print(json.dumps(blockchain_data, indent=2))


if __name__ == "__main__":
    print("Teleprompt Fine-tuning Pipeline Examples")
    print("=" * 50)

    # Note: These examples assume MLflow is running and traces are available
    # In a real scenario, you would need actual trace data

    try:
        # Basic optimization
        run_basic_optimization()

        # Scheduled pipeline
        run_scheduled_optimization()

        # Contributor attribution
        demonstrate_contributor_attribution()

        # Attestation verification
        show_attestation_verification()

    except Exception as e:
        print(f"\nError in example: {e}")
        print("\nNote: These examples require:")
        print("  - MLflow tracking server running")
        print("  - DSPy traces logged to MLflow")
        print("  - Sufficient trace data for optimization")
