"""
Tests for the main CLI interface
"""
import pytest
from unittest.mock import Mock, patch
from click.testing import CliRunner
import sys
import os

# Add the src directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cli import cli


class TestCLI:
    """Test the main CLI interface"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_cli_exists(self):
        """Test that the CLI command exists"""
        result = self.runner.invoke(cli)
        assert result.exit_code == 0
    
    def test_cli_has_help(self):
        """Test that the CLI provides help information"""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Hokusai Data Pipeline CLI' in result.output
    
    def test_cli_version(self):
        """Test that the CLI provides version information"""
        result = self.runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        assert '0.1.0' in result.output


class TestRunCommand:
    """Test the run command"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_run_command_exists(self):
        """Test that the run command exists"""
        result = self.runner.invoke(cli, ['run', '--help'])
        assert result.exit_code == 0
        assert 'Run the evaluation pipeline' in result.output
    
    @patch('cli.Pipeline')
    def test_run_command_with_config(self, mock_pipeline):
        """Test running with a config file"""
        mock_instance = Mock()
        mock_pipeline.return_value = mock_instance
        
        with self.runner.isolated_filesystem():
            # Create a dummy config file
            with open('config.yaml', 'w') as f:
                f.write('model_path: /path/to/model\n')
            
            result = self.runner.invoke(cli, ['run', '--config', 'config.yaml'])
            assert result.exit_code == 0
            mock_pipeline.assert_called_once()
            mock_instance.run.assert_called_once()
    
    def test_run_command_without_config(self):
        """Test that run command requires a config file"""
        result = self.runner.invoke(cli, ['run'])
        assert result.exit_code != 0
        assert 'Error' in result.output or 'Missing' in result.output


class TestEvaluateCommand:
    """Test the evaluate command"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_evaluate_command_exists(self):
        """Test that the evaluate command exists"""
        result = self.runner.invoke(cli, ['evaluate', '--help'])
        assert result.exit_code == 0
        assert 'Evaluate a model' in result.output
    
    @patch('cli.Evaluator')
    def test_evaluate_command_with_required_args(self, mock_evaluator):
        """Test evaluate command with required arguments"""
        mock_instance = Mock()
        mock_evaluator.return_value = mock_instance
        mock_instance.evaluate.return_value = {'accuracy': 0.95}
        
        result = self.runner.invoke(cli, [
            'evaluate',
            '--model-path', '/path/to/model',
            '--dataset-path', '/path/to/dataset'
        ])
        assert result.exit_code == 0
        mock_evaluator.assert_called_once()
        mock_instance.evaluate.assert_called_once()
    
    def test_evaluate_command_missing_args(self):
        """Test that evaluate command requires necessary arguments"""
        result = self.runner.invoke(cli, ['evaluate'])
        assert result.exit_code != 0


class TestCompareCommand:
    """Test the compare command"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_compare_command_exists(self):
        """Test that the compare command exists"""
        result = self.runner.invoke(cli, ['compare', '--help'])
        assert result.exit_code == 0
        assert 'Compare two models' in result.output
    
    @patch('cli.Comparator')
    def test_compare_command_with_models(self, mock_comparator):
        """Test compare command with two model paths"""
        mock_instance = Mock()
        mock_comparator.return_value = mock_instance
        mock_instance.compare.return_value = {
            'model1_accuracy': 0.93,
            'model2_accuracy': 0.95,
            'improvement': 0.02
        }
        
        result = self.runner.invoke(cli, [
            'compare',
            '--model1', '/path/to/model1',
            '--model2', '/path/to/model2',
            '--dataset', '/path/to/dataset'
        ])
        assert result.exit_code == 0
        mock_comparator.assert_called_once()
        mock_instance.compare.assert_called_once()


class TestStatusCommand:
    """Test the status command"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_status_command_exists(self):
        """Test that the status command exists"""
        result = self.runner.invoke(cli, ['status', '--help'])
        assert result.exit_code == 0
        assert 'Check pipeline status' in result.output
    
    @patch('cli.StatusChecker')
    def test_status_command_shows_status(self, mock_status_checker):
        """Test that status command shows pipeline status"""
        mock_instance = Mock()
        mock_status_checker.return_value = mock_instance
        mock_instance.get_status.return_value = {
            'running': False,
            'last_run': '2024-01-01 12:00:00',
            'status': 'idle'
        }
        
        result = self.runner.invoke(cli, ['status'])
        assert result.exit_code == 0
        mock_status_checker.assert_called_once()
        mock_instance.get_status.assert_called_once()