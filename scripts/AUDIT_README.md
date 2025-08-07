# Hokusai API Endpoint Audit Scripts

This directory contains scripts to audit and test all endpoints in the Hokusai MLOps API.

## Scripts Overview

### 1. `audit_endpoints.py` - Main Audit Script

The comprehensive endpoint audit script that:
- Automatically discovers all endpoints by parsing route files
- Tests each endpoint against a live API server  
- Generates detailed reports in JSON format
- Supports authentication and concurrent testing

**Usage:**
```bash
python scripts/audit_endpoints.py [options]
```

**Options:**
- `--base-url URL` - API server URL to test (default: https://registry.hokus.ai)
- `--api-key KEY` - API key for authentication
- `--output FILE` - Output file for JSON report
- `--timeout SECONDS` - Request timeout (default: 10)
- `--max-concurrent N` - Max concurrent requests (default: 10)
- `--routes-dir DIR` - Directory with route files (default: src/api/routes)

**Examples:**
```bash
# Test production API
python scripts/audit_endpoints.py --base-url https://registry.hokus.ai

# Test with authentication
python scripts/audit_endpoints.py --api-key sk-1234567890 --output report.json

# Test local development server
python scripts/audit_endpoints.py --base-url http://localhost:8000 --timeout 5
```

### 2. `analyze_audit.py` - Report Analysis Script

Analyzes audit reports and provides human-readable insights.

**Usage:**
```bash
python scripts/analyze_audit.py <report.json>
```

**Output includes:**
- Success/failure statistics
- Status code distribution
- Working endpoints list
- Authentication-required endpoints
- Missing/not implemented endpoints
- File-by-file analysis
- Recommendations

### 3. `run_audit.sh` - Convenience Script

Shell script wrapper for common audit scenarios.

**Usage:**
```bash
./scripts/run_audit.sh [environment] [api_key]
```

**Environments:**
- `production` - https://registry.hokus.ai (default)
- `staging` - https://staging-registry.hokus.ai  
- `local` - http://localhost:8000

**Examples:**
```bash
# Audit production environment
./scripts/run_audit.sh production

# Audit with API key
./scripts/run_audit.sh production sk-1234567890

# Audit local development
./scripts/run_audit.sh local
```

## How It Works

### Endpoint Discovery

The audit script uses regex parsing to extract endpoint definitions from FastAPI route files:

1. **Route Files Scanning**: Scans `src/api/routes/*.py` for route decorators
2. **Decorator Parsing**: Finds `@router.get()`, `@router.post()`, etc. patterns
3. **Prefix Application**: Applies known route prefixes from `main.py` configuration
4. **Catalog Generation**: Creates a comprehensive list of all expected endpoints

### Endpoint Testing

For each discovered endpoint:

1. **HTTP Request**: Makes appropriate HTTP request (GET/POST/PUT/DELETE/etc.)
2. **Authentication**: Includes API key headers if provided
3. **Response Analysis**: Determines success based on status codes and context
4. **Performance Tracking**: Records response times

### Success Criteria

The script considers endpoints successful based on context:
- **2xx responses**: Always successful
- **401/403 for auth endpoints**: Expected (indicates auth is working)
- **404 for GET endpoints**: May be acceptable (no test data)
- **422 for POST/PUT**: May be acceptable (invalid test data format)
- **405 Method Not Allowed**: Indicates endpoint exists but wrong method

## Report Format

### JSON Report Structure

```json
{
  "audit_timestamp": "2025-08-07T12:22:29.183972",
  "base_url": "https://registry.hokus.ai",
  "summary": {
    "total_endpoints": 78,
    "successful": 29,
    "failed": 49,
    "success_rate": "37.2%",
    "average_response_time_ms": 128.9
  },
  "status_code_distribution": {
    "200": 1,
    "401": 19,
    "404": 58
  },
  "results_by_file": {
    "models.py": {
      "total": 13,
      "success": 8,
      "failed": 5
    }
  },
  "detailed_results": [
    {
      "method": "GET",
      "path": "/health",
      "status_code": 200,
      "success": true,
      "response_time_ms": 145.2,
      "has_auth": false
    }
  ],
  "failed_endpoints": [...]
}
```

## Interpreting Results

### Status Code Meanings

- **200 OK**: Endpoint working correctly
- **401 Unauthorized**: Authentication required (provide API key)
- **404 Not Found**: Endpoint may not be implemented or requires parameters
- **422 Unprocessable Entity**: Invalid request data (expected for test data)
- **500 Internal Server Error**: Server-side issue
- **502 Bad Gateway**: Proxy/infrastructure issue
- **503 Service Unavailable**: Service temporarily down

### Common Issues

1. **High 404 Rate**: Many endpoints may require specific URL parameters or not be implemented
2. **401 Errors**: Endpoints requiring authentication - provide `--api-key`
3. **{path:path} Endpoints**: Catch-all routes that may need specific paths
4. **Timeout Errors**: Network issues or slow responses

## Development Notes

### Adding New Route Files

When adding new route files to `src/api/routes/`, the audit script will automatically discover them. If routes use prefixes, update the `prefix_mappings` in `_apply_route_prefixes()`.

### Testing Strategy

The audit uses simple test data patterns:
- Model endpoints: `{"name": "test-model", "version": "1"}`
- DSPy endpoints: `{"program_id": "test-program", "inputs": {"test": "data"}}`
- Generic: `{"test": "data"}`

For more comprehensive testing, implement endpoint-specific test data generation.

### Performance Considerations

- Use `--max-concurrent` to control load on the server
- Adjust `--timeout` based on expected response times
- Consider rate limiting when testing production APIs

## Requirements

- Python 3.7+
- `httpx` library for HTTP requests
- Access to `src/api/routes/` directory
- Optional: API key for authenticated endpoints

## Installation

```bash
pip install httpx
```

That's it! The scripts are self-contained Python files.