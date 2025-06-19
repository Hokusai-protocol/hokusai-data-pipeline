"""Tests for ETH address in schema examples."""

import json
import pytest
from pathlib import Path


class TestSchemaEthAddress:
    """Test suite for ETH address fields in schema examples."""
    
    @pytest.fixture
    def valid_example_path(self):
        """Path to valid example JSON."""
        return Path(__file__).parent.parent.parent / "schema" / "examples" / "valid_zk_output.json"
    
    @pytest.fixture
    def valid_example_data(self, valid_example_path):
        """Load valid example JSON data."""
        with open(valid_example_path, 'r') as f:
            return json.load(f)
    
    def test_single_contributor_has_wallet_address(self, valid_example_data):
        """Test that single contributor example includes wallet_address field."""
        # Check if contributor_info exists
        assert "contributor_info" in valid_example_data, "Example should have contributor_info"
        
        contributor_info = valid_example_data["contributor_info"]
        
        # Check that wallet_address field exists
        assert "wallet_address" in contributor_info, "contributor_info should include wallet_address"
        
        # Validate ETH address format (0x + 40 hex chars)
        wallet_address = contributor_info["wallet_address"]
        assert isinstance(wallet_address, str), "wallet_address should be a string"
        assert wallet_address.startswith("0x"), "ETH address should start with 0x"
        assert len(wallet_address) == 42, "ETH address should be 42 characters (0x + 40 hex)"
        
        # Check that it's valid hex
        try:
            int(wallet_address[2:], 16)
        except ValueError:
            pytest.fail(f"Invalid ETH address format: {wallet_address}")
    
    def test_eth_address_format_validation(self, valid_example_data):
        """Test that ETH address follows correct format."""
        if "contributor_info" in valid_example_data:
            wallet_address = valid_example_data["contributor_info"].get("wallet_address", "")
            if wallet_address:
                # Should match pattern ^0[xX][a-fA-F0-9]{40}$
                import re
                pattern = r"^0[xX][a-fA-F0-9]{40}$"
                assert re.match(pattern, wallet_address), f"ETH address {wallet_address} doesn't match required pattern"
    
    def test_multiple_contributors_example(self):
        """Test for multiple contributors with wallet addresses."""
        # Load the multiple contributors example
        multi_example_path = Path(__file__).parent.parent.parent / "schema" / "examples" / "valid_zk_output_multiple_contributors.json"
        
        assert multi_example_path.exists(), f"Multiple contributors example should exist at {multi_example_path}"
        
        with open(multi_example_path, 'r') as f:
            example_data = json.load(f)
        
        # Verify structure
        assert "contributors" in example_data, "Example should have contributors array"
        contributors = example_data["contributors"]
        
        # Check that it's an array with multiple contributors
        assert isinstance(contributors, list), "contributors should be an array"
        assert len(contributors) >= 2, "Should have at least 2 contributors in example"
        
        # Check all contributors have wallet_address
        for contributor in contributors:
            assert "wallet_address" in contributor, f"Contributor {contributor.get('id')} missing wallet_address"
            assert contributor["wallet_address"].startswith("0x")
            assert len(contributor["wallet_address"]) == 42
            
            # Validate ETH address format
            import re
            pattern = r"^0[xX][a-fA-F0-9]{40}$"
            assert re.match(pattern, contributor["wallet_address"]), f"Invalid ETH address: {contributor['wallet_address']}"
        
        # Verify weights sum to 1.0
        total_weight = sum(c.get("weight", 0) for c in contributors)
        assert abs(total_weight - 1.0) < 0.001, f"Contributor weights should sum to 1.0, got {total_weight}"
        
        # Verify each contributor has different ETH addresses
        addresses = [c["wallet_address"] for c in contributors]
        assert len(addresses) == len(set(addresses)), "Each contributor should have a unique ETH address"
    
    def test_example_file_exists(self, valid_example_path):
        """Test that the valid example file exists."""
        assert valid_example_path.exists(), f"Valid example file should exist at {valid_example_path}"
    
    def test_example_is_valid_json(self, valid_example_path):
        """Test that the example file contains valid JSON."""
        try:
            with open(valid_example_path, 'r') as f:
                json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"Example file is not valid JSON: {e}")