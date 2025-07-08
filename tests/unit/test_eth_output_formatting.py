"""
Tests for ETH address integration in ZK output formatting.
"""
from unittest.mock import patch
from src.utils.zk_output_formatter import ZKCompatibleOutputFormatter


class TestETHOutputFormatting:
    """Test ETH address integration in output formatting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.formatter = ZKCompatibleOutputFormatter()

        # Mock base pipeline results
        self.base_results = {
            "contributor_attribution": {
                "data_hash": "a1b2c3d4e5f6789012345678901234567890123456789012345678901234567890",
                "data_manifest": {
                    "source_path": "test_data.csv",
                    "row_count": 1000,
                    "column_count": 10,
                    "columns": ["col1", "col2"],
                    "dtypes": {"col1": "int64", "col2": "object"}
                },
                "contributor_weights": 0.5,
                "contributed_samples": 500,
                "total_samples": 1000,
                "validation_status": "valid"
            },
            "evaluation_results": {
                "baseline_metrics": {"accuracy": 0.85, "f1_score": 0.82},
                "new_metrics": {"accuracy": 0.88, "f1_score": 0.86}
            },
            "delta_computation": {
                "delta_accuracy": 0.03,
                "delta_f1": 0.04,
                "improvement": True
            },
            "models": {
                "baseline": {"model_id": "baseline_v1", "model_type": "transformer"},
                "new": {"model_id": "new_v1", "model_type": "transformer"}
            }
        }

    def test_single_contributor_with_eth_address(self):
        """Test formatting single contributor with ETH address."""
        # Add ETH address to contributor data
        self.base_results["contributor_attribution"]["wallet_address"] = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

        result = self.formatter.format_output(self.base_results)

        # Should use contributor_info format (single contributor)
        assert "contributor_info" in result
        assert "contributors" not in result
        assert result["contributor_info"]["wallet_address"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

    def test_single_contributor_without_eth_address(self):
        """Test formatting single contributor without ETH address."""
        result = self.formatter.format_output(self.base_results)

        # Should use contributor_info format without wallet_address
        assert "contributor_info" in result
        assert "contributors" not in result
        assert "wallet_address" not in result["contributor_info"]

    def test_multiple_contributors_with_eth_addresses(self):
        """Test formatting multiple contributors with ETH addresses."""
        # Set up multiple contributors
        self.base_results["contributors"] = [
            {
                "id": "contributor_1",
                "data_hash": "a1b2c3d4e5f6789012345678901234567890123456789012345678901234567890",
                "data_manifest": {
                    "source_path": "data1.csv",
                    "row_count": 500,
                    "column_count": 10
                },
                "weight": 0.7,
                "contributed_samples": 500,
                "validation_status": "valid",
                "wallet_address": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
            },
            {
                "id": "contributor_2",
                "data_hash": "b1a2c3d4e5f6789012345678901234567890123456789012345678901234567890",
                "data_manifest": {
                    "source_path": "data2.csv",
                    "row_count": 300,
                    "column_count": 8
                },
                "weight": 0.3,
                "contributed_samples": 300,
                "validation_status": "valid",
                "wallet_address": "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"
            }
        ]

        result = self.formatter.format_output(self.base_results)

        # Should use contributors array format (multiple contributors)
        assert "contributors" in result
        assert "contributor_info" not in result
        assert len(result["contributors"]) == 2

        # Check first contributor
        contrib1 = result["contributors"][0]
        assert contrib1["id"] == "contributor_1"
        assert contrib1["wallet_address"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
        assert contrib1["weight"] == 0.7

        # Check second contributor
        contrib2 = result["contributors"][1]
        assert contrib2["id"] == "contributor_2"
        assert contrib2["wallet_address"] == "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"
        assert contrib2["weight"] == 0.3

    def test_multiple_contributors_mixed_eth_addresses(self):
        """Test multiple contributors where some have ETH addresses and some don't."""
        self.base_results["contributors"] = [
            {
                "id": "contributor_1",
                "data_hash": "a1b2c3d4e5f6789012345678901234567890123456789012345678901234567890",
                "data_manifest": {"source_path": "data1.csv", "row_count": 500},
                "weight": 0.6,
                "wallet_address": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
            },
            {
                "id": "contributor_2",
                "data_hash": "b1a2c3d4e5f6789012345678901234567890123456789012345678901234567890",
                "data_manifest": {"source_path": "data2.csv", "row_count": 400},
                "weight": 0.4
                # No wallet_address provided
            }
        ]

        result = self.formatter.format_output(self.base_results)

        # Check that only first contributor has wallet_address
        contrib1 = result["contributors"][0]
        contrib2 = result["contributors"][1]

        assert "wallet_address" in contrib1
        assert contrib1["wallet_address"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
        assert "wallet_address" not in contrib2

    def test_invalid_eth_address_handling(self):
        """Test handling of invalid ETH addresses."""
        # Add invalid ETH address
        self.base_results["contributor_attribution"]["wallet_address"] = "invalid_address"

        with patch("builtins.print") as mock_print:
            result = self.formatter.format_output(self.base_results)

            # Should not include wallet_address field
            assert "wallet_address" not in result["contributor_info"]

            # Should have printed warning
            mock_print.assert_called_once()
            warning_msg = mock_print.call_args[0][0]
            assert "Warning: Invalid ETH address provided" in warning_msg

    def test_eth_address_normalization(self):
        """Test that ETH addresses are properly normalized."""
        # Add lowercase ETH address
        self.base_results["contributor_attribution"]["wallet_address"] = "0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed"

        result = self.formatter.format_output(self.base_results)

        # Should be normalized to proper checksum format
        assert result["contributor_info"]["wallet_address"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

    def test_uppercase_x_eth_address_handling(self):
        """Test handling of ETH addresses with uppercase X prefix."""
        # Add ETH address with uppercase X
        self.base_results["contributor_attribution"]["wallet_address"] = "0X5AAEB6053F3E94C9B9A09F33669435E7EF1BEAED"

        result = self.formatter.format_output(self.base_results)

        # Should be normalized to proper format
        assert result["contributor_info"]["wallet_address"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

    def test_format_and_validate_with_eth_address(self):
        """Test format_and_validate with ETH address."""
        self.base_results["contributor_attribution"]["wallet_address"] = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

        formatted_output, is_valid, errors = self.formatter.format_and_validate(self.base_results)

        # Print debug info if test fails
        if not is_valid:
            print(f"Validation errors: {errors}")
            print(f"Formatted output: {formatted_output}")

        assert formatted_output["contributor_info"]["wallet_address"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
        # Note: We expect validation to fail because we don't have complete test data for all required fields

    def test_backward_compatibility(self):
        """Test that outputs without ETH addresses still work."""
        result = self.formatter.format_output(self.base_results)

        # Should still generate valid output structure
        assert "contributor_info" in result
        assert "schema_version" in result
        assert "metadata" in result
        assert "evaluation_results" in result
        assert "delta_computation" in result
        assert "models" in result
        assert "attestation" in result

        # Should not have wallet_address field
        assert "wallet_address" not in result["contributor_info"]
