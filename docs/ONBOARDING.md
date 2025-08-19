# Developer Onboarding Guide

## Welcome to Hokusai Data Pipeline

This guide will help you get up and running with the Hokusai data pipeline development environment. Pay special attention to the authentication section, as it's critical for proper service communication.

## Table of Contents
1. [Environment Setup](#environment-setup)
2. [Understanding Authentication](#understanding-authentication)
3. [Development Workflow](#development-workflow)
4. [Testing Guidelines](#testing-guidelines)
5. [Common Tasks](#common-tasks)
6. [Troubleshooting](#troubleshooting)

## Environment Setup

### Prerequisites
- Python 3.9+
- Docker and Docker Compose
- AWS CLI configured
- Node.js 16+ (for some tooling)

### Initial Setup
```bash
# Clone the repository
git clone <repository-url>
cd hokusai-data-pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
pip install -r requirements.txt

# Install pre-commit hooks (IMPORTANT!)
pip install pre-commit
pre-commit install

# Copy environment variables
cp .env.example .env
# Edit .env with your configuration
```

### Docker Setup
```bash
# Start local services
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs if needed
docker-compose logs -f api
docker-compose logs -f mlflow
```

## Understanding Authentication

### 🔐 Day 1: Authentication Basics

**CRITICAL**: Understanding authentication is essential for working with this codebase. Many bugs and production issues stem from improper auth handling.

#### Required Reading
1. **[AUTH_ARCHITECTURE.md](./AUTH_ARCHITECTURE.md)** - Complete authentication flow
2. **[PROXY_CHECKLIST.md](./PROXY_CHECKLIST.md)** - Checklist for proxy modifications

#### Key Concepts

1. **Authentication Flow**
   ```
   Client → ALB → Auth Service → Data Pipeline API → MLflow
   ```
   Every request must maintain authentication headers throughout this chain.

2. **Critical Headers**
   - `Authorization: Bearer <token>` - JWT token for authentication
   - `X-User-ID` - User identifier for audit logging
   - `X-Request-ID` - Request tracing ID

3. **Service Communication**
   - External: Through ALB with public URLs
   - Internal: Through service discovery (*.hokusai-development.local)

#### Authentication Quick Test
```bash
# Set up test token (get from auth service)
export TOKEN="your-jwt-token-here"

# Test API authentication
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8001/api/v1/health

# Test MLflow authentication
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:5000/api/2.0/mlflow/experiments/list
```

### 🛡️ Before Your First Code Change

If you're modifying ANY of these files/areas:
- `src/api/proxy.py`
- Any file with "auth" in the name
- Any MLflow integration code
- Any API endpoint handlers

**YOU MUST**:
1. Read [PROXY_CHECKLIST.md](./PROXY_CHECKLIST.md)
2. Run auth tests before committing
3. Ensure pre-commit hooks pass

### 🧪 Testing Authentication Locally

```bash
# Start auth service mock for testing
docker-compose up auth-mock

# Get a test token
export TOKEN=$(cat test/fixtures/valid-token.txt)

# Run auth flow tests
pytest tests/auth/test_auth_flow.py -v

# Test proxy with auth
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-User-ID: test-user" \
     http://localhost:8001/api/v1/models

# Validate complete auth flow
./scripts/validate_auth_flow.sh
```

## Development Workflow

### 1. Pre-Commit Hooks
Pre-commit hooks are MANDATORY and will check:
- Code formatting (ruff)
- Authentication header handling
- Proxy configuration validation
- MLflow authentication setup

```bash
# Run hooks manually
pre-commit run --all-files

# Run specific hook
pre-commit run check-auth-headers --all-files
```

### 2. Branch Strategy
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Create bugfix branch
git checkout -b bugfix/issue-description
```

### 3. Making Changes
1. Write tests first (TDD encouraged)
2. Implement feature/fix
3. Run tests locally
4. Ensure pre-commit hooks pass
5. Create pull request

### 4. Code Review Checklist
Before requesting review:
- [ ] Tests pass locally
- [ ] Pre-commit hooks pass
- [ ] Auth headers properly handled (if applicable)
- [ ] Documentation updated
- [ ] No hardcoded credentials

## Testing Guidelines

### Running Tests
```bash
# All tests
pytest

# Specific test file
pytest tests/unit/test_api.py

# With coverage
pytest --cov=src --cov-report=html

# Auth-specific tests (RUN THESE if you touch auth code!)
pytest tests/auth/ -v
pytest tests/integration/test_proxy_auth.py -v
```

### Test Categories
- **Unit Tests**: `tests/unit/` - Fast, isolated tests
- **Integration Tests**: `tests/integration/` - Test service interactions
- **Auth Tests**: `tests/auth/` - Authentication flow tests
- **E2E Tests**: `tests/e2e/` - Full system tests

## Common Tasks

### Adding a New API Endpoint
1. Define endpoint in `src/api/routes/`
2. Add authentication decorator
3. Write tests
4. Update API documentation

Example:
```python
from src.api.auth import require_auth

@app.route('/api/v1/resource', methods=['POST'])
@require_auth  # Always add authentication!
def create_resource():
    # Your endpoint logic
    pass
```

### Working with MLflow
```python
# Always set up authentication for MLflow
import os
from src.api.auth_utils import get_auth_headers

# Option 1: Environment variable
os.environ['MLFLOW_TRACKING_TOKEN'] = get_token()

# Option 2: With headers (for requests)
headers = get_auth_headers(request)
response = requests.post(mlflow_url, headers=headers)
```

### Modifying the Proxy
⚠️ **CRITICAL**: Read [PROXY_CHECKLIST.md](./PROXY_CHECKLIST.md) first!

```python
# ALWAYS preserve headers
def proxy_request(path, request):
    headers = dict(request.headers)  # Preserve ALL headers
    headers.pop('Host', None)  # Only remove Host
    
    # Make upstream request with preserved headers
    response = requests.request(
        method=request.method,
        url=upstream_url,
        headers=headers,  # Auth preserved!
        data=request.get_data()
    )
```

### Database Migrations
```bash
# Create migration
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

## Troubleshooting

### Common Issues

#### 1. Authentication Errors
```bash
# Error: 401 Unauthorized
# Solution: Check if token is valid
curl -H "Authorization: Bearer $TOKEN" https://auth.hokus.ai/api/v1/validate

# Check if headers are being forwarded
python scripts/diagnose_auth_issue.py
```

#### 2. MLflow Connection Issues
```bash
# Test MLflow connectivity
python scripts/test_mlflow_connection.py

# Check MLflow logs
docker-compose logs mlflow

# Verify auth headers in MLflow
MLFLOW_TRACKING_TOKEN=$TOKEN python -c "import mlflow; mlflow.list_experiments()"
```

#### 3. Service Discovery Issues
```bash
# Test internal service resolution
nslookup mlflow.hokusai-development.local

# Check service health
curl http://localhost:8001/health
curl http://localhost:5000/health
```

### Debug Commands
```bash
# View service logs
docker-compose logs -f api
aws logs tail /ecs/hokusai-api-development --follow

# Check for auth errors in logs
aws logs filter-log-events \
    --log-group-name /ecs/hokusai-api-development \
    --filter-pattern "401|403|Unauthorized"

# Test complete auth flow
./scripts/test_auth_flow.sh
```

### Getting Help
1. Check existing documentation in `docs/`
2. Search for similar issues in the codebase
3. Ask in the development Slack channel
4. Create a detailed issue if you find a bug

## Important Resources

### Documentation
- [AUTH_ARCHITECTURE.md](./AUTH_ARCHITECTURE.md) - Authentication details
- [PROXY_CHECKLIST.md](./PROXY_CHECKLIST.md) - Proxy modification guide
- [API Documentation](./api/README.md) - API endpoint reference
- [MLflow Guide](./MLFLOW_GUIDE.md) - MLflow integration

### Scripts
- `scripts/validate_auth_flow.sh` - Validate authentication
- `scripts/test_mlflow_connection.py` - Test MLflow connectivity
- `scripts/diagnose_service_health.py` - Service health checks

### Key Files
- `src/api/auth.py` - Authentication logic
- `src/api/proxy.py` - Proxy implementation
- `src/api/auth_utils.py` - Auth utility functions
- `.env.example` - Environment variables template

## Final Checklist

Before pushing code:
- [ ] Pre-commit hooks pass
- [ ] Tests pass locally
- [ ] No hardcoded credentials
- [ ] Auth headers preserved (if touching proxy/API code)
- [ ] Documentation updated if needed

## Welcome Aboard! 🚀

You're now ready to contribute to the Hokusai data pipeline. Remember:
- **Authentication is critical** - When in doubt, preserve all headers
- **Test thoroughly** - Especially auth-related changes
- **Ask questions** - Better to ask than break production

Happy coding!