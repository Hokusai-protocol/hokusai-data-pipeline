"""Main CLI interface for Hokusai data validation."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__
from .exceptions import UnsupportedFormatError, ValidationError
from .file_loader import FileLoader
from .pipeline import ValidationPipeline


def _detect_file_format(input_file: Path, force_format: str | None, verbose: bool) -> str:
    """Detect or use forced file format."""
    if force_format:
        return force_format

    loader = FileLoader()
    file_format = loader.detect_format(str(input_file))
    if verbose:
        click.echo(f"Detected format: {file_format}")
    return file_format


def _validate_eth_address(eth_address: str | None, verbose: bool) -> str | None:
    """Validate and normalize Ethereum address."""
    if not eth_address:
        return None

    from src.utils.eth_address_validator import (
        normalize_eth_address,
        validate_eth_address,
    )
    validate_eth_address(eth_address)
    validated_eth_address = normalize_eth_address(eth_address)
    if verbose:
        click.echo(f"Validated ETH address: {validated_eth_address}")
    return validated_eth_address


def _display_results(result: dict[str, any], verbose: bool) -> None:
    """Display validation results."""
    if result["valid"]:
        click.echo("\n✅ Validation successful!")
        click.echo(f"Data hash: {result['hash']}")
        click.echo(f"Manifest saved: {result['manifest_path']}")

        if result.get("pii_detected"):
            click.echo("⚠️  PII detected - check the detailed report")

        if result.get("quality_issues"):
            click.echo("⚠️  Data quality issues found - check the detailed report")
    else:
        click.echo("\n❌ Validation failed!")
        for error in result.get("errors", []):
            click.echo(f"Error: {error}")

        for warning in result.get("warnings", []):
            click.echo(f"Warning: {warning}")

        sys.exit(1)


@click.command(name="hokusai-validate")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--schema",
              type=click.Path(exists=True, path_type=Path),
              help="Path to schema definition file")
@click.option("--output-dir",
              type=click.Path(path_type=Path),
              default=Path.cwd(),
              help="Directory for output files (default: current directory)")
@click.option("--no-pii-scan",
              is_flag=True,
              help="Skip PII detection")
@click.option("--redact-pii",
              is_flag=True,
              help="Automatically redact detected PII")
@click.option("--verbose",
              is_flag=True,
              help="Show detailed validation progress")
@click.option("--format",
              "force_format",
              type=click.Choice(["csv", "json", "parquet"]),
              help="Force specific file format (auto-detected by default)")
@click.option("--eth-address",
              type=str,
              help="Ethereum wallet address for contributor attribution")
@click.version_option(version=__version__)
def main(
    input_file: Path,
    schema: Path | None,
    output_dir: Path,
    no_pii_scan: bool,
    redact_pii: bool,
    verbose: bool,
    force_format: str | None,
    eth_address: str | None,
) -> None:
    """Validate data files for Hokusai contribution.

    This tool validates data files, checks for PII, generates hashes,
    and creates manifests for data contribution to the Hokusai pipeline.

    INPUT_FILE: Path to the data file to validate (.csv, .json, or .parquet)
    """
    try:
        # Configure output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        if verbose:
            click.echo(f"Validating file: {input_file}")
            click.echo(f"Output directory: {output_dir}")

        # Detect file format
        try:
            file_format = _detect_file_format(input_file, force_format, verbose)
        except UnsupportedFormatError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Validate ETH address if provided
        try:
            validated_eth_address = _validate_eth_address(eth_address, verbose)
        except Exception as e:
            click.echo(f"Error: Invalid ETH address '{eth_address}': {e}", err=True)
            sys.exit(1)

        # Configure validation pipeline
        config = {
            "schema_path": str(schema) if schema else None,
            "pii_detection": not no_pii_scan,
            "pii_redaction": redact_pii,
            "verbose": verbose,
            "format": file_format,
            "eth_address": validated_eth_address,
        }

        # Run validation pipeline
        pipeline = ValidationPipeline(config)

        with click.progressbar(length=100, label="Validating data") as bar:
            def progress_callback(step: str, progress: float) -> None:
                if verbose:
                    click.echo(f"\n{step}")
                bar.update(int(progress - bar.pos))

            result = pipeline.validate(str(input_file), output_dir, progress_callback)

        # Display results
        _display_results(result, verbose)

    except ValidationError as e:
        click.echo(f"Validation error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"Unexpected error: {e}", err=True)
        if verbose:
            import traceback  # noqa: PLC0415
            traceback.print_exc()
        sys.exit(1)


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """Hokusai Data Validation CLI."""


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
def validate(input_file: str) -> None:
    """Validate a data file."""
    main.callback(Path(input_file), None, Path.cwd(), False, False, False, None)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
def hash_file(input_file: str) -> None:
    """Generate hash for a data file."""
    from .file_loader import FileLoader  # noqa: PLC0415
    from .hash_generator import HashGenerator  # noqa: PLC0415

    try:
        loader = FileLoader()
        data = loader.load(input_file)

        generator = HashGenerator()
        hash_value = generator.generate(data)

        click.echo(f"SHA256: {hash_value}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
def scan_pii(input_file: str) -> None:
    """Scan a file for PII."""
    from .file_loader import FileLoader  # noqa: PLC0415
    from .validators import PIIDetector  # noqa: PLC0415

    try:
        loader = FileLoader()
        data = loader.load(input_file)

        detector = PIIDetector()
        result = detector.scan(data)

        if result["pii_found"]:
            click.echo("⚠️  PII detected!")
            click.echo(f"Patterns found: {', '.join(result['patterns_detected'])}")
            click.echo(f"Flagged fields: {len(result['flagged_fields'])}")
        else:
            click.echo("✅ No PII detected")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
