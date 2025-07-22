#!/usr/bin/env python3
"""Terraform state drift analyzer for detecting configuration drift."""

import json
import boto3
import subprocess
from typing import List, Dict, Optional
import logging
from datetime import datetime
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def detect_drift(tf_state: Dict, actual_state: Dict) -> List[Dict]:
    """Detect drift between Terraform state and actual AWS resources.
    
    Args:
        tf_state: Terraform state data
        actual_state: Actual AWS resource state
        
    Returns:
        List of drift items
    """
    drift_items = []
    
    # Analyze RDS instances
    tf_rds_instances = {}
    for resource in tf_state.get('resources', []):
        if resource['type'] == 'aws_db_instance':
            for instance in resource.get('instances', []):
                attrs = instance.get('attributes', {})
                tf_rds_instances[attrs.get('id')] = attrs
    
    # Compare with actual RDS instances
    for db_instance in actual_state.get('DBInstances', []):
        db_id = db_instance['DBInstanceIdentifier']
        
        if db_id in tf_rds_instances:
            tf_attrs = tf_rds_instances[db_id]
            
            # Check engine version
            if tf_attrs.get('engine_version') != db_instance.get('EngineVersion'):
                drift_items.append({
                    'resource': f'aws_db_instance.{db_id}',
                    'attribute': 'engine_version',
                    'terraform_value': tf_attrs.get('engine_version'),
                    'actual_value': db_instance.get('EngineVersion')
                })
            
            # Check instance class
            if tf_attrs.get('instance_class') != db_instance.get('DBInstanceClass'):
                drift_items.append({
                    'resource': f'aws_db_instance.{db_id}',
                    'attribute': 'instance_class',
                    'terraform_value': tf_attrs.get('instance_class'),
                    'actual_value': db_instance.get('DBInstanceClass')
                })
            
            # Check allocated storage
            if tf_attrs.get('allocated_storage') != db_instance.get('AllocatedStorage'):
                drift_items.append({
                    'resource': f'aws_db_instance.{db_id}',
                    'attribute': 'allocated_storage',
                    'terraform_value': tf_attrs.get('allocated_storage'),
                    'actual_value': db_instance.get('AllocatedStorage')
                })
    
    return drift_items


def get_terraform_state(state_file: Optional[str] = None) -> Dict:
    """Get Terraform state, either from file or remote backend.
    
    Args:
        state_file: Optional path to state file
        
    Returns:
        Terraform state dict
    """
    if state_file and os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return json.load(f)
    else:
        # Pull state from backend
        try:
            result = subprocess.run(
                ['terraform', 'state', 'pull'],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to pull Terraform state: {e}")
            raise


def get_actual_aws_state(region: str = 'us-east-1') -> Dict:
    """Get actual state of AWS resources.
    
    Args:
        region: AWS region
        
    Returns:
        Dictionary of actual AWS resource states
    """
    actual_state = {}
    
    # Get RDS instances
    rds_client = boto3.client('rds', region_name=region)
    try:
        response = rds_client.describe_db_instances()
        actual_state['DBInstances'] = response.get('DBInstances', [])
    except Exception as e:
        logger.error(f"Error getting RDS instances: {e}")
    
    # Get ECS task definitions
    ecs_client = boto3.client('ecs', region_name=region)
    try:
        # Get clusters first
        clusters_response = ecs_client.list_clusters()
        clusters = clusters_response.get('clusterArns', [])
        
        actual_state['ECSClusters'] = []
        for cluster_arn in clusters:
            cluster_detail = ecs_client.describe_clusters(clusters=[cluster_arn])
            actual_state['ECSClusters'].extend(cluster_detail.get('clusters', []))
    except Exception as e:
        logger.error(f"Error getting ECS clusters: {e}")
    
    # Get S3 buckets
    s3_client = boto3.client('s3', region_name=region)
    try:
        response = s3_client.list_buckets()
        actual_state['S3Buckets'] = response.get('Buckets', [])
    except Exception as e:
        logger.error(f"Error getting S3 buckets: {e}")
    
    return actual_state


def analyze_state_locks(region: str = 'us-east-1') -> Dict:
    """Analyze Terraform state locking mechanism.
    
    Args:
        region: AWS region
        
    Returns:
        State lock analysis
    """
    dynamodb = boto3.client('dynamodb', region_name=region)
    
    # Look for common Terraform lock table patterns
    lock_tables = []
    try:
        response = dynamodb.list_tables()
        for table_name in response.get('TableNames', []):
            if 'terraform' in table_name.lower() and 'lock' in table_name.lower():
                lock_tables.append(table_name)
    except Exception as e:
        logger.error(f"Error listing DynamoDB tables: {e}")
    
    lock_analysis = {
        'lock_tables_found': lock_tables,
        'recommendations': []
    }
    
    if not lock_tables:
        lock_analysis['recommendations'].append(
            "No Terraform state lock table found. Consider implementing state locking to prevent concurrent modifications."
        )
    
    return lock_analysis


def check_terraform_workspaces() -> Dict:
    """Check Terraform workspace configuration.
    
    Returns:
        Workspace information
    """
    workspace_info = {
        'current_workspace': 'default',
        'all_workspaces': ['default']
    }
    
    try:
        # Get current workspace
        result = subprocess.run(
            ['terraform', 'workspace', 'show'],
            capture_output=True,
            text=True,
            check=True
        )
        workspace_info['current_workspace'] = result.stdout.strip()
        
        # List all workspaces
        result = subprocess.run(
            ['terraform', 'workspace', 'list'],
            capture_output=True,
            text=True,
            check=True
        )
        workspaces = [w.strip().replace('*', '').strip() for w in result.stdout.split('\n') if w.strip()]
        workspace_info['all_workspaces'] = workspaces
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking Terraform workspaces: {e}")
    
    return workspace_info


def generate_drift_report(
    drift_items: List[Dict],
    lock_analysis: Dict,
    workspace_info: Dict,
    output_file: str = 'terraform_drift_report.json'
):
    """Generate a comprehensive drift report.
    
    Args:
        drift_items: List of drift items
        lock_analysis: State lock analysis
        workspace_info: Workspace information
        output_file: Output file path
    """
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'summary': {
            'total_drift_items': len(drift_items),
            'affected_resources': list(set(item['resource'] for item in drift_items)),
            'current_workspace': workspace_info['current_workspace']
        },
        'drift_details': drift_items,
        'state_locking': lock_analysis,
        'workspace_info': workspace_info,
        'recommendations': []
    }
    
    # Add recommendations based on findings
    if drift_items:
        report['recommendations'].append(
            "Significant drift detected. Run 'terraform plan' to review changes and 'terraform apply' to reconcile."
        )
    
    if not lock_analysis['lock_tables_found']:
        report['recommendations'].append(
            "Implement Terraform state locking using DynamoDB to prevent concurrent state modifications."
        )
    
    if len(workspace_info['all_workspaces']) > 1:
        report['recommendations'].append(
            f"Multiple workspaces detected: {workspace_info['all_workspaces']}. Ensure you're in the correct workspace."
        )
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Drift report saved to {output_file}")
    
    if drift_items:
        logger.warning(f"Found {len(drift_items)} drift items!")
        for item in drift_items[:5]:  # Show first 5
            logger.warning(f"  - {item['resource']}.{item['attribute']}: {item['terraform_value']} -> {item['actual_value']}")


def run_terraform_plan(output_file: str = 'terraform_plan.txt'):
    """Run terraform plan and save output.
    
    Args:
        output_file: File to save plan output
    """
    try:
        logger.info("Running terraform plan...")
        result = subprocess.run(
            ['terraform', 'plan', '-no-color'],
            capture_output=True,
            text=True,
            check=False
        )
        
        with open(output_file, 'w') as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n\nERRORS:\n")
                f.write(result.stderr)
        
        logger.info(f"Terraform plan output saved to {output_file}")
        
        # Check if there are changes
        if "No changes" in result.stdout:
            logger.info("No changes detected by Terraform")
        else:
            logger.warning("Terraform detected changes that need to be applied")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running terraform plan: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze Terraform state drift')
    parser.add_argument('--state-file', help='Path to Terraform state file (optional)')
    parser.add_argument('--plan', action='store_true', help='Also run terraform plan')
    parser.add_argument('--output', default='terraform_drift_report.json', help='Output report file')
    
    args = parser.parse_args()
    
    # Get Terraform state
    logger.info("Getting Terraform state...")
    tf_state = get_terraform_state(args.state_file)
    
    # Get actual AWS state
    logger.info("Getting actual AWS state...")
    actual_state = get_actual_aws_state()
    
    # Detect drift
    logger.info("Detecting drift...")
    drift_items = detect_drift(tf_state, actual_state)
    
    # Analyze state locking
    logger.info("Analyzing state locking...")
    lock_analysis = analyze_state_locks()
    
    # Check workspaces
    logger.info("Checking Terraform workspaces...")
    workspace_info = check_terraform_workspaces()
    
    # Generate report
    generate_drift_report(drift_items, lock_analysis, workspace_info, args.output)
    
    # Optionally run terraform plan
    if args.plan:
        run_terraform_plan()