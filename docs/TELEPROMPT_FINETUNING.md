# Teleprompt Fine-tuning Pipeline

This document describes the Teleprompt Fine-tuning Pipeline that automatically optimizes DSPy programs based on usage logs and generates attestations for DeltaOne achievements.

## Overview

The Teleprompt Fine-tuning Pipeline enables continuous improvement of DSPy programs by:

1. **Collecting execution traces** from production usage with outcome scores
2. **Running teleprompt.compile()** to optimize programs based on real performance
3. **Evaluating improvements** against DeltaOne thresholds
4. **Generating attestations** for verifiable improvements
5. **Tracking contributor attribution** for reward distribution

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   MLflow Logs   │────▶│ Trace Loader │────▶│   Teleprompt    │
│ (with outcomes) │     │              │     │   Finetuner     │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                      │
                                                      ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Attestation    │◀────│   DeltaOne   │◀────│   Optimized     │
│   Generator     │     │  Evaluator   │     │    Program      │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

## Components

### 1. Teleprompt Finetuner (`src/services/teleprompt_finetuner.py`)

The core service that orchestrates the optimization process.

```python
from src.services.teleprompt_finetuner import (
    TelepromptFinetuner,
    OptimizationConfig,
    OptimizationStrategy
)

# Configure optimization
config = OptimizationConfig(
    strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT,
    min_traces=1000,
    optimization_rounds=3,
    deltaone_threshold=0.01  # 1% improvement
)

# Run optimization
finetuner = TelepromptFinetuner(config)
result = finetuner.run_optimization(
    program=my_dspy_program,
    start_date=datetime.now() - timedelta(days=7),
    end_date=datetime.now(),
    outcome_metric="reply_rate"
)
```

### 2. Trace Loader (`src/services/trace_loader.py`)

Loads execution traces from MLflow with filtering and sampling capabilities.

```python
from src.services.trace_loader import TraceLoader

loader = TraceLoader()
traces = loader.load_traces(
    program_name="EmailDraft",
    start_date=start_date,
    end_date=end_date,
    min_score=0.7,
    outcome_metric="engagement_score",
    limit=10000
)
```

### 3. Optimization Attestation Service (`src/services/optimization_attestation.py`)

Generates verifiable attestations for DeltaOne achievements.

```python
from src.services.optimization_attestation import OptimizationAttestationService

attestation_service = OptimizationAttestationService()
attestation = attestation_service.create_attestation(
    model_info={...},
    performance_data={...},
    optimization_metadata={...},
    contributors=[...]
)
```

## Configuration

### Optimization Strategies

The pipeline supports multiple optimization strategies:

1. **BOOTSTRAP_FEWSHOT**: Standard few-shot learning with bootstrapping
2. **BOOTSTRAP_FEWSHOT_RANDOM**: Random search over program variants
3. **COPRO**: Cooperative Prompt Optimization (future)
4. **MIPRO**: Multi-stage Instruction Proposal & Optimization (future)

### Configuration Options

```python
OptimizationConfig(
    strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT,
    min_traces=1000,              # Minimum traces required
    max_traces=100000,            # Maximum traces to use
    min_quality_score=0.7,        # Minimum outcome score
    optimization_rounds=3,        # Number of optimization iterations
    timeout_seconds=7200,         # 2-hour timeout
    enable_deltaone_check=True,   # Check for DeltaOne achievement
    deltaone_threshold=0.01,      # 1% improvement threshold
    batch_size=1000,              # Batch size for processing
    num_candidates=10             # Candidates for random search
)
```

## Usage Patterns

### Basic Optimization

```python
# 1. Configure optimization
config = OptimizationConfig(
    strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT,
    min_traces=5000
)

# 2. Run optimization
finetuner = TelepromptFinetuner(config)
result = finetuner.run_optimization(
    program=email_draft_program,
    start_date=datetime.now() - timedelta(days=30),
    end_date=datetime.now(),
    outcome_metric="reply_rate"
)

# 3. Check if successful
if result.success:
    print(f"Optimization complete: {result.trace_count} traces used")
    
    # 4. Evaluate DeltaOne
    deltaone = finetuner.evaluate_deltaone(result)
    
    if deltaone["deltaone_achieved"]:
        # 5. Generate attestation
        attestation = finetuner.generate_attestation(result, deltaone)
        
        # 6. Save optimized model
        model_info = finetuner.save_optimized_model(
            result,
            model_name="EmailDraft-Optimized"
        )
```

### Scheduled Pipeline

```python
import schedule
import time

def run_weekly_optimization():
    """Run optimization for all registered programs."""
    programs = load_registered_programs()
    
    for program in programs:
        try:
            finetuner = TelepromptFinetuner(production_config)
            result = finetuner.run_optimization(
                program=program,
                start_date=datetime.now() - timedelta(days=7),
                end_date=datetime.now()
            )
            
            if result.success:
                handle_optimization_result(result)
                
        except Exception as e:
            logger.error(f"Optimization failed for {program}: {e}")

# Schedule weekly runs
schedule.every().monday.at("02:00").do(run_weekly_optimization)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Contributor Attribution

The pipeline tracks which data contributed to optimizations:

```python
# After optimization
result = finetuner.run_optimization(...)

# View contributors
for contributor_id, info in result.contributors.items():
    print(f"{contributor_id}:")
    print(f"  Address: {info['address']}")
    print(f"  Weight: {info['weight']:.2%}")
    print(f"  Traces: {info['trace_count']}")
    print(f"  Avg Score: {info['avg_score']:.3f}")

# Calculate rewards
if deltaone["deltaone_achieved"]:
    attestation_service = OptimizationAttestationService()
    rewards = attestation_service.calculate_rewards(
        attestation,
        total_reward=1000.0  # Total reward amount
    )
    
    for address, amount in rewards.items():
        print(f"{address}: {amount} tokens")
```

## Attestation Format

Attestations include all information needed to verify improvements:

```json
{
  "schema_version": "1.0",
  "attestation_type": "teleprompt_optimization",
  "attestation_id": "a1b2c3d4e5f6",
  "timestamp": "2024-01-15T12:00:00Z",
  "model_info": {
    "model_id": "EmailDraft",
    "baseline_version": "1.0.0",
    "optimized_version": "1.0.0-opt-bfs-20240115120000",
    "optimization_strategy": "bootstrap_fewshot"
  },
  "performance": {
    "deltaone_achieved": true,
    "performance_delta": 0.023,
    "baseline_metrics": {
      "reply_rate": 0.134,
      "click_rate": 0.089
    },
    "optimized_metrics": {
      "reply_rate": 0.157,
      "click_rate": 0.095
    }
  },
  "optimization_metadata": {
    "trace_count": 15000,
    "optimization_time_seconds": 180.5,
    "outcome_metric": "reply_rate",
    "date_range": {
      "start": "2024-01-01T00:00:00",
      "end": "2024-01-15T00:00:00"
    }
  },
  "contributors": [
    {
      "contributor_id": "alice",
      "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
      "weight": 0.7,
      "trace_count": 10500
    },
    {
      "contributor_id": "bob",
      "address": "0x5aAeb6053f3E94C9b9A09f33669435E7Ef1BeAed",
      "weight": 0.3,
      "trace_count": 4500
    }
  ],
  "attestation_hash": "3f4e5d6c7b8a9..."
}
```

## Integration with MLflow

### Logging Traces

Ensure your DSPy executions log traces with outcome scores:

```python
import mlflow

with mlflow.start_run():
    # Execute DSPy program
    result = dspy_program.forward(**inputs)
    
    # Log trace data
    mlflow.log_params({
        "input.recipient": inputs["recipient"],
        "input.subject": inputs["subject"]
    })
    
    mlflow.log_params({
        "output.email_body": result["email_body"]
    })
    
    # Log outcome score (crucial for optimization)
    mlflow.log_metric("reply_rate", actual_reply_rate)
    mlflow.log_metric("outcome_score", normalized_score)
    
    # Tag with contributor info
    mlflow.set_tags({
        "contributor_id": contributor_id,
        "contributor_address": eth_address,
        "dspy_program_name": "EmailDraft",
        "has_dspy_traces": "true"
    })
```

### Retrieving Optimized Models

```python
import mlflow

# Get latest optimized version
client = mlflow.tracking.MlflowClient()
versions = client.search_model_versions(
    filter_string="name='EmailDraft-Optimized'"
)

latest = max(versions, key=lambda v: v.version)
print(f"Latest optimized version: {latest.version}")
print(f"DeltaOne achieved: {latest.tags.get('deltaone')}")
```

## Best Practices

### 1. Data Quality

- Ensure traces have accurate outcome scores
- Filter out anomalous or low-quality traces
- Use stratified sampling for balanced optimization

### 2. Optimization Frequency

- Run optimization when sufficient new traces accumulate
- Weekly or monthly schedules work well for most use cases
- Monitor trace volume to adjust frequency

### 3. Performance Monitoring

- Track optimization success rates
- Monitor DeltaOne achievement frequency
- Alert on optimization failures

### 4. Contributor Fairness

- Validate all contributor addresses
- Ensure proper weight calculation
- Audit reward distributions

### 5. Version Management

- Use semantic versioning for optimized models
- Maintain clear lineage from baseline
- Enable rollback capabilities

## Troubleshooting

### Insufficient Traces

```
Error: Insufficient traces: 500 < 1000
```

**Solution**: 
- Lower `min_traces` in config
- Extend date range for trace collection
- Check if traces are being logged correctly

### Optimization Timeout

```
Error: Optimization timed out after 7200 seconds
```

**Solution**:
- Increase `timeout_seconds` in config
- Reduce `max_traces` to process fewer traces
- Use simpler optimization strategy

### No DeltaOne Achievement

**Possible causes**:
- Model already well-optimized
- Poor quality training traces
- Insufficient diversity in traces

**Solution**:
- Collect more diverse usage data
- Adjust outcome metrics
- Try different optimization strategies

### Invalid Contributor Addresses

```
Warning: Invalid ETH address: 0xinvalid...
```

**Solution**:
- Validate addresses when logging traces
- Use proper ETH address format
- Filter out invalid contributors

## Security Considerations

1. **Attestation Integrity**: Attestations include cryptographic hashes
2. **Contributor Validation**: All ETH addresses are validated
3. **Access Control**: Limit who can trigger optimizations
4. **Audit Trail**: All optimizations are logged in MLflow
5. **Rollback Safety**: Keep baseline models for rollback

## Future Enhancements

1. **Advanced Strategies**: COPRO and MIPRO optimization
2. **Real-time Optimization**: Continuous learning from streams
3. **Multi-objective Optimization**: Optimize for multiple metrics
4. **Cross-program Learning**: Share learnings across programs
5. **On-chain Integration**: Direct blockchain attestation submission