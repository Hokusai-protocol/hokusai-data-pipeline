"""Unit tests for benchmark dataset upload endpoint."""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.api.main import app
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.benchmark_specs import BenchmarkSpecService
from src.api.services.privacy.pii_detector import PIIDetector, PIIScanResult
from src.middleware.auth import require_auth


async def _passthrough_middleware_dispatch(self: Any, request: Request, call_next: Any) -> Response:
    request.state.user_id = "test-user"
    request.state.api_key_id = "key-1"
    request.state.service_id = "test"
    request.state.scopes = []
    request.state.rate_limit_per_hour = None
    return await call_next(request)


def _make_authed_client() -> tuple[TestClient, MagicMock, MagicMock, MagicMock]:
    mock_service = MagicMock(spec=BenchmarkSpecService)
    mock_audit = MagicMock(spec=AuditLogger)
    mock_pii = MagicMock(spec=PIIDetector)

    from src.api.dependencies import get_audit_logger, get_benchmark_spec_service, get_pii_detector

    app.dependency_overrides[get_benchmark_spec_service] = lambda: mock_service
    app.dependency_overrides[get_audit_logger] = lambda: mock_audit
    app.dependency_overrides[get_pii_detector] = lambda: mock_pii

    return TestClient(app, raise_server_exceptions=False), mock_service, mock_audit, mock_pii


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


CSV_CONTENT = b"input,expected_output\nhello,world\nfoo,bar\n"
CSV_HASH = hashlib.sha256(CSV_CONTENT).hexdigest()


class TestUploadCSV:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_upload_csv_returns_201(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            svc.upload_dataset.return_value = {
                "s3_uri": "s3://test-bucket/datasets/model-1/v1/test.csv",
                "sha256_hash": CSV_HASH,
                "spec_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "filename": "test.csv",
                "file_size_bytes": len(CSV_CONTENT),
            }
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("test.csv", CSV_CONTENT, "text/csv")},
                data={
                    "eval_split": "test",
                    "metric_name": "accuracy",
                    "metric_direction": "higher_is_better",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["s3_uri"].startswith("s3://")
            assert body["sha256_hash"] == CSV_HASH
            assert body["spec_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            assert body["filename"] == "test.csv"
            assert body["file_size_bytes"] == len(CSV_CONTENT)
            svc.upload_dataset.assert_called_once()
            audit.log.assert_called_once()
        finally:
            _cleanup_overrides()


class TestUploadParquet:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_upload_parquet_returns_201(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            parquet_bytes = b"PAR1fake-parquet-content"
            svc.upload_dataset.return_value = {
                "s3_uri": "s3://test-bucket/datasets/model-1/v1/test.parquet",
                "sha256_hash": hashlib.sha256(parquet_bytes).hexdigest(),
                "spec_id": "11111111-2222-3333-4444-555555555555",
                "filename": "test.parquet",
                "file_size_bytes": len(parquet_bytes),
            }
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("test.parquet", parquet_bytes, "application/octet-stream")},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["filename"] == "test.parquet"
        finally:
            _cleanup_overrides()


class TestUploadPIIDetection:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_pii_detected_returns_422(self) -> None:
        from src.api.services.governance.benchmark_specs import PIIFoundError

        client, svc, audit, pii = _make_authed_client()
        try:
            svc.upload_dataset.side_effect = PIIFoundError(
                "PII detected in uploaded dataset: 3 finding(s). Set allow_pii=true to proceed."
            )
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("data.csv", CSV_CONTENT, "text/csv")},
            )
            assert resp.status_code == 422
            assert "PII detected" in resp.json()["detail"]
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_pii_allowed_returns_201(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            svc.upload_dataset.return_value = {
                "s3_uri": "s3://test-bucket/datasets/model-1/v1/pii.csv",
                "sha256_hash": CSV_HASH,
                "spec_id": "aaaaaaaa-1111-2222-3333-444444444444",
                "filename": "pii.csv",
                "file_size_bytes": len(CSV_CONTENT),
            }
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("pii.csv", CSV_CONTENT, "text/csv")},
                data={"allow_pii": "true"},
            )
            assert resp.status_code == 201
            call_kwargs = svc.upload_dataset.call_args
            assert call_kwargs.kwargs["allow_pii"] is True
        finally:
            _cleanup_overrides()


class TestUploadInvalidFile:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_json_file_rejected_with_400(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("data.json", b'{"a":1}', "application/json")},
            )
            assert resp.status_code == 400
            assert "Only CSV and Parquet" in resp.json()["detail"]
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_no_extension_rejected_with_400(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("datafile", CSV_CONTENT, "text/plain")},
            )
            assert resp.status_code == 400
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_uppercase_csv_accepted(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            svc.upload_dataset.return_value = {
                "s3_uri": "s3://test-bucket/datasets/model-1/v1/DATA.CSV",
                "sha256_hash": CSV_HASH,
                "spec_id": "aaaaaaaa-1111-2222-3333-555555555555",
                "filename": "DATA.CSV",
                "file_size_bytes": len(CSV_CONTENT),
            }
            resp = client.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("DATA.CSV", CSV_CONTENT, "text/csv")},
            )
            assert resp.status_code == 201
        finally:
            _cleanup_overrides()


class TestUploadOversizedFile:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_oversized_file_returns_413(self) -> None:
        client, svc, audit, pii = _make_authed_client()
        try:
            with patch("src.api.routes.benchmarks.MAX_UPLOAD_SIZE_BYTES", 10):
                resp = client.post(
                    "/api/v1/benchmarks/upload/model-1",
                    files={"file": ("big.csv", b"a" * 100, "text/csv")},
                )
            assert resp.status_code == 413
            assert "maximum upload size" in resp.json()["detail"]
        finally:
            _cleanup_overrides()


class TestUploadAuth:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_upload_returns_401_when_auth_fails(self) -> None:
        """require_auth raises 401 when overridden to reject."""
        from fastapi import HTTPException

        async def _reject_auth(request: Request) -> dict[str, Any]:
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[require_auth] = _reject_auth
        try:
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post(
                "/api/v1/benchmarks/upload/model-1",
                files={"file": ("test.csv", CSV_CONTENT, "text/csv")},
            )
            assert resp.status_code == 401
        finally:
            _cleanup_overrides()

    def test_upload_route_has_require_auth(self) -> None:
        import inspect

        from src.api.routes.benchmarks import router as benchmarks_router

        for route in benchmarks_router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            if getattr(endpoint, "__name__", "") != "upload_benchmark_dataset":
                continue
            sig = inspect.signature(endpoint)
            param_defaults = [p.default for p in sig.parameters.values()]
            has_auth = any(
                hasattr(d, "dependency") and d.dependency is require_auth
                for d in param_defaults
                if hasattr(d, "dependency")
            )
            assert has_auth, "upload_benchmark_dataset missing require_auth dependency"
            return
        raise AssertionError("upload_benchmark_dataset endpoint not found")


class TestUploadServiceMethod:
    """Tests for the BenchmarkSpecService.upload_dataset method directly."""

    @patch.dict("os.environ", {"HOKUSAI_DATASET_BUCKET": "test-bucket"})
    @patch("src.api.services.governance.benchmark_specs.boto3")
    def test_upload_dataset_happy_path(self, mock_boto3: MagicMock) -> None:
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_pii = MagicMock(spec=PIIDetector)
        mock_pii.scan_dataframe.return_value = PIIScanResult(
            findings=[], total_findings=0, by_entity_type={}, severity="none", scanned_records=2
        )

        service = BenchmarkSpecService()
        result = service.upload_dataset(
            model_id="model-42",
            filename="test.csv",
            file_bytes=CSV_CONTENT,
            pii_detector=mock_pii,
            allow_pii=False,
            spec_fields={
                "eval_split": "test",
                "metric_name": "accuracy",
                "metric_direction": "higher_is_better",
                "input_schema": {"columns": ["input"]},
                "output_schema": {"target_column": "expected_output"},
            },
        )

        assert result["s3_uri"].startswith("s3://test-bucket/datasets/model-42/")
        assert result["sha256_hash"] == CSV_HASH
        assert result["filename"] == "test.csv"
        assert result["file_size_bytes"] == len(CSV_CONTENT)
        assert result["spec_id"]  # UUID string

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["ServerSideEncryption"] == "aws:kms"
        assert call_kwargs["Key"].startswith("datasets/model-42/")
        assert call_kwargs["Key"].endswith("/test.csv")

        mock_pii.scan_dataframe.assert_called_once()

    @patch.dict("os.environ", {"HOKUSAI_DATASET_BUCKET": "test-bucket"})
    @patch("src.api.services.governance.benchmark_specs.boto3")
    def test_upload_dataset_pii_blocked(self, mock_boto3: MagicMock) -> None:
        from src.api.services.governance.benchmark_specs import PIIFoundError
        from src.api.services.privacy.pii_detector import PIIFinding

        mock_pii = MagicMock(spec=PIIDetector)
        mock_pii.scan_dataframe.return_value = PIIScanResult(
            findings=[
                PIIFinding(
                    entity_type="EMAIL",
                    start=0,
                    end=10,
                    confidence=1.0,
                    severity="high",
                    source="regex",
                )
            ],
            total_findings=1,
            by_entity_type={"EMAIL": 1},
            severity="high",
            scanned_records=2,
        )

        service = BenchmarkSpecService()
        try:
            service.upload_dataset(
                model_id="model-42",
                filename="test.csv",
                file_bytes=CSV_CONTENT,
                pii_detector=mock_pii,
                allow_pii=False,
                spec_fields={
                    "eval_split": "test",
                    "metric_name": "accuracy",
                    "metric_direction": "higher_is_better",
                    "input_schema": {},
                    "output_schema": {},
                },
            )
            raise AssertionError("Expected PIIFoundError")
        except PIIFoundError:
            pass

        # S3 should NOT have been called
        mock_boto3.client.return_value.put_object.assert_not_called()

    @patch.dict("os.environ", {"HOKUSAI_DATASET_BUCKET": "test-bucket"})
    @patch("src.api.services.governance.benchmark_specs.boto3")
    def test_upload_dataset_s3_cleanup_on_spec_failure(self, mock_boto3: MagicMock) -> None:
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_pii = MagicMock(spec=PIIDetector)
        mock_pii.scan_dataframe.return_value = PIIScanResult(
            findings=[], total_findings=0, by_entity_type={}, severity="none", scanned_records=2
        )

        service = BenchmarkSpecService()
        # Make register_spec fail
        service.register_spec = MagicMock(side_effect=RuntimeError("DB error"))

        try:
            service.upload_dataset(
                model_id="model-42",
                filename="test.csv",
                file_bytes=CSV_CONTENT,
                pii_detector=mock_pii,
                allow_pii=False,
                spec_fields={
                    "eval_split": "test",
                    "metric_name": "accuracy",
                    "metric_direction": "higher_is_better",
                    "input_schema": {},
                    "output_schema": {},
                },
            )
            raise AssertionError("Expected RuntimeError")
        except RuntimeError:
            pass

        # S3 put_object was called
        mock_s3.put_object.assert_called_once()
        # S3 delete_object was called for cleanup
        mock_s3.delete_object.assert_called_once()
        delete_kwargs = mock_s3.delete_object.call_args.kwargs
        assert delete_kwargs["Bucket"] == "test-bucket"
        assert delete_kwargs["Key"].startswith("datasets/model-42/")
