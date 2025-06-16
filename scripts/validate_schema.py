#!/usr/bin/env python3
"""
CLI tool for validating Hokusai pipeline outputs against the ZK-compatible schema.

Usage:
    python scripts/validate_schema.py <json_file> [options]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.schema_validator import SchemaValidator, validate_for_zk_proof


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Validate Hokusai pipeline outputs against ZK-compatible schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Validate a single output file
    python scripts/validate_schema.py outputs/delta_output.json
    
    # Validate with verbose output
    python scripts/validate_schema.py outputs/delta_output.json --verbose
    
    # Check ZK proof readiness
    python scripts/validate_schema.py outputs/delta_output.json --zk-check
    
    # Use custom schema file
    python scripts/validate_schema.py outputs/delta_output.json --schema custom_schema.json
        """
    )
    
    parser.add_argument(
        "input_file",
        help="Path to the JSON file to validate"
    )
    
    parser.add_argument(
        "--schema",
        help="Path to custom schema file (default: use built-in schema)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed validation information"
    )
    
    parser.add_argument(
        "--zk-check",
        action="store_true",
        help="Perform additional ZK proof readiness checks"
    )
    
    parser.add_argument(
        "--output-hash",
        action="store_true",
        help="Output the deterministic hash for ZK proof generation"
    )
    
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    
    args = parser.parse_args()
    
    # Validate input file exists
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # Initialize validator
    try:
        validator = SchemaValidator(args.schema)
    except Exception as e:
        print(f"Error loading schema: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Perform validation
    try:
        is_valid, errors = validator.validate_file(str(input_path))
        
        # Load data for additional checks if needed
        data = None
        if args.zk_check or args.output_hash:
            with open(input_path, 'r') as f:
                data = json.load(f)
        
        # Perform ZK proof readiness check if requested
        zk_ready = False
        deterministic_hash = ""
        zk_errors = []
        
        if args.zk_check and data:
            zk_ready, deterministic_hash, zk_errors = validate_for_zk_proof(data)
            errors.extend(zk_errors)
            is_valid = is_valid and zk_ready
        elif args.output_hash and data:
            from utils.schema_validator import compute_deterministic_hash
            deterministic_hash = compute_deterministic_hash(data)
        
        # Output results
        if args.format == "json":
            output_json_results(input_path, is_valid, errors, args, deterministic_hash, zk_ready)
        else:
            output_text_results(input_path, is_valid, errors, args, deterministic_hash, zk_ready, validator)
        
        # Exit with appropriate code
        sys.exit(0 if is_valid else 1)
        
    except Exception as e:
        print(f"Error during validation: {e}", file=sys.stderr)
        sys.exit(1)


def output_text_results(input_path: Path, is_valid: bool, errors: list, args: argparse.Namespace, 
                       deterministic_hash: str, zk_ready: bool, validator: SchemaValidator):
    """Output results in human-readable text format."""
    print(f"Validating: {input_path}")
    print(f"Schema: {validator.get_schema_version()}")
    print()
    
    if is_valid:
        print("✅ VALID - File conforms to the ZK-compatible schema")
        
        if args.zk_check:
            if zk_ready:
                print("✅ ZK-READY - File is ready for zero-knowledge proof generation")
            else:
                print("❌ NOT ZK-READY - File has issues preventing ZK proof generation")
        
        if args.output_hash and deterministic_hash:
            print(f"📋 Deterministic Hash: {deterministic_hash}")
            
    else:
        print("❌ INVALID - File does not conform to the schema")
    
    if errors and (args.verbose or not is_valid):
        print()
        print("Validation Errors:")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
    
    if args.verbose and is_valid:
        print()
        print("All validations passed successfully!")


def output_json_results(input_path: Path, is_valid: bool, errors: list, args: argparse.Namespace,
                       deterministic_hash: str, zk_ready: bool):
    """Output results in JSON format."""
    result = {
        "file": str(input_path),
        "valid": is_valid,
        "errors": errors,
        "zk_ready": zk_ready if args.zk_check else None,
        "deterministic_hash": deterministic_hash if (args.output_hash or args.zk_check) else None
    }
    
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()