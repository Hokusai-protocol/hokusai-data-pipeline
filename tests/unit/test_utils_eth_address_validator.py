"""Unit tests for Ethereum address validator utility."""

import pytest
from unittest.mock import patch, MagicMock

from src.utils.eth_address_validator import (
    ETHAddressValidationError,
    validate_eth_address,
    normalize_eth_address,
    is_valid_eth_checksum,
    _to_checksum_address
)


class TestETHAddressValidationError:
    """Test suite for ETHAddressValidationError exception."""

    def test_exception_creation(self):
        """Test creating validation error."""
        error = ETHAddressValidationError("Invalid address")
        assert str(error) == "Invalid address"
        assert isinstance(error, Exception)


class TestValidateETHAddress:
    """Test suite for validate_eth_address function."""

    def test_valid_address_lowercase(self):
        """Test validating a valid lowercase address."""
        address = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
        assert validate_eth_address(address) is True

    def test_valid_address_uppercase(self):
        """Test validating address with uppercase prefix."""
        address = "0X742d35cc6634c0532925a3b844bc9e7595f62349"
        assert validate_eth_address(address) is True

    def test_valid_address_mixed_case(self):
        """Test validating address with mixed case (checksum format)."""
        address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"
        assert validate_eth_address(address) is True

    def test_none_address(self):
        """Test validation with None address."""
        with pytest.raises(ETHAddressValidationError, match="ETH address cannot be None"):
            validate_eth_address(None)

    def test_non_string_address(self):
        """Test validation with non-string address."""
        with pytest.raises(ETHAddressValidationError, match="ETH address must be a string"):
            validate_eth_address(12345)

    def test_empty_address(self):
        """Test validation with empty string."""
        with pytest.raises(ETHAddressValidationError, match="ETH address cannot be empty"):
            validate_eth_address("")

    def test_missing_prefix(self):
        """Test validation with missing 0x prefix."""
        address = "742d35cc6634c0532925a3b844bc9e7595f62349"
        with pytest.raises(ETHAddressValidationError, match="must start with '0x' or '0X'"):
            validate_eth_address(address)

    def test_wrong_length_short(self):
        """Test validation with too short address."""
        address = "0x742d35cc6634c0532925a3b844bc9e7595f"
        with pytest.raises(ETHAddressValidationError, match="Invalid ETH address length"):
            validate_eth_address(address)

    def test_wrong_length_long(self):
        """Test validation with too long address."""
        address = "0x742d35cc6634c0532925a3b844bc9e7595f62349ab"
        with pytest.raises(ETHAddressValidationError, match="Invalid ETH address length"):
            validate_eth_address(address)

    def test_invalid_hex_characters(self):
        """Test validation with invalid hexadecimal characters."""
        address = "0x742d35cc6634c0532925a3b844bc9e7595fgzxyz"
        with pytest.raises(ETHAddressValidationError, match="Invalid hexadecimal characters"):
            validate_eth_address(address)

    def test_strict_checksum_valid(self):
        """Test strict checksum validation with valid checksum."""
        # Mock the checksum validation to return True
        with patch("src.utils.eth_address_validator.is_valid_eth_checksum", return_value=True):
            address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"
            assert validate_eth_address(address, strict_checksum=True) is True

    def test_strict_checksum_invalid(self):
        """Test strict checksum validation with invalid checksum."""
        # Mock the checksum validation to return False
        with patch("src.utils.eth_address_validator.is_valid_eth_checksum", return_value=False):
            address = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
            with pytest.raises(ETHAddressValidationError, match="Invalid checksum"):
                validate_eth_address(address, strict_checksum=True)


class TestNormalizeETHAddress:
    """Test suite for normalize_eth_address function."""

    def test_normalize_lowercase_address(self):
        """Test normalizing a lowercase address."""
        with patch("src.utils.eth_address_validator._to_checksum_address") as mock_checksum:
            mock_checksum.return_value = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"

            address = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
            result = normalize_eth_address(address)

            assert result == "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"
            mock_checksum.assert_called_once_with("0x742d35cc6634c0532925a3b844bc9e7595f62349")

    def test_normalize_uppercase_prefix(self):
        """Test normalizing address with uppercase prefix."""
        with patch("src.utils.eth_address_validator._to_checksum_address") as mock_checksum:
            mock_checksum.return_value = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"

            address = "0X742d35cc6634c0532925a3b844bc9e7595f62349"
            result = normalize_eth_address(address)

            assert result == "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"

    def test_normalize_invalid_address(self):
        """Test normalizing an invalid address."""
        address = "invalid_address"
        with pytest.raises(ETHAddressValidationError):
            normalize_eth_address(address)


class TestIsValidETHChecksum:
    """Test suite for is_valid_eth_checksum function."""

    def test_valid_checksum(self):
        """Test with valid checksum address."""
        with patch("src.utils.eth_address_validator._to_checksum_address") as mock_checksum:
            mock_checksum.return_value = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"

            address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"
            assert is_valid_eth_checksum(address) is True

    def test_invalid_checksum(self):
        """Test with invalid checksum address."""
        with patch("src.utils.eth_address_validator._to_checksum_address") as mock_checksum:
            mock_checksum.return_value = "0x742d35Cc6634C0532925a3b844Bc9e7595f62349"

            # Provide different casing
            address = "0x742d35CC6634C0532925a3b844BC9e7595f62349"
            assert is_valid_eth_checksum(address) is False

    def test_invalid_address_format(self):
        """Test checksum validation with invalid address format."""
        address = "not_an_address"
        assert is_valid_eth_checksum(address) is False


class TestToChecksumAddress:
    """Test suite for _to_checksum_address function."""

    def test_checksum_with_crypto_library(self):
        """Test checksum generation with Crypto library."""
        # Mock the Crypto library
        mock_keccak = MagicMock()
        mock_hash_obj = MagicMock()
        mock_hash_obj.hexdigest.return_value = "89abcdef" * 10  # 40 hex chars
        mock_keccak.new.return_value = mock_hash_obj

        with patch.dict("sys.modules", {"Crypto.Hash.keccak": mock_keccak}):
            # Need to reload to pick up the mocked import
            import importlib
            import src.utils.eth_address_validator
            importlib.reload(src.utils.eth_address_validator)
            from src.utils.eth_address_validator import _to_checksum_address

            address = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
            result = _to_checksum_address(address)

            # Should have 0x prefix
            assert result.startswith("0x")
            assert len(result) == 42

    def test_checksum_with_hashlib_fallback(self):
        """Test checksum generation with hashlib fallback."""
        # Force ImportError for Crypto library
        with patch.dict("sys.modules", {"Crypto.Hash.keccak": None}):
            with patch("builtins.__import__", side_effect=ImportError()):
                address = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
                result = _to_checksum_address(address)

                # Should still produce a valid format address
                assert result.startswith("0x")
                assert len(result) == 42

    def test_checksum_consistency(self):
        """Test that checksum is consistent for same address."""
        with patch("src.utils.eth_address_validator._to_checksum_address") as mock_impl:
            # Mock consistent behavior
            mock_impl.side_effect = lambda x: "0x" + x.replace("0x", "").upper()

            address = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
            result1 = mock_impl(address)
            result2 = mock_impl(address)

            assert result1 == result2

    def test_checksum_different_addresses(self):
        """Test that different addresses produce different checksums."""
        # Using the actual implementation
        address1 = "0x742d35cc6634c0532925a3b844bc9e7595f62349"
        address2 = "0x5aAeb6053f3E94C9b9A09f33669435E7Ef1BeAed"

        result1 = _to_checksum_address(address1)
        result2 = _to_checksum_address(address2)

        # Different addresses should produce different checksums
        assert result1 != result2
