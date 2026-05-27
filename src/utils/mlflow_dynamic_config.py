"""Dynamic MLflow configuration that adapts to the deployment environment."""

from src.utils.mlflow_url import get_mlflow_url


def get_mlflow_tracking_uri():
    """Return the canonical MLflow tracking URI."""
    return get_mlflow_url()


# Export the function for use in other modules
MLFLOW_TRACKING_URI = get_mlflow_tracking_uri()
