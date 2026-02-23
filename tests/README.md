# Test Markers

This repository uses pytest marks to classify tests by execution scope (unit, integration, e2e, chaos).

## Default behavior

Default command (runs all tests unless filtered):

```bash
pytest tests/ --no-cov
```

## Mark definitions

- `integration`: tests that require live or full-stack service behavior (MLflow, database, Redis, external APIs, or heavy service bootstrapping)
- `e2e`: end-to-end workflow tests
- `chaos`: resilience and fault-injection tests

## Running marked suites

```bash
pytest tests/ --no-cov -m integration
pytest tests/ --no-cov -m e2e
pytest tests/ --no-cov -m chaos
```

## Offline-safe local run

Use this when you want to skip service-dependent suites locally:

```bash
pytest tests/ --no-cov -m "not integration and not e2e and not chaos"
```
