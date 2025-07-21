#!/usr/bin/env python3
"""Set up infrastructure monitoring and alerts."""

import json
import boto3
from typing import Dict, List, Optional
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_rds_change_alarm(
    db_instance_id: str,
    sns_topic_arn: str,
    region: str = 'us-east-1'
) -> str:
    """Create CloudWatch alarm for RDS password changes.
    
    Args:
        db_instance_id: RDS instance identifier
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
        
    Returns:
        Alarm name
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    alarm_name = f"RDS-PasswordChange-{db_instance_id}"
    
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName='UserActivityCount',
            Namespace='AWS/RDS',
            Period=300,
            Statistic='Sum',
            Threshold=0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription=f'Alert on password changes for RDS instance {db_instance_id}',
            Dimensions=[
                {
                    'Name': 'DBInstanceIdentifier',
                    'Value': db_instance_id
                }
            ]
        )
        
        logger.info(f"Created alarm: {alarm_name}")
        return alarm_name
        
    except Exception as e:
        logger.error(f"Error creating RDS alarm: {e}")
        raise


def create_ecs_task_definition_alarm(
    cluster_name: str,
    service_name: str,
    sns_topic_arn: str,
    region: str = 'us-east-1'
) -> str:
    """Create CloudWatch alarm for ECS task definition changes.
    
    Args:
        cluster_name: ECS cluster name
        service_name: ECS service name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
        
    Returns:
        Alarm name
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    alarm_name = f"ECS-TaskDefChange-{service_name}"
    
    try:
        # Create custom metric filter first
        logs = boto3.client('logs', region_name=region)
        
        filter_name = f"ECS-TaskDef-{service_name}"
        log_group = f"/aws/events/ecs/{cluster_name}"
        
        try:
            logs.put_metric_filter(
                logGroupName=log_group,
                filterName=filter_name,
                filterPattern='[time, request_id, event_type="TaskDefinitionChange", ...]',
                metricTransformations=[
                    {
                        'metricName': f'TaskDefinitionChanges-{service_name}',
                        'metricNamespace': 'CustomMetrics/ECS',
                        'metricValue': '1'
                    }
                ]
            )
        except Exception as e:
            logger.warning(f"Could not create metric filter: {e}")
        
        # Create alarm
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName=f'TaskDefinitionChanges-{service_name}',
            Namespace='CustomMetrics/ECS',
            Period=300,
            Statistic='Sum',
            Threshold=0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription=f'Alert on task definition changes for {service_name}'
        )
        
        logger.info(f"Created alarm: {alarm_name}")
        return alarm_name
        
    except Exception as e:
        logger.error(f"Error creating ECS alarm: {e}")
        raise


def create_s3_lifecycle_alarm(
    bucket_name: str,
    sns_topic_arn: str,
    region: str = 'us-east-1'
) -> str:
    """Create CloudWatch alarm for S3 lifecycle transitions.
    
    Args:
        bucket_name: S3 bucket name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
        
    Returns:
        Alarm name
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    alarm_name = f"S3-LifecycleTransition-{bucket_name}"
    
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='LessThanThreshold',
            EvaluationPeriods=2,
            MetricName='NumberOfObjects',
            Namespace='AWS/S3',
            Period=86400,  # Daily
            Statistic='Average',
            Threshold=0.9,  # Alert if objects drop by more than 10%
            TreatMissingData='notBreaching',
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription=f'Alert on significant object count changes in {bucket_name}',
            Dimensions=[
                {
                    'Name': 'BucketName',
                    'Value': bucket_name
                },
                {
                    'Name': 'StorageType',
                    'Value': 'AllStorageTypes'
                }
            ]
        )
        
        logger.info(f"Created alarm: {alarm_name}")
        return alarm_name
        
    except Exception as e:
        logger.error(f"Error creating S3 alarm: {e}")
        raise


def create_sns_topic(topic_name: str, email: str, region: str = 'us-east-1') -> str:
    """Create SNS topic for infrastructure alerts.
    
    Args:
        topic_name: SNS topic name
        email: Email address for notifications
        region: AWS region
        
    Returns:
        Topic ARN
    """
    sns = boto3.client('sns', region_name=region)
    
    try:
        # Create topic
        response = sns.create_topic(Name=topic_name)
        topic_arn = response['TopicArn']
        
        logger.info(f"Created SNS topic: {topic_arn}")
        
        # Subscribe email
        sns.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=email
        )
        
        logger.info(f"Subscribed {email} to topic (check email for confirmation)")
        
        return topic_arn
        
    except Exception as e:
        logger.error(f"Error creating SNS topic: {e}")
        raise


def setup_aws_config_rules(region: str = 'us-east-1') -> List[str]:
    """Set up AWS Config rules for compliance monitoring.
    
    Args:
        region: AWS region
        
    Returns:
        List of created rule names
    """
    config = boto3.client('config', region_name=region)
    created_rules = []
    
    # Check if Config is enabled
    try:
        response = config.describe_configuration_recorders()
        if not response['ConfigurationRecorders']:
            logger.warning("AWS Config is not enabled. Please enable Config service first.")
            return created_rules
    except Exception as e:
        logger.error(f"Error checking Config status: {e}")
        return created_rules
    
    # Define rules to create
    rules = [
        {
            'name': 'rds-instance-backup-enabled',
            'source': {
                'Owner': 'AWS',
                'SourceIdentifier': 'DB_INSTANCE_BACKUP_ENABLED'
            },
            'description': 'Checks if RDS instances have backup enabled'
        },
        {
            'name': 'ecs-task-definition-log-configuration',
            'source': {
                'Owner': 'AWS',
                'SourceIdentifier': 'ECS_TASK_DEFINITION_LOG_CONFIGURATION'
            },
            'description': 'Checks if ECS task definitions have logging configured'
        },
        {
            'name': 's3-bucket-lifecycle-policy-check',
            'source': {
                'Owner': 'AWS',
                'SourceIdentifier': 'S3_LIFECYCLE_POLICY_CHECK'
            },
            'description': 'Checks if S3 buckets have lifecycle policies'
        }
    ]
    
    for rule in rules:
        try:
            config.put_config_rule(
                ConfigRule={
                    'ConfigRuleName': rule['name'],
                    'Description': rule['description'],
                    'Source': rule['source'],
                    'Scope': {
                        'ComplianceResourceTypes': [
                            'AWS::RDS::DBInstance',
                            'AWS::ECS::TaskDefinition',
                            'AWS::S3::Bucket'
                        ]
                    }
                }
            )
            
            created_rules.append(rule['name'])
            logger.info(f"Created Config rule: {rule['name']}")
            
        except Exception as e:
            logger.error(f"Error creating Config rule {rule['name']}: {e}")
    
    return created_rules


def create_cloudtrail_event_rules(sns_topic_arn: str, region: str = 'us-east-1') -> List[str]:
    """Create EventBridge rules for infrastructure changes.
    
    Args:
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
        
    Returns:
        List of created rule names
    """
    events = boto3.client('events', region_name=region)
    created_rules = []
    
    # Define event patterns
    event_patterns = [
        {
            'name': 'RDS-PasswordChange-Rule',
            'pattern': {
                "source": ["aws.rds"],
                "detail-type": ["AWS API Call via CloudTrail"],
                "detail": {
                    "eventSource": ["rds.amazonaws.com"],
                    "eventName": ["ModifyDBInstance"],
                    "requestParameters": {
                        "masterUserPassword": [{"exists": True}]
                    }
                }
            }
        },
        {
            'name': 'ECS-TaskDefinition-Rule',
            'pattern': {
                "source": ["aws.ecs"],
                "detail-type": ["AWS API Call via CloudTrail"],
                "detail": {
                    "eventSource": ["ecs.amazonaws.com"],
                    "eventName": ["RegisterTaskDefinition"]
                }
            }
        }
    ]
    
    for rule_config in event_patterns:
        try:
            # Create rule
            response = events.put_rule(
                Name=rule_config['name'],
                EventPattern=json.dumps(rule_config['pattern']),
                State='ENABLED',
                Description=f"Monitor {rule_config['name'].replace('-Rule', '')} events"
            )
            
            rule_arn = response['RuleArn']
            
            # Add SNS target
            events.put_targets(
                Rule=rule_config['name'],
                Targets=[
                    {
                        'Id': '1',
                        'Arn': sns_topic_arn
                    }
                ]
            )
            
            created_rules.append(rule_config['name'])
            logger.info(f"Created EventBridge rule: {rule_config['name']}")
            
        except Exception as e:
            logger.error(f"Error creating EventBridge rule {rule_config['name']}: {e}")
    
    return created_rules


def generate_monitoring_report(
    alarms: List[str],
    config_rules: List[str],
    event_rules: List[str],
    sns_topic_arn: str,
    output_file: str = 'monitoring_setup_report.json'
):
    """Generate a report of monitoring setup.
    
    Args:
        alarms: List of created CloudWatch alarms
        config_rules: List of created Config rules
        event_rules: List of created EventBridge rules
        sns_topic_arn: SNS topic ARN
        output_file: Output file path
    """
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'summary': {
            'cloudwatch_alarms': len(alarms),
            'config_rules': len(config_rules),
            'event_rules': len(event_rules),
            'sns_topic': sns_topic_arn
        },
        'monitoring_components': {
            'cloudwatch_alarms': alarms,
            'aws_config_rules': config_rules,
            'eventbridge_rules': event_rules
        },
        'next_steps': [
            "Confirm SNS email subscription",
            "Test alarms with simulated events",
            "Review and adjust alarm thresholds",
            "Set up CloudWatch dashboard"
        ]
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Monitoring setup report saved to {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Set up infrastructure monitoring')
    parser.add_argument('--email', required=True, help='Email for notifications')
    parser.add_argument('--rds-instance', help='RDS instance to monitor')
    parser.add_argument('--ecs-cluster', help='ECS cluster name')
    parser.add_argument('--ecs-service', help='ECS service name')
    parser.add_argument('--s3-bucket', help='S3 bucket to monitor')
    parser.add_argument('--output', default='monitoring_setup_report.json', help='Output report file')
    
    args = parser.parse_args()
    
    # Create SNS topic
    logger.info("Creating SNS topic...")
    sns_topic_arn = create_sns_topic('HokusaiInfrastructureAlerts', args.email)
    
    alarms = []
    
    # Create RDS alarm
    if args.rds_instance:
        alarm_name = create_rds_change_alarm(args.rds_instance, sns_topic_arn)
        alarms.append(alarm_name)
    
    # Create ECS alarm
    if args.ecs_cluster and args.ecs_service:
        alarm_name = create_ecs_task_definition_alarm(
            args.ecs_cluster,
            args.ecs_service,
            sns_topic_arn
        )
        alarms.append(alarm_name)
    
    # Create S3 alarm
    if args.s3_bucket:
        alarm_name = create_s3_lifecycle_alarm(args.s3_bucket, sns_topic_arn)
        alarms.append(alarm_name)
    
    # Set up Config rules
    logger.info("Setting up AWS Config rules...")
    config_rules = setup_aws_config_rules()
    
    # Create EventBridge rules
    logger.info("Creating EventBridge rules...")
    event_rules = create_cloudtrail_event_rules(sns_topic_arn)
    
    # Generate report
    generate_monitoring_report(alarms, config_rules, event_rules, sns_topic_arn, args.output)