"""Tests for Trace Loader Service."""

import pytest
from unittest.mock import Mock, patch, call
from datetime import datetime, timedelta

from src.services.trace_loader import TraceLoader


@pytest.fixture
def sample_runs():
    """Create sample MLflow runs for testing."""
    runs = []
    for i in range(20):
        run = Mock()
        run.info.run_id = f"run_{i}"
        run.info.start_time = int((datetime.now() - timedelta(days=i)).timestamp() * 1000)
        
        # Set tags
        run.data.tags = {
            "contributor_id": f"contrib_{i % 3}",
            "contributor_address": f"0x{i % 3:040x}",
            "dspy_program_name": "TestProgram" if i % 2 == 0 else "OtherProgram",
            "has_dspy_traces": "true"
        }
        
        # Set metrics
        run.data.metrics = {
            "outcome_score": 0.7 + (i % 5) * 0.05,
            "reply_rate": 0.1 + (i % 4) * 0.02
        }
        
        # Set params (inputs/outputs)
        run.data.params = {
            "input.text": f"Input text {i}",
            "input.prompt": f"Prompt {i}",
            "output.result": f"Result {i}",
            "output.score": str(0.8 + (i % 3) * 0.05)
        }
        
        runs.append(run)
    
    return runs


class TestTraceLoader:
    """Test the TraceLoader service."""
    
    def test_initialization(self):
        """Test trace loader initialization."""
        loader = TraceLoader()
        assert hasattr(loader, 'client')
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_load_traces_basic(self, mock_client_class, sample_runs):
        """Test basic trace loading."""
        # Setup mock
        mock_client = Mock()
        mock_client.search_runs.return_value = sample_runs[:10]
        mock_client.search_experiments.return_value = []  # Return empty list for experiments
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        traces = loader.load_traces()
        
        assert len(traces) == 10
        mock_client.search_runs.assert_called_once()
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_load_traces_with_filters(self, mock_client_class, sample_runs):
        """Test trace loading with filters."""
        # Setup mock
        mock_client = Mock()
        mock_client.search_runs.return_value = sample_runs[:5]
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
        
        traces = loader.load_traces(
            program_name="TestProgram",
            start_date=start_date,
            end_date=end_date,
            min_score=0.75,
            outcome_metric="reply_rate",
            limit=100
        )
        
        # Check that search was called with filters
        call_args = mock_client.search_runs.call_args
        filter_string = call_args[1]['filter_string']
        
        assert "tags.has_dspy_traces = 'true'" in filter_string
        assert "tags.dspy_program_name = 'TestProgram'" in filter_string
        assert "metrics.reply_rate >= 0.75" in filter_string
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_parse_trace_data(self, mock_client_class, sample_runs):
        """Test trace data parsing."""
        # Setup mock with one run
        mock_client = Mock()
        mock_client.search_runs.return_value = [sample_runs[0]]
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        traces = loader.load_traces()
        
        assert len(traces) == 1
        trace = traces[0]
        
        # Check trace structure
        assert "trace_id" in trace
        assert trace["trace_id"] == "run_0"
        assert "contributor_id" in trace
        assert trace["contributor_id"] == "contrib_0"
        assert "contributor_address" in trace
        assert "timestamp" in trace
        assert isinstance(trace["timestamp"], datetime)
        assert "outcome_score" in trace
        assert trace["outcome_score"] == 0.7
        
        # Check inputs/outputs
        assert "inputs" in trace
        assert trace["inputs"]["text"] == "Input text 0"
        assert trace["inputs"]["prompt"] == "Prompt 0"
        assert "outputs" in trace
        assert trace["outputs"]["result"] == "Result 0"
        assert trace["outputs"]["score"] == "0.8"
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_experiment_name_filter(self, mock_client_class, sample_runs):
        """Test filtering by experiment name."""
        # Setup mock
        mock_client = Mock()
        mock_client.search_runs.return_value = sample_runs[:3]
        mock_client.get_experiment_by_name.return_value = Mock(experiment_id="exp_123")
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        traces = loader.load_traces(experiment_name="test_experiment")
        
        # Check experiment lookup
        mock_client.get_experiment_by_name.assert_called_once_with("test_experiment")
        
        # Check search was called with experiment ID
        call_args = mock_client.search_runs.call_args
        assert call_args[1]['experiment_ids'] == ["exp_123"]
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_empty_results(self, mock_client_class):
        """Test handling of empty results."""
        # Setup mock
        mock_client = Mock()
        mock_client.search_runs.return_value = []
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        traces = loader.load_traces()
        
        assert traces == []
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_missing_outcome_metric(self, mock_client_class):
        """Test handling of missing outcome metric."""
        # Create run without outcome metric
        run = Mock()
        run.info.run_id = "run_missing"
        run.info.start_time = int(datetime.now().timestamp() * 1000)
        run.data.tags = {
            "contributor_id": "contrib_1",
            "has_dspy_traces": "true"
        }
        run.data.metrics = {"other_metric": 0.5}  # No outcome_score
        run.data.params = {}
        
        mock_client = Mock()
        mock_client.search_runs.return_value = [run]
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        traces = loader.load_traces()
        
        # Should still return the trace but with outcome_score = 0
        assert len(traces) == 1
        assert traces[0]["outcome_score"] == 0
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_date_filtering(self, mock_client_class, sample_runs):
        """Test date range filtering."""
        # Setup mock
        mock_client = Mock()
        mock_client.search_runs.return_value = sample_runs[:5]
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now() - timedelta(days=5)
        
        traces = loader.load_traces(
            start_date=start_date,
            end_date=end_date
        )
        
        # Check date filter in search
        call_args = mock_client.search_runs.call_args
        filter_string = call_args[1]['filter_string']
        
        # Should contain timestamp filters
        assert "attributes.start_time >=" in filter_string
        assert "attributes.start_time <=" in filter_string
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_limit_and_ordering(self, mock_client_class, sample_runs):
        """Test limit and ordering of results."""
        # Setup mock
        mock_client = Mock()
        mock_client.search_runs.return_value = sample_runs
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        traces = loader.load_traces(limit=5)
        
        # Check max_results parameter
        call_args = mock_client.search_runs.call_args
        assert call_args[1]['max_results'] == 5
        
        # Check order by parameter (should order by outcome score desc)
        assert call_args[1]['order_by'] == ["metrics.outcome_score DESC"]
    
    @patch('src.services.trace_loader.MlflowClient')
    def test_error_handling(self, mock_client_class):
        """Test error handling in trace loading."""
        # Setup mock to raise exception
        mock_client = Mock()
        mock_client.search_runs.side_effect = Exception("MLflow error")
        mock_client.search_experiments.return_value = []
        mock_client_class.return_value = mock_client
        
        loader = TraceLoader()
        
        # Should handle error and return empty list
        traces = loader.load_traces()
        assert traces == []
    
    def test_build_filter_string(self):
        """Test filter string building."""
        loader = TraceLoader()
        
        # Test with all parameters
        filter_string = loader._build_filter_string(
            program_name="TestProgram",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 15),
            min_score=0.8,
            outcome_metric="engagement_score"
        )
        
        assert "tags.has_dspy_traces = 'true'" in filter_string
        assert "tags.dspy_program_name = 'TestProgram'" in filter_string
        assert "metrics.engagement_score >= 0.8" in filter_string
        assert "attributes.start_time >=" in filter_string
        assert "attributes.start_time <=" in filter_string
    
    def test_parse_inputs_outputs(self):
        """Test parsing of inputs and outputs from params."""
        loader = TraceLoader()
        
        params = {
            "input.text": "Hello",
            "input.prompt": "Write a greeting",
            "output.response": "Hi there!",
            "output.confidence": "0.95",
            "other_param": "ignored"
        }
        
        inputs, outputs = loader._parse_inputs_outputs(params)
        
        assert inputs == {
            "text": "Hello",
            "prompt": "Write a greeting"
        }
        
        assert outputs == {
            "response": "Hi there!",
            "confidence": "0.95"
        }