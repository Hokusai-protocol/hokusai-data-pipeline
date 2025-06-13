# Hokusai Data Pipeline CLI

A command-line interface for the Hokusai Data Evaluation Pipeline, providing reproducible machine learning model evaluation with attestation-ready outputs.

## Project Structure

```
cli/
├── src/                    # Source code
│   ├── cli.py             # Main CLI interface
│   ├── pipeline.py        # Pipeline orchestration
│   ├── evaluator.py       # Model evaluation
│   ├── comparator.py      # Model comparison
│   ├── status_checker.py  # Pipeline status
│   ├── data_loader.py     # Data loading utilities
│   └── model_loader.py    # Model loading utilities
├── tests/                 # Test suite
│   ├── test_cli.py        # CLI tests
│   ├── test_pipeline.py   # Pipeline tests
│   ├── test_evaluator.py  # Evaluator tests
│   └── test_comparator.py # Comparator tests
├── requirements.txt       # Python dependencies
├── setup.py              # Package setup
├── pytest.ini           # Test configuration
├── Makefile              # Build automation
└── example_config.yaml   # Example configuration
```

## Installation

### Development Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows
```

2. Install dependencies:
```bash
make install
# or
pip install -r requirements.txt
```

3. Run tests to verify installation:
```bash
make test-quick
```

### Package Installation (Future)

```bash
pip install -e .
```

## Usage

### Basic Commands

The CLI provides several commands for different evaluation tasks:

```bash
# Show help
cd src && python cli.py --help

# Run full evaluation pipeline
cd src && python cli.py run --config ../example_config.yaml

# Evaluate a single model
cd src && python cli.py evaluate --model-path /path/to/model --dataset-path /path/to/dataset

# Compare two models
cd src && python cli.py compare --model1 /path/to/model1 --model2 /path/to/model2 --dataset /path/to/dataset

# Check pipeline status
cd src && python cli.py status
```

### Configuration

Create a YAML configuration file for pipeline runs:

```yaml
model_path: /path/to/your/model
dataset_path: /path/to/your/dataset
output_dir: /path/to/output
batch_size: 32
random_seed: 42
```

## Development

### Running Tests

```bash
# Run all tests
make test

# Run quick tests only
make test-quick

# Run specific test file
python -m pytest tests/test_cli.py -v
```

### Test-Driven Development

This project follows TDD principles:

1. **Tests First**: All functionality is tested before implementation
2. **Comprehensive Coverage**: Tests cover happy paths, edge cases, and error conditions
3. **Mocking**: External dependencies are mocked for isolated testing
4. **Reproducible**: Tests use fixed seeds for deterministic results

### Key Features Tested

- **CLI Interface**: Command existence, help text, argument validation
- **Pipeline Orchestration**: Step execution, error handling, status tracking
- **Model Evaluation**: Metrics calculation, sampling, batch processing
- **Model Comparison**: Statistical significance testing, improvement calculation
- **Reproducibility**: Fixed random seeds, deterministic outputs

### Adding New Features

1. Write tests first in the appropriate test file
2. Run tests to see them fail
3. Implement the minimum code to make tests pass
4. Refactor and improve
5. Ensure all tests pass

### Code Quality

- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Document functions with docstrings
- Handle errors gracefully
- Log important events

## Architecture

### Design Principles

- **Modular**: Each component has a single responsibility
- **Testable**: All components can be tested in isolation
- **Configurable**: Behavior controlled through configuration
- **Reproducible**: Fixed seeds ensure consistent results
- **Observable**: Comprehensive logging and status tracking

### Integration Points

- **MLflow**: For experiment tracking and metrics storage
- **Metaflow**: For pipeline orchestration (future)
- **Scikit-learn**: For metrics and sampling utilities
- **Click**: For CLI interface

## Future Enhancements

- [ ] Metaflow integration for distributed processing
- [ ] Model format auto-detection
- [ ] Dataset format support (CSV, Parquet, etc.)
- [ ] Visualization generation
- [ ] Attestation/proof generation
- [ ] Cloud storage integration
- [ ] Configuration validation
- [ ] Progress bars for long operations

## Contributing

1. Follow TDD principles
2. Ensure all tests pass
3. Add tests for new functionality
4. Update documentation
5. Follow existing code style

## License

This project is part of the Hokusai data pipeline system.