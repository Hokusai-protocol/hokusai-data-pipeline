# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Hokusai data evaluation pipeline - a system for evaluating machine learning models with reproducible, attestation-ready outputs. The project is in early development stages with focus on workflow automation tooling.

## Development Commands

### Python Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies (once requirements.txt exists)
pip install -r requirements.txt
```

### Running Workflow Tools
```bash
# Run the main workflow automation
node tools/workflow.js

# Get Linear backlog
node tools/get-backlog.ts

# Environment setup
# Ensure .env file contains LINEAR_API_KEY
```

### TypeScript Execution
Since there's no formal build system yet, TypeScript files are run directly:
```bash
# Run TypeScript files with tsx or ts-node
npx tsx tools/get-backlog.ts
```

## Architecture Overview

### Core Pipeline Components (To Be Implemented in Python)
1. **Data Preparation Module**: Processes golden query dataset with stratified sampling
2. **Inference Module**: Uses Metaflow for distributed processing
3. **Evaluation Module**: Computes metrics (precision, recall, F1)
4. **Reporting Module**: Generates JSON reports and visualizations
5. **Comparison Module**: Compares current vs baseline models
6. **Attestation Module**: Produces zk/attestation-ready proofs
7. **Monitoring Module**: Tracks processing and errors

### Current Implementation: Workflow Automation
- **Linear Integration**: `tools/linear-tasks.ts` manages task retrieval from Linear
- **Git Automation**: `tools/git.ts` handles branch creation
- **GitHub Integration**: `tools/github.ts` manages PR creation
- **Workflow Runner**: `tools/workflow.js` orchestrates the development process

### Key Architectural Decisions
- **Python SDK**: All pipeline implementation will use Python
- **Metaflow**: Python-based framework for pipeline orchestration
- **MLFlow**: For experiment tracking and metrics storage
- **Deterministic Execution**: Fixed random seeds for reproducibility
- **Modular Design**: Each pipeline step as a separate Metaflow step
- **Error Handling**: Comprehensive error tracking with structured logging

## Development Workflow

The project uses a structured 7-step workflow (defined in `tools/prompts/workflow-prompt.md`):
1. Retrieve task from Linear
2. Generate PRD from task description
3. Create detailed implementation tasks
4. Create feature branch
5. Update TODO.md with tasks
6. Implement features (AI-assisted)
7. Create pull request

## Important Context

### Pipeline Requirements (from hokusai_evaluation_pipeline.md)
- Must handle golden query datasets with 10k-100k queries
- Stratified sampling required to reduce dataset size
- Results must be deterministic and reproducible
- Output includes zk-proof ready attestations
- Support for A/B testing between model versions

### Technology Stack
- **Pipeline Language**: Python
- **Pipeline Framework**: Metaflow (Python)
- **Metrics**: MLFlow (Python)
- **Workflow Automation**: TypeScript/Node.js
- **Task Management**: Linear API
- **Version Control**: Git/GitHub

### Python Dependencies (To Be Added)
- `metaflow`: Pipeline orchestration
- `mlflow`: Experiment tracking
- `pandas`: Data manipulation
- `numpy`: Numerical operations
- `scikit-learn`: For stratified sampling
- `pytest`: Testing framework

### Environment Variables
- `LINEAR_API_KEY`: Required for Linear API access

## Notes for Implementation

When implementing the actual pipeline in Python:
- Follow the 7-step module structure in hokusai_evaluation_pipeline.md
- Use Python's `random.seed()` and `numpy.random.seed()` for reproducibility
- Implement comprehensive error logging with Python's logging module
- Create pytest unit tests for each module
- Use Metaflow's @step decorators for each pipeline stage
- Store all metrics in MLFlow for tracking
- Follow PEP 8 style guidelines for Python code