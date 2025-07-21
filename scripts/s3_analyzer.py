#!/usr/bin/env python3
"""S3 bucket lifecycle analyzer for investigating unexpected transitions."""

import json
import boto3
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_lifecycle_rules(lifecycle_config: Dict) -> List[Dict]:
    """Parse S3 lifecycle configuration into a simplified format.
    
    Args:
        lifecycle_config: S3 lifecycle configuration
        
    Returns:
        List of parsed rules
    """
    parsed_rules = []
    
    for rule in lifecycle_config.get('Rules', []):
        parsed_rule = {
            'id': rule.get('ID', 'Unnamed'),
            'status': rule.get('Status', 'Unknown'),
            'prefix': rule.get('Prefix', ''),
            'transitions': [],
            'expiration_days': None,
            'noncurrent_version_expiration_days': None
        }
        
        # Parse transitions
        for transition in rule.get('Transitions', []):
            parsed_rule['transitions'].append({
                'days': transition.get('Days'),
                'storage_class': transition.get('StorageClass')
            })
        
        # Parse expiration
        if 'Expiration' in rule:
            parsed_rule['expiration_days'] = rule['Expiration'].get('Days')
        
        # Parse noncurrent version expiration
        if 'NoncurrentVersionExpiration' in rule:
            parsed_rule['noncurrent_version_expiration_days'] = rule['NoncurrentVersionExpiration'].get('NoncurrentDays')
        
        parsed_rules.append(parsed_rule)
    
    return parsed_rules


def audit_bucket_lifecycles(region: str = 'us-east-1') -> Dict:
    """Audit lifecycle policies across all S3 buckets.
    
    Args:
        region: AWS region
        
    Returns:
        Dictionary of bucket audit results
    """
    s3_client = boto3.client('s3', region_name=region)
    audit_results = {}
    
    try:
        # List all buckets
        response = s3_client.list_buckets()
        buckets = response.get('Buckets', [])
        
        logger.info(f"Found {len(buckets)} buckets to audit")
        
        for bucket in buckets:
            bucket_name = bucket['Name']
            logger.info(f"Auditing bucket: {bucket_name}")
            
            try:
                # Get lifecycle configuration
                lifecycle = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                
                audit_results[bucket_name] = {
                    'has_lifecycle': True,
                    'rules': parse_lifecycle_rules(lifecycle),
                    'creation_date': bucket['CreationDate'].isoformat()
                }
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
                    audit_results[bucket_name] = {
                        'has_lifecycle': False,
                        'rules': [],
                        'creation_date': bucket['CreationDate'].isoformat()
                    }
                else:
                    logger.error(f"Error getting lifecycle for {bucket_name}: {e}")
                    audit_results[bucket_name] = {
                        'error': str(e),
                        'has_lifecycle': None
                    }
    
    except Exception as e:
        logger.error(f"Error listing buckets: {e}")
        raise
    
    return audit_results


def analyze_lifecycle_risks(audit_results: Dict) -> Dict:
    """Analyze lifecycle policies for potential risks.
    
    Args:
        audit_results: Results from audit_bucket_lifecycles
        
    Returns:
        Risk analysis
    """
    risks = {
        'high_risk': [],
        'medium_risk': [],
        'low_risk': [],
        'no_lifecycle': []
    }
    
    for bucket_name, bucket_info in audit_results.items():
        if bucket_info.get('error'):
            continue
            
        if not bucket_info['has_lifecycle']:
            risks['no_lifecycle'].append(bucket_name)
            continue
        
        for rule in bucket_info['rules']:
            if rule['status'] != 'Enabled':
                continue
            
            # High risk: Deletion within 30 days
            if rule['expiration_days'] and rule['expiration_days'] <= 30:
                risks['high_risk'].append({
                    'bucket': bucket_name,
                    'rule_id': rule['id'],
                    'reason': f"Objects expire after {rule['expiration_days']} days"
                })
            
            # Medium risk: Glacier transition within 7 days
            for transition in rule['transitions']:
                if transition['days'] and transition['days'] <= 7 and transition['storage_class'] in ['GLACIER', 'DEEP_ARCHIVE']:
                    risks['medium_risk'].append({
                        'bucket': bucket_name,
                        'rule_id': rule['id'],
                        'reason': f"Objects transition to {transition['storage_class']} after {transition['days']} days"
                    })
    
    return risks


def get_bucket_metrics(bucket_name: str, days: int = 7, region: str = 'us-east-1') -> Dict:
    """Get CloudWatch metrics for S3 bucket lifecycle transitions.
    
    Args:
        bucket_name: S3 bucket name
        days: Number of days to look back
        region: AWS region
        
    Returns:
        Metrics data
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    metrics = {}
    
    # Get number of objects
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/S3',
            MetricName='NumberOfObjects',
            Dimensions=[
                {'Name': 'BucketName', 'Value': bucket_name},
                {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,  # Daily
            Statistics=['Average']
        )
        
        metrics['object_count'] = [
            {'timestamp': dp['Timestamp'].isoformat(), 'value': dp['Average']}
            for dp in response.get('Datapoints', [])
        ]
        
    except Exception as e:
        logger.error(f"Error getting metrics for {bucket_name}: {e}")
    
    return metrics


def generate_s3_report(audit_results: Dict, output_file: str = 's3_lifecycle_report.json'):
    """Generate a report of S3 lifecycle analysis.
    
    Args:
        audit_results: Results from audit_bucket_lifecycles
        output_file: Output file path
    """
    risk_analysis = analyze_lifecycle_risks(audit_results)
    
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'summary': {
            'total_buckets': len(audit_results),
            'buckets_with_lifecycle': sum(1 for b in audit_results.values() if b.get('has_lifecycle')),
            'high_risk_rules': len(risk_analysis['high_risk']),
            'medium_risk_rules': len(risk_analysis['medium_risk'])
        },
        'risk_analysis': risk_analysis,
        'detailed_audit': audit_results
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report saved to {output_file}")
    
    # Log warnings for high-risk rules
    if risk_analysis['high_risk']:
        logger.warning(f"Found {len(risk_analysis['high_risk'])} high-risk lifecycle rules!")
        for risk in risk_analysis['high_risk']:
            logger.warning(f"  - {risk['bucket']}: {risk['reason']}")


def export_lifecycle_configs(output_dir: str = 'lifecycle_configs'):
    """Export all lifecycle configurations to individual JSON files.
    
    Args:
        output_dir: Directory to save configurations
    """
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    s3_client = boto3.client('s3')
    response = s3_client.list_buckets()
    
    for bucket in response.get('Buckets', []):
        bucket_name = bucket['Name']
        
        try:
            lifecycle = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
            
            output_file = os.path.join(output_dir, f"{bucket_name}_lifecycle.json")
            with open(output_file, 'w') as f:
                json.dump(lifecycle, f, indent=2)
            
            logger.info(f"Exported lifecycle config for {bucket_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchLifecycleConfiguration':
                logger.error(f"Error exporting lifecycle for {bucket_name}: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze S3 bucket lifecycle policies')
    parser.add_argument('--export', action='store_true', help='Export all lifecycle configs')
    parser.add_argument('--output', default='s3_lifecycle_report.json', help='Output report file')
    
    args = parser.parse_args()
    
    if args.export:
        export_lifecycle_configs()
    
    audit_results = audit_bucket_lifecycles()
    generate_s3_report(audit_results, args.output)