"""
Tests for ETH address validation utilities.
"""
import pytest
from src.utils.eth_address_validator import (
    validate_eth_address,
    normalize_eth_address,
    is_valid_eth_checksum,
    ETHAddressValidationError
)


class TestETHAddressValidation:
    """Test ETH address validation functionality."""

    def test_valid_eth_addresses(self):
        """Test validation of valid ETH addresses."""
        valid_addresses = [
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
            "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
            "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
            "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb",
            "0x0000000000000000000000000000000000000000",
            "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
        ]
        
        for address in valid_addresses:
            assert validate_eth_address(address) is True

    def test_invalid_eth_address_format(self):
        """Test validation rejects invalid address formats."""
        invalid_addresses = [
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAe",  # Too short
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAedd",  # Too long
            "5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",   # Missing 0x prefix
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeG",  # Invalid hex character
            "0x",                                           # Only prefix
            "",                                             # Empty string
            "not_an_address",                               # Invalid format
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1Be ed",  # Contains space
        ]
        
        for address in invalid_addresses:
            with pytest.raises(ETHAddressValidationError):
                validate_eth_address(address)

    def test_address_normalization(self):
        """Test ETH address normalization."""
        test_cases = [
            ("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"),
            ("0x5AAEB6053F3E94C9B9A09F33669435E7EF1BEAED", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"),
            ("0X5AAEB6053F3E94C9B9A09F33669435E7EF1BEAED", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"),
            ("0xfb6916095ca1df60bb79ce92ce3ea74c37c5d359", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"),
        ]
        
        for input_address, expected_output in test_cases:
            assert normalize_eth_address(input_address) == expected_output

    def test_checksum_validation(self):
        """Test ETH address checksum validation."""
        # Valid checksummed addresses
        valid_checksummed = [
            "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
            "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
            "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
        ]
        
        for address in valid_checksummed:
            assert is_valid_eth_checksum(address) is True

        # Invalid checksummed addresses
        invalid_checksummed = [
            "0x5aaeb6053F3E94C9b9A09f33669435E7Ef1BeAed",  # Mixed case incorrect
            "0xfb6916095ca1df60bb79ce92ce3ea74c37c5d359",  # All lowercase
            "0xFB6916095CA1DF60BB79CE92CE3EA74C37C5D359",  # All uppercase
        ]
        
        for address in invalid_checksummed:
            assert is_valid_eth_checksum(address) is False

    def test_validation_with_strict_checksum(self):
        """Test validation with strict checksum enforcement."""
        # Should pass with correct checksum
        assert validate_eth_address("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", strict_checksum=True) is True
        
        # Should fail with incorrect checksum
        with pytest.raises(ETHAddressValidationError, match="Invalid checksum"):
            validate_eth_address("0x5aaeb6053F3E94C9b9A09f33669435E7Ef1BeAed", strict_checksum=True)

    def test_validation_without_strict_checksum(self):
        """Test validation without strict checksum enforcement."""
        # Should pass even with incorrect checksum
        assert validate_eth_address("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed", strict_checksum=False) is True
        assert validate_eth_address("0x5AAEB6053F3E94C9B9A09F33669435E7EF1BEAED", strict_checksum=False) is True

    def test_error_messages(self):
        """Test that validation errors contain helpful messages."""
        test_cases = [
            ("", "ETH address cannot be empty"),
            ("not_an_address", "Invalid ETH address format"),
            ("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAe", "Invalid ETH address length"),
            ("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeG", "Invalid hexadecimal characters"),
        ]
        
        for invalid_address, expected_message in test_cases:
            with pytest.raises(ETHAddressValidationError) as exc_info:
                validate_eth_address(invalid_address)
            assert expected_message in str(exc_info.value)

    def test_none_address_handling(self):
        """Test handling of None address values."""
        with pytest.raises(ETHAddressValidationError, match="ETH address cannot be None"):
            validate_eth_address(None)

    def test_type_error_handling(self):
        """Test handling of non-string address values."""
        invalid_types = [123, [], {}, True]
        
        for invalid_type in invalid_types:
            with pytest.raises(ETHAddressValidationError, match="ETH address must be a string"):
                validate_eth_address(invalid_type)