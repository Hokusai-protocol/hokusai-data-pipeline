# API Endpoint Testing Suite

This directory contains a comprehensive testing suite for all Hokusai API endpoints, providing both unit tests and integration tests with authentication verification and response validation.

## Overview

The testing suite includes:

- **Unit Tests**: Test endpoint logic in isolation with comprehensive mocking
- **Integration Tests**: Test complete API workflows with realistic scenarios  
- **Authentication Tests**: Verify proper authentication behavior for protected endpoints
- **Response Validation**: Ensure responses match expected schemas and formats
- **Error Handling**: Test error conditions and edge cases
- **Live API Testing**: Test against real API servers

## Test Files

### Core Test Files

- `tests/integration/test_comprehensive_endpoint_suite.py` - Integration tests for all endpoints
- `tests/unit/test_api_endpoints_unit.py` - Unit tests with mocking
- `tests/conftest.py` - Shared test fixtures and configuration

### Test Scripts

- `scripts/test_api_endpoints.py` - Live API testing script
- `scripts/run_endpoint_tests.py` - Test runner with multiple modes
- `pytest-endpoints.ini` - Pytest configuration for endpoint testing

## Endpoints Tested

### Health & Status Endpoints (Public)
- `GET /health` - Basic health check
- `GET /health?detailed=true` - Detailed health with system info
- `GET /ready` - Readiness check
- `GET /live` - Liveness check  
- `GET /version` - Version information
- `GET /metrics` - Service metrics (Prometheus/JSON)

### Model Management Endpoints
- `GET /models/` - List all models
- `GET /models/?name=filter` - List models with filter
- `GET /models/{name}/{version}` - Get specific model
- `GET /models/{name}/lineage` - Get model lineage (auth required)
- `POST /models/register` - Register new model (auth required)
- `PATCH /models/{name}/{version}` - Update model metadata
- `DELETE /models/{name}/{version}` - Delete model version
- `POST /models/{name}/{version}/transition` - Transition model stage
- `GET /models/compare` - Compare two models
- `POST /models/evaluate` - Evaluate model performance
- `GET /models/{name}/{version}/metrics` - Get model metrics
- `GET /models/production` - List production models
- `POST /models/batch` - Batch model operations
- `GET /models/contributors/{address}/impact` - Contributor impact (auth required)

### DSPy Pipeline Endpoints (Auth Required)
- `GET /api/v1/dspy/health` - DSPy service health (public)
- `POST /api/v1/dspy/execute` - Execute DSPy program
- `POST /api/v1/dspy/execute/batch` - Batch DSPy execution
- `GET /api/v1/dspy/programs` - List available programs
- `GET /api/v1/dspy/execution/{id}` - Get execution details
- `GET /api/v1/dspy/stats` - Execution statistics
- `POST /api/v1/dspy/cache/clear` - Clear cache

### MLflow Proxy Endpoints
- `/mlflow/api/2.0/mlflow/*` - Proxy to MLflow API
- `/mlflow/api/2.0/mlflow-artifacts/*` - Proxy to MLflow artifacts

### MLflow Health Endpoints (Public)
- `GET /api/health/mlflow` - MLflow health check
- `GET /api/health/mlflow/detailed` - Detailed MLflow health
- `GET /api/health/mlflow/connectivity` - Connectivity check
- `POST /health/mlflow/reset` - Reset circuit breaker (auth required)
- `GET /health/status` - Detailed service status (auth required)

## Running Tests

### Quick Start

```bash
# Install dependencies
pip install pytest fastapi httpx tabulate pytest-cov

# Run unit tests (fast, no dependencies)
python scripts/run_endpoint_tests.py --mode unit

# Run against local development server
python scripts/run_endpoint_tests.py --mode integration --api-url http://localhost:8000

# Test against live API
python scripts/run_endpoint_tests.py --mode live --api-url https://api.hokus.ai --api-key hok_your_key

# Run full suite with coverage
python scripts/run_endpoint_tests.py --mode full --coverage
```

### Test Modes

#### Unit Tests (`--mode unit`)
- Fast execution with mocks
- No external dependencies required
- Tests endpoint logic in isolation
- Good for development and CI

#### Integration Tests (`--mode integration`) 
- Requires running API server
- Tests with FastAPI TestClient
- Comprehensive workflow testing
- Authentication middleware testing

#### Live API Tests (`--mode live`)
- Tests against real API server
- Requires valid API key for auth tests
- Real HTTP requests
- Network connectivity validation
- Production readiness checks

#### Category Tests (`--mode category`)
- Test specific endpoint categories
- Available categories: health, models, dspy, mlflow, auth

### Direct Pytest Usage

```bash
# Run specific test files
pytest tests/unit/test_api_endpoints_unit.py -v

# Run with markers
pytest -m "health" -v
pytest -m "not slow" -v
pytest -m "auth" -v

# Run with coverage
pytest tests/unit/test_api_endpoints_unit.py --cov=src.api --cov-report=html

# Run integration tests
pytest tests/integration/test_comprehensive_endpoint_suite.py -v
```

### Live API Testing Script

```bash
# Test local development server
python scripts/test_api_endpoints.py --base-url http://localhost:8000

# Test with authentication
python scripts/test_api_endpoints.py --base-url https://api.hokus.ai --api-key hok_your_key

# Export results to JSON
python scripts/test_api_endpoints.py --export results.json
```

## Test Features

### Authentication Testing
- Tests endpoints with and without API keys
- Verifies 401 responses for protected endpoints  
- Tests proper authentication header handling
- Validates auth middleware behavior

### Response Validation
- JSON schema validation
- Required field presence checking
- Content-type header verification
- Response structure consistency

### Error Handling
- 404 for non-existent endpoints
- 405 for wrong HTTP methods
- 422 for invalid input data
- 400 for malformed requests
- 500 for server errors

### Performance Testing
- Response time measurement
- Timeout handling
- Rate limiting behavior (if implemented)

### Security Testing
- SQL injection protection
- XSS prevention
- Input validation
- CORS header verification

## Configuration

### Environment Variables

```bash
# For integration tests
export TEST_API_URL=http://localhost:8000
export TEST_API_KEY=hok_your_api_key

# For test database
export POSTGRES_URI=postgresql://test:test@localhost:5432/test_db
export MLFLOW_TRACKING_URI=file:///tmp/test_mlruns
```

### Pytest Configuration

The `pytest-endpoints.ini` file contains:
- Test discovery patterns
- Marker definitions  
- Timeout settings
- Logging configuration
- Filter settings

## Writing New Endpoint Tests

### Unit Test Example

```python
class TestNewEndpointUnit:
    """Unit tests for new endpoint."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    @pytest.fixture
    def mock_service(self):
        with patch("src.api.routes.new.service") as mock:
            yield mock
    
    def test_new_endpoint_success(self, client, mock_service):
        mock_service.method.return_value = {"data": "test"}
        
        response = client.get("/new-endpoint")
        
        assert response.status_code == 200
        assert response.json()["data"] == "test"
```

### Integration Test Example

```python
class TestNewEndpointIntegration(EndpointTestSuite):
    """Integration tests for new endpoint."""
    
    def test_new_endpoint_workflow(self, client, auth_headers):
        # Test complete workflow
        response = client.post("/new-endpoint", 
                             json={"input": "test"},
                             headers=auth_headers)
        
        assert response.status_code == 201
        # Add more assertions
```

### Live API Test Configuration

Add new endpoints to `scripts/test_api_endpoints.py`:

```python
{
    "path": "/new-endpoint",
    "method": "GET", 
    "auth_required": True,
    "expected_status": [200],
    "expected_fields": ["result", "timestamp"],
    "description": "New endpoint description"
}
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: API Endpoint Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run unit tests
        run: python scripts/run_endpoint_tests.py --mode unit --coverage
      - name: Start API server
        run: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
      - name: Wait for server
        run: sleep 5
      - name: Run integration tests
        run: python scripts/run_endpoint_tests.py --mode integration
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `PYTHONPATH=.` or run from project root
2. **MLflow Connection**: Mock MLflow in unit tests, ensure server runs for integration
3. **Authentication**: Use valid API keys for live tests, mock auth middleware for unit tests
4. **Database**: Use test database or mock database connections
5. **Timeouts**: Increase timeout values for slow networks

### Debug Mode

```bash
# Run with debug logging
pytest tests/ -v --log-cli-level=DEBUG

# Run single test with pdb
pytest tests/unit/test_api_endpoints_unit.py::TestHealthEndpointsUnit::test_health_check_success -s --pdb
```

### Test Data

- Use fixtures for consistent test data
- Mock external services in unit tests  
- Use test databases for integration tests
- Clean up test data after tests

## Contributing

When adding new API endpoints:

1. Add unit tests to `test_api_endpoints_unit.py`
2. Add integration tests to `test_comprehensive_endpoint_suite.py`
3. Add live API test configuration to `test_api_endpoints.py`
4. Update this documentation
5. Add appropriate test markers
6. Ensure authentication behavior is tested

## Test Results

The test suite provides:

- ✅/❌ Pass/fail indicators
- Response times
- Authentication verification  
- Field validation results
- Error details for failures
- Coverage reports
- JSON export of results

This comprehensive testing ensures API reliability, security, and proper functionality across all endpoints.