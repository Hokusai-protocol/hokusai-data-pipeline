#!/bin/bash
#
# Simple script to run API endpoint audit against different environments.
#
# Usage:
#     ./scripts/run_audit.sh [production|staging|local] [API_KEY]
#
# Examples:
#     ./scripts/run_audit.sh production
#     ./scripts/run_audit.sh local
#     ./scripts/run_audit.sh production sk-1234567890
#

set -e

# Default values
ENVIRONMENT=${1:-production}
API_KEY=${2:-""}
TIMEOUT=10
MAX_CONCURRENT=5

# Environment URLs
case $ENVIRONMENT in
    production)
        BASE_URL="https://registry.hokus.ai"
        ;;
    staging)
        BASE_URL="https://staging-registry.hokus.ai"
        ;;
    local)
        BASE_URL="http://localhost:8000"
        TIMEOUT=5
        ;;
    *)
        echo "Error: Unknown environment '$ENVIRONMENT'"
        echo "Supported environments: production, staging, local"
        exit 1
        ;;
esac

# Output files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="audit_report_${ENVIRONMENT}_${TIMESTAMP}.json"
SUMMARY_FILE="audit_summary_${ENVIRONMENT}_${TIMESTAMP}.txt"

echo "Starting API endpoint audit..."
echo "Environment: $ENVIRONMENT"
echo "Base URL: $BASE_URL"
echo "Report file: $REPORT_FILE"
echo "----------------------------------------"

# Build command
CMD="python scripts/audit_endpoints.py --base-url $BASE_URL --timeout $TIMEOUT --max-concurrent $MAX_CONCURRENT --output $REPORT_FILE"

# Add API key if provided
if [ -n "$API_KEY" ]; then
    CMD="$CMD --api-key $API_KEY"
    echo "Using provided API key"
fi

# Run the audit
echo "Running audit..."
if eval $CMD; then
    echo "✅ Audit completed successfully!"
else
    echo "⚠️  Audit completed with some issues."
fi

# Generate analysis
if [ -f "$REPORT_FILE" ]; then
    echo "Generating analysis..."
    python scripts/analyze_audit.py "$REPORT_FILE" > "$SUMMARY_FILE"
    
    echo "Files generated:"
    echo "  📄 Detailed report: $REPORT_FILE"
    echo "  📊 Summary analysis: $SUMMARY_FILE"
    
    # Show summary
    echo ""
    echo "Summary:"
    head -20 "$SUMMARY_FILE"
    echo ""
    echo "For full analysis, see: $SUMMARY_FILE"
else
    echo "❌ Report file not generated"
    exit 1
fi