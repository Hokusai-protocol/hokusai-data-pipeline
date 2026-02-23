"""Unit tests for OpenAIEvalsAdapter."""

import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from src.evals import OpenAIEvalsAdapter


def _mock_run_context(mock_start_run: Mock, run_id: str = "run-123") -> None:
    run = Mock()
    run.info.run_id = run_id
    mock_start_run.return_value.__enter__ = Mock(return_value=run)
    mock_start_run.return_value.__exit__ = Mock(return_value=None)


@patch("src.evals.openai_adapter.mlflow.set_tracking_uri")
@patch("src.evals.openai_adapter.mlflow.set_experiment")
def test_init_sets_experiment_when_provided(mock_set_experiment: Mock, mock_set_uri: Mock) -> None:
    with patch.dict(os.environ, {"MLFLOW_TRACKING_TOKEN": "test-token"}):
        OpenAIEvalsAdapter(experiment_name="openai-evals")
    mock_set_uri.assert_called_once()
    mock_set_experiment.assert_called_once_with("openai-evals")


@patch("src.evals.openai_adapter.subprocess.run")
@patch("src.evals.openai_adapter.shutil.which", return_value="/usr/local/bin/oaieval")
@patch("src.evals.openai_adapter.mlflow.start_run")
@patch("src.evals.openai_adapter.mlflow.log_metrics")
@patch("src.evals.openai_adapter.mlflow.log_text")
@patch("src.evals.openai_adapter.mlflow.set_tag")
@patch("src.evals.openai_adapter.mlflow.set_tracking_uri")
def test_run_success_logs_metrics_and_tags(
    mock_set_uri: Mock,
    mock_set_tag: Mock,
    mock_log_text: Mock,
    mock_log_metrics: Mock,
    mock_start_run: Mock,
    mock_which: Mock,
    mock_subprocess_run: Mock,
) -> None:
    _mock_run_context(mock_start_run, run_id="abc123")
    mock_subprocess_run.return_value = subprocess.CompletedProcess(
        args=["oaieval", "gpt-4.1-mini", "test.eval"],
        returncode=0,
        stdout='{"final_report":{"accuracy":0.91,"f1":0.88}}\n',
        stderr="",
    )

    adapter = OpenAIEvalsAdapter(experiment_name="evals")
    run_id = adapter.run(
        eval_spec="test.eval",
        model_ref="gpt-4.1-mini",
        tags={"team": "evals", "purpose": "regression"},
    )

    assert run_id == "abc123"
    mock_subprocess_run.assert_called_once_with(
        ["/usr/local/bin/oaieval", "gpt-4.1-mini", "test.eval"],
        check=True,
        capture_output=True,
        text=True,
    )
    mock_which.assert_called_once_with("oaieval")
    mock_log_metrics.assert_called_once_with({"accuracy": 0.91, "f1": 0.88})
    mock_log_text.assert_called_once_with(
        '{"final_report":{"accuracy":0.91,"f1":0.88}}\n',
        "output.txt",
    )
    mock_set_tag.assert_any_call("eval:provider", "openai_evals")
    mock_set_tag.assert_any_call("eval:spec", "test.eval")
    mock_set_tag.assert_any_call("eval:model_ref", "gpt-4.1-mini")
    mock_set_tag.assert_any_call("eval:status", "success")
    mock_set_tag.assert_any_call("team", "evals")
    mock_set_tag.assert_any_call("purpose", "regression")
    mock_set_uri.assert_called_once()


@patch("src.evals.openai_adapter.shutil.which", return_value=None)
@patch("src.evals.openai_adapter.mlflow.set_tracking_uri")
def test_run_raises_when_oaieval_missing(mock_set_uri: Mock, mock_which: Mock) -> None:
    adapter = OpenAIEvalsAdapter()
    with pytest.raises(RuntimeError, match="CLI not found"):
        adapter.run(eval_spec="test.eval", model_ref="gpt-4.1-mini")
    mock_which.assert_called_once_with("oaieval")
    mock_set_uri.assert_called_once()


@patch("src.evals.openai_adapter.subprocess.run")
@patch("src.evals.openai_adapter.shutil.which", return_value="/usr/local/bin/oaieval")
@patch("src.evals.openai_adapter.mlflow.start_run")
@patch("src.evals.openai_adapter.mlflow.log_metric")
@patch("src.evals.openai_adapter.mlflow.log_text")
@patch("src.evals.openai_adapter.mlflow.set_tag")
@patch("src.evals.openai_adapter.mlflow.set_tracking_uri")
def test_run_logs_failure_and_raises_on_non_zero_exit(
    mock_set_uri: Mock,
    mock_set_tag: Mock,
    mock_log_text: Mock,
    mock_log_metric: Mock,
    mock_start_run: Mock,
    mock_which: Mock,
    mock_subprocess_run: Mock,
) -> None:
    _mock_run_context(mock_start_run, run_id="failed123")
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=2,
        cmd=["oaieval", "gpt-4.1-mini", "bad.eval"],
        output="",
        stderr="bad eval config",
    )

    adapter = OpenAIEvalsAdapter()
    with pytest.raises(RuntimeError, match="exit code 2"):
        adapter.run(eval_spec="bad.eval", model_ref="gpt-4.1-mini", tags={"env": "test"})

    mock_which.assert_called_once_with("oaieval")
    mock_log_metric.assert_called_once_with("parsed_metric_count", 0.0)
    mock_log_text.assert_called_once_with("bad eval config", "output.txt")
    mock_set_tag.assert_any_call("eval:status", "failed")
    mock_set_tag.assert_any_call("eval:error", "bad eval config")
    mock_set_tag.assert_any_call("env", "test")
    mock_set_uri.assert_called_once()


@patch("src.evals.openai_adapter.mlflow.set_tracking_uri")
def test_parse_results_supports_json_lines_and_text_fallback(_mock_set_uri: Mock) -> None:
    adapter = OpenAIEvalsAdapter()

    metrics_from_json = adapter._parse_results(
        "\n".join(
            [
                '{"record_type":"sample","accuracy":0.3}',
                '{"final_report":{"accuracy":0.95,"f1":0.89,"ignored":"x"}}',
            ]
        )
    )
    assert metrics_from_json == {"accuracy": 0.95, "f1": 0.89}

    metrics_from_text = adapter._parse_results("accuracy: 0.72\nf1=0.67\nnote=pass")
    assert metrics_from_text == {"accuracy": 0.72, "f1": 0.67}


@patch("src.evals.openai_adapter.mlflow.set_tracking_uri")
def test_run_rejects_shell_metacharacters(_mock_set_uri: Mock) -> None:
    adapter = OpenAIEvalsAdapter()
    with pytest.raises(ValueError, match="metacharacters"):
        adapter.run(eval_spec="suite; rm -rf /", model_ref="gpt-4.1-mini")
