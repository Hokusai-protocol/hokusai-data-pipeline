"""Custom MLflow REST store for Hokusai API authentication."""

import os
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import requests
from mlflow.store.rest_store import RestStore
from mlflow.utils.rest_utils import augmented_raise_for_status


class HokusaiMLflowRestStore(RestStore):
    """Custom REST store that uses X-API-Key header for Hokusai API."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize with Hokusai API key."""
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("HOKUSAI_API_KEY")
        
        # Check if we're using the Hokusai API proxy
        parsed_uri = urlparse(self.tracking_uri)
        self.is_hokusai_proxy = "registry.hokus.ai/api" in self.tracking_uri
        
    def _get_headers(self, request_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Get headers with proper authentication."""
        headers = request_headers or {}
        
        if self.is_hokusai_proxy and self.api_key:
            # Use X-API-Key for Hokusai API proxy
            headers["X-API-Key"] = self.api_key
        else:
            # Use standard MLflow authentication for other servers
            if "MLFLOW_TRACKING_TOKEN" in os.environ:
                headers["Authorization"] = f"Bearer {os.environ['MLFLOW_TRACKING_TOKEN']}"
            elif "MLFLOW_TRACKING_USERNAME" in os.environ:
                import base64
                username = os.environ["MLFLOW_TRACKING_USERNAME"]
                password = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"
                
        return headers
    
    def _call_endpoint(self, method, endpoint, json_body=None, **kwargs):
        """Override to add Hokusai authentication."""
        # Get headers with authentication
        headers = kwargs.get("headers", {})
        headers = self._get_headers(headers)
        kwargs["headers"] = headers
        
        # Call parent method
        return super()._call_endpoint(method, endpoint, json_body, **kwargs)