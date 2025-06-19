# 📋 Hokusai Evaluation Pipeline Requirements

## 🎯 Goal

To create a reproducible, structured pipeline that:

- Enables contributors to prepare and optionally test their data locally
- Trains and evaluates contributed data against a baseline model
- Measures performance delta using a shared metric (e.g., accuracy, AUROC)
- Produces a verifiable attestation that can eventually feed into a ZK-based DeltaOneVerifier
- Logs all model metadata, inputs, and evaluation steps via MLFlow

---

## 1. 🧹 Data Preparation (Local by Contributor)

**Objective:** Prepare, clean, and structure the data into a Hokusai-compatible format.

**Tasks:**
- Validate file format (e.g., JSON, CSV, Parquet)
- Annotate or label data (QA pairs, completions, etc.)
- Remove or redact any PII or sensitive data
- Optionally hash the dataset and generate metadata manifest
- Use a CLI or SDK tool to validate dataset format before submission

---

## 2. 🔍 Local Evaluation (Optional, Incentive Preview)

**Objective:** Estimate the potential performance boost from your data before submission.

**Tasks:**
- Run a local RAG or fine-tuning pipeline
- Apply hallucination detection models (e.g., TLM)
- Estimate AUROC or improvement over baseline
- Display estimated DeltaOne value and potential token reward (non-binding)

---

## 3. 🛠 Pipeline Infrastructure (Metaflow)

### ✅ Requirements

- Define a **Metaflow flow** with the following high-level steps:
  1. `load_baseline_model`
  2. `integrate_contributed_data`
  3. `train_new_model`
  4. `evaluate_on_benchmark`
  5. `compare_and_output_delta`

- Each step should be isolated and parameterized
- Ensure reproducibility (e.g., fixed seeds, version-controlled inputs)
- Output must be deterministic from identical inputs

---

## 4. 📊 Model Evaluation Logic (MLFlow)

### ✅ Requirements

- Track all experiments and artifacts using MLFlow:
  - Baseline model
  - Contributed dataset hash or ID
  - Performance metric scores (before/after)
  - Final serialized model (optional)

- Use consistent metric definitions tied to the `ModelRegistry`

- Store output in structured JSON format:

```json
{
  "modelId": 1,
  "baselineScore": 0.842,
  "newScore": 0.856,
  "deltaOneValue": 1.4,
  "metric": "accuracy",
  "contributorHashes": ["0xabc123...", "0xdef456..."],
  "contributorAddresses": ["0x742d35Cc6634C0532925a3b844Bc9e7595f62341", "0x6C3e007f281f6948b37c511a11E43c8026d2F069"],
  "weights": [0.7, 0.3],
  "datasetHash": "0xdeadbeef...",
  "signature": "<optional_placeholder>"
}
```

---

## 5. 🔐 zk/Attestation-Ready Output

### ✅ Requirements

- Output must be:
  - Canonical (stable JSON structure)
  - Hashable (supports off-chain signatures or zk-proof circuits)

- Prepare fields for:
  - Attestation signature (if using an off-chain oracle)
  - zk-proof object (future integration)

- Design should support:
  - Trusted oracle verification as an initial approach
  - Upgrade to full zkML verification over metric delta

---

## 6. 🧪 Test Mode

### ✅ Requirements

- Implement `--dry-run` mode using mock datasets
- Allows rapid CI feedback and local simulation of pipeline

---

## 7. 🧩 Integration Points

### ✅ Requirements

- Accept configuration from:
  - `ModelRegistry` schema (JSON)
  - Contribution hash or dataset ID

- Produce output compatible with:
  - `DeltaOneVerifier` smart contract
  - ZK attestation bridge or hash-signing oracle

---

## 🧠 Future Add-Ons

- Plug-in modules for custom evaluation metrics
- Contributor attribution validation (e.g., Shapley-based weights)
- zkSnark circuit templates for performance deltas