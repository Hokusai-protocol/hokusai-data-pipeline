#!/usr/bin/env python3
"""CloudTrail log analyzer for investigating RDS password changes."""

import json
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_rds_events(events: List[Dict]) -> List[Dict]:
    """Parse RDS-related events from CloudTrail logs.
    
    Args:
        events: List of CloudTrail events
        
    Returns:
        List of parsed RDS events with relevant information
    """
    parsed_events = []
    
    for event in events:
        if event.get('eventSource') == 'rds.amazonaws.com':
            parsed_event = {
                'event_time': event.get('eventTime'),
                'event_name': event.get('eventName'),
                'instance_id': None,
                'changed_by': None,
                'password_changed': False
            }
            
            # Extract user identity
            user_identity = event.get('userIdentity', {})
            parsed_event['changed_by'] = user_identity.get('userName', user_identity.get('type', 'Unknown'))
            
            # Extract request parameters
            request_params = event.get('requestParameters', {})
            parsed_event['instance_id'] = request_params.get('dBInstanceIdentifier')
            
            # Check if password was changed
            if 'masterUserPassword' in request_params:
                parsed_event['password_changed'] = True
            
            # Only include events that modified instances
            if event.get('eventName') in ['ModifyDBInstance', 'CreateDBInstance', 'RestoreDBInstanceFromDBSnapshot']:
                parsed_events.append(parsed_event)
    
    return parsed_events


def filter_events_by_time(events: List[Dict], days_back: int = 7) -> List[Dict]:
    """Filter events by time range.
    
    Args:
        events: List of events with eventTime field
        days_back: Number of days to look back
        
    Returns:
        Filtered list of events within the time range
    """
    cutoff_time = datetime.utcnow() - timedelta(days=days_back)
    filtered_events = []
    
    for event in events:
        event_time_str = event.get('eventTime', '')
        # Remove 'Z' suffix and parse
        event_time_str = event_time_str.rstrip('Z')
        try:
            event_time = datetime.fromisoformat(event_time_str)
            if event_time >= cutoff_time:
                filtered_events.append(event)
        except ValueError:
            logger.warning(f"Could not parse event time: {event_time_str}")
    
    return filtered_events


def fetch_cloudtrail_events(
    event_name: Optional[str] = None,
    days_back: int = 7,
    region: str = 'us-east-1'
) -> List[Dict]:
    """Fetch events from AWS CloudTrail.
    
    Args:
        event_name: Optional event name filter
        days_back: Number of days to look back
        region: AWS region
        
    Returns:
        List of CloudTrail events
    """
    client = boto3.client('cloudtrail', region_name=region)
    events = []
    
    start_time = datetime.utcnow() - timedelta(days=days_back)
    end_time = datetime.utcnow()
    
    lookup_attributes = []
    if event_name:
        lookup_attributes.append({
            'AttributeKey': 'EventName',
            'AttributeValue': event_name
        })
    
    try:
        paginator = client.get_paginator('lookup_events')
        page_iterator = paginator.paginate(
            LookupAttributes=lookup_attributes,
            StartTime=start_time,
            EndTime=end_time
        )
        
        for page in page_iterator:
            for event in page.get('Events', []):
                # Parse the CloudTrailEvent JSON string
                if 'CloudTrailEvent' in event:
                    event_detail = json.loads(event['CloudTrailEvent'])
                    event_detail['eventTime'] = event['EventTime'].isoformat() + 'Z'
                    events.append(event_detail)
        
    except ClientError as e:
        logger.error(f"Error fetching CloudTrail events: {e}")
        raise
    
    return events


def analyze_rds_password_changes(days_back: int = 30):
    """Analyze RDS password changes in CloudTrail logs.
    
    Args:
        days_back: Number of days to analyze
    """
    logger.info(f"Fetching CloudTrail events for the last {days_back} days...")
    
    # Fetch ModifyDBInstance events
    events = fetch_cloudtrail_events(
        event_name='ModifyDBInstance',
        days_back=days_back
    )
    
    logger.info(f"Found {len(events)} ModifyDBInstance events")
    
    # Parse RDS events
    rds_events = parse_rds_events(events)
    
    # Filter for password changes
    password_changes = [e for e in rds_events if e['password_changed']]
    
    if password_changes:
        logger.info(f"\nFound {len(password_changes)} password change events:")
        for event in password_changes:
            logger.info(f"  - {event['event_time']}: {event['instance_id']} by {event['changed_by']}")
    else:
        logger.info("No RDS password changes found in the specified time range")
    
    return password_changes


def generate_report(password_changes: List[Dict], output_file: str = 'rds_password_changes_report.json'):
    """Generate a report of RDS password changes.
    
    Args:
        password_changes: List of password change events
        output_file: Output file path
    """
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'summary': {
            'total_password_changes': len(password_changes),
            'affected_instances': list(set(e['instance_id'] for e in password_changes)),
            'users_involved': list(set(e['changed_by'] for e in password_changes))
        },
        'events': password_changes
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report saved to {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze CloudTrail logs for RDS password changes')
    parser.add_argument('--days', type=int, default=30, help='Number of days to look back')
    parser.add_argument('--output', default='rds_password_changes_report.json', help='Output report file')
    
    args = parser.parse_args()
    
    password_changes = analyze_rds_password_changes(days_back=args.days)
    if password_changes:
        generate_report(password_changes, args.output)