"""Unit tests for src/cli/_api.py."""

import json
import os
import sys
from unittest.mock import MagicMock, patch
from urllib import error as urllib_error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from src.cli._api import BenchmarkSpecLookupError, fetch_benchmark_spec

SAMPLE_SPEC = {
    "id": "bs-abc123",
    "model_id": "XRAY",
    "metric_name": "auroc",
    "metric_direction": "maximize",
    "baseline_value": 0.82,
    "is_active": True,
}


def _make_urlopen_response(data: dict, status: int = 200):
    """Return a mock context manager for urllib.request.urlopen."""
    body = json.dumps(data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestFetchBenchmarkSpec:
    def test_happy_path_builds_correct_request_and_returns_parsed_json(self):
        with patch("src.cli._api.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(SAMPLE_SPEC)
            with patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}):
                result = fetch_benchmark_spec("bs-abc123", api_url="http://localhost:8001")

        assert result["model_id"] == "XRAY"
        assert result["baseline_value"] == 0.82

        # Verify correct URL was used
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.full_url == "http://localhost:8001/api/v1/benchmarks/bs-abc123"
        assert req.get_header("Authorization") == "Bearer test-key"

    def test_missing_api_key_raises_error(self):
        env = {k: v for k, v in os.environ.items() if k != "HOKUSAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(BenchmarkSpecLookupError, match="HOKUSAI_API_KEY is not set"):
                fetch_benchmark_spec("bs-abc123")

    def test_404_raises_not_found_error(self):
        http_error = urllib_error.HTTPError(
            url="http://localhost:8001/api/v1/benchmarks/bs-abc123",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with patch("src.cli._api.request.urlopen", side_effect=http_error):
            with patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}):
                with pytest.raises(BenchmarkSpecLookupError, match="not found"):
                    fetch_benchmark_spec("bs-abc123")

    def test_401_raises_auth_error(self):
        http_error = urllib_error.HTTPError(
            url="http://localhost:8001/api/v1/benchmarks/bs-abc123",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        with patch("src.cli._api.request.urlopen", side_effect=http_error):
            with patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}):
                with pytest.raises(BenchmarkSpecLookupError, match="Authentication failed"):
                    fetch_benchmark_spec("bs-abc123")

    def test_403_raises_auth_error(self):
        http_error = urllib_error.HTTPError(
            url="http://localhost:8001/api/v1/benchmarks/bs-abc123",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        with patch("src.cli._api.request.urlopen", side_effect=http_error):
            with patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}):
                with pytest.raises(BenchmarkSpecLookupError, match="Authentication failed"):
                    fetch_benchmark_spec("bs-abc123")

    def test_connection_error_raises_lookup_error(self):
        url_error = urllib_error.URLError(reason="Connection refused")
        with patch("src.cli._api.request.urlopen", side_effect=url_error):
            with patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}):
                with pytest.raises(BenchmarkSpecLookupError, match="Could not reach Hokusai API"):
                    fetch_benchmark_spec("bs-abc123", api_url="http://localhost:8001")

    def test_api_key_from_explicit_kwarg(self):
        with patch("src.cli._api.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(SAMPLE_SPEC)
            env = {k: v for k, v in os.environ.items() if k != "HOKUSAI_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                # Should not raise even without env var because explicit key is provided
                result = fetch_benchmark_spec(
                    "bs-abc123",
                    api_url="http://localhost:8001",
                    api_key="explicit-key",
                )
        assert result["id"] == "bs-abc123"
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer explicit-key"

    def test_api_url_trailing_slash_stripped(self):
        with patch("src.cli._api.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(SAMPLE_SPEC)
            with patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}):
                fetch_benchmark_spec("bs-abc123", api_url="http://localhost:8001/")
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8001/api/v1/benchmarks/bs-abc123"

    def test_api_url_from_env(self):
        with patch("src.cli._api.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _make_urlopen_response(SAMPLE_SPEC)
            with patch.dict(
                os.environ,
                {"HOKUSAI_API_KEY": "test-key", "HOKUSAI_API_URL": "http://custom:9999"},
            ):
                fetch_benchmark_spec("bs-abc123")
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://custom:9999/api/v1/benchmarks/bs-abc123"
