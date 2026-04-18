"""Shared httpx kwargs for talking to internal MLflow over mTLS.

MLflow serves TLS with an internal CA; the API container's entrypoint stages
the CA bundle and this service's client cert/key on disk and exposes their
paths via env vars. Every ``httpx.AsyncClient`` that talks to the internal
MLflow URL (proxy, health probes, diagnostics) should spread these kwargs so
the TLS handshake has a chain to verify against and presents the expected
client certificate.

When the files are absent (local dev, unit tests) the helper returns an empty
dict and default httpx behavior applies.
"""

from __future__ import annotations

import os


def mlflow_mtls_httpx_kwargs() -> dict:
    """Return ``verify`` / ``cert`` kwargs for ``httpx.AsyncClient``."""
    kwargs: dict = {}
    ca = os.getenv("MLFLOW_CA_BUNDLE_PATH")
    if ca and os.path.isfile(ca):
        kwargs["verify"] = ca
    client_cert = os.getenv("MLFLOW_CLIENT_CERT_PATH")
    client_key = os.getenv("MLFLOW_CLIENT_KEY_PATH")
    if client_cert and client_key and os.path.isfile(client_cert) and os.path.isfile(client_key):
        kwargs["cert"] = (client_cert, client_key)
    return kwargs
