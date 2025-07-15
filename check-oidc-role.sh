#\!/bin/bash
# Check if the role exists and what repos it trusts
ROLE_NAME="GitHubActionsDeployRole"
TRUST_POLICY=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.AssumeRolePolicyDocument' 2>/dev/null)

if [ $? -eq 0 ]; then
    echo "Role exists. Trust policy:"
    echo "$TRUST_POLICY" | jq .
    echo ""
    echo "Role ARN:"
    aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text
else
    echo "Role does not exist. You need to create it."
fi
