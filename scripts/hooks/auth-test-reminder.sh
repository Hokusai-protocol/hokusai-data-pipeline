#!/bin/bash
# Remind developers to run auth tests after changes

set -e

# Colors for output
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}⚠️  AUTHENTICATION CODE MODIFIED - TESTING REQUIRED${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "You've modified authentication-related code. Please run the following tests:"
echo ""
echo -e "${CYAN}1. Unit tests for auth flow:${NC}"
echo "   pytest tests/auth/test_auth_flow.py -v"
echo ""
echo -e "${CYAN}2. Integration tests for proxy:${NC}"
echo "   pytest tests/integration/test_proxy_auth.py -v"
echo ""
echo -e "${CYAN}3. MLflow authentication test:${NC}"
echo "   python scripts/test_mlflow_connection.py"
echo ""
echo -e "${CYAN}4. Full auth validation:${NC}"
echo "   ./scripts/validate_auth_flow.sh"
echo ""
echo "After testing, review the checklist in docs/PROXY_CHECKLIST.md"
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Always exit 0 - this is just a reminder
exit 0