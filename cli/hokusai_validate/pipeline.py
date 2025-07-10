"""Main validation pipeline orchestrator."""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

from .file_loader import FileLoader
from .hash_generator import HashGenerator
from .manifest_generator import ManifestGenerator
from .validators import DataQualityChecker, PIIDetector, SchemaValidator

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """Orchestrates the complete data validation pipeline."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize validation pipeline.

        Args:
            config: Configuration dictionary with validation settings

        """
        self.config = config
        self.file_loader = FileLoader()
        self.schema_validator = SchemaValidator()
        self.pii_detector = PIIDetector()
        self.quality_checker = DataQualityChecker()
        self.hash_generator = HashGenerator()
        self.manifest_generator = ManifestGenerator()

        # Configure logging
        log_level = logging.DEBUG if config.get("verbose") else logging.INFO
        logging.basicConfig(level=log_level)

    def validate(
        self,
        file_path: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Dict[str, Any]:
        """Run the complete validation pipeline.

        Args:
            file_path: Path to file to validate
            output_dir: Directory for output files
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with validation results

        """
        try:
            result = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "file_path": file_path,
                "output_dir": str(output_dir),
            }

            # Step 1: Load file
            self._update_progress(progress_callback, "Loading file...", 10)
            data = self._load_data(file_path)
            result["rows"] = len(data)
            result["columns"] = len(data.columns)

            # Step 2: Schema validation (if schema provided)
            if self.config.get("schema_path"):
                self._update_progress(progress_callback, "Validating schema...", 25)
                schema_result = self._validate_schema(data)
                result.update(schema_result)
                if not schema_result["schema_valid"]:
                    result["valid"] = False

            # Step 3: PII detection
            if self.config.get("pii_detection", True):
                self._update_progress(progress_callback, "Scanning for PII...", 45)
                pii_result = self._detect_pii(data)
                result.update(pii_result)

                # Redact PII if requested
                if self.config.get("pii_redaction") and pii_result.get("pii_found"):
                    data = self.pii_detector.redact(data)
                    result["pii_redacted"] = True

            # Step 4: Data quality checks
            self._update_progress(progress_callback, "Checking data quality...", 65)
            quality_result = self._check_quality(data)
            result.update(quality_result)

            # Step 5: Generate hash
            self._update_progress(progress_callback, "Generating data hash...", 80)
            hash_result = self._generate_hash(data)
            result.update(hash_result)

            # Step 6: Generate manifest
            self._update_progress(progress_callback, "Creating manifest...", 90)
            manifest_result = self._generate_manifest(file_path, data, result, output_dir)
            result.update(manifest_result)

            self._update_progress(progress_callback, "Validation complete", 100)

            return result

        except Exception as e:
            logger.error(f"Pipeline error: {e!s}")
            return {"valid": False, "errors": [str(e)], "warnings": [], "file_path": file_path}

    def _load_data(self, file_path: str) -> pd.DataFrame:
        """Load data from file."""
        format_type = self.config.get("format")
        return self.file_loader.load(file_path, format_type)

    def _validate_schema(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Validate data against schema."""
        try:
            # Load schema from file
            import json

            with open(self.config["schema_path"]) as f:
                schema = json.load(f)

            result = self.schema_validator.validate(data, schema)
            return {
                "schema_valid": result["valid"],
                "schema_errors": result.get("errors", []),
                "missing_columns": result.get("missing_columns", []),
                "type_errors": result.get("type_errors", {}),
            }
        except Exception as e:
            logger.error(f"Schema validation error: {e!s}")
            return {"schema_valid": False, "schema_errors": [str(e)]}

    def _detect_pii(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Detect PII in data."""
        try:
            result = self.pii_detector.scan(data)
            return {
                "pii_found": result["pii_found"],
                "pii_patterns": result.get("patterns_detected", []),
                "pii_fields": result.get("flagged_fields", []),
            }
        except Exception as e:
            logger.error(f"PII detection error: {e!s}")
            return {"pii_found": False, "pii_error": str(e)}

    def _check_quality(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Check data quality."""
        try:
            result = self.quality_checker.check(data)
            return {
                "quality_score": result.get("quality_score", 0.0),
                "quality_issues": result.get("issues", []),
                "missing_values": result.get("missing_values", {}),
                "outliers": result.get("outliers", []),
            }
        except Exception as e:
            logger.error(f"Quality check error: {e!s}")
            return {"quality_score": 0.0, "quality_error": str(e)}

    def _generate_hash(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Generate hash for data."""
        try:
            hash_value = self.hash_generator.generate(data)
            return {"hash": hash_value, "hash_algorithm": "SHA256"}
        except Exception as e:
            logger.error(f"Hash generation error: {e!s}")
            return {"hash": None, "hash_error": str(e)}

    def _generate_manifest(
        self,
        file_path: str,
        data: pd.DataFrame,
        validation_results: Dict[str, Any],
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Generate and save manifest."""
        try:
            manifest = self.manifest_generator.generate(
                file_path=file_path,
                data=data,
                validation_results=validation_results,
                data_hash=validation_results.get("hash"),
                eth_address=self.config.get("eth_address"),
            )

            # Save manifest
            manifest_path = output_dir / "manifest.json"
            import json

            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            return {"manifest": manifest, "manifest_path": str(manifest_path)}
        except Exception as e:
            logger.error(f"Manifest generation error: {e!s}")
            return {"manifest": None, "manifest_error": str(e)}

    def _update_progress(
        self, callback: Optional[Callable[[str, float], None]], step: str, progress: float,
    ):
        """Update progress if callback provided."""
        if callback:
            callback(step, progress)

        if self.config.get("verbose"):
            logger.info(f"{step} ({progress}%)")
