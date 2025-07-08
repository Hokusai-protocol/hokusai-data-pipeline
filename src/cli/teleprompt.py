"""CLI commands for Teleprompt fine-tuning pipeline."""

import click
import json
from datetime import datetime, timedelta
from typing import Optional

from src.services.teleprompt_finetuner import (
    TelepromptFinetuner,
    OptimizationConfig,
    OptimizationStrategy
)
from src.services.optimization_attestation import OptimizationAttestationService
from src.services.dspy_model_loader import DSPyModelLoader


@click.group()
def teleprompt():
    """Manage teleprompt fine-tuning pipeline."""
    pass


@teleprompt.command()
@click.option("--program", "-p", required=True, help="DSPy program name or path")
@click.option("--strategy", "-s",
              type=click.Choice(["bootstrap_fewshot", "bootstrap_fewshot_random"]),
              default="bootstrap_fewshot",
              help="Optimization strategy")
@click.option("--days", "-d", type=int, default=7, help="Days of traces to use")
@click.option("--min-traces", type=int, default=1000, help="Minimum traces required")
@click.option("--outcome-metric", "-m", default="outcome_score", help="Outcome metric to optimize")
@click.option("--deltaone-threshold", type=float, default=0.01, help="DeltaOne threshold (default 1%)")
@click.option("--save-model", is_flag=True, help="Save optimized model to MLflow")
@click.option("--model-name", help="Name for saved model")
def optimize(program: str, strategy: str, days: int, min_traces: int,
             outcome_metric: str, deltaone_threshold: float, save_model: bool,
             model_name: Optional[str]):
    """Run teleprompt optimization on a DSPy program."""
    click.echo(f"Starting teleprompt optimization for {program}")

    # Load program
    loader = DSPyModelLoader()
    try:
        if program.endswith(".yaml"):
            dspy_program = loader.load_from_config(program)
        else:
            # Try to load from signature library
            dspy_program = loader.load_signature_from_library(program)
    except Exception as e:
        click.echo(f"Error loading program: {e}", err=True)
        return

    # Configure optimization
    config = OptimizationConfig(
        strategy=OptimizationStrategy(strategy),
        min_traces=min_traces,
        deltaone_threshold=deltaone_threshold
    )

    # Run optimization
    finetuner = TelepromptFinetuner(config)
    result = finetuner.run_optimization(
        program=dspy_program,
        start_date=datetime.now() - timedelta(days=days),
        end_date=datetime.now(),
        outcome_metric=outcome_metric
    )

    if not result.success:
        click.echo(f"Optimization failed: {result.error_message}", err=True)
        return

    click.echo("✓ Optimization successful!")
    click.echo(f"  Traces used: {result.trace_count}")
    click.echo(f"  Time: {result.optimization_time:.2f}s")
    click.echo(f"  Contributors: {len(result.contributors)}")

    # Evaluate DeltaOne
    click.echo("\nEvaluating DeltaOne...")
    deltaone = finetuner.evaluate_deltaone(result)

    click.echo(f"  Performance delta: {deltaone['delta']:.2%}")
    click.echo(f"  DeltaOne achieved: {deltaone['deltaone_achieved']}")

    if deltaone["deltaone_achieved"]:
        click.echo("\n🎉 DeltaOne threshold reached!")

        # Generate attestation
        attestation = finetuner.generate_attestation(result, deltaone)
        click.echo(f"  Attestation ID: {attestation['attestation_hash'][:16]}...")

        # Save model if requested
        if save_model:
            if not model_name:
                model_name = f"{program}-Optimized"

            model_info = finetuner.save_optimized_model(
                result,
                model_name=model_name,
                tags={"deltaone": "true", "cli_optimized": "true"}
            )
            click.echo(f"  Model saved: {model_info['model_name']} v{model_info['version']}")


@teleprompt.command()
@click.option("--start-date", "-s", type=click.DateTime(),
              default=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
              help="Start date for trace collection")
@click.option("--end-date", "-e", type=click.DateTime(),
              default=datetime.now().strftime("%Y-%m-%d"),
              help="End date for trace collection")
@click.option("--program", "-p", help="Filter by program name")
@click.option("--min-score", type=float, default=0.0, help="Minimum outcome score")
@click.option("--limit", type=int, default=1000, help="Maximum traces to show")
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
def list_traces(start_date, end_date, program, min_score, limit, format):
    """List available traces for optimization."""
    from src.services.trace_loader import TraceLoader

    loader = TraceLoader()
    traces = loader.load_traces(
        program_name=program,
        start_date=start_date,
        end_date=end_date,
        min_score=min_score,
        limit=limit
    )

    click.echo(f"Found {len(traces)} traces")

    if format == "json":
        click.echo(json.dumps(traces[:10], indent=2))
    else:
        if traces:
            # Show summary table
            click.echo("\nTrace Summary:")
            click.echo(f"{'Program':<20} {'Date':<20} {'Score':<10} {'Contributor':<15}")
            click.echo("-" * 70)

            for trace in traces[:10]:
                program = trace.get("program_name", "unknown")[:20]
                date = trace.get("timestamp", datetime.now()).strftime("%Y-%m-%d %H:%M")
                score = trace.get("outcome_score", 0.0)
                contrib = trace.get("contributor_id", "unknown")[:15]

                click.echo(f"{program:<20} {date:<20} {score:<10.3f} {contrib:<15}")

            if len(traces) > 10:
                click.echo(f"\n... and {len(traces) - 10} more traces")


@teleprompt.command()
@click.option("--model-id", "-m", help="Model ID to list attestations for")
@click.option("--contributor", "-c", help="Contributor address")
@click.option("--deltaone-only", is_flag=True, default=True, help="Only show DeltaOne achievements")
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
def list_attestations(model_id, contributor, deltaone_only, format):
    """List optimization attestations."""
    service = OptimizationAttestationService()
    attestations = service.list_attestations(
        model_id=model_id,
        contributor_address=contributor,
        deltaone_only=deltaone_only
    )

    click.echo(f"Found {len(attestations)} attestations")

    if format == "json":
        data = [att.to_dict() for att in attestations]
        click.echo(json.dumps(data, indent=2))
    else:
        if attestations:
            click.echo("\nAttestations:")
            click.echo(f"{'ID':<16} {'Model':<20} {'Delta':<10} {'Traces':<10} {'Date':<20}")
            click.echo("-" * 80)

            for att in attestations:
                att_id = att.attestation_id[:16]
                model = att.model_id[:20]
                delta = f"{att.performance_delta:.2%}"
                traces = str(att.trace_count)
                date = att.timestamp[:19]

                click.echo(f"{att_id:<16} {model:<20} {delta:<10} {traces:<10} {date:<20}")


@teleprompt.command()
@click.argument("attestation_id")
@click.option("--format", "-f", type=click.Choice(["summary", "json", "blockchain"]),
              default="summary")
def show_attestation(attestation_id: str, format: str):
    """Show detailed attestation information."""
    service = OptimizationAttestationService()

    # Try to find attestation by partial ID
    attestations = service.list_attestations()
    matching = [a for a in attestations if a.attestation_id.startswith(attestation_id)]

    if not matching:
        click.echo(f"No attestation found matching: {attestation_id}", err=True)
        return

    if len(matching) > 1:
        click.echo(f"Multiple attestations match: {attestation_id}", err=True)
        for att in matching:
            click.echo(f"  - {att.attestation_id}")
        return

    attestation = matching[0]

    if format == "json":
        click.echo(attestation.to_json())
    elif format == "blockchain":
        blockchain_data = service.prepare_for_blockchain(attestation)
        click.echo(json.dumps(blockchain_data, indent=2))
    else:
        # Summary format
        click.echo(f"\nAttestation: {attestation.attestation_id}")
        click.echo("=" * 60)

        click.echo("\nModel Information:")
        click.echo(f"  Model ID: {attestation.model_id}")
        click.echo(f"  Baseline: {attestation.baseline_version}")
        click.echo(f"  Optimized: {attestation.optimized_version}")
        click.echo(f"  Strategy: {attestation.optimization_strategy}")

        click.echo("\nPerformance:")
        click.echo(f"  DeltaOne Achieved: {attestation.deltaone_achieved}")
        click.echo(f"  Performance Delta: {attestation.performance_delta:.2%}")
        click.echo(f"  Baseline Metrics: {attestation.baseline_metrics}")
        click.echo(f"  Optimized Metrics: {attestation.optimized_metrics}")

        click.echo("\nOptimization Details:")
        click.echo(f"  Trace Count: {attestation.trace_count:,}")
        click.echo(f"  Time: {attestation.optimization_time_seconds:.2f}s")
        click.echo(f"  Outcome Metric: {attestation.outcome_metric}")

        click.echo(f"\nContributors ({len(attestation.contributors)}):")
        for contrib in attestation.contributors:
            click.echo(f"  - {contrib['address'][:16]}... ({contrib['weight']:.2%}, {contrib['trace_count']} traces)")

        click.echo("\nVerification:")
        click.echo(f"  Hash: {attestation.attestation_hash[:32]}...")
        click.echo(f"  Valid: {service.verify_attestation(attestation)}")


@teleprompt.command()
@click.argument("attestation_id")
@click.option("--total-reward", "-r", type=float, required=True, help="Total reward amount")
@click.option("--token", "-t", default="HOKU", help="Token symbol")
def calculate_rewards(attestation_id: str, total_reward: float, token: str):
    """Calculate reward distribution for an attestation."""
    service = OptimizationAttestationService()

    # Find attestation
    attestations = service.list_attestations()
    matching = [a for a in attestations if a.attestation_id.startswith(attestation_id)]

    if not matching:
        click.echo(f"No attestation found matching: {attestation_id}", err=True)
        return

    attestation = matching[0]

    if not attestation.deltaone_achieved:
        click.echo("Attestation did not achieve DeltaOne - no rewards", err=True)
        return

    # Calculate rewards
    rewards = service.calculate_rewards(attestation, total_reward)

    click.echo(f"\nReward Distribution ({total_reward} {token}):")
    click.echo("=" * 60)

    total_distributed = 0
    for address, amount in rewards.items():
        # Find contributor info
        contrib = next(
            (c for c in attestation.contributors if c["address"] == address),
            None
        )

        weight = contrib["weight"] if contrib else 0
        traces = contrib["trace_count"] if contrib else 0

        click.echo(f"{address[:16]}...")
        click.echo(f"  Amount: {amount:.6f} {token}")
        click.echo(f"  Weight: {weight:.2%}")
        click.echo(f"  Traces: {traces}")

        total_distributed += amount

    click.echo(f"\nTotal Distributed: {total_distributed:.6f} {token}")

    # Verify total matches
    if abs(total_distributed - total_reward) > 0.000001:
        click.echo("WARNING: Distribution does not match total reward!", err=True)


if __name__ == "__main__":
    teleprompt()
