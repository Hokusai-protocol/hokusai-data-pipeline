"""Updates to hokusai_pipeline.py for standardized metric logging.

This file shows the changes needed to update the pipeline to use the new
standardized metric logging convention.
"""

# Add this import to the imports section at the top of hokusai_pipeline.py:
from src.utils.metrics import log_model_metrics, log_pipeline_metrics, MetricLogger

# In the train_new_model step, replace the log_step_metrics call around line 275:
# OLD:
# log_step_metrics({
#     "training_time_seconds": training_time,
#     "training_samples": len(self.integrated_data),
#     "contributed_samples": len(self.contributed_data),
#     "feature_count": num_features,
#     **trainer.get_mock_metrics()
# })

# NEW:
# Log pipeline metrics
log_pipeline_metrics({
    "training_time_seconds": training_time,
    "training_samples": len(self.integrated_data),
    "contributed_samples": len(self.contributed_data),
    "feature_count": num_features
})

# Log model metrics separately
model_metrics = trainer.get_mock_metrics()
log_model_metrics(model_metrics)

# Similarly, around line 401 for real training:
# OLD:
# log_step_metrics({
#     "training_time_seconds": training_time,
#     "training_samples": len(self.integrated_data),
#     "contributed_samples": len(self.contributed_data),
#     "model_type": model_type,
#     **train_metrics
# })

# NEW:
# Log pipeline metrics
log_pipeline_metrics({
    "training_time_seconds": training_time,
    "training_samples": len(self.integrated_data),
    "contributed_samples": len(self.contributed_data)
})

# Log model type as parameter (not metric)
mlflow.log_param("model_type", model_type)

# Log model metrics with proper prefix
log_model_metrics(train_metrics)

# In the evaluate_on_benchmark step, around line 506:
# OLD:
# log_step_metrics({
#     "evaluation_time_seconds": eval_time,
#     "benchmark_size": len(mock_benchmark),
#     "baseline_accuracy": baseline_results["accuracy"],
#     "new_accuracy": new_results["accuracy"],
#     "delta_accuracy": new_results["accuracy"] - baseline_results["accuracy"],
#     "baseline_f1": baseline_results["f1_score"],
#     "new_f1": new_results["f1_score"],
#     "delta_f1": new_results["f1_score"] - baseline_results["f1_score"]
# })

# NEW:
# Log pipeline metrics
log_pipeline_metrics({
    "evaluation_time_seconds": eval_time,
    "benchmark_size": len(mock_benchmark)
})

# Log model comparison metrics with custom prefix
logger = MetricLogger()
logger.log_metrics({
    "model:baseline_accuracy": baseline_results["accuracy"],
    "model:new_accuracy": new_results["accuracy"],
    "model:delta_accuracy": new_results["accuracy"] - baseline_results["accuracy"],
    "model:baseline_f1": baseline_results["f1_score"],
    "model:new_f1": new_results["f1_score"],
    "model:delta_f1": new_results["f1_score"] - baseline_results["f1_score"]
})

# Around line 587 for real evaluation:
# Similar pattern - separate pipeline and model metrics

# In compare_and_output_delta step, around line 704:
# OLD:
# log_step_metrics({
#     "delta_one_score": delta_computation["delta_one"],
#     "metrics_compared": delta_computation["metrics_count"],
#     "improved_metrics": len(delta_computation["improved_metrics"]),
#     "degraded_metrics": len(delta_computation["degraded_metrics"]),
#     "contributor_weights": self.data_manifest["contributor_weights"],
#     "contributed_samples": self.data_manifest["contributed_samples"],
#     "total_samples": self.data_manifest["contributed_samples"] + self.data_manifest.get("base_samples", 0)
# })

# NEW:
# Log delta metrics with custom prefix
logger = MetricLogger()
logger.log_metrics({
    "custom:delta_one_score": delta_computation["delta_one"],
    "custom:metrics_compared": delta_computation["metrics_count"],
    "custom:improved_metrics": len(delta_computation["improved_metrics"]),
    "custom:degraded_metrics": len(delta_computation["degraded_metrics"])
})

# Log pipeline metrics
log_pipeline_metrics({
    "contributor_weights": self.data_manifest["contributor_weights"],
    "contributed_samples": self.data_manifest["contributed_samples"],
    "total_samples": self.data_manifest["contributed_samples"] + self.data_manifest.get("base_samples", 0)
})