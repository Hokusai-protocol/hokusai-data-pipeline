"""Constants for the Hokusai pipeline."""

# Pipeline step names
STEP_LOAD_BASELINE = "load_baseline_model"
STEP_INTEGRATE_DATA = "integrate_contributed_data"
STEP_TRAIN_MODEL = "train_new_model"
STEP_EVALUATE = "evaluate_on_benchmark"
STEP_COMPARE = "compare_and_output_delta"
STEP_ATTESTATION = "generate_attestation_output"
STEP_MONITOR = "monitor_and_log"

# Model artifact names
BASELINE_MODEL_NAME = "baseline_model"
NEW_MODEL_NAME = "new_model"

# Metric names
METRIC_ACCURACY = "accuracy"
METRIC_PRECISION = "precision"
METRIC_RECALL = "recall"
METRIC_F1 = "f1_score"
METRIC_AUROC = "auroc"

# Output formats
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_PARQUET = "parquet"
OUTPUT_FORMAT_CSV = "csv"

# File extensions
SUPPORTED_DATA_FORMATS = [".json", ".csv", ".parquet"]

# Attestation constants
ATTESTATION_VERSION = "1.0"
ATTESTATION_SCHEMA_VERSION = "1.0"

# Status codes
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_PARTIAL = "partial"

# Error messages
ERROR_MODEL_NOT_FOUND = "Model not found: {}"
ERROR_DATA_VALIDATION = "Data validation failed: {}"
ERROR_METRIC_CALCULATION = "Metric calculation failed: {}"

# Logging formats
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"