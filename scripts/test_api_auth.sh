#!/bin/bash

# Test API Authentication Methods

API_URL="http://registry.hokus.ai/api"

echo "Testing Hokusai API Authentication"
echo "=================================="

# Test 1: Try with the existing test_user key
echo -e "\n1. Testing with existing test_user API key:"
API_KEY=$(aws secretsmanager get-secret-value --secret-id hokusai/api-keys/test_user --query SecretString --output text 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "   Found API key: ${API_KEY:0:10}..."
    curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/health" | jq . || echo "Failed"
else
    echo "   Could not retrieve test_user API key"
fi

# Test 2: Generate and test a new API key
echo -e "\n2. Generate a new API key:"
echo "   Run: python scripts/auth_helper.py"
echo "   Choose option 1 and follow the prompts"

# Test 3: Example ETH authentication
echo -e "\n3. Example ETH authentication test:"
echo "   For testing, you can use a test private key (DO NOT use real keys!):"
echo "   "
echo "   # Example with test private key"
echo "   python scripts/auth_helper.py"
echo "   # Choose option 2"
echo "   # Enter a test private key like: 0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
echo "   "
echo "   This will generate the curl command with proper headers"

# Test 4: Check if API is accessible without auth (should fail)
echo -e "\n4. Testing without authentication (should fail):"
curl -s "$API_URL/health" | jq .

echo -e "\n5. API Documentation (requires authentication):"
echo "   Once authenticated, access: $API_URL/docs"