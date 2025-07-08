"""Tests for data integration module."""

import pytest
import pandas as pd
from pathlib import Path

from src.modules.data_integration import DataIntegrator


class TestDataIntegrator:
    """Test DataIntegrator class."""

    @pytest.fixture
    def integrator(self):
        """Create DataIntegrator instance."""
        return DataIntegrator(random_seed=42)

    def test_load_csv(self, integrator, sample_contributed_data):
        """Test loading CSV data."""
        df = integrator.load_data(sample_contributed_data["csv_path"])

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 100
        assert "query_id" in df.columns
        assert "label" in df.columns

    def test_load_json(self, integrator, sample_contributed_data):
        """Test loading JSON data."""
        df = integrator.load_data(sample_contributed_data["json_path"])

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 100

    def test_load_parquet(self, integrator, sample_contributed_data):
        """Test loading Parquet data."""
        df = integrator.load_data(sample_contributed_data["parquet_path"])

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 100

    def test_load_nonexistent_file(self, integrator):
        """Test loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            integrator.load_data(Path("nonexistent.csv"))

    def test_load_unsupported_format(self, integrator, temp_dir):
        """Test loading unsupported format raises error."""
        bad_file = temp_dir / "data.xyz"
        bad_file.write_text("data")

        with pytest.raises(ValueError, match="Unsupported data format"):
            integrator.load_data(bad_file)

    def test_validate_schema(self, integrator, sample_data):
        """Test schema validation."""
        # Valid schema
        assert integrator.validate_schema(
            sample_data,
            ["query_id", "label"]
        )

        # Missing columns
        with pytest.raises(ValueError, match="Missing required columns"):
            integrator.validate_schema(
                sample_data,
                ["query_id", "nonexistent_column"]
            )

    def test_remove_pii(self, integrator):
        """Test PII removal."""
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "email": ["user1@test.com", "user2@test.com", "user3@test.com"],
            "phone": ["123-456-7890", "234-567-8901", "345-678-9012"],
            "feature": [0.1, 0.2, 0.3]
        })

        df_clean = integrator.remove_pii(df)

        # Check that PII columns are hashed
        assert df_clean["email"].iloc[0] != "user1@test.com"
        assert len(df_clean["email"].iloc[0]) == 16  # Truncated hash
        assert df_clean["feature"].iloc[0] == 0.1  # Non-PII unchanged

    def test_deduplicate(self, integrator):
        """Test deduplication."""
        df = pd.DataFrame({
            "id": [1, 2, 2, 3],
            "value": ["a", "b", "b", "c"]
        })

        df_dedup = integrator.deduplicate(df)

        assert len(df_dedup) == 3
        assert df_dedup["id"].tolist() == [1, 2, 3]

    def test_stratified_sample(self, integrator, sample_data):
        """Test stratified sampling."""
        sample_size = 100
        sampled_df = integrator.stratified_sample(
            sample_data,
            sample_size=sample_size,
            stratify_column="label"
        )

        assert len(sampled_df) == sample_size

        # Check stratification maintained
        original_dist = sample_data["label"].value_counts(normalize=True)
        sampled_dist = sampled_df["label"].value_counts(normalize=True)

        for label in original_dist.index:
            assert abs(original_dist[label] - sampled_dist[label]) < 0.1

    def test_merge_datasets(self, integrator):
        """Test dataset merging strategies."""
        base_df = pd.DataFrame({
            "id": [1, 2, 3],
            "value": ["a", "b", "c"]
        })

        contrib_df = pd.DataFrame({
            "id": [4, 5],
            "value": ["d", "e"]
        })

        # Test append
        merged = integrator.merge_datasets(base_df, contrib_df, "append")
        assert len(merged) == 5

        # Test replace
        merged = integrator.merge_datasets(base_df, contrib_df, "replace")
        assert len(merged) == 2

        # Test invalid strategy
        with pytest.raises(ValueError):
            integrator.merge_datasets(base_df, contrib_df, "invalid")

    def test_calculate_data_hash(self, integrator, sample_data):
        """Test data hash calculation."""
        hash1 = integrator.calculate_data_hash(sample_data)
        hash2 = integrator.calculate_data_hash(sample_data)

        # Same data should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

        # Modified data should produce different hash
        modified_data = sample_data.copy()
        modified_data.loc[0, "label"] = 1 - modified_data.loc[0, "label"]
        hash3 = integrator.calculate_data_hash(modified_data)

        assert hash1 != hash3

    def test_create_data_manifest(self, integrator, sample_contributed_data):
        """Test data manifest creation."""
        df = sample_contributed_data["data"]
        manifest = integrator.create_data_manifest(
            df,
            sample_contributed_data["csv_path"]
        )

        assert "source_path" in manifest
        assert manifest["row_count"] == 100
        assert manifest["column_count"] == len(df.columns)
        assert "data_hash" in manifest
        assert len(manifest["columns"]) == len(df.columns)
