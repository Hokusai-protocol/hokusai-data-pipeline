"""Output formatter module for preview pipeline."""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Union


class PreviewOutputFormatter:
    """Formats preview results for display and export."""

    def __init__(self, use_colors: bool = False) -> None:
        """Initialize PreviewOutputFormatter.

        Args:
            use_colors: Whether to use ANSI colors in output

        """
        self.use_colors = use_colors and sys.stdout.isatty()

        # ANSI color codes
        self.colors = (
            {
                "green": "\033[92m",
                "red": "\033[91m",
                "yellow": "\033[93m",
                "blue": "\033[94m",
                "bold": "\033[1m",
                "reset": "\033[0m",
            }
            if self.use_colors
            else dict.fromkeys(["green", "red", "yellow", "blue", "bold", "reset"], "")
        )

    def format_json(self, data: dict[str, Any]) -> str:
        """Format output as JSON string.

        Args:
            data: Output data dictionary

        Returns:
            Formatted JSON string

        """
        # Add disclaimer to the data
        data_with_disclaimer = self.add_disclaimer(data)

        # Format with indentation
        return json.dumps(data_with_disclaimer, indent=2, default=str)

    def format_pretty(self, data: dict[str, Any]) -> None:
        """Format and print pretty console output.

        Args:
            data: Output data dictionary

        """
        logging.info(f"\n{self.colors['bold']}{'=' * 60}{self.colors['reset']}")
        logging.info(f"{self.colors['yellow']}PREVIEW - NON-BINDING ESTIMATE{self.colors['reset']}")
        logging.info(f"{self.colors['bold']}{'=' * 60}{self.colors['reset']}\n")

        # DeltaOne Score
        delta_score = data.get("delta_computation", {}).get("delta_one_score", 0)
        score_color = self.colors["green"] if delta_score > 0 else self.colors["red"]
        logging.info(
            f"{self.colors['bold']}DeltaOne Score:{self.colors['reset']} "
            f"{score_color}{delta_score:.4f}{self.colors['reset']}"
        )

        # Preview metadata
        preview_meta = data.get("preview_metadata", {})
        if preview_meta:
            confidence = preview_meta.get("estimation_confidence", 0)
            sample_size = preview_meta.get("sample_size_used", 0)
            time_elapsed = preview_meta.get("time_elapsed", 0)

            logging.info(f"\n{self.colors['bold']}Preview Details:{self.colors['reset']}")
            logging.info(f"  Confidence: {self.format_percentage(confidence)}")
            logging.info(f"  Sample Size: {sample_size:,}")
            logging.info(f"  Time Elapsed: {self.format_time(time_elapsed)}")

        # Metrics comparison
        logging.info(f"\n{self.colors['bold']}Metrics Comparison:{self.colors['reset']}")
        metric_deltas = data.get("delta_computation", {}).get("metric_deltas", {})

        for metric_name, delta_info in metric_deltas.items():
            baseline = delta_info["baseline_value"]
            new_val = delta_info["new_value"]
            abs_delta = delta_info["absolute_delta"]
            improvement = delta_info["improvement"]

            # Format values
            baseline_str = self.format_percentage(baseline)
            new_str = self.format_percentage(new_val)
            delta_str = self.format_delta(abs_delta)

            # Choose color and symbol
            if improvement:
                color = self.colors["green"]
                symbol = "✓"
            else:
                color = self.colors["red"]
                symbol = "✗"

            logging.info(
                f"  {metric_name:<12} {baseline_str} → {new_str} "
                f"{color}{delta_str} {symbol}{self.colors['reset']}"
            )

        logging.info(f"\n{self.colors['bold']}{'=' * 60}{self.colors['reset']}\n")

    def format_pretty_with_colors(self, data: dict[str, Any]) -> str:
        """Format output with ANSI colors for terminal display.

        Args:
            data: Output data dictionary

        Returns:
            Formatted string with color codes

        """
        # Temporarily enable colors
        old_use_colors = self.use_colors
        self.use_colors = True
        self._update_colors()

        # Capture output
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            self.format_pretty(data)
        output = f.getvalue()

        # Restore color setting
        self.use_colors = old_use_colors
        self._update_colors()

        return output

    def add_disclaimer(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add preview disclaimer to output data.

        Args:
            data: Original output data

        Returns:
            Data with disclaimer added

        """
        data_copy = data.copy()
        data_copy["disclaimer"] = (
            "PREVIEW - NON-BINDING ESTIMATE: This is a preview of potential "
            "performance improvements. Actual results may vary. This estimate "
            "is provided for informational purposes only and should not be "
            "used for production decisions."
        )
        return data_copy

    def save_to_file(self, data: dict[str, Any], file_path: Union[str, Path]) -> None:
        """Save formatted output to file.

        Args:
            data: Output data
            file_path: Path to save file

        """
        file_path = Path(file_path)

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Format and save
        formatted_json = self.format_json(data)
        file_path.write_text(formatted_json)

    def format_time(self, seconds: float) -> str:
        """Format time duration in human-readable format.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted time string

        """
        if seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.2f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.2f}s"

    def format_percentage(self, value: float) -> str:
        """Format value as percentage.

        Args:
            value: Value between 0 and 1

        Returns:
            Formatted percentage string

        """
        return f"{value * 100:.1f}%"

    def format_delta(self, value: float) -> str:
        """Format delta value with sign.

        Args:
            value: Delta value

        Returns:
            Formatted delta string

        """
        sign = "+" if value >= 0 else ""
        return f"{sign}{value * 100:.1f}%"

    def validate_output(self, data: dict[str, Any]) -> bool:
        """Validate output data against expected schema.

        Args:
            data: Output data to validate

        Returns:
            True if valid, False otherwise

        """
        required_fields = ["schema_version", "delta_computation"]

        # Check required fields
        for field in required_fields:
            if field not in data:
                return False

        # Check delta_computation structure
        delta_comp = data.get("delta_computation", {})
        if "delta_one_score" not in delta_comp:
            return False

        return True

    def _update_colors(self):
        """Update color codes based on use_colors setting."""
        if self.use_colors:
            self.colors = {
                "green": "\033[92m",
                "red": "\033[91m",
                "yellow": "\033[93m",
                "blue": "\033[94m",
                "bold": "\033[1m",
                "reset": "\033[0m",
            }
        else:
            self.colors = dict.fromkeys(["green", "red", "yellow", "blue", "bold", "reset"], "")
