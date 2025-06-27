"""Unit tests for DSPy configuration parser."""

import pytest
import yaml
import json
from pathlib import Path
import tempfile

from src.services.dspy.config_parser import DSPyConfigParser


class TestDSPyConfigParser:
    """Test suite for DSPy configuration parser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DSPyConfigParser()
        self.temp_dir = tempfile.mkdtemp()
        
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
        
    def test_parse_valid_yaml_config(self):
        """Test parsing a valid YAML configuration."""
        config = {
            "name": "test-dspy-model",
            "version": "1.0.0",
            "source": {
                "type": "local",
                "path": "./models/test.py"
            }
        }
        
        # Write to temp file
        config_path = Path(self.temp_dir) / "config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
            
        # Parse
        result = self.parser.parse_yaml(config_path)
        
        assert result["name"] == "test-dspy-model"
        assert result["version"] == "1.0.0"
        assert result["source"]["type"] == "local"
        
    def test_parse_yaml_with_signatures(self):
        """Test parsing YAML with signature definitions."""
        config = {
            "name": "test-model",
            "version": "1.0",
            "source": {"type": "local", "path": "test.py"},
            "signatures": {
                "text_gen": {
                    "inputs": ["prompt"],
                    "outputs": ["text"],
                    "description": "Generate text"
                }
            }
        }
        
        config_path = Path(self.temp_dir) / "sig_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
            
        result = self.parser.parse_yaml(config_path)
        
        assert "signatures" in result
        assert "text_gen" in result["signatures"]
        assert result["signatures"]["text_gen"]["inputs"] == ["prompt"]
        
    def test_parse_json_config(self):
        """Test parsing JSON configuration."""
        config = {
            "name": "json-model",
            "version": "2.0",
            "source": {
                "type": "huggingface",
                "repo_id": "test/model",
                "filename": "model.py"
            }
        }
        
        config_path = Path(self.temp_dir) / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
            
        result = self.parser.parse_json(config_path)
        
        assert result["name"] == "json-model"
        assert result["source"]["type"] == "huggingface"
        
    def test_missing_required_fields(self):
        """Test validation catches missing required fields."""
        config = {
            "name": "incomplete-model"
            # Missing version and source
        }
        
        config_path = Path(self.temp_dir) / "bad_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
            
        with pytest.raises(ValueError, match="Missing required fields"):
            self.parser.parse_yaml(config_path)
            
    def test_invalid_source_type(self):
        """Test validation catches invalid source type."""
        config = {
            "name": "test",
            "version": "1.0",
            "source": {
                "type": "invalid_type"
            }
        }
        
        config_path = Path(self.temp_dir) / "invalid_source.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
            
        with pytest.raises(ValueError, match="Invalid source type"):
            self.parser.parse_yaml(config_path)
            
    def test_process_chains(self):
        """Test processing chain definitions."""
        config = {
            "name": "chain-model",
            "version": "1.0",
            "source": {"type": "local", "path": "test.py"},
            "chains": {
                "main": {
                    "steps": ["step1", "step2"],
                    "description": "Main processing chain"
                }
            }
        }
        
        result = self.parser.parse_python_config(config)
        
        assert "chains" in result
        assert "main" in result["chains"]
        assert result["chains"]["main"]["steps"] == ["step1", "step2"]
        
    def test_file_not_found(self):
        """Test handling of missing configuration file."""
        with pytest.raises(FileNotFoundError):
            self.parser.parse_yaml("nonexistent.yaml")
            
    def test_invalid_yaml(self):
        """Test handling of invalid YAML syntax."""
        config_path = Path(self.temp_dir) / "invalid.yaml"
        with open(config_path, 'w') as f:
            f.write("invalid: yaml: content: [")
            
        with pytest.raises(ValueError, match="Invalid YAML"):
            self.parser.parse_yaml(config_path)
            
    def test_create_example_config(self):
        """Test creating an example configuration file."""
        example_path = Path(self.temp_dir) / "example.yaml"
        self.parser.create_example_config(example_path)
        
        assert example_path.exists()
        
        # Load and validate the example
        result = self.parser.parse_yaml(example_path)
        assert result["name"] == "example-dspy-model"
        assert "signatures" in result
        assert "chains" in result