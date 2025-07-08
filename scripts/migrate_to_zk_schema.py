#!/usr/bin/env python3
"""Migration script to convert existing outputs to ZK-compatible format."""

import argparse
import json
import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.schema_validator import SchemaValidator
from src.utils.zk_output_formatter import ZKCompatibleOutputFormatter


def migrate_output_file(
    input_path: str, output_path: str, formatter: ZKCompatibleOutputFormatter
) -> bool:
    """Migrate a single output file to ZK-compatible format.

    Args:
        input_path: Path to existing output file
        output_path: Path for ZK-compatible output
        formatter: ZK formatter instance

    Returns:
        True if migration successful, False otherwise

    """
    try:
        with open(input_path, "r") as f:
            old_output = json.load(f)

        # Format to ZK-compatible
        new_output, is_valid, errors = formatter.format_and_validate(old_output)

        if not is_valid:
            print(f"❌ Migration failed for {input_path}: {errors}")
            return False

        # Save new output
        with open(output_path, "w") as f:
            json.dump(new_output, f, indent=2)

        print(f"✅ Migrated {input_path} -> {output_path}")
        return True

    except Exception as e:
        print(f"❌ Error migrating {input_path}: {e}")
        return False


def validate_zk_output(file_path: str, validator: SchemaValidator) -> bool:
    """Validate a ZK output file.

    Args:
        file_path: Path to ZK output file
        validator: Schema validator instance

    Returns:
        True if valid, False otherwise

    """
    try:
        with open(file_path, "r") as f:
            data = json.load(f)

        is_valid, errors = validator.validate_output(data)
        if not is_valid:
            print(f"❌ Validation failed for {file_path}: {errors}")
            return False

        # Check ZK readiness
        from src.utils.schema_validator import validate_for_zk_proof

        is_zk_ready, deterministic_hash, zk_errors = validate_for_zk_proof(data)
        if not is_zk_ready:
            print(f"❌ ZK validation failed for {file_path}: {zk_errors}")
            return False

        print(f"✅ {file_path} is valid and ZK-ready (hash: {deterministic_hash[:16]}...)")
        return True

    except Exception as e:
        print(f"❌ Error validating {file_path}: {e}")
        return False


def main() -> int:
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate existing outputs to ZK-compatible format")
    parser.add_argument(
        "--input-dir", default="outputs", help="Directory containing existing outputs"
    )
    parser.add_argument(
        "--output-dir", default="outputs", help="Directory for ZK-compatible outputs"
    )
    parser.add_argument("--pattern", default="delta_output_*.json", help="File pattern to migrate")
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate existing ZK outputs"
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing ZK outputs")

    args = parser.parse_args()

    formatter = ZKCompatibleOutputFormatter()
    validator = SchemaValidator()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(f"❌ Input directory {input_dir} does not exist")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.validate_only:
        # Validate existing ZK outputs
        zk_pattern = args.pattern.replace(".json", "_zk.json")
        zk_files = list(input_dir.glob(zk_pattern))

        if not zk_files:
            print(f"No ZK output files found matching pattern: {zk_pattern}")
            return 1

        print(f"Validating {len(zk_files)} ZK output files...")
        valid_count = 0

        for zk_file in zk_files:
            if validate_zk_output(str(zk_file), validator):
                valid_count += 1

        print(f"\n✅ {valid_count}/{len(zk_files)} files are valid")
        return 0 if valid_count == len(zk_files) else 1

    # Find files to migrate
    input_files = list(input_dir.glob(args.pattern))

    if not input_files:
        print(f"No input files found matching pattern: {args.pattern}")
        return 1

    print(f"Found {len(input_files)} files to migrate...")

    success_count = 0
    for input_file in input_files:
        # Skip files that are already ZK format
        if "_zk" in input_file.stem:
            continue

        # Generate output filename
        output_filename = input_file.stem + "_zk.json"
        output_file = output_dir / output_filename

        # Skip if output exists and not overwriting
        if output_file.exists() and not args.overwrite:
            print(f"⏭️  Skipping {input_file} (output exists, use --overwrite to replace)")
            continue

        if migrate_output_file(str(input_file), str(output_file), formatter):
            success_count += 1

    print(f"\n✅ Successfully migrated {success_count}/{len(input_files)} files")

    # Validate migrated outputs
    if success_count > 0:
        print("\nValidating migrated outputs...")
        zk_files = list(output_dir.glob("*_zk.json"))
        valid_count = 0

        for zk_file in zk_files:
            if validate_zk_output(str(zk_file), validator):
                valid_count += 1

        print(f"✅ {valid_count}/{len(zk_files)} migrated files are valid")

    return 0 if success_count == len(input_files) else 1


if __name__ == "__main__":
    exit(main())
