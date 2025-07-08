"""File loading utilities for different data formats."""

import json
from pathlib import Path
from typing import Optional

import pandas as pd

from .exceptions import FileLoadError, UnsupportedFormatError


class FileLoader:
    """Handles loading of different file formats."""

    SUPPORTED_FORMATS = {"csv", "json", "parquet"}

    def detect_format(self, file_path: str) -> str:
        """Detect file format from file extension.

        Args:
            file_path: Path to the file

        Returns:
            Detected format string

        Raises:
            UnsupportedFormatError: If format is not supported

        """
        path = Path(file_path)
        extension = path.suffix.lower().lstrip(".")

        if extension not in self.SUPPORTED_FORMATS:
            raise UnsupportedFormatError(
                f"Unsupported file format: .{extension}. "
                f"Supported formats: {', '.join(f'.{fmt}' for fmt in self.SUPPORTED_FORMATS)}",
            )

        return extension

    def load(self, file_path: str, format_type: Optional[str] = None) -> pd.DataFrame:
        """Load data from file into a pandas DataFrame.

        Args:
            file_path: Path to the file
            format_type: Force specific format (auto-detected if None)

        Returns:
            Loaded data as DataFrame

        Raises:
            FileLoadError: If file loading fails
            UnsupportedFormatError: If format is not supported

        """
        try:
            if format_type is None:
                format_type = self.detect_format(file_path)

            if format_type == "csv":
                return self._load_csv(file_path)
            if format_type == "json":
                return self._load_json(file_path)
            if format_type == "parquet":
                return self._load_parquet(file_path)
            raise UnsupportedFormatError(f"Unsupported format: {format_type}")

        except Exception as e:
            if isinstance(e, (UnsupportedFormatError, FileLoadError)):
                raise
            raise FileLoadError(f"Failed to load file {file_path}: {e!s}")

    def _load_csv(self, file_path: str) -> pd.DataFrame:
        """Load CSV file."""
        try:
            # Try different encodings and separators
            encodings = ["utf-8", "latin1", "cp1252"]
            separators = [",", ";", "\t"]

            for encoding in encodings:
                for sep in separators:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding, sep=sep)
                        # Basic validation - should have more than 1 column for most separators
                        if len(df.columns) > 1 or sep == separators[-1]:
                            return df
                    except (UnicodeDecodeError, pd.errors.EmptyDataError):
                        continue
                    except Exception:
                        if encoding == encodings[-1] and sep == separators[-1]:
                            raise
                        continue

            raise FileLoadError("Could not parse CSV file with any encoding/separator combination")

        except Exception as e:
            raise FileLoadError(f"Error loading CSV file: {e!s}")

    def _load_json(self, file_path: str) -> pd.DataFrame:
        """Load JSON file."""
        try:
            # Try different JSON orientations
            orientations = ["records", "index", "values", "split"]

            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            # If it's already a list of records, try records first
            if isinstance(data, list):
                orientations = ["records"] + [o for o in orientations if o != "records"]

            for orientation in orientations:
                try:
                    if orientation == "records":
                        if isinstance(data, list):
                            return pd.DataFrame(data)
                        continue
                    return pd.read_json(file_path, orient=orientation)
                except (ValueError, KeyError):
                    continue

            # If none of the standard orientations work, try to infer structure
            if isinstance(data, dict):
                # Try to convert dict to DataFrame
                return pd.DataFrame.from_dict(data, orient="index")
            if isinstance(data, list):
                return pd.DataFrame(data)
            raise FileLoadError("Could not convert JSON data to DataFrame")

        except json.JSONDecodeError as e:
            raise FileLoadError(f"Invalid JSON file: {e!s}")
        except Exception as e:
            raise FileLoadError(f"Error loading JSON file: {e!s}")

    def _load_parquet(self, file_path: str) -> pd.DataFrame:
        """Load Parquet file."""
        try:
            return pd.read_parquet(file_path)
        except ImportError:
            raise FileLoadError(
                "Parquet support not available. Please install pyarrow: pip install pyarrow",
            )
        except Exception as e:
            raise FileLoadError(f"Error loading Parquet file: {e!s}")

    def get_file_info(self, file_path: str) -> dict:
        """Get metadata about the file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file metadata

        """
        path = Path(file_path)

        if not path.exists():
            raise FileLoadError(f"File not found: {file_path}")

        return {
            "path": str(path.absolute()),
            "name": path.name,
            "size": path.stat().st_size,
            "format": self.detect_format(file_path),
            "exists": True,
        }
