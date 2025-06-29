---
id: glossary
title: Glossary
sidebar_label: Glossary
---

# Glossary

Key terms and concepts used throughout the Hokusai ML Platform.

## A

### A/B Testing
A method of comparing two versions of a model to determine which performs better in production. Hokusai supports various routing strategies including random, deterministic, and sticky routing.

### Attestation
A cryptographically verifiable proof that a model improvement has occurred. Used for on-chain verification of DeltaOne achievements.

## B

### Baseline Model
The reference model version against which improvements are measured. Usually the current production model or a previously established benchmark.

### Batch Contribution
Submitting multiple data samples or datasets in a single operation for efficiency.

### Benchmark Metric
The primary performance metric (e.g., accuracy, F1 score) used to measure model improvements and determine DeltaOne achievements.

### Benchmark Value
The baseline performance value of a model on the benchmark metric. New versions must exceed this by ≥1 percentage point for DeltaOne.

## C

### Contributor
An individual or entity that provides data to improve Hokusai models. Contributors are identified by their Ethereum wallet address.

### Contribution Hash
A SHA-256 hash of contributed data that ensures data integrity and enables verification without revealing the actual data.

## D

### Data Contribution
The process of submitting new training data to improve existing models. Contributions that lead to DeltaOne achievements earn token rewards.

### DeltaOne
The threshold for significant model improvement: ≥1 percentage point gain in the benchmark metric. Achieving DeltaOne triggers token rewards.

### DSPy
Declarative Self-improving Language Programs - A framework integrated into Hokusai for systematic prompt optimization and signature-based programming.

## E

### ETH Address
Ethereum wallet address used to identify contributors and distribute token rewards. Must be a valid 42-character hexadecimal string starting with "0x".

### Execution Mode
Operating mode for DSPy pipeline execution: DEVELOPMENT (with logging), TESTING (with mocks), or PRODUCTION (optimized).

## F

### Fine-tuning
The process of adapting a pre-trained model to specific tasks or domains using additional training data.

## H

### Hokusai Token
Blockchain tokens associated with specific models that enable ownership, governance, and reward distribution for improvements.

## I

### Inference Pipeline
The system that handles model predictions in production, including caching, load balancing, and performance monitoring.

## L

### Lineage
The complete history of a model's versions, improvements, and contributors. Tracked automatically by the Model Registry.

## M

### Metric Direction
Whether a metric should be maximized (e.g., accuracy) or minimized (e.g., error rate) for improvement detection.

### MLflow
The underlying experiment tracking and model registry platform that Hokusai extends with blockchain integration.

### Model Registry
The token-aware system for managing model versions, metadata, and associated Hokusai tokens.

### Model Version
A specific iteration of a model, identified by a version number and associated with performance metrics and contributor information.

## P

### Percentage Point (pp)
The unit of measurement for DeltaOne. A change from 85% to 87% accuracy is a 2 percentage point improvement (not 2.35% relative change).

### PII (Personally Identifiable Information)
Sensitive data that must be detected and anonymized before contribution. Hokusai provides automatic PII detection and removal.

## R

### Reward Distribution
The process of allocating tokens to contributors whose data led to DeltaOne achievements. Handled automatically by smart contracts.

### Routing Strategy
The method used to direct traffic between model versions in A/B testing: RANDOM, DETERMINISTIC, or STICKY.

## S

### Signature (DSPy)
A specification of input/output behavior for language model programs. Defines what a prompt should accomplish without specifying how.

### Stratified Sampling
A data sampling technique that preserves the distribution of classes or categories when creating training/test splits.

## T

### Teleprompt
The automatic optimization system for DSPy signatures that improves prompts based on examples and feedback.

### Token ID
Unique identifier for a Hokusai token, following the format: uppercase letters, numbers, and hyphens (e.g., "MSG-AI", "SENT-001").

### Traffic Split
The percentage distribution of requests between model versions in A/B testing (e.g., 80% to baseline, 20% to challenger).

## V

### Validation
The process of checking data quality, format compliance, and licensing compatibility before accepting contributions.

### Version Tag
Metadata attached to model versions including performance metrics, contributor information, and training details.

## W

### Webhook
HTTP endpoint that receives notifications when DeltaOne is achieved or other significant events occur.

## Z

### Zero-Knowledge Proof (ZK Proof)
Cryptographic method to verify model improvements without revealing proprietary model weights or training data.

### ZK Schema
The standardized format for zero-knowledge compatible outputs that enable on-chain verification of model improvements.

---

## Acronyms

- **API**: Application Programming Interface
- **CLI**: Command Line Interface
- **ETH**: Ethereum
- **JSON**: JavaScript Object Notation
- **ML**: Machine Learning
- **MLOps**: Machine Learning Operations
- **PII**: Personally Identifiable Information
- **pp**: Percentage Points
- **SDK**: Software Development Kit
- **URI**: Uniform Resource Identifier
- **ZK**: Zero-Knowledge