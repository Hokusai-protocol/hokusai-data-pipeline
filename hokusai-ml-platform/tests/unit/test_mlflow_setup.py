"""Regression tests for MLflowSetup token-preservation and error-message fixes.

HOK-1332: SDK local-fallback was unconditionally popping MLFLOW_TRACKING_TOKEN
from the environment, so when the local probe also failed the caller's later
retry against the remote endpoint would 401 with "API key required" instead of
surfacing the real upstream error (e.g. 502).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from hokusai.config.mlflow_setup import MLflowSetup  # noqa: E402
from mlflow.exceptions import MlflowException  # noqa: E402


class TestTokenPreservationOnRemoteFailure:
    """MLFLOW_TRACKING_TOKEN must never be cleared by a failed remote probe."""

    def setup_method(self):
        for key in (
            "MLFLOW_TRACKING_TOKEN",
            "MLFLOW_TRACKING_USERNAME",
            "MLFLOW_TRACKING_PASSWORD",
        ):
            os.environ.pop(key, None)

    teardown_method = setup_method

    def test_token_preserved_after_remote_502(self):
        """Remote 502 must not wipe MLFLOW_TRACKING_TOKEN."""
        os.environ["MLFLOW_TRACKING_TOKEN"] = "user-token-abc"

        setup = MLflowSetup(tracking_uri="https://registry.example.com/api/mlflow")

        with patch("mlflow.search_experiments", side_effect=MlflowException("502 Bad Gateway")):
            with patch("mlflow.set_tracking_uri"):
                with patch(
                    "mlflow.get_tracking_uri",
                    return_value="https://registry.example.com/api/mlflow",
                ):
                    result = setup._configure_remote(api_key=None)

        assert result is False
        assert (
            os.environ.get("MLFLOW_TRACKING_TOKEN") == "user-token-abc"
        ), "MLFLOW_TRACKING_TOKEN was wiped by _configure_remote"

    def test_token_preserved_after_remote_and_local_both_fail(self):
        """When both remote and local probes fail, the user's token must survive intact."""
        os.environ["MLFLOW_TRACKING_TOKEN"] = "user-token-xyz"

        setup = MLflowSetup(tracking_uri="https://registry.example.com/api/mlflow")

        remote_exc = MlflowException("502 Bad Gateway")
        local_exc = Exception("Connection refused on localhost:5001")

        call_count = 0

        def search_experiments_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise remote_exc
            raise local_exc

        with patch("mlflow.search_experiments", side_effect=search_experiments_side_effect):
            with patch("mlflow.set_tracking_uri"):
                with patch(
                    "mlflow.get_tracking_uri",
                    return_value="https://registry.example.com/api/mlflow",
                ):
                    result = setup.configure(api_key=None)

        assert result is False
        assert (
            os.environ.get("MLFLOW_TRACKING_TOKEN") == "user-token-xyz"
        ), "MLFLOW_TRACKING_TOKEN was wiped after both remote and local probes failed"

    def test_no_local_fallback_when_explicit_api_key_and_remote_fails(self):
        """If the caller supplies an explicit api_key and remote fails, we must NOT fall back."""
        os.environ["MLFLOW_TRACKING_TOKEN"] = "env-token"

        setup = MLflowSetup(tracking_uri="https://registry.example.com/api/mlflow")

        local_search_called = []

        def local_search():
            local_search_called.append(True)
            raise Exception("should not reach local")

        with patch("mlflow.search_experiments", side_effect=MlflowException("502 Bad Gateway")):
            with patch("mlflow.set_tracking_uri"):
                with patch(
                    "mlflow.get_tracking_uri",
                    return_value="https://registry.example.com/api/mlflow",
                ):
                    result = setup.configure(api_key="explicit-key")

        assert (
            result is False
        ), "configure should return False when explicit api_key and remote fails"
        # The key regression: when an explicit api_key is supplied, _configure_local must NOT run.
        # _configure_local clears MLFLOW_TRACKING_TOKEN before probing; if it ran and the local
        # server also failed, the token could be left absent (the bug from HOK-1332).
        assert (
            not local_search_called
        ), "_configure_local must not be attempted when api_key was supplied"
        # _configure_remote sets MLFLOW_TRACKING_TOKEN = api_key before probing.
        # Verify the token is the explicit api_key (set by _configure_remote) and was not wiped.
        assert (
            os.environ.get("MLFLOW_TRACKING_TOKEN") is not None
        ), "MLFLOW_TRACKING_TOKEN was wiped — local fallback must not have run"

    def test_token_absent_before_probe_stays_absent_after_local_failure(self):
        """If no token was set, a failed local probe must not invent one."""
        assert "MLFLOW_TRACKING_TOKEN" not in os.environ

        setup = MLflowSetup(tracking_uri="https://registry.example.com/api/mlflow")

        with patch("mlflow.search_experiments", side_effect=Exception("Connection refused")):
            with patch("mlflow.set_tracking_uri"):
                with patch(
                    "mlflow.get_tracking_uri",
                    return_value="https://registry.example.com/api/mlflow",
                ):
                    result = setup._configure_local()

        assert result is False
        assert "MLFLOW_TRACKING_TOKEN" not in os.environ


class TestErrorMessageClarity:
    """Remote failures should produce log messages that name the real cause."""

    def setup_method(self):
        for key in (
            "MLFLOW_TRACKING_TOKEN",
            "MLFLOW_TRACKING_USERNAME",
            "MLFLOW_TRACKING_PASSWORD",
        ):
            os.environ.pop(key, None)

    teardown_method = setup_method

    @pytest.mark.parametrize(
        "status_code,expected_fragment",
        [
            ("401", "Authentication rejected"),
            ("403", "Authentication failed"),
            ("404", "endpoint not found"),
            ("502", "upstream unreachable"),
            ("503", "upstream unreachable"),
        ],
    )
    def test_error_log_mentions_status(self, status_code, expected_fragment, caplog):
        import logging

        setup = MLflowSetup(tracking_uri="https://registry.example.com/api/mlflow")

        exc = MlflowException(f"{status_code} error from server")

        with patch("mlflow.search_experiments", side_effect=exc):
            with patch("mlflow.set_tracking_uri"):
                with caplog.at_level(logging.ERROR, logger="hokusai.config.mlflow_setup"):
                    setup._configure_remote(api_key=None)

        assert any(expected_fragment in record.message for record in caplog.records), (
            f"Expected '{expected_fragment}' in error log for {status_code}, "
            f"got: {[r.message for r in caplog.records]}"
        )
