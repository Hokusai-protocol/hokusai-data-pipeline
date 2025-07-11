# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Hokusai data evaluation pipeline - a system for evaluating machine learning models with reproducible, attestation-ready outputs. The project is in early development stages with focus on workflow automation tooling.

## Documentation Structure

The project maintains two separate documentation directories for different audiences:

### `/docs` - Internal Developer Documentation
- **Purpose**: Technical documentation for contributors and developers working on Hokusai
- **Content**: Architecture decisions, implementation details, advanced configuration, debugging guides
- **Format**: Standard Markdown
- **Audience**: Hokusai contributors, developers extending the platform

### `/documentation` - Public User Documentation  
- **Purpose**: User-facing documentation for docs.hokus.ai (Docusaurus format)
- **Content**: Getting started guides, tutorials, API reference, best practices
- **Format**: Docusaurus-compatible with frontmatter
- **Audience**: Data scientists using Hokusai, third-party developers

See `DOCUMENTATION_MAP.md` for detailed guidelines on what content belongs where.

## Common Commands
Common prompts: 
@~/.claude/my-common-prompts.md

For this repo, use the "Hokusai data platform" project in Linear to pull the backlog list.

### Quick Start for New Users
```bash
# Install the Python SDK (recommended approach)
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform

# Or run local services with Docker
docker compose -f docker-compose.minimal.yml up -d
``` 

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
npx tsx ~/.claude/tools/get-backlog.ts "Hokusai data pipeline"

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

### Token-Aware MLflow Model Registry
The project now includes token-aware model registration capabilities:
- **register_tokenized_model()**: Register models with Hokusai token metadata
- **validate_hokusai_tags()**: Ensure required token metadata is present
- **get_tokenized_model()**: Retrieve models by name and version
- **list_models_by_token()**: Find all models associated with a token
- **validate_token_id()**: Enforce token ID naming conventions

Required tags for tokenized models:
- `hokusai_token_id`: Token identifier (e.g., "msg-ai")
- `benchmark_metric`: Performance metric name
- `benchmark_value`: Baseline performance value

### Metric Logging Convention
The project now uses standardized metric logging with categories:
- **usage:** - User metrics (e.g., `usage:reply_rate`)
- **model:** - Model metrics (e.g., `model:accuracy`)
- **pipeline:** - Pipeline metrics (e.g., `pipeline:duration_seconds`)
- **custom:** - Custom metrics (e.g., `custom:delta_one_score`)

Use the helper functions in `src/utils/metrics.py`:
- `log_usage_metrics()` - Automatically prefixes with "usage:"
- `log_model_metrics()` - Automatically prefixes with "model:"
- `log_pipeline_metrics()` - Automatically prefixes with "pipeline:"

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

## Documentation Guidelines

When updating documentation:

### For User-Facing Features
- Update `/documentation` directory (Docusaurus format)
- Include frontmatter with id, title, sidebar_label, sidebar_position
- Focus on how to use features, not implementation details
- Add to appropriate section in `documentation/sidebars.js`

### For Technical Implementation
- Update `/docs` directory (standard Markdown)
- Include architecture diagrams and technical details
- Document design decisions and trade-offs
- Link to relevant code sections

### Documentation Best Practices
- Use the Python SDK as the primary example in user docs
- Show REST API as alternative for non-Python users
- Keep installation instructions simple (2 methods max)
- Move complex options to advanced sections
- Test all code examples before documenting