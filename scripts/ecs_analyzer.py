#!/usr/bin/env python3
"""ECS task definition analyzer for investigating version reversions."""

import json
import boto3
from typing import List, Dict, Tuple, Optional
import logging
from datetime import datetime
from deepdiff import DeepDiff

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def compare_task_definitions(task_def_old: Dict, task_def_new: Dict) -> Dict:
    """Compare two task definition versions and return differences.
    
    Args:
        task_def_old: Older task definition
        task_def_new: Newer task definition
        
    Returns:
        Dictionary of differences
    """
    differences = {}
    
    # Check container definitions
    old_containers = {c['name']: c for c in task_def_old.get('containerDefinitions', [])}
    new_containers = {c['name']: c for c in task_def_new.get('containerDefinitions', [])}
    
    for container_name in old_containers:
        if container_name in new_containers:
            old_container = old_containers[container_name]
            new_container = new_containers[container_name]
            
            # Check image changes
            if old_container.get('image') != new_container.get('image'):
                old_image = old_container.get('image', '').split('/')[-1]
                new_image = new_container.get('image', '').split('/')[-1]
                differences['image'] = {
                    'old': old_image,
                    'new': new_image
                }
            
            # Check memory/CPU changes
            if old_container.get('memory') != new_container.get('memory'):
                differences['memory'] = {
                    'old': old_container.get('memory'),
                    'new': new_container.get('memory')
                }
            
            if old_container.get('cpu') != new_container.get('cpu'):
                differences['cpu'] = {
                    'old': old_container.get('cpu'),
                    'new': new_container.get('cpu')
                }
            
            # Check environment variables
            old_env = {e['name']: e['value'] for e in old_container.get('environment', [])}
            new_env = {e['name']: e['value'] for e in new_container.get('environment', [])}
            
            if old_env != new_env:
                differences['environment'] = {
                    'added': {k: v for k, v in new_env.items() if k not in old_env},
                    'removed': {k: v for k, v in old_env.items() if k not in new_env},
                    'changed': {k: {'old': old_env[k], 'new': new_env[k]} 
                               for k in old_env if k in new_env and old_env[k] != new_env[k]}
                }
    
    return differences


def list_task_definition_revisions(family: str, region: str = 'us-east-1') -> List[int]:
    """List all revisions of a task definition family.
    
    Args:
        family: Task definition family name
        region: AWS region
        
    Returns:
        List of revision numbers
    """
    client = boto3.client('ecs', region_name=region)
    revisions = []
    
    try:
        paginator = client.get_paginator('list_task_definitions')
        page_iterator = paginator.paginate(
            familyPrefix=family,
            sort='DESC'
        )
        
        for page in page_iterator:
            for task_def_arn in page.get('taskDefinitionArns', []):
                # Extract revision number from ARN
                revision = int(task_def_arn.split(':')[-1])
                revisions.append(revision)
        
        revisions.sort()
        
    except Exception as e:
        logger.error(f"Error listing task definitions: {e}")
        raise
    
    return revisions


def get_task_definition(family: str, revision: int, region: str = 'us-east-1') -> Dict:
    """Get a specific task definition revision.
    
    Args:
        family: Task definition family name
        revision: Revision number
        region: AWS region
        
    Returns:
        Task definition dict
    """
    client = boto3.client('ecs', region_name=region)
    
    try:
        response = client.describe_task_definition(
            taskDefinition=f"{family}:{revision}"
        )
        return response['taskDefinition']
    except Exception as e:
        logger.error(f"Error getting task definition {family}:{revision}: {e}")
        raise


def analyze_task_definition_history(
    family: str,
    start_revision: Optional[int] = None,
    end_revision: Optional[int] = None,
    region: str = 'us-east-1'
) -> Dict:
    """Analyze task definition revision history.
    
    Args:
        family: Task definition family name
        start_revision: Starting revision (optional)
        end_revision: Ending revision (optional)
        region: AWS region
        
    Returns:
        Analysis results
    """
    logger.info(f"Analyzing task definition history for {family}")
    
    # Get all revisions
    all_revisions = list_task_definition_revisions(family, region)
    logger.info(f"Found {len(all_revisions)} revisions: {all_revisions}")
    
    # Filter revisions if specified
    if start_revision:
        all_revisions = [r for r in all_revisions if r >= start_revision]
    if end_revision:
        all_revisions = [r for r in all_revisions if r <= end_revision]
    
    # Analyze changes between consecutive revisions
    changes = []
    for i in range(len(all_revisions) - 1):
        old_revision = all_revisions[i]
        new_revision = all_revisions[i + 1]
        
        logger.info(f"Comparing revision {old_revision} -> {new_revision}")
        
        old_def = get_task_definition(family, old_revision, region)
        new_def = get_task_definition(family, new_revision, region)
        
        differences = compare_task_definitions(old_def, new_def)
        
        if differences:
            changes.append({
                'from_revision': old_revision,
                'to_revision': new_revision,
                'changes': differences,
                'registered_at': new_def.get('registeredAt', '').split('.')[0] + 'Z' if new_def.get('registeredAt') else None
            })
    
    return {
        'family': family,
        'total_revisions': len(all_revisions),
        'analyzed_revisions': all_revisions,
        'changes': changes
    }


def check_for_reversions(changes: List[Dict]) -> List[Dict]:
    """Check for potential reversions in task definition changes.
    
    Args:
        changes: List of changes from analyze_task_definition_history
        
    Returns:
        List of potential reversions
    """
    reversions = []
    
    # Look for patterns where an image or config goes back to a previous value
    seen_images = {}
    
    for change in changes:
        if 'image' in change['changes']:
            old_image = change['changes']['image']['old']
            new_image = change['changes']['image']['new']
            
            # Check if we've seen this image before
            if new_image in seen_images and seen_images[new_image] < change['from_revision']:
                reversions.append({
                    'type': 'image_reversion',
                    'revision': change['to_revision'],
                    'reverted_to': new_image,
                    'previously_used_in': seen_images[new_image],
                    'timestamp': change.get('registered_at')
                })
            
            seen_images[old_image] = change['from_revision']
            seen_images[new_image] = change['to_revision']
    
    return reversions


def generate_ecs_report(analysis: Dict, output_file: str = 'ecs_task_definition_report.json'):
    """Generate a report of ECS task definition analysis.
    
    Args:
        analysis: Analysis results
        output_file: Output file path
    """
    # Check for reversions
    reversions = check_for_reversions(analysis['changes'])
    
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'summary': {
            'family': analysis['family'],
            'total_revisions': analysis['total_revisions'],
            'total_changes': len(analysis['changes']),
            'reversions_detected': len(reversions)
        },
        'reversions': reversions,
        'detailed_changes': analysis['changes']
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report saved to {output_file}")
    
    if reversions:
        logger.warning(f"Found {len(reversions)} potential reversions!")
        for reversion in reversions:
            logger.warning(f"  - Revision {reversion['revision']} reverted to image previously used in revision {reversion['previously_used_in']}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze ECS task definition history')
    parser.add_argument('family', help='Task definition family name')
    parser.add_argument('--start', type=int, help='Start revision')
    parser.add_argument('--end', type=int, help='End revision')
    parser.add_argument('--output', default='ecs_task_definition_report.json', help='Output report file')
    
    args = parser.parse_args()
    
    analysis = analyze_task_definition_history(
        args.family,
        start_revision=args.start,
        end_revision=args.end
    )
    
    generate_ecs_report(analysis, args.output)