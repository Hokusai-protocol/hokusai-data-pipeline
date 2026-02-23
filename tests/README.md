# Test Markers

This repository uses pytest marks to keep the default test run independent from live backing services.

## Default behavior

`pytest.ini` excludes these marks by default:
- `integration`
- `e2e`
- `chaos`

Default command:

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
