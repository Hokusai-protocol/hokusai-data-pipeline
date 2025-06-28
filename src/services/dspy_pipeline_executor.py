"""DSPy Pipeline Executor for running DSPy programs within Hokusai ML platform."""

import json
import time
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import mlflow
from src.services.dspy_model_loader import DSPyModelLoader
from src.utils.config import get_config
from src.dspy_signatures.base import BaseSignature

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Execution modes for DSPy pipeline."""
    NORMAL = "normal"
    DRY_RUN = "dry_run"
    DEBUG = "debug"
    BATCH = "batch"


class DSPyExecutionError(Exception):
    """Custom exception for DSPy execution errors."""
    pass


class ValidationError(DSPyExecutionError):
    """Exception for input validation errors."""
    pass


@dataclass
class ExecutionResult:
    """Result of DSPy program execution."""
    success: bool
    outputs: Optional[Dict[str, Any]]
    error: Optional[str]
    execution_time: float
    program_name: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict())


class DSPyPipelineExecutor:
    """Executor for DSPy programs with MLflow tracking and caching."""
    
    def __init__(
        self,
        cache_enabled: bool = True,
        mlflow_tracking: bool = True,
        timeout: int = 300,
        max_retries: int = 1,
        max_workers: int = 4
    ):
        """Initialize DSPy Pipeline Executor.
        
        Args:
            cache_enabled: Enable caching of programs and results
            mlflow_tracking: Enable MLflow experiment tracking
            timeout: Execution timeout in seconds
            max_retries: Maximum number of retry attempts
            max_workers: Maximum workers for batch execution
        """
        self.cache_enabled = cache_enabled
        self.mlflow_tracking = mlflow_tracking
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_workers = max_workers
        
        self._program_cache = {}
        self._result_cache = {}
        self._model_loader = DSPyModelLoader()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._execution_stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "execution_times": []
        }
        
        # Initialize MLflow if enabled
        if self.mlflow_tracking:
            self._init_mlflow()
    
    def _init_mlflow(self):
        """Initialize MLflow tracking."""
        try:
            # Use configured tracking URI or default
            config = get_config()
            tracking_uri = config.mlflow_tracking_uri
            mlflow.set_tracking_uri(tracking_uri)
            
            # Set experiment name
            experiment_name = config.mlflow_experiment_name or "dspy-execution"
            mlflow.set_experiment(experiment_name)
            
            # Enable DSPy autolog using our integration
            try:
                from src.integrations.mlflow_dspy import autolog
                autolog()
                logger.info("MLflow DSPy autolog enabled via Hokusai integration")
            except ImportError:
                # Fallback to native MLflow DSPy autolog if available
                try:
                    if hasattr(mlflow, 'dspy'):
                        mlflow.dspy.autolog()
                        logger.info("MLflow DSPy autolog enabled (native)")
                except Exception as e:
                    logger.debug(f"MLflow DSPy autolog not available: {e}")
                
        except Exception as e:
            logger.warning(f"Failed to initialize MLflow tracking: {e}")
            self.mlflow_tracking = False
    
    def _validate_inputs(self, inputs: Dict[str, Any], program: Any) -> None:
        """Validate inputs against program signature.
        
        Args:
            inputs: Input dictionary
            program: DSPy program instance
            
        Raises:
            ValidationError: If inputs are invalid
        """
        # Check if program has a signature attribute
        signature = None
        if hasattr(program, 'signature'):
            signature = program.signature
        elif isinstance(program, BaseSignature):
            signature = program
            
        if not signature:
            # If no signature found, assume inputs are valid
            return
            
        # If signature is a BaseSignature instance, use its validation
        if isinstance(signature, BaseSignature):
            try:
                signature.validate_inputs(inputs)
            except ValueError as e:
                raise ValidationError(str(e))
        # Otherwise check for required input fields
        elif hasattr(signature, 'input_fields'):
            required_fields = signature.input_fields
            missing_fields = [f for f in required_fields if f not in inputs]
            
            if missing_fields:
                raise ValidationError(
                    f"Missing required input fields: {missing_fields}"
                )
    
    def _load_program_by_id(self, model_id: str) -> Any:
        """Load DSPy program by model ID.
        
        Args:
            model_id: Model identifier
            
        Returns:
            DSPy program instance
        """
        # Check cache first
        if self.cache_enabled and model_id in self._program_cache:
            return self._program_cache[model_id]
            
        try:
            # Try to load from model registry first
            from src.services.model_registry import HokusaiModelRegistry
            registry = HokusaiModelRegistry()
            
            model_info = registry.get_model(model_id)
            if model_info and 'program_path' in model_info:
                program_data = self._model_loader.load_from_config(
                    model_info['program_path']
                )
                program = program_data['program']
            else:
                # Fallback to direct loading
                raise ValueError(f"Model {model_id} not found in registry")
            
            # Cache the loaded program
            if self.cache_enabled:
                self._program_cache[model_id] = program
                
            return program
            
        except Exception as e:
            raise DSPyExecutionError(f"Failed to load model {model_id}: {e}")
    
    def _execute_program(
        self,
        program: Any,
        inputs: Dict[str, Any],
        mode: ExecutionMode = ExecutionMode.NORMAL
    ) -> Dict[str, Any]:
        """Execute DSPy program with given inputs.
        
        Args:
            program: DSPy program instance
            inputs: Input dictionary
            mode: Execution mode
            
        Returns:
            Program outputs
        """
        if mode == ExecutionMode.DRY_RUN:
            # In dry-run mode, only validate without execution
            self._validate_inputs(inputs, program)
            return None
            
        if mode == ExecutionMode.DEBUG:
            # Enable verbose logging for debug mode
            original_level = logger.level
            logger.setLevel(logging.DEBUG)
            logger.debug(f"Executing program {type(program).__name__} with inputs: {inputs}")
            
        try:
            # Execute program
            if hasattr(program, 'forward'):
                outputs = program.forward(**inputs)
            elif callable(program):
                outputs = program(**inputs)
            else:
                raise DSPyExecutionError(
                    f"Program {type(program).__name__} is not callable"
                )
            
            # Convert outputs to dictionary if needed
            if hasattr(outputs, '__dict__'):
                outputs = outputs.__dict__
            elif not isinstance(outputs, dict):
                outputs = {"output": outputs}
            
            if mode == ExecutionMode.DEBUG:
                logger.debug(f"Program outputs: {outputs}")
                
            return outputs
            
        finally:
            if mode == ExecutionMode.DEBUG:
                logger.setLevel(original_level)
    
    def execute(
        self,
        program: Any = None,
        model_id: str = None,
        inputs: Dict[str, Any] = None,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        retry_on_failure: bool = True
    ) -> ExecutionResult:
        """Execute DSPy program with inputs.
        
        Args:
            program: DSPy program instance (optional if model_id provided)
            model_id: Model ID to load (optional if program provided)
            inputs: Input dictionary
            mode: Execution mode
            retry_on_failure: Whether to retry on failure
            
        Returns:
            ExecutionResult with outputs and metadata
        """
        start_time = time.time()
        
        # Load program if model_id provided
        if model_id and not program:
            program = self._load_program_by_id(model_id)
        elif not program:
            raise ValueError("Either program or model_id must be provided")
        
        # Get program name
        program_name = getattr(program, 'name', type(program).__name__)
        
        # Check cache if enabled
        cache_key = None
        if self.cache_enabled and mode == ExecutionMode.NORMAL:
            cache_key = f"{program_name}:{json.dumps(inputs, sort_keys=True)}"
            if cache_key in self._result_cache:
                cached_result = self._result_cache[cache_key]
                cached_result.metadata['cache_hit'] = True
                return cached_result
        
        # Initialize result
        result = ExecutionResult(
            success=False,
            outputs=None,
            error=None,
            execution_time=0,
            program_name=program_name,
            metadata={"mode": mode.value}
        )
        
        # Track with MLflow
        mlflow_run = None
        if self.mlflow_tracking and mode != ExecutionMode.DRY_RUN:
            try:
                mlflow_run = mlflow.start_run(nested=True)
                mlflow.log_params({
                    "program_name": program_name,
                    "mode": mode.value,
                    "input_keys": list(inputs.keys()) if inputs else []
                })
            except Exception as e:
                logger.debug(f"MLflow tracking error: {e}")
                self.mlflow_tracking = False
        
        attempts = 0
        max_attempts = self.max_retries if retry_on_failure else 1
        
        while attempts < max_attempts:
            attempts += 1
            
            try:
                # Validate inputs
                self._validate_inputs(inputs, program)
                
                if mode == ExecutionMode.DRY_RUN:
                    result.success = True
                    result.metadata['validation_passed'] = True
                else:
                    # Execute with timeout
                    future = self._executor.submit(
                        self._execute_program,
                        program,
                        inputs,
                        mode
                    )
                    
                    outputs = future.result(timeout=self.timeout)
                    
                    result.success = True
                    result.outputs = outputs
                    
                    if mode == ExecutionMode.DEBUG:
                        result.metadata['debug_trace'] = {
                            "program_type": type(program).__name__,
                            "input_count": len(inputs),
                            "output_count": len(outputs) if outputs else 0
                        }
                
                break  # Success, exit retry loop
                
            except TimeoutError:
                error_msg = f"Execution timeout after {self.timeout} seconds"
                result.error = error_msg
                logger.error(error_msg)
                
            except ValidationError as e:
                result.error = str(e)
                logger.error(f"Validation error: {e}")
                break  # Don't retry validation errors
                
            except Exception as e:
                error_msg = f"Execution error (attempt {attempts}/{max_attempts}): {str(e)}"
                result.error = error_msg
                logger.error(error_msg)
                
                if attempts < max_attempts:
                    time.sleep(0.5 * attempts)  # Exponential backoff
        
        # Calculate execution time
        result.execution_time = time.time() - start_time
        
        # Update statistics
        self._update_stats(result)
        
        # Log to MLflow
        if self.mlflow_tracking and mode != ExecutionMode.DRY_RUN and mlflow_run:
            try:
                mlflow.log_metrics({
                    "execution_time": result.execution_time,
                    "success": 1.0 if result.success else 0.0
                })
                
                if result.outputs:
                    # Log sample outputs (limit size)
                    sample_outputs = {
                        f"output_{k}": str(v)[:100] for k, v in list(result.outputs.items())[:5]
                    }
                    mlflow.log_params(sample_outputs)
                
                mlflow.end_run()
            except Exception as e:
                logger.debug(f"MLflow logging error: {e}")
        
        # Cache successful results
        if cache_key and result.success and self.cache_enabled:
            self._result_cache[cache_key] = result
        
        return result
    
    def execute_batch(
        self,
        program: Any = None,
        model_id: str = None,
        inputs_list: List[Dict[str, Any]] = None
    ) -> List[ExecutionResult]:
        """Execute DSPy program on batch of inputs.
        
        Args:
            program: DSPy program instance
            model_id: Model ID to load
            inputs_list: List of input dictionaries
            
        Returns:
            List of ExecutionResults
        """
        if not inputs_list:
            return []
        
        # Load program once for batch
        if model_id and not program:
            program = self._load_program_by_id(model_id)
        
        # Execute in parallel
        futures = []
        for inputs in inputs_list:
            future = self._executor.submit(
                self.execute,
                program=program,
                inputs=inputs,
                retry_on_failure=False  # Don't retry in batch mode
            )
            futures.append(future)
        
        # Collect results
        results = []
        for future in futures:
            try:
                result = future.result(timeout=self.timeout)
                results.append(result)
            except Exception as e:
                # Create error result for failed execution
                error_result = ExecutionResult(
                    success=False,
                    outputs=None,
                    error=f"Batch execution error: {str(e)}",
                    execution_time=0,
                    program_name=getattr(program, 'name', 'unknown')
                )
                results.append(error_result)
        
        return results
    
    def _update_stats(self, result: ExecutionResult):
        """Update execution statistics."""
        self._execution_stats['total'] += 1
        
        if result.success:
            self._execution_stats['success'] += 1
        else:
            self._execution_stats['failed'] += 1
        
        self._execution_stats['execution_times'].append(result.execution_time)
        
        # Keep only recent execution times
        if len(self._execution_stats['execution_times']) > 1000:
            self._execution_stats['execution_times'] = \
                self._execution_stats['execution_times'][-1000:]
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics.
        
        Returns:
            Dictionary with execution statistics
        """
        exec_times = self._execution_stats['execution_times']
        
        stats = {
            "total_executions": self._execution_stats['total'],
            "successful_executions": self._execution_stats['success'],
            "failed_executions": self._execution_stats['failed'],
            "success_rate": (
                self._execution_stats['success'] / self._execution_stats['total']
                if self._execution_stats['total'] > 0 else 0
            )
        }
        
        if exec_times:
            stats.update({
                "average_execution_time": sum(exec_times) / len(exec_times),
                "min_execution_time": min(exec_times),
                "max_execution_time": max(exec_times),
                "p95_execution_time": sorted(exec_times)[int(len(exec_times) * 0.95)]
                if len(exec_times) > 20 else max(exec_times)
            })
        
        return stats
    
    def clear_cache(self):
        """Clear program and result caches."""
        self._program_cache.clear()
        self._result_cache.clear()
        logger.info("Caches cleared")
    
    def shutdown(self):
        """Shutdown executor and cleanup resources."""
        self._executor.shutdown(wait=True)
        self.clear_cache()
        logger.info("DSPyPipelineExecutor shutdown complete")