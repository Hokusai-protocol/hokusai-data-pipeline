# Hokusai Public Documentation (Docusaurus)

> **Note**: This is the public-facing documentation for docs.hokus.ai. For internal developer documentation, see the [`/docs`](../docs/README.md) directory.

This directory contains the comprehensive documentation for the Hokusai ML Platform, formatted for Docusaurus.

## Overview

The documentation covers:

- **Getting Started**: Installation, quickstart, and configuration guides
- **Core Features**: Model Registry, DeltaOne Detection, DSPy Integration, A/B Testing
- **Tutorials**: Step-by-step guides for common tasks
- **API Reference**: Complete API documentation with examples
- **Guides**: Architecture, best practices, deployment, and troubleshooting

## Structure

```
documentation/
├── index.md                 # Main landing page
├── sidebars.js             # Navigation configuration
├── getting-started/        # Installation and setup guides
├── core-features/          # Feature documentation
├── tutorials/              # Step-by-step tutorials
├── api-reference/          # API documentation
├── guides/                 # Best practices and architecture
├── contributing/           # Data contribution guides
└── reference/              # Glossary, FAQ, etc.
```

## Integration with docs.hokus.ai

These documentation files are designed to integrate with the existing Docusaurus site at docs.hokus.ai. To deploy:

1. Copy the contents of this directory to your Docusaurus docs folder
2. Update `docusaurus.config.js` to include the new sidebar
3. Build and deploy the site

## Key Features Documented

### 1. Token-Aware Model Registry
- Register models with associated Hokusai tokens
- Track model lineage and improvements
- Automatic reward distribution

### 2. DeltaOne Detection
- Automatic detection of ≥1 percentage point improvements
- Webhook notifications
- Smart contract integration

### 3. DSPy Integration
- Pre-built signature library
- Teleprompt fine-tuning
- Pipeline execution

### 4. A/B Testing Framework
- Multiple routing strategies
- Real-time metrics
- Statistical analysis

### 5. Data Contribution
- Support for multiple formats
- ETH wallet integration
- HuggingFace dataset compatibility

## Documentation Standards

- All files include proper Docusaurus frontmatter
- Code examples are tested and working
- Consistent formatting and styling
- Cross-references between related topics
- Comprehensive examples for all features

## Contributing

To contribute to the documentation:

1. Follow the existing structure and formatting
2. Test all code examples
3. Update the sidebar configuration if adding new pages
4. Ensure proper frontmatter on all pages
5. Add cross-references to related content

## Building Locally

To preview the documentation locally:

```bash
# Install Docusaurus (if not already installed)
npm install -g docusaurus

# Navigate to your Docusaurus site directory
cd path/to/docusaurus-site

# Copy documentation files
cp -r path/to/hokusai-data-pipeline/documentation/* docs/

# Start development server
npm start
```

## Questions or Issues

If you find any issues with the documentation:

- Open an issue on GitHub
- Join our Discord for discussion
- Email documentation@hokusai.ai