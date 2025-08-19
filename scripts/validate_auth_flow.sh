#!/bin/bash
# Validate authentication flow across all services

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}          Authentication Flow Validation Script${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Track overall status
ALL_PASSED=true

# Function to check command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to run a test
run_test() {
    local test_name=$1
    local test_command=$2
    
    echo -n "Testing $test_name... "
    
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        ALL_PASSED=false
        return 1
    fi
}

echo -e "${YELLOW}1. Checking Prerequisites${NC}"
echo "----------------------------"

# Check Python
if command_exists python3; then
    echo -e "Python: ${GREEN}✓${NC} $(python3 --version)"
else
    echo -e "Python: ${RED}✗ Not found${NC}"
    exit 1
fi

# Check pytest
if command_exists pytest; then
    echo -e "Pytest: ${GREEN}✓${NC} Found"
else
    echo -e "Pytest: ${RED}✗ Not found${NC}"
    echo "  Install with: pip install pytest"
    exit 1
fi

# Check if services are running
echo ""
echo -e "${YELLOW}2. Checking Local Services${NC}"
echo "----------------------------"

# Check API service
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "API Service: ${GREEN}✓ Running${NC}"
else
    echo -e "API Service: ${YELLOW}⚠ Not running${NC}"
    echo "  Start with: docker-compose up -d api"
fi

# Check MLflow service
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "MLflow Service: ${GREEN}✓ Running${NC}"
else
    echo -e "MLflow Service: ${YELLOW}⚠ Not running${NC}"
    echo "  Start with: docker-compose up -d mlflow"
fi

echo ""
echo -e "${YELLOW}3. Running Auth Unit Tests${NC}"
echo "----------------------------"

# Run auth unit tests
if [ -f "tests/auth/test_auth_flow.py" ]; then
    run_test "Auth flow tests" "pytest tests/auth/test_auth_flow.py -v --tb=short -q"
else
    echo -e "${YELLOW}⚠ Auth tests not found${NC}"
fi

echo ""
echo -e "${YELLOW}4. Running Proxy Validation Tests${NC}"
echo "-----------------------------------"

# Run proxy tests
if [ -f "tests/integration/test_proxy_auth.py" ]; then
    run_test "Proxy auth tests" "pytest tests/integration/test_proxy_auth.py -v --tb=short -q -m 'not integration'"
else
    echo -e "${YELLOW}⚠ Proxy tests not found${NC}"
fi

echo ""
echo -e "${YELLOW}5. Checking Source Code Patterns${NC}"
echo "---------------------------------"

# Check for auth anti-patterns in proxy code
echo -n "Checking for auth anti-patterns... "

ANTI_PATTERNS_FOUND=false

# Check for empty headers dict
if grep -r "headers = {}" src/api/proxy.py 2>/dev/null; then
    echo -e "${RED}✗ Found 'headers = {}' anti-pattern${NC}"
    ANTI_PATTERNS_FOUND=true
fi

# Check for auth header deletion
if grep -r "del.*Authorization" src/api/proxy.py 2>/dev/null; then
    echo -e "${RED}✗ Found Authorization header deletion${NC}"
    ANTI_PATTERNS_FOUND=true
fi

# Check for header popping
if grep -r "headers.pop.*Authorization" src/api/proxy.py 2>/dev/null; then
    echo -e "${RED}✗ Found Authorization header removal${NC}"
    ANTI_PATTERNS_FOUND=true
fi

if [ "$ANTI_PATTERNS_FOUND" = false ]; then
    echo -e "${GREEN}✓ No anti-patterns found${NC}"
fi

echo ""
echo -e "${YELLOW}6. Testing Auth Headers with Mock Token${NC}"
echo "----------------------------------------"

# Create a test token if not provided
if [ -z "$TEST_TOKEN" ]; then
    TEST_TOKEN="test-token-$(date +%s)"
    echo "Using mock token for testing"
fi

# Test with curl if services are running
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -n "Testing API with auth header... "
    
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TEST_TOKEN" \
        -H "X-User-ID: test-user" \
        http://localhost:8001/api/v1/health)
    
    if [ "$RESPONSE" != "401" ] && [ "$RESPONSE" != "403" ]; then
        echo -e "${GREEN}✓ Headers accepted${NC}"
    else
        echo -e "${YELLOW}⚠ Got $RESPONSE response${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}7. Validating Pre-commit Hooks${NC}"
echo "-------------------------------"

# Check if pre-commit is installed
if [ -f ".pre-commit-config.yaml" ]; then
    echo -n "Pre-commit config: "
    echo -e "${GREEN}✓ Found${NC}"
    
    # Check if hooks are installed
    if [ -d ".git/hooks" ] && [ -f ".git/hooks/pre-commit" ]; then
        echo -n "Pre-commit hooks: "
        echo -e "${GREEN}✓ Installed${NC}"
    else
        echo -n "Pre-commit hooks: "
        echo -e "${YELLOW}⚠ Not installed${NC}"
        echo "  Install with: pre-commit install"
    fi
    
    # Check hook scripts exist
    for hook in check-auth-headers.sh validate-proxy.py check-mlflow-auth.py; do
        if [ -f "scripts/hooks/$hook" ]; then
            echo -n "  $hook: "
            echo -e "${GREEN}✓${NC}"
        else
            echo -n "  $hook: "
            echo -e "${RED}✗ Missing${NC}"
            ALL_PASSED=false
        fi
    done
else
    echo -e "${RED}✗ Pre-commit config not found${NC}"
    ALL_PASSED=false
fi

echo ""
echo -e "${YELLOW}8. Documentation Check${NC}"
echo "----------------------"

# Check for auth documentation
for doc in AUTH_ARCHITECTURE.md PROXY_CHECKLIST.md ONBOARDING.md; do
    if [ -f "docs/$doc" ]; then
        echo -n "$doc: "
        echo -e "${GREEN}✓ Present${NC}"
    else
        echo -n "$doc: "
        echo -e "${RED}✗ Missing${NC}"
        ALL_PASSED=false
    fi
done

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}                     Validation Summary${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$ALL_PASSED" = true ]; then
    echo -e "${GREEN}✓ All authentication checks passed!${NC}"
    echo ""
    echo "Your authentication setup is properly configured."
    exit 0
else
    echo -e "${RED}✗ Some authentication checks failed${NC}"
    echo ""
    echo "Please review the failures above and:"
    echo "1. Fix any anti-patterns in the code"
    echo "2. Ensure all tests pass"
    echo "3. Install pre-commit hooks"
    echo "4. Review authentication documentation"
    echo ""
    echo "See docs/AUTH_ARCHITECTURE.md for details"
    exit 1
fi