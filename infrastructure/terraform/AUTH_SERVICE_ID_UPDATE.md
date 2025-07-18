# AUTH_SERVICE_ID Terraform Configuration Update

## Changes Made

1. **Added to variables.tf**:
   - New variable `auth_service_id` with default value "platform"
   - This allows flexible configuration between "platform" and "ml-platform"

2. **Updated main.tf**:
   - Added AUTH_SERVICE_ID environment variable to the API task definition
   - Uses the variable value, making it configurable

## Deployment Instructions

1. **Navigate to the Terraform directory**:
   ```bash
   cd infrastructure/terraform
   ```

2. **Initialize Terraform** (if not already done):
   ```bash
   terraform init
   ```

3. **Review the changes**:
   ```bash
   terraform plan
   ```
   
   You should see that the API task definition will be updated to include the new environment variable.

4. **Apply the changes**:
   ```bash
   terraform apply
   ```
   
   Type "yes" when prompted to confirm.

5. **ECS will automatically update**:
   - The ECS service will detect the task definition change
   - It will perform a rolling update, replacing containers with the new configuration
   - This typically takes 2-5 minutes

## Verification

After deployment, run:
```bash
python test_deployment_status.py
```

This should show:
- ✅ API key validates with 'platform' service
- ✅ Proxy accepts the API key
- ✅ Model registration works

## Customization

If you need to use a different service ID, you can override the default:

```bash
terraform apply -var="auth_service_id=ml-platform"
```

Or create a terraform.tfvars file:
```hcl
auth_service_id = "ml-platform"
```

## Rollback

If needed, you can rollback by setting it back to "ml-platform":
```bash
terraform apply -var="auth_service_id=ml-platform"
```