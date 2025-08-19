"""
Async task processing module.
"""

import logging
from typing import Dict, Any
from celery import Celery

logger = logging.getLogger(__name__)

# Mock Celery app for testing
celery_app = Celery('tasks')


def process_model_async(model_id: str, auth_headers: Dict[str, str]) -> None:
    """
    Process a model asynchronously.
    
    Args:
        model_id: Model identifier
        auth_headers: Authentication headers to preserve
    """
    # Extract auth token to pass to async task
    auth_token = auth_headers.get('Authorization', '')
    
    # Send task with auth context
    celery_app.send_task(
        'process_model',
        args=[model_id, auth_token],
        queue='model_processing'
    )
    
    logger.info(f"Queued async processing for model {model_id}")