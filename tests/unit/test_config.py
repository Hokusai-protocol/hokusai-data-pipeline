"""Tests for configuration management."""

import pytest
import os
from pathlib import Path

from src.utils.config import PipelineConfig, get_config, get_test_config


class TestPipelineConfig:
    """Test PipelineConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = PipelineConfig()
        
        assert config.environment == "development"
        assert config.log_level == "INFO"
        assert config.dry_run is False
        assert config.random_seed == 42
        assert config.batch_size == 1000
        assert isinstance(config.evaluation_metrics, list)
        assert "accuracy" in config.evaluation_metrics
    
    def test_env_override(self, monkeypatch):
        """Test environment variable overrides."""
        monkeypatch.setenv("PIPELINE_ENV", "production")
        monkeypatch.setenv("PIPELINE_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("RANDOM_SEED", "123")
        
        config = PipelineConfig()
        
        assert config.environment == "production"
        assert config.log_level == "DEBUG"
        assert config.dry_run is True
        assert config.random_seed == 123
    
    def test_directory_creation(self, temp_dir):
        """Test that directories are created."""
        data_dir = temp_dir / "data"
        model_dir = temp_dir / "models"
        
        config = PipelineConfig()
        config.data_dir = data_dir
        config.model_dir = model_dir
        config.__post_init__()
        
        assert data_dir.exists()
        assert model_dir.exists()
    
    def test_to_dict(self):
        """Test configuration serialization."""
        config = PipelineConfig()
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert "environment" in config_dict
        assert "random_seed" in config_dict
        assert config_dict["random_seed"] == 42
        assert isinstance(config_dict["data_dir"], str)


class TestConfigHelpers:
    """Test configuration helper functions."""
    
    def test_get_config(self):
        """Test get_config returns PipelineConfig."""
        config = get_config()
        assert isinstance(config, PipelineConfig)
    
    def test_get_test_config(self):
        """Test get_test_config returns test configuration."""
        config = get_test_config()
        
        assert isinstance(config, PipelineConfig)
        assert config.dry_run is True
        assert config.environment == "test"
        assert "test_fixtures" in str(config.data_dir)