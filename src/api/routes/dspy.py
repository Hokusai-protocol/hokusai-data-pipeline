"""API endpoints for DSPy pipeline execution."""

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.middleware.auth import require_auth
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor, ExecutionMode
from src.utils.config import get_config

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/dspy", tags=["dspy"])

# Initialize executor (singleton)
_executor = None


def get_executor() -> DSPyPipelineExecutor:
    """Get or create DSPy executor instance."""
    global _executor
    if _executor is None:
        config = get_config()
        _executor = DSPyPipelineExecutor(
            cache_enabled=True, mlflow_tracking=True, timeout=300, max_workers=config.max_workers
        )
    return _executor


class DSPyExecutionRequest(BaseModel):
    """Request model for DSPy execution."""

    program_id: Optional[str] = Field(None, description="ID of the registered DSPy program")
    inputs: dict[str, Any] = Field(..., description="Input data for the program")
    mode: Optional[str] = Field("normal", description="Execution mode: normal, dry_run, debug")
    timeout: Optional[int] = Field(None, description="Override default timeout in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "program_id": "email-assistant-v1",
                "inputs": {
                    "recipient": "john@example.com",
                    "subject": "Meeting Follow-up",
                    "context": "Discussed Q4 targets",
                },
                "mode": "normal",
            }
        }


class DSPyBatchExecutionRequest(BaseModel):
    """Request model for batch DSPy execution."""

    program_id: str = Field(..., description="ID of the registered DSPy program")
    inputs_list: list[dict[str, Any]] = Field(..., description="List of input dictionaries")

    class Config:
        json_schema_extra = {
            "example": {
                "program_id": "email-assistant-v1",
                "inputs_list": [
                    {
                        "recipient": "john@example.com",
                        "subject": "Meeting Follow-up",
                        "context": "Discussed Q4 targets",
                    },
                    {
                        "recipient": "jane@example.com",
                        "subject": "Project Update",
                        "context": "Milestone completed",
                    },
                ],
            }
        }


class DSPyExecutionResponse(BaseModel):
    """Response model for DSPy execution."""

    execution_id: str = Field(..., description="Unique execution identifier")
    success: bool = Field(..., description="Whether execution was successful")
    outputs: Optional[dict[str, Any]] = Field(None, description="Program outputs")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time: float = Field(..., description="Execution time in seconds")
    program_name: str = Field(..., description="Name of the executed program")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class DSPyBatchExecutionResponse(BaseModel):
    """Response model for batch DSPy execution."""

    batch_id: str = Field(..., description="Unique batch identifier")
    total: int = Field(..., description="Total number of executions")
    successful: int = Field(..., description="Number of successful executions")
    failed: int = Field(..., description="Number of failed executions")
    results: list[DSPyExecutionResponse] = Field(..., description="Individual execution results")


class DSPyProgramInfo(BaseModel):
    """Information about a DSPy program."""

    program_id: str = Field(..., description="Program identifier")
    name: str = Field(..., description="Program name")
    version: str = Field(..., description="Program version")
    signatures: list[dict[str, Any]] = Field(..., description="Program signatures")
    description: Optional[str] = Field(None, description="Program description")


@router.post("/execute", response_model=DSPyExecutionResponse)
async def execute_dspy_program(
    request: DSPyExecutionRequest,
    background_tasks: BackgroundTasks,
    token_data: dict = Depends(require_auth),
):
    """Execute a DSPy program with given inputs.

    This endpoint executes a registered DSPy program with the provided inputs.
    Supports different execution modes including dry-run and debug modes.
    """
    try:
        executor = get_executor()

        # Parse execution mode
        mode = ExecutionMode.NORMAL
        if request.mode:
            mode = ExecutionMode[request.mode.upper()]

        # Execute program
        result = executor.execute(model_id=request.program_id, inputs=request.inputs, mode=mode)

        # Generate execution ID
        execution_id = str(uuid.uuid4())

        # Log execution for tracking
        logger.info(
            f"DSPy execution {execution_id} for user {token_data.get('sub')}: "
            f"program={request.program_id}, success={result.success}"
        )

        return DSPyExecutionResponse(
            execution_id=execution_id,
            success=result.success,
            outputs=result.outputs,
            error=result.error,
            execution_time=result.execution_time,
            program_name=result.program_name,
            metadata=result.metadata,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"DSPy execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}") from e


@router.post("/execute/batch", response_model=DSPyBatchExecutionResponse)
async def execute_dspy_batch(
    request: DSPyBatchExecutionRequest,
    background_tasks: BackgroundTasks,
    token_data: dict = Depends(require_auth),
):
    """Execute a DSPy program on multiple inputs in batch.

    This endpoint executes a registered DSPy program with multiple input sets
    in parallel, returning results for each execution.
    """
    try:
        executor = get_executor()

        # Execute batch
        results = executor.execute_batch(
            model_id=request.program_id, inputs_list=request.inputs_list
        )

        # Generate batch ID
        batch_id = str(uuid.uuid4())

        # Count successes and failures
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        # Convert results to response format
        response_results = []
        for i, result in enumerate(results):
            response_results.append(
                DSPyExecutionResponse(
                    execution_id=f"{batch_id}-{i}",
                    success=result.success,
                    outputs=result.outputs,
                    error=result.error,
                    execution_time=result.execution_time,
                    program_name=result.program_name,
                    metadata=result.metadata,
                )
            )

        logger.info(
            f"DSPy batch execution {batch_id} for user {token_data.get('sub')}: "
            f"program={request.program_id}, total={len(results)}, "
            f"successful={successful}, failed={failed}"
        )

        return DSPyBatchExecutionResponse(
            batch_id=batch_id,
            total=len(results),
            successful=successful,
            failed=failed,
            results=response_results,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"DSPy batch execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch execution failed: {str(e)}") from e


@router.get("/programs", response_model=list[DSPyProgramInfo])
async def list_dspy_programs(token_data: dict = Depends(require_auth)):
    """List available DSPy programs.

    Returns a list of all registered DSPy programs that can be executed.
    """
    try:
        # Get list of available programs from model registry
        from src.services.model_registry import HokusaiModelRegistry

        registry = HokusaiModelRegistry()

        # Filter for DSPy programs
        programs = []
        all_models = registry.list_models(model_type="dspy")

        for model in all_models:
            programs.append(
                DSPyProgramInfo(
                    program_id=model["id"],
                    name=model["name"],
                    version=model.get("version", "1.0.0"),
                    signatures=model.get("signatures", []),
                    description=model.get("description"),
                )
            )

        logger.info(f"Listed {len(programs)} DSPy programs for user {token_data.get('sub')}")

        return programs

    except Exception as e:
        logger.error(f"Error listing DSPy programs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list programs: {str(e)}") from e


@router.get("/execution/{execution_id}")
async def get_execution_details(
    execution_id: str, token_data: dict = Depends(require_auth)
) -> dict[str, Any]:
    """Get details of a specific execution.

    This endpoint would typically retrieve execution details from a database
    or cache. For now, it returns a placeholder response.
    """
    # TODO: Implement execution history storage and retrieval
    raise HTTPException(status_code=501, detail="Execution history retrieval not yet implemented")


@router.get("/stats")
async def get_execution_stats(token_data: dict = Depends(require_auth)):
    """Get execution statistics for the DSPy pipeline executor.

    Returns aggregated statistics about DSPy executions including
    success rates, execution times, and performance metrics.
    """
    try:
        executor = get_executor()
        stats = executor.get_execution_stats()

        return {
            "statistics": stats,
            "cache_enabled": executor.cache_enabled,
            "mlflow_tracking": executor.mlflow_tracking,
        }

    except Exception as e:
        logger.error(f"Error getting execution stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}") from e


@router.post("/cache/clear")
async def clear_cache(token_data: dict = Depends(require_auth)):
    """Clear the DSPy program cache.

    This endpoint clears cached programs and results, forcing fresh loads
    on subsequent executions.
    """
    try:
        executor = get_executor()
        executor.clear_cache()

        logger.info(f"DSPy cache cleared by user {token_data.get('sub')}")

        return {"message": "Cache cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}") from e


# Health check endpoint
@router.get("/health")
async def dspy_health_check():
    """Check health of DSPy executor service."""
    try:
        executor = get_executor()
        stats = executor.get_execution_stats()

        return {
            "status": "healthy",
            "total_executions": stats.get("total_executions", 0),
            "success_rate": stats.get("success_rate", 0),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
