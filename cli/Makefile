.PHONY: test install clean cli-help

# Install dependencies
install:
	pip install -r requirements.txt

# Run all tests
test:
	python -m pytest tests/ -v

# Run quick tests (just basic CLI)
test-quick:
	python -m pytest tests/test_cli.py::TestCLI -v

# Run CLI help
cli-help:
	cd src && python cli.py --help

# Run CLI commands
cli-run-help:
	cd src && python cli.py run --help

cli-evaluate-help:
	cd src && python cli.py evaluate --help

cli-compare-help:
	cd src && python cli.py compare --help

cli-status-help:
	cd src && python cli.py status --help

# Clean up
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/
	rm -rf src/__pycache__/
	rm -rf tests/__pycache__/

# Show project structure
structure:
	tree -I "__pycache__|*.pyc|.pytest_cache"