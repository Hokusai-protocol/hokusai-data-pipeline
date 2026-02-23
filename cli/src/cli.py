"""Main CLI interface for the Hokusai Data Evaluation Pipeline."""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import click
from comparator import Comparator
from evaluator import Evaluator
from pipeline import Pipeline, PipelineConfig
from status_checker import StatusChecker

# Add repository root to path so repo-level imports under src.* are importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LAZY_SUBCOMMANDS = {
    "auth": (REPO_ROOT / "src/cli/auth.py", "auth_group", "hokusai_lazy_auth"),
    "benchmark": (
        REPO_ROOT / "src/cli/hoku_eval.py",
        "benchmark_group",
        "hokusai_lazy_benchmark",
    ),
    "eval": (REPO_ROOT / "src/cli/hoku_eval.py", "eval_group", "hokusai_lazy_eval"),
    "model": (REPO_ROOT / "src/cli/model.py", "model", "hokusai_lazy_model"),
    "signatures": (
        REPO_ROOT / "src/cli/signatures.py",
        "signatures",
        "hokusai_lazy_signatures",
    ),
    "teleprompt": (
        REPO_ROOT / "src/cli/teleprompt.py",
        "teleprompt",
        "hokusai_lazy_teleprompt",
    ),
}

LAZY_SHORT_HELP = {
    "auth": "Manage API keys and authentication.",
    "benchmark": "Manage benchmark specification bindings.",
    "eval": "Manage evaluation commands.",
    "model": "Model management commands.",
    "signatures": "Manage DSPy signatures in the Hokusai platform.",
    "teleprompt": "Manage teleprompt fine-tuning pipeline.",
}


class LazyGroup(click.Group):
    """Click command group that lazily imports selected subcommands."""

    def list_commands(self: "LazyGroup", ctx: click.Context) -> list[str]:
        commands = set(super().list_commands(ctx))
        commands.update(LAZY_SUBCOMMANDS.keys())
        return sorted(commands)

    def get_command(self: "LazyGroup", ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command

        target = LAZY_SUBCOMMANDS.get(cmd_name)
        if target is None:
            return None

        module_path, attribute, module_name = target
        module = _load_module_from_path(module_name=module_name, module_path=module_path)
        loaded_command: Any = getattr(module, attribute)
        if not isinstance(loaded_command, click.Command):
            raise click.ClickException(
                f"Lazy-loaded command '{cmd_name}' from {module_name}.{attribute} is invalid."
            )

        self.add_command(loaded_command, name=cmd_name)
        return loaded_command

    def format_commands(
        self: "LazyGroup", ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Render command list without importing lazy subcommand modules."""
        rows: list[tuple[str, str]] = []
        for command_name in self.list_commands(ctx):
            loaded = self.commands.get(command_name)
            if loaded is not None:
                help_text = loaded.get_short_help_str(limit=formatter.width - 6)
            else:
                help_text = LAZY_SHORT_HELP.get(command_name, "")
            rows.append((command_name, help_text))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


def _load_module_from_path(*, module_name: str, module_path: Path) -> Any:
    """Load a module from an absolute path, caching by module name."""
    _ensure_repo_src_package()

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"Unable to load module for lazy command: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_repo_src_package() -> None:
    """Ensure `src` resolves to the repository-level package, not cli/src."""
    expected_src_dir = str(REPO_ROOT / "src")
    existing = sys.modules.get("src")
    if existing is not None:
        file_path = str(getattr(existing, "__file__", "") or "")
        path_entries = [str(entry) for entry in (getattr(existing, "__path__", []) or [])]
        if expected_src_dir not in path_entries and not file_path.startswith(expected_src_dir):
            for module_name in list(sys.modules):
                if module_name == "src" or module_name.startswith("src."):
                    del sys.modules[module_name]

    importlib.import_module("src")


@click.group(cls=LazyGroup, invoke_without_command=True)
@click.version_option(version="0.1.0")
def cli() -> None:
    """Hokusai Data Pipeline CLI.

    A command-line interface for running machine learning model evaluations
    with reproducible, attestation-ready outputs.
    """
    pass


@cli.command()
@click.option("--config", required=True, help="Path to configuration YAML file")
def run(config: str) -> None:
    """Run the evaluation pipeline."""
    try:
        pipeline_config = PipelineConfig.from_yaml(config)
        pipeline = Pipeline(pipeline_config)
        results = pipeline.run()

        click.echo("Pipeline completed successfully!")
        click.echo(f"Results: {results}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from e


@cli.command()
@click.option("--model-path", required=True, help="Path to the model to evaluate")
@click.option("--dataset-path", required=True, help="Path to the evaluation dataset")
@click.option("--output-dir", help="Directory to save evaluation results")
def evaluate(model_path: str, dataset_path: str, output_dir: str) -> None:
    """Evaluate a model on a dataset."""
    try:
        evaluator = Evaluator()
        # This is a simplified interface - actual implementation would load model/dataset
        click.echo(f"Evaluating model at {model_path}")
        click.echo(f"Using dataset at {dataset_path}")

        # Placeholder for actual evaluation
        results = evaluator.evaluate(model_path, dataset_path)

        if output_dir:
            click.echo(f"Results saved to {output_dir}")
        else:
            click.echo(f"Evaluation complete: {results}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from e


@cli.command()
@click.option("--model1", required=True, help="Path to first model")
@click.option("--model2", required=True, help="Path to second model")
@click.option("--dataset", required=True, help="Path to evaluation dataset")
@click.option("--output-dir", help="Directory to save comparison results")
def compare(model1: str, model2: str, dataset: str, output_dir: str) -> None:
    """Compare two models on a dataset."""
    try:
        comparator = Comparator()

        click.echo("Comparing models:")
        click.echo(f"  Model 1: {model1}")
        click.echo(f"  Model 2: {model2}")
        click.echo(f"  Dataset: {dataset}")

        results = comparator.compare(model1, model2, dataset)

        if output_dir:
            click.echo(f"Comparison results saved to {output_dir}")
        else:
            click.echo(f"Comparison complete: {results}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from e


@cli.command()
def status() -> None:
    """Check pipeline status."""
    try:
        status_checker = StatusChecker()
        status_info = status_checker.get_status()

        click.echo("Pipeline Status:")
        click.echo(f"  Running: {status_info.get('running', False)}")
        click.echo(f"  Last Run: {status_info.get('last_run', 'Never')}")
        click.echo(f"  Status: {status_info.get('status', 'Unknown')}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from e


if __name__ == "__main__":
    cli()
