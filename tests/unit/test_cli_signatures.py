"""Unit tests for CLI signatures commands."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
import json
import yaml
import tempfile
import os

from src.cli.signatures import signatures


class TestSignaturesCLI:
    """Test suite for signatures CLI commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        
    def test_signatures_group(self):
        """Test signatures command group."""
        result = self.runner.invoke(signatures, ['--help'])
        assert result.exit_code == 0
        assert 'Manage DSPy signatures' in result.output
        
    @patch('src.cli.signatures.get_global_registry')
    def test_list_command(self, mock_get_registry):
        """Test list signatures command."""
        # Mock registry
        mock_registry = Mock()
        mock_registry.list_signatures.return_value = ['EmailDraft', 'SummarizeText']
        
        # Mock metadata
        mock_metadata1 = Mock()
        mock_metadata1.category = 'text_generation'
        mock_metadata1.description = 'Generate email drafts'
        mock_metadata1.tags = ['email', 'generation']
        mock_metadata1.version = '1.0.0'
        
        mock_metadata2 = Mock()
        mock_metadata2.category = 'analysis'
        mock_metadata2.description = 'Summarize text content'
        mock_metadata2.tags = ['summary', 'analysis']
        mock_metadata2.version = '1.0.0'
        
        mock_registry.get_metadata.side_effect = [mock_metadata1, mock_metadata2]
        mock_get_registry.return_value = mock_registry
        
        result = self.runner.invoke(signatures, ['list'])
        
        assert result.exit_code == 0
        assert 'EmailDraft' in result.output
        assert 'text_generation' in result.output
        
    @patch('src.cli.signatures.get_global_registry')
    def test_list_with_category_filter(self, mock_get_registry):
        """Test list signatures filtered by category."""
        mock_registry = Mock()
        mock_registry.search.return_value = ['EmailDraft']
        
        mock_metadata = Mock()
        mock_metadata.category = 'text_generation'
        mock_metadata.description = 'Generate email drafts'
        mock_metadata.tags = ['email']
        mock_metadata.version = '1.0.0'
        
        mock_registry.get_metadata.return_value = mock_metadata
        mock_get_registry.return_value = mock_registry
        
        result = self.runner.invoke(signatures, ['list', '--category', 'text_generation'])
        
        assert result.exit_code == 0
        mock_registry.search.assert_called_once_with(category='text_generation', tags=None)
        
    @patch('src.cli.signatures.get_global_registry')
    def test_list_json_format(self, mock_get_registry):
        """Test list signatures with JSON output."""
        mock_registry = Mock()
        mock_registry.list_signatures.return_value = ['EmailDraft']
        
        mock_metadata = Mock()
        mock_metadata.category = 'text_generation'
        mock_metadata.description = 'Generate email drafts'
        mock_metadata.tags = ['email']
        mock_metadata.version = '1.0.0'
        
        mock_registry.get_metadata.return_value = mock_metadata
        mock_get_registry.return_value = mock_registry
        
        result = self.runner.invoke(signatures, ['list', '--format', 'json'])
        
        assert result.exit_code == 0
        output_data = json.loads(result.output)
        assert len(output_data) == 1
        assert output_data[0]['name'] == 'EmailDraft'
        
    @patch('src.cli.signatures.get_global_registry')
    def test_show_command(self, mock_get_registry):
        """Test show signature details."""
        # Mock signature
        mock_field_in = Mock()
        mock_field_in.name = 'recipient'
        mock_field_in.description = 'Email recipient'
        mock_field_in.type_hint = str
        mock_field_in.required = True
        mock_field_in.default = None
        
        mock_field_out = Mock()
        mock_field_out.name = 'email_body'
        mock_field_out.description = 'Generated email body'
        mock_field_out.type_hint = str
        mock_field_out.required = True
        
        mock_signature = Mock()
        mock_signature.input_fields = [mock_field_in]
        mock_signature.output_fields = [mock_field_out]
        
        # Mock metadata
        mock_metadata = Mock()
        mock_metadata.category = 'text_generation'
        mock_metadata.description = 'Generate email drafts'
        mock_metadata.tags = ['email']
        mock_metadata.version = '1.0.0'
        mock_metadata.author = 'Hokusai Team'
        
        mock_registry = Mock()
        mock_registry.get.return_value = mock_signature
        mock_registry.get_metadata.return_value = mock_metadata
        mock_get_registry.return_value = mock_registry
        
        result = self.runner.invoke(signatures, ['show', 'EmailDraft'])
        
        assert result.exit_code == 0
        assert 'EmailDraft' in result.output
        assert 'text_generation' in result.output
        assert 'recipient' in result.output
        assert 'email_body' in result.output
        
    @patch('src.cli.signatures.get_global_registry')
    def test_show_not_found(self, mock_get_registry):
        """Test show signature when not found."""
        mock_registry = Mock()
        mock_registry.get.side_effect = KeyError("Signature not found")
        mock_get_registry.return_value = mock_registry
        
        result = self.runner.invoke(signatures, ['show', 'NonExistent'])
        
        assert result.exit_code == 0
        assert 'not found' in result.output
        
    @patch('src.cli.signatures.SignatureLoader')
    def test_load_command(self, mock_loader_class):
        """Test load signature from file."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'name': 'CustomSignature',
                'type': 'signature',
                'version': '1.0.0',
                'inputs': {
                    'text': {'type': 'str', 'description': 'Input text'}
                },
                'outputs': {
                    'result': {'type': 'str', 'description': 'Result'}
                }
            }, f)
            config_path = f.name
        
        try:
            mock_loader = Mock()
            mock_signature = Mock()
            mock_loader.load_from_yaml.return_value = mock_signature
            mock_loader_class.return_value = mock_loader
            
            result = self.runner.invoke(signatures, ['load', config_path])
            
            assert result.exit_code == 0
            assert 'Successfully loaded signature' in result.output
            
        finally:
            os.unlink(config_path)
            
    @patch('src.cli.signatures.DSPyPipelineExecutor')
    def test_execute_command(self, mock_executor_class):
        """Test execute signature command."""
        # Create input file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'recipient': 'John Doe',
                'subject': 'Meeting Tomorrow'
            }, f)
            input_file = f.name
        
        try:
            mock_executor = Mock()
            mock_result = {'email_body': 'Dear John...'}
            mock_executor.execute_signature.return_value = mock_result
            mock_executor_class.return_value = mock_executor
            
            result = self.runner.invoke(signatures, [
                'execute', 
                'EmailDraft',
                '--input-file', input_file
            ])
            
            assert result.exit_code == 0
            assert 'email_body' in result.output
            
        finally:
            os.unlink(input_file)
            
    @patch('src.cli.signatures.get_global_registry')
    @patch('src.cli.signatures.DSPyPipelineExecutor')
    def test_test_command(self, mock_executor_class, mock_get_registry):
        """Test signature testing command."""
        # Create test file
        test_cases = [
            {
                'input': {'recipient': 'John', 'subject': 'Meeting'},
                'expected': {'email_body': 'Dear John...'}
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_cases, f)
            test_file = f.name
        
        try:
            # Mock registry and signature
            mock_signature = Mock()
            mock_registry = Mock()
            mock_registry.get.return_value = mock_signature
            mock_get_registry.return_value = mock_registry
            
            # Mock executor
            mock_executor = Mock()
            mock_executor.execute_signature.return_value = {'email_body': 'Dear John...'}
            mock_executor_class.return_value = mock_executor
            
            result = self.runner.invoke(signatures, [
                'test',
                'EmailDraft',
                '--test-file', test_file
            ])
            
            assert result.exit_code == 0
            assert 'Test Results' in result.output
            assert 'Passed: 1' in result.output
            
        finally:
            os.unlink(test_file)
            
    def test_invalid_format_option(self):
        """Test invalid format option."""
        result = self.runner.invoke(signatures, ['list', '--format', 'invalid'])
        
        assert result.exit_code != 0
        assert 'Invalid value' in result.output
        
    @patch('src.cli.signatures.get_global_registry')
    def test_show_json_format(self, mock_get_registry):
        """Test show command with JSON format."""
        mock_field = Mock()
        mock_field.name = 'text'
        mock_field.description = 'Input text'
        mock_field.type_hint = str
        mock_field.required = True
        mock_field.default = None
        
        mock_signature = Mock()
        mock_signature.input_fields = [mock_field]
        mock_signature.output_fields = []
        
        mock_metadata = Mock()
        mock_metadata.category = 'analysis'
        mock_metadata.description = 'Analyze text'
        mock_metadata.tags = []
        mock_metadata.version = '1.0.0'
        mock_metadata.author = None
        
        mock_registry = Mock()
        mock_registry.get.return_value = mock_signature
        mock_registry.get_metadata.return_value = mock_metadata
        mock_get_registry.return_value = mock_registry
        
        result = self.runner.invoke(signatures, ['show', 'AnalyzeText', '--format', 'json'])
        
        assert result.exit_code == 0
        output_data = json.loads(result.output)
        assert output_data['name'] == 'AnalyzeText'
        assert output_data['category'] == 'analysis'