# Metric Naming Convention Guide

This guide defines the standardized metric naming conventions for the Hokusai platform.

## Overview

All metrics in the Hokusai platform follow a consistent naming pattern to ensure:
- Easy discovery and searchability
- Clear categorization
- Consistent tracking across components
- Compatibility with MLflow and other tools

## Naming Pattern

### Basic Format
```
[category:]metric_name[.submetric]
```

### Rules
1. **Lowercase only**: All metric names must be lowercase
2. **Underscores for spaces**: Use underscores to separate words
3. **Category prefix**: Include category followed by colon
4. **No special characters**: Only letters, numbers, underscores, and dots allowed
5. **Start with letter**: Metric names must start with a letter

### Valid Examples
- `usage:reply_rate`
- `model:accuracy`
- `pipeline:duration_seconds`
- `custom:delta_one_score`
- `model:latency_ms.p99`

### Invalid Examples
- `Usage:ReplyRate` (uppercase)
- `usage:reply-rate` (hyphen)
- `usage:reply rate` (space)
- `123_metric` (starts with number)
- `metric@special` (special character)

## Metric Categories

### usage: User Interaction Metrics
Metrics that track how users interact with models or features.

**Standard Metrics:**
- `usage:reply_rate` - Rate of replies to messages
- `usage:conversion_rate` - Conversion rate for actions
- `usage:engagement_rate` - User engagement rate
- `usage:click_through_rate` - Click-through rate
- `usage:retention_rate` - User retention rate

**Example:**
```python
log_usage_metrics({
    "reply_rate": 0.1523,
    "conversion_rate": 0.0821
})
```

### model: Model Performance Metrics
Metrics that track model performance and characteristics.

**Standard Metrics:**
- `model:accuracy` - Model accuracy score
- `model:precision` - Model precision score
- `model:recall` - Model recall score
- `model:f1_score` - F1 score
- `model:auroc` - Area under ROC curve
- `model:latency_ms` - Inference latency in milliseconds
- `model:throughput_qps` - Queries per second

**Example:**
```python
log_model_metrics({
    "accuracy": 0.8934,
    "f1_score": 0.8756,
    "latency_ms": 23.5
})
```

### pipeline: Pipeline Execution Metrics
Metrics that track pipeline execution and resource usage.

**Standard Metrics:**
- `pipeline:data_processed` - Amount of data processed
- `pipeline:success_rate` - Pipeline success rate
- `pipeline:duration_seconds` - Pipeline execution time
- `pipeline:memory_usage_mb` - Memory usage in megabytes
- `pipeline:error_rate` - Pipeline error rate

**Example:**
```python
log_pipeline_metrics({
    "duration_seconds": 120.5,
    "data_processed": 10000,
    "success_rate": 0.98
})
```

### custom: Custom Metrics
Metrics specific to your use case that don't fit other categories.

**Examples:**
- `custom:delta_one_score` - DeltaOne improvement score
- `custom:contributor_score` - Contributor impact score
- `custom:experiment_variant` - A/B test variant performance

## Best Practices

### 1. Use Standard Metrics When Possible
Always check if a standard metric exists before creating a custom one.

### 2. Be Descriptive but Concise
Metric names should be self-explanatory but not overly long.

**Good:**
- `model:inference_latency_ms`
- `usage:daily_active_users`

**Bad:**
- `model:lat` (too short)
- `usage:number_of_users_who_were_active_in_the_last_24_hours` (too long)

### 3. Include Units in Name
When relevant, include units in the metric name:
- `_seconds` for time
- `_ms` for milliseconds
- `_mb` for megabytes
- `_rate` for ratios
- `_count` for counts

### 4. Use Consistent Naming Within Categories
If you have `model:training_time_seconds`, use `model:inference_time_seconds` (not `model:prediction_duration_seconds`).

### 5. Version Metrics When Needed
Use dots for versioning or sub-metrics:
- `model:accuracy.v2`
- `model:latency_ms.p95`
- `usage:conversion_rate.mobile`

## Migration Guide

### Converting Legacy Metrics

Use the `migrate_metric_name()` function:

```python
from src.utils.metrics import migrate_metric_name

# Automatic migration for known metrics
old_name = "accuracy"
new_name = migrate_metric_name(old_name)  # Returns "model:accuracy"
```

### Manual Migration Rules

For metrics not in the migration map:

1. **Performance metrics** → `model:`
   - `accuracy` → `model:accuracy`
   - `latency` → `model:latency_ms`

2. **Time/duration metrics** → `pipeline:`
   - `training_time` → `pipeline:training_time_seconds`
   - `processing_duration` → `pipeline:processing_duration_seconds`

3. **User metrics** → `usage:`
   - `user_clicks` → `usage:click_count`
   - `conversion` → `usage:conversion_rate`

4. **Everything else** → `custom:`
   - `special_score` → `custom:special_score`
   - `experiment_result` → `custom:experiment_result`

## Validation

### Using the Validator

```python
from src.utils.metrics import validate_metric_name

# Check if a metric name is valid
is_valid = validate_metric_name("usage:reply_rate")  # True
is_valid = validate_metric_name("invalid metric")    # False
```

### Common Validation Errors

1. **Invalid characters**: Only lowercase letters, numbers, underscores, dots, and one colon allowed
2. **Wrong format**: Must match pattern `^([a-z]+:)?[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$`
3. **Missing category**: While optional, categories are strongly recommended

## Integration with MLflow

The metric naming convention is designed to work seamlessly with MLflow:

1. **MLflow UI**: Metrics are grouped by prefix in the UI
2. **Searching**: Easy to filter metrics by category
3. **Comparison**: Compare metrics across runs with consistent names
4. **API Access**: Programmatic access using standardized names

## Examples

### Complete Pipeline Example

```python
from src.utils.metrics import MetricLogger, log_model_metrics, log_pipeline_metrics

# Initialize logger
logger = MetricLogger()

# Start of pipeline
log_pipeline_metrics({"data_processed": 0})

# During training
log_model_metrics({
    "accuracy": 0.89,
    "f1_score": 0.87
})

# Track usage
logger.log_metric("usage:api_calls", 1523)

# Custom metrics
logger.log_metric("custom:experiment_id", 42)

# End of pipeline
log_pipeline_metrics({
    "duration_seconds": 145.2,
    "success_rate": 1.0
})
```

### Metric Aggregation Example

```python
# Get all model metrics from a run
model_metrics = logger.get_metrics_by_prefix(run_id, "model:")

# Get all usage metrics
usage_metrics = logger.get_metrics_by_prefix(run_id, "usage:")

# Aggregate across multiple runs
aggregated = logger.aggregate_metrics([run1_metrics, run2_metrics, run3_metrics])
```