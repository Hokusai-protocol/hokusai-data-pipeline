"""
Tests for ETH address integration in CLI.
"""
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from pathlib import Path
import tempfile
import json

from cli.hokusai_validate.cli import main
from src.utils.eth_address_validator import ETHAddressValidationError


class TestCLIETHIntegration:
    """Test ETH address integration in CLI."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_cli_with_valid_eth_address(self):
        """Test CLI with valid ETH address."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,test\n2,data\n")
            temp_file = f.name

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('cli.hokusai_validate.pipeline.ValidationPipeline') as mock_pipeline:
                # Mock successful validation
                mock_instance = MagicMock()
                mock_instance.validate.return_value = {
                    'valid': True,
                    'hash': 'abc123',
                    'manifest_path': f"{temp_dir}/manifest.json"
                }
                mock_pipeline.return_value = mock_instance

                result = self.runner.invoke(main, [
                    temp_file,
                    '--output-dir', temp_dir,
                    '--eth-address', '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed',
                    '--verbose'
                ])

                assert result.exit_code == 0
                assert "Validated ETH address: 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed" in result.output

                # Verify the pipeline was called with ETH address in config
                mock_pipeline.assert_called_once()
                config = mock_pipeline.call_args[0][0]
                assert config['eth_address'] == '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'

        Path(temp_file).unlink()

    def test_cli_with_invalid_eth_address(self):
        """Test CLI with invalid ETH address."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,test\n2,data\n")
            temp_file = f.name

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(main, [
                temp_file,
                '--output-dir', temp_dir,
                '--eth-address', 'invalid_address'
            ])

            assert result.exit_code == 1
            assert "Error: Invalid ETH address 'invalid_address'" in result.output

        Path(temp_file).unlink()

    def test_cli_without_eth_address(self):
        """Test CLI without ETH address (should work normally)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,test\n2,data\n")
            temp_file = f.name

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('cli.hokusai_validate.pipeline.ValidationPipeline') as mock_pipeline:
                # Mock successful validation
                mock_instance = MagicMock()
                mock_instance.validate.return_value = {
                    'valid': True,
                    'hash': 'abc123',
                    'manifest_path': f"{temp_dir}/manifest.json"
                }
                mock_pipeline.return_value = mock_instance

                result = self.runner.invoke(main, [
                    temp_file,
                    '--output-dir', temp_dir
                ])

                assert result.exit_code == 0

                # Verify the pipeline was called with None ETH address in config
                mock_pipeline.assert_called_once()
                config = mock_pipeline.call_args[0][0]
                assert config['eth_address'] is None

        Path(temp_file).unlink()

    def test_cli_normalizes_eth_address(self):
        """Test that CLI normalizes ETH addresses."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,test\n2,data\n")
            temp_file = f.name

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('cli.hokusai_validate.pipeline.ValidationPipeline') as mock_pipeline:
                # Mock successful validation
                mock_instance = MagicMock()
                mock_instance.validate.return_value = {
                    'valid': True,
                    'hash': 'abc123',
                    'manifest_path': f"{temp_dir}/manifest.json"
                }
                mock_pipeline.return_value = mock_instance

                # Use lowercase address
                result = self.runner.invoke(main, [
                    temp_file,
                    '--output-dir', temp_dir,
                    '--eth-address', '0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed',
                    '--verbose'
                ])

                assert result.exit_code == 0
                assert "Validated ETH address: 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed" in result.output

                # Verify normalized address was passed to pipeline
                config = mock_pipeline.call_args[0][0]
                assert config['eth_address'] == '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'

        Path(temp_file).unlink()

    def test_manifest_generation_includes_eth_address(self):
        """Test that manifest generation includes ETH address."""
        from cli.hokusai_validate.manifest_generator import ManifestGenerator
        import pandas as pd

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,test\n2,data\n")
            temp_file = f.name

        try:
            generator = ManifestGenerator()
            data = pd.DataFrame({'col1': [1, 2], 'col2': ['test', 'data']})
            validation_results = {'valid': True}
            
            manifest = generator.generate(
                file_path=temp_file,
                data=data,
                validation_results=validation_results,
                data_hash='abc123',
                eth_address='0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'
            )

            assert 'contributor_metadata' in manifest
            assert manifest['contributor_metadata']['wallet_address'] == '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'
        finally:
            Path(temp_file).unlink()

    def test_manifest_generation_without_eth_address(self):
        """Test that manifest generation works without ETH address."""
        from cli.hokusai_validate.manifest_generator import ManifestGenerator
        import pandas as pd

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,test\n2,data\n")
            temp_file = f.name

        try:
            generator = ManifestGenerator()
            data = pd.DataFrame({'col1': [1, 2], 'col2': ['test', 'data']})
            validation_results = {'valid': True}
            
            manifest = generator.generate(
                file_path=temp_file,
                data=data,
                validation_results=validation_results,
                data_hash='abc123'
            )

            assert 'contributor_metadata' in manifest
            assert 'wallet_address' not in manifest['contributor_metadata']
        finally:
            Path(temp_file).unlink()