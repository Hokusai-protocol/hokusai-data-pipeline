# 📄 Infrastructure Consolidation Requirements

## 🧩 Overview

All Hokusai-related repositories currently manage infrastructure independently, leading to frequent routing conflicts, overlapping resource definitions, and operational drift.

To solve this, we are centralizing shared infrastructure into a new repository:

> **`hokusai-infrastructure`**

This document outlines the required changes for each service repository to:
- Package relevant infra components for migration
- Adopt a standard integration interface
- Rely on the centralized `hokusai-infrastructure` repo for shared resource provisioning

---

## 🗃️ Part 1: What to Move into `hokusai-infrastructure`

Each repo must audit and move the following:

### ✅ Move These:
| Resource Type | Examples |
|---------------|----------|
| Load balancers (ALB, NLB) | ALB listeners, rules, target groups |
| API Gateway domains and base path mappings | Shared custom domains |
| Route53 DNS records | Subdomains like `auth.hokusai.ai`, `api.hokusai.ai` |
| VPC, subnets, NAT Gateways | If not service-specific |
| CloudFront distributions | If shared among services |
| IAM roles used for cross-service access | AssumeRole roles, shared policies |

**📂 Output**: Each repo must submit a `terraform_module/` subdirectory that defines their currently owned shared resources.

---

## 🛠️ Part 2: How to Transition

### 🔄 Step 1: Extract Shared Resources
- Identify all resources that match the list above.
- Move them into a `terraform_module/<service_name>` directory.
- Replace hardcoded values with variables and outputs where possible.

### 🔀 Step 2: Refactor Local Code
- Remove the now-centralized infrastructure from local Terraform code.
- Replace it with `data` lookups or output references from the `hokusai-infrastructure` repo.

Example:

```hcl
data "terraform_remote_state" "infra" {
  backend = "s3"
  config = {
    bucket = "hokusai-infrastructure-tfstate"
    key    = "prod/infra.tfstate"
    region = "us-east-1"
  }
}

resource "aws_lambda_permission" "allow_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = module.my_lambda.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = data.terraform_remote_state.infra.outputs.api_gateway_execution_arn
}
```

---

## 📘 Part 3: Documenting Path and Resource Ownership

Each team **must submit a registry entry** into the shared registry file at:

> `hokusai-infrastructure/docs/resource_registry.md`

### Example Entry Format:

```markdown
### Service: auth-api

**Path Prefix**: `/auth/*`  
**DNS**: `auth.hokusai.ai`  
**Provisioned Resources**:  
- API Gateway base path `/auth`
- Route53 record `auth.hokusai.ai`
- IAM Role: `auth_service_execution_role`

**Owner**: `auth-team@hokusai.ai`  
**Contact**: `slack: #hokusai-auth`
```

---

## 🚀 Part 4: Provisioning Strategy (Current & Future)

### 🔧 For Current Services

Each service should:
1. Submit their `terraform_module/` with all shared components.
2. Open a PR to the `hokusai-infrastructure` repo with:
   - Their module
   - A usage example in `environments/prod.tf`
   - An entry in the `resource_registry.md`

### 🛎️ For Future Provisioning Requests

To request new infrastructure (e.g., subdomains, base path mappings, or shared roles), service teams must:

1. Submit a PR to `hokusai-infrastructure`
2. Add a module invocation in the relevant `environments/` file (e.g., `prod.tf`, `staging.tf`)
3. Update the registry file
4. Provide a Terraform plan output for approval

Provisioning is managed via GitHub Actions and will only run after manual approval from the infrastructure team.

---

## 🧪 Part 5: Validation and CI Checks

### Required in Each Module Submission:
- Follows `terraform fmt`
- Passes `tflint`
- Does not duplicate any path or DNS entries in `resource_registry.md`
- Provides `outputs.tf` with values required by the calling service

---

## 📎 Part 6: Directory Structure of `hokusai-infrastructure`

```
hokusai-infrastructure/
├── terraform_module/
│   ├── auth-api/
│   ├── user-service/
│   └── payments-api/
├── environments/
│   ├── staging.tf
│   └── prod.tf
├── modules/
│   └── shared/
├── docs/
│   └── resource_registry.md
└── .github/workflows/
    └── terraform-deploy.yml
```

---

## 🧭 Migration Timeline

| Date        | Milestone |
|-------------|-----------|
| Week 1      | Repo audits and resource extraction |
| Week 2      | Submit PRs to `hokusai-infrastructure` |
| Week 3–4    | Merge + cutover to new Terraform outputs |
| Week 5      | Lock down path conflicts and finalize registry enforcement |