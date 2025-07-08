"""Status checking module for the Hokusai Data Evaluation Pipeline.
"""
import json
import os
from datetime import datetime
from typing import Any, Dict


class StatusChecker:
    """Check the status of pipeline runs and components."""

    def __init__(self, status_file: str = "/tmp/hokusai_status.json") -> None:
        self.status_file = status_file

    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, "r") as f:
                    status = json.load(f)
                return status
            except (json.JSONDecodeError, IOError):
                # If status file is corrupted, return default status
                pass

        # Default status if no status file exists
        return {
            "running": False,
            "last_run": None,
            "status": "idle",
            "last_error": None
        }

    def update_status(self, status_update: Dict[str, Any]) -> None:
        """Update the pipeline status."""
        current_status = self.get_status()
        current_status.update(status_update)
        current_status["last_updated"] = datetime.now().isoformat()

        try:
            os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
            with open(self.status_file, "w") as f:
                json.dump(current_status, f, indent=2)
        except IOError as e:
            # If we can't write status, at least don't crash
            print(f"Warning: Could not update status file: {e}")

    def mark_running(self) -> None:
        """Mark pipeline as currently running."""
        self.update_status({
            "running": True,
            "status": "running",
            "started_at": datetime.now().isoformat()
        })

    def mark_completed(self, results: Dict[str, Any] = None) -> None:
        """Mark pipeline as completed."""
        update = {
            "running": False,
            "status": "completed",
            "last_run": datetime.now().isoformat(),
            "last_error": None
        }

        if results:
            update["last_results"] = results

        self.update_status(update)

    def mark_error(self, error_message: str) -> None:
        """Mark pipeline as failed with error."""
        self.update_status({
            "running": False,
            "status": "error",
            "last_run": datetime.now().isoformat(),
            "last_error": error_message
        })
