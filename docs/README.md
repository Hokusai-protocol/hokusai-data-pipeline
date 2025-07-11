# Hokusai Internal Documentation

> **Note**: This is the internal developer documentation. For public-facing documentation intended for docs.hokus.ai, see the [`/documentation`](../documentation/README.md) directory.

## Purpose

This `/docs` directory contains internal documentation for developers working on the Hokusai codebase. It includes technical implementation details, architecture decisions, and advanced configuration options.

## Documentation Structure

We maintain two separate documentation sets:

1. **`/docs` (This Directory)** - Internal developer documentation
   - Technical implementation details
   - Architecture decisions
   - Advanced configuration
   - Development guides

2. **`/documentation`** - Public documentation for docs.hokus.ai
   - User-facing guides
   - API documentation
   - Tutorials
   - Getting started content

## For Developers

Choose the guide that best fits your needs:

## 🚀 For Data Scientists

Start here if you want to train, register, and evaluate models.

- **[Getting Started Guide](./getting_started.md)** - Quick 5-minute setup
- **[Model Registration Guide](./model_registration_guide.md)** - Register models with tokens
- **[Third Party Integration Guide](./third_party_integration_guide.md)** - Integrate your existing ML pipelines

## 🔧 For Developers & Integrators

Building applications that use Hokusai models or integrating with existing systems.

- **[API Documentation](./api_documentation.md)** - REST API reference
- **[SDK Reference](../hokusai-ml-platform/README.md)** - Python SDK documentation
- **[DSPy Integration](./DSPY_MODEL_LOADER.md)** - Working with DSPy models

## 🏗️ For DevOps & Infrastructure

Setting up and maintaining Hokusai infrastructure.

- **[Deployment Guide](../infrastructure/README.md)** - AWS deployment instructions
- **[Docker Setup](./docker_setup.md)** - Local development with Docker
- **[Monitoring Guide](./monitoring.md)** - Prometheus and Grafana setup

## 📚 Advanced Topics

For users who need deeper technical details.

- **[Advanced Documentation Index](./advanced/README.md)** - All advanced topics
- **[Pipeline Architecture](./PIPELINE_README.md)** - Metaflow pipeline details
- **[CLI Reference](./CLI_SIGNATURES.md)** - Command-line tools
- **[Model Registration Guide](./model_registration_guide.md)** - Detailed registration process

## 🎯 Quick Links

### Most Common Tasks

1. **Install Hokusai**: `pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform`
2. **Register a Model**: See [Getting Started Guide](./getting_started.md#common-tasks)
3. **Run Local Services**: `docker compose -f docker-compose.minimal.yml up -d`
4. **Access Production**: http://registry.hokus.ai

### Key Concepts

- **Model Registry**: Central storage for all models
- **Experiment Tracking**: MLflow-based experiment management
- **Performance Delta**: Improvement metrics between model versions
- **Attestations**: Blockchain-ready proof of model improvements

## 🆘 Getting Help

- **Issues**: [GitHub Issues](https://github.com/hokusai/hokusai-data-pipeline/issues)
- **Discord**: [Join our community](https://discord.gg/hokusai)
- **API Status**: http://registry.hokus.ai/health

## 📖 Documentation Structure

```
docs/
├── README.md                    # This file
├── getting_started.md          # Quick start for data scientists
├── third_party_integration_guide.md  # Integration options
├── api_documentation.md        # REST API reference
├── model_registration_guide.md # Token-based registration
├── PIPELINE_README.md          # Pipeline architecture
├── DSPY_*.md                   # DSPy-related docs
└── advanced/                   # Advanced topics
    ├── direct_pipeline_execution.md
    ├── metaflow_details.md
    └── infrastructure_deep_dive.md
```

---

**New to Hokusai?** Start with the [Getting Started Guide](./getting_started.md) →