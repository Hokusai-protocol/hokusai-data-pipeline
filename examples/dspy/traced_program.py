"""Example of using MLflow DSPy autolog for tracing DSPy programs."""

import os
import mlflow
from src.integrations.mlflow_dspy import autolog, MLflowDSPyConfig
from src.dspy_signatures import DraftText, ReviseText, RefineText
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor


def basic_tracing_example():
    """Basic example of automatic DSPy tracing."""
    # Enable autolog with default configuration
    autolog()
    
    # Create pipeline executor
    executor = DSPyPipelineExecutor()
    
    # Execute a simple text generation
    result = executor.execute(
        program=DraftText(),
        inputs={
            "topic": "The impact of AI on education",
            "requirements": "Write a 200-word introduction",
            "style": "academic"
        }
    )
    
    print(f"Generated text: {result.outputs['draft'][:100]}...")
    print(f"Execution time: {result.execution_time:.2f}s")


def custom_configuration_example():
    """Example with custom tracing configuration."""
    # Create custom configuration
    config = MLflowDSPyConfig(
        experiment_name="dspy-custom-traces",
        log_intermediate_steps=True,
        sampling_rate=0.5,  # Only trace 50% of executions
        custom_tags={"team": "ml-research", "project": "hokusai"}
    )
    
    # Enable autolog with custom config
    autolog(config=config)
    
    # Execute multiple steps
    executor = DSPyPipelineExecutor()
    
    # Step 1: Draft
    draft_result = executor.execute(
        program=DraftText(),
        inputs={
            "topic": "Climate change solutions",
            "requirements": "300 words, include statistics",
            "style": "persuasive"
        }
    )
    
    # Step 2: Revise
    revise_result = executor.execute(
        program=ReviseText(),
        inputs={
            "original_text": draft_result.outputs["draft"],
            "feedback": "Add more specific examples and data",
            "revision_goals": ["add_evidence", "improve_clarity"]
        }
    )
    
    print(f"Revised text improved by {len(revise_result.outputs['revised_text']) - len(draft_result.outputs['draft'])} characters")


def environment_configuration_example():
    """Example using environment variables for configuration."""
    # Set environment variables
    os.environ["MLFLOW_DSPY_ENABLED"] = "true"
    os.environ["MLFLOW_DSPY_SAMPLING_RATE"] = "0.1"
    os.environ["MLFLOW_DSPY_EXPERIMENT"] = "dspy-production"
    
    # Autolog will use environment configuration
    autolog()
    
    # Run pipeline
    executor = DSPyPipelineExecutor()
    
    # This will be traced based on sampling rate (10% chance)
    for i in range(10):
        result = executor.execute(
            program=RefineText(),
            inputs={
                "text": f"Sample text {i} that needs refinement.",
                "refinement_criteria": ["clarity", "conciseness"],
                "formality_level": "formal"
            }
        )
        print(f"Execution {i+1} completed")


def trace_analysis_example():
    """Example of analyzing traces after execution."""
    # Enable full tracing
    config = MLflowDSPyConfig(
        log_signatures=True,
        log_intermediate_steps=True
    )
    autolog(config=config)
    
    # Run with MLflow tracking
    with mlflow.start_run() as run:
        executor = DSPyPipelineExecutor()
        
        # Execute program
        result = executor.execute(
            program=DraftText(),
            inputs={
                "topic": "Future of transportation",
                "requirements": "Focus on sustainability",
                "style": "informative"
            }
        )
        
        # Log additional metrics
        mlflow.log_metric("output_length", len(result.outputs.get("draft", "")))
        mlflow.log_metric("execution_time_ms", result.execution_time * 1000)
        
        print(f"Run ID: {run.info.run_id}")
        print(f"View traces at: {mlflow.get_tracking_uri()}")


def batch_execution_with_tracing():
    """Example of batch execution with tracing."""
    # Configure for batch processing
    config = MLflowDSPyConfig(
        trace_buffer_size=50,  # Buffer traces for efficiency
        sampling_rate=0.2  # Sample 20% of executions
    )
    autolog(config=config)
    
    executor = DSPyPipelineExecutor()
    
    # Batch inputs
    topics = [
        "Artificial Intelligence",
        "Quantum Computing",
        "Renewable Energy",
        "Space Exploration",
        "Biotechnology"
    ]
    
    # Execute batch
    results = executor.execute_batch(
        model_id="DraftText",
        inputs_list=[
            {
                "topic": topic,
                "requirements": "100 words, technical audience",
                "style": "technical"
            }
            for topic in topics
        ]
    )
    
    # Analyze results
    successful = sum(1 for r in results if r.success)
    avg_time = sum(r.execution_time for r in results) / len(results)
    
    print(f"Batch execution complete: {successful}/{len(results)} successful")
    print(f"Average execution time: {avg_time:.2f}s")


if __name__ == "__main__":
    print("=== Basic Tracing Example ===")
    basic_tracing_example()
    
    print("\n=== Custom Configuration Example ===")
    custom_configuration_example()
    
    print("\n=== Environment Configuration Example ===")
    environment_configuration_example()
    
    print("\n=== Trace Analysis Example ===")
    trace_analysis_example()
    
    print("\n=== Batch Execution Example ===")
    batch_execution_with_tracing()