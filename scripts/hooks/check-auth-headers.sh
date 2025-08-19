#!/bin/bash
# Check for proper authentication header forwarding in modified files

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

issues_found=0

echo "Checking authentication header handling..."

for file in "$@"; do
    # Skip non-Python files for detailed checks
    if [[ ! "$file" =~ \.py$ ]]; then
        continue
    fi
    
    # Check for API calls without auth headers
    if grep -l "requests\.\(get\|post\|put\|delete\|patch\)" "$file" > /dev/null 2>&1; then
        # Check if headers are being passed
        if ! grep -l "headers\s*=" "$file" > /dev/null 2>&1; then
            echo -e "${YELLOW}Warning: $file contains HTTP requests but may not pass headers${NC}"
            issues_found=1
        fi
    fi
    
    # Check for proxy functions that might strip headers
    if grep -l "def.*proxy" "$file" > /dev/null 2>&1; then
        # Check if Authorization header is preserved
        if ! grep -l "Authorization" "$file" > /dev/null 2>&1; then
            echo -e "${RED}Error: $file contains proxy function but doesn't mention Authorization header${NC}"
            echo "       Ensure all authentication headers are forwarded!"
            issues_found=1
        fi
    fi
    
    # Check for MLflow client usage without auth
    if grep -l "MlflowClient\|mlflow\." "$file" > /dev/null 2>&1; then
        # Check if auth headers or tokens are configured
        if ! grep -E "(MLFLOW_TRACKING_TOKEN|Authorization|headers)" "$file" > /dev/null 2>&1; then
            echo -e "${YELLOW}Warning: $file uses MLflow but may lack authentication setup${NC}"
            issues_found=1
        fi
    fi
done

if [ $issues_found -eq 0 ]; then
    echo -e "${GREEN}✓ Authentication header checks passed${NC}"
    exit 0
else
    echo -e "${RED}✗ Authentication issues detected. Please review the warnings above.${NC}"
    echo ""
    echo "Before proceeding, ensure:"
    echo "1. All API calls include proper authentication headers"
    echo "2. Proxy functions forward ALL headers (especially Authorization)"
    echo "3. MLflow operations include authentication tokens"
    echo ""
    echo "Refer to docs/AUTH_ARCHITECTURE.md for details"
    exit 1
fi