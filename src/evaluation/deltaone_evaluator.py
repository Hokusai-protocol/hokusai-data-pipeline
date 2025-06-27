"""DeltaOne Detector - Automatically detect ≥1pp model improvements."""
import logging
from typing import Optional, List, Dict, Any
import mlflow
from mlflow.entities.model_registry import ModelVersion
from mlflow.tracking import MlflowClient
import requests
import time

logger = logging.getLogger(__name__)


def detect_delta_one(model_name: str, webhook_url: Optional[str] = None) -> bool:
    """
    Detect if the latest model version achieves ≥1 percentage point improvement.
    
    Args:
        model_name: Name of the registered model in MLflow
        webhook_url: Optional webhook URL for notifications
        
    Returns:
        True if DeltaOne improvement detected, False otherwise
    """
    try:
        client = MlflowClient()
        
        # Get all versions sorted by version number (descending)
        versions = _get_sorted_model_versions(client, model_name)
        
        if len(versions) < 2:
            logger.info(f"Not enough versions for model {model_name}. Found {len(versions)} versions.")
            return False
            
        # Get latest version
        latest_version = versions[0]
        
        # Find baseline version with benchmark_value
        baseline_version = _find_baseline_version(versions[1:])
        
        if not baseline_version:
            logger.warning(f"No baseline version found for model {model_name}")
            return False
            
        # Extract metric name from latest version or baseline
        metric_name = latest_version.tags.get("benchmark_metric") or baseline_version.tags.get("benchmark_metric")
        baseline_value = float(baseline_version.tags.get("benchmark_value"))
        
        if not metric_name:
            logger.error("No benchmark_metric tag found in latest or baseline version")
            return False
            
        # Get current metric value from latest version
        current_value = _get_metric_value(client, latest_version, metric_name)
        
        if current_value is None:
            logger.error(f"Metric {metric_name} not found in latest version")
            return False
            
        # Calculate percentage point difference
        delta = _calculate_percentage_point_difference(baseline_value, current_value)
        
        # Check if ≥1pp improvement achieved
        if delta >= 0.01:  # 1 percentage point
            logger.info(f"DeltaOne achieved for {model_name}: {delta:.3f}pp improvement")
            
            # Log achievement to MLflow
            try:
                # Check if we're in an active run, otherwise log metrics are just informational
                if mlflow.active_run():
                    mlflow.log_metric("custom:deltaone_achieved", 1.0)
                    mlflow.log_metric("custom:delta_value", delta)
                else:
                    # If not in a run, we can still call log_metric for mocking in tests
                    mlflow.log_metric("custom:deltaone_achieved", 1.0)
                    mlflow.log_metric("custom:delta_value", delta)
            except Exception as e:
                logger.debug(f"Could not log metrics to MLflow: {e}")
            
            # Send webhook notification if configured
            if webhook_url:
                payload = {
                    "model_name": model_name,
                    "delta_value": delta,
                    "baseline_version": baseline_version.version,
                    "new_version": latest_version.version,
                    "metric_name": metric_name,
                    "baseline_value": baseline_value,
                    "current_value": current_value
                }
                send_deltaone_webhook(webhook_url, payload)
                
            return True
            
        logger.info(f"No DeltaOne improvement for {model_name}: {delta:.3f}pp")
        return False
        
    except Exception as e:
        logger.error(f"Error detecting DeltaOne for {model_name}: {e}")
        return False


def _get_sorted_model_versions(client: MlflowClient, model_name: str) -> List[ModelVersion]:
    """Get model versions sorted by version number (descending)."""
    versions = client.search_model_versions(f"name='{model_name}'")
    return sorted(versions, key=lambda v: int(v.version), reverse=True)


def _find_baseline_version(versions: List[ModelVersion]) -> Optional[ModelVersion]:
    """Find the latest version with benchmark_value tag."""
    for version in versions:
        if "benchmark_value" in version.tags and "benchmark_metric" in version.tags:
            return version
    return None


def _get_metric_value(client: MlflowClient, version: ModelVersion, metric_name: str) -> Optional[float]:
    """Get metric value from a model version's run."""
    try:
        run = client.get_run(version.run_id)
        return run.data.metrics.get(metric_name)
    except Exception as e:
        logger.error(f"Error getting metric {metric_name}: {e}")
        return None


def _calculate_percentage_point_difference(baseline: float, current: float) -> float:
    """Calculate percentage point difference between two values."""
    return current - baseline


def send_deltaone_webhook(webhook_url: str, payload: Dict[str, Any], max_retries: int = 3) -> bool:
    """
    Send webhook notification for DeltaOne achievement.
    
    Args:
        webhook_url: URL to send notification to
        payload: Notification payload
        max_retries: Maximum number of retry attempts
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Hokusai-DeltaOne/1.0"
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("DeltaOne webhook notification sent successfully")
                return True
            else:
                logger.warning(f"Webhook returned status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Webhook request failed (attempt {attempt + 1}): {e}")
            
        # Exponential backoff for retries
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
            
    logger.error(f"Failed to send webhook after {max_retries} attempts")
    return False