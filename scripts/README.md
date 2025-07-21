# Infrastructure Investigation Scripts

This directory contains Python scripts for investigating and monitoring AWS infrastructure issues.

## Prerequisites

```bash
pip install boto3 deepdiff
```

Ensure AWS credentials are configured:
```bash
aws configure
```

## Scripts Overview

### 1. CloudTrail Analyzer (`cloudtrail_analyzer.py`)

Analyzes AWS CloudTrail logs to identify RDS password changes and other security events.

**Usage:**
```bash
# Analyze last 30 days of RDS password changes
python cloudtrail_analyzer.py --days 30

# Generate report
python cloudtrail_analyzer.py --days 7 --output rds_report.json
```

**Features:**
- Filters RDS modification events
- Identifies password changes
- Tracks user identities
- Generates JSON reports

### 2. ECS Task Definition Analyzer (`ecs_analyzer.py`)

Compares ECS task definition versions to detect reversions and configuration changes.

**Usage:**
```bash
# Analyze all revisions of a task definition
python ecs_analyzer.py hokusai-api

# Analyze specific revision range
python ecs_analyzer.py hokusai-api --start 28 --end 32

# Generate detailed report
python ecs_analyzer.py hokusai-api --output ecs_report.json
```

**Features:**
- Lists all task definition revisions
- Compares configurations between versions
- Detects image reversions
- Identifies environment variable changes

### 3. S3 Lifecycle Analyzer (`s3_analyzer.py`)

Audits S3 bucket lifecycle policies to identify aggressive retention rules.

**Usage:**
```bash
# Audit all buckets
python s3_analyzer.py

# Export all lifecycle configurations
python s3_analyzer.py --export

# Generate risk analysis report
python s3_analyzer.py --output s3_report.json
```

**Features:**
- Audits all S3 buckets
- Identifies high-risk lifecycle rules
- Exports configurations for backup
- Analyzes retention policies

### 4. Terraform Drift Detector (`terraform_analyzer.py`)

Detects configuration drift between Terraform state and actual AWS resources.

**Usage:**
```bash
# Analyze drift in current directory
python terraform_analyzer.py

# Use specific state file
python terraform_analyzer.py --state-file terraform.tfstate

# Also run terraform plan
python terraform_analyzer.py --plan

# Generate drift report
python terraform_analyzer.py --output drift_report.json
```

**Features:**
- Compares Terraform state with AWS
- Detects resource drift
- Checks state locking configuration
- Analyzes workspace setup

### 5. Monitoring Setup (`monitoring_setup.py`)

Sets up comprehensive AWS monitoring for infrastructure changes.

**Usage:**
```bash
# Set up monitoring for all resources
python monitoring_setup.py \
  --email admin@example.com \
  --rds-instance my-database \
  --ecs-cluster my-cluster \
  --ecs-service my-service \
  --s3-bucket my-bucket

# Minimal setup (just email)
python monitoring_setup.py --email admin@example.com
```

**Features:**
- Creates SNS topic for alerts
- Sets up CloudWatch alarms
- Configures AWS Config rules
- Creates EventBridge rules
- Generates setup report

## Running Tests

```bash
# Run all tests
pytest tests/test_infrastructure_investigation.py -v

# Run specific test class
pytest tests/test_infrastructure_investigation.py::TestCloudTrailAnalyzer -v
```

## Daily Operations

### Morning Health Check
```bash
# Check for overnight issues
python cloudtrail_analyzer.py --days 1
python terraform_analyzer.py
```

### Weekly Audit
```bash
# Comprehensive infrastructure audit
python cloudtrail_analyzer.py --days 7 --output weekly_rds.json
python ecs_analyzer.py hokusai-api --output weekly_ecs.json
python s3_analyzer.py --output weekly_s3.json
python terraform_analyzer.py --plan --output weekly_drift.json
```

### Incident Investigation
```bash
# When investigating a specific incident
python cloudtrail_analyzer.py --days 30 | grep -i "suspicious_user"
python ecs_analyzer.py service-name --start 50 --end 60
```

## Output Files

All scripts generate JSON reports with standardized format:
```json
{
  "generated_at": "2025-07-20T10:30:00Z",
  "summary": {
    "key_metrics": "values"
  },
  "details": [],
  "recommendations": []
}
```

## Troubleshooting

### Permission Errors
Ensure your AWS credentials have the following permissions:
- `cloudtrail:LookupEvents`
- `ecs:Describe*`
- `s3:GetBucketLifecycleConfiguration`
- `cloudwatch:PutMetricAlarm`
- `sns:CreateTopic`

### Timeout Issues
For large environments, increase timeouts:
```python
# In scripts, modify boto3 client creation:
client = boto3.client('service', 
                     region_name='us-east-1',
                     config=Config(read_timeout=300))
```

### Missing Dependencies
```bash
pip install -r requirements.txt
```

## Contributing

1. Add tests for new functionality
2. Follow existing code patterns
3. Update this README with new script documentation
4. Include example usage in script help text

## License

Internal use only - Hokusai Infrastructure Team