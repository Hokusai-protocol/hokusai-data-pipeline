"""Tests for infrastructure investigation tools."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestCloudTrailAnalyzer:
    """Test CloudTrail log analysis for RDS password changes."""

    def test_parse_rds_password_change_event(self):
        """Test parsing of RDS password change events from CloudTrail."""
        from scripts.cloudtrail_analyzer import parse_rds_events

        # Sample CloudTrail event for RDS password change
        sample_event = {
            "eventTime": "2025-07-20T10:30:00Z",
            "eventName": "ModifyDBInstance",
            "eventSource": "rds.amazonaws.com",
            "userIdentity": {"type": "IAMUser", "userName": "terraform-user"},
            "requestParameters": {
                "dBInstanceIdentifier": "hokusai-production",
                "masterUserPassword": "HIDDEN_DUE_TO_SECURITY_REASONS",
            },
        }

        events = [sample_event]
        parsed = parse_rds_events(events)

        assert len(parsed) == 1
        assert parsed[0]["instance_id"] == "hokusai-production"
        assert parsed[0]["changed_by"] == "terraform-user"
        assert "password_changed" in parsed[0]
        assert parsed[0]["password_changed"] is True

    @patch("scripts.cloudtrail_analyzer.datetime")
    def test_filter_events_by_time_range(self, mock_datetime):
        """Test filtering CloudTrail events by time range."""
        from scripts.cloudtrail_analyzer import filter_events_by_time

        # Mock datetime.utcnow() to return a fixed time
        fixed_now = datetime(2025, 7, 20, 12, 0, 0)
        mock_datetime.utcnow.return_value = fixed_now
        mock_datetime.fromisoformat = datetime.fromisoformat  # Keep the original fromisoformat

        events = [
            {"eventTime": (fixed_now - timedelta(days=1)).isoformat() + "Z"},
            {"eventTime": (fixed_now - timedelta(days=6)).isoformat() + "Z"},
            {"eventTime": (fixed_now - timedelta(days=30)).isoformat() + "Z"},
        ]

        # Filter last 7 days
        filtered = filter_events_by_time(events, days_back=7)
        assert len(filtered) == 2

        # Filter last 24 hours
        filtered = filter_events_by_time(events, days_back=1)
        assert len(filtered) == 1

    @patch("boto3.client")
    def test_fetch_cloudtrail_events(self, mock_boto_client):
        """Test fetching events from CloudTrail API."""
        from scripts.cloudtrail_analyzer import fetch_cloudtrail_events

        # Mock CloudTrail client
        mock_cloudtrail = MagicMock()
        mock_boto_client.return_value = mock_cloudtrail

        # Mock response
        mock_cloudtrail.lookup_events.return_value = {
            "Events": [
                {
                    "EventName": "ModifyDBInstance",
                    "EventTime": datetime.utcnow(),
                    "CloudTrailEvent": json.dumps(
                        {
                            "eventSource": "rds.amazonaws.com",
                            "requestParameters": {"dBInstanceIdentifier": "test-db"},
                        }
                    ),
                }
            ],
            "NextToken": None,
        }

        events = fetch_cloudtrail_events(event_name="ModifyDBInstance", days_back=7)

        assert len(events) == 1
        mock_cloudtrail.lookup_events.assert_called_once()


class TestECSTaskDefinitionAnalyzer:
    """Test ECS task definition version analysis."""

    def test_compare_task_definitions(self):
        """Test comparison between two task definition versions."""
        from scripts.ecs_analyzer import compare_task_definitions

        task_def_v30 = {
            "family": "hokusai-api",
            "taskDefinitionArn": "arn:aws:ecs:us-east-1:123456789:task-definition/hokusai-api:30",
            "containerDefinitions": [
                {
                    "name": "api",
                    "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/hokusai-api:v1.0.0",
                    "memory": 512,
                    "cpu": 256,
                }
            ],
        }

        task_def_v31 = {
            "family": "hokusai-api",
            "taskDefinitionArn": "arn:aws:ecs:us-east-1:123456789:task-definition/hokusai-api:31",
            "containerDefinitions": [
                {
                    "name": "api",
                    "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/hokusai-api:v1.1.0",
                    "memory": 512,
                    "cpu": 256,
                }
            ],
        }

        differences = compare_task_definitions(task_def_v30, task_def_v31)

        assert "image" in differences
        assert differences["image"]["old"] == "hokusai-api:v1.0.0"
        assert differences["image"]["new"] == "hokusai-api:v1.1.0"

    @patch("boto3.client")
    def test_list_task_definition_revisions(self, mock_boto_client):
        """Test listing all revisions of a task definition."""
        from scripts.ecs_analyzer import list_task_definition_revisions

        mock_ecs = MagicMock()
        mock_boto_client.return_value = mock_ecs

        mock_ecs.list_task_definitions.return_value = {
            "taskDefinitionArns": [
                "arn:aws:ecs:us-east-1:123456789:task-definition/hokusai-api:30",
                "arn:aws:ecs:us-east-1:123456789:task-definition/hokusai-api:31",
            ]
        }

        revisions = list_task_definition_revisions("hokusai-api")

        assert len(revisions) == 2
        assert revisions[0] == 30
        assert revisions[1] == 31


class TestS3LifecycleAnalyzer:
    """Test S3 bucket lifecycle policy analysis."""

    def test_parse_lifecycle_rules(self):
        """Test parsing S3 lifecycle configuration."""
        from scripts.s3_analyzer import parse_lifecycle_rules

        lifecycle_config = {
            "Rules": [
                {
                    "ID": "DeleteOldFiles",
                    "Status": "Enabled",
                    "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}],
                    "Expiration": {"Days": 90},
                }
            ]
        }

        parsed = parse_lifecycle_rules(lifecycle_config)

        assert len(parsed) == 1
        assert parsed[0]["id"] == "DeleteOldFiles"
        assert parsed[0]["transitions"][0]["days"] == 30
        assert parsed[0]["expiration_days"] == 90

    @patch("boto3.client")
    def test_audit_bucket_lifecycles(self, mock_boto_client):
        """Test auditing lifecycle policies across buckets."""
        from scripts.s3_analyzer import audit_bucket_lifecycles

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock list buckets
        mock_s3.list_buckets.return_value = {
            "Buckets": [{"Name": "hokusai-data"}, {"Name": "hokusai-models"}]
        }

        # Mock lifecycle configurations
        mock_s3.get_bucket_lifecycle_configuration.side_effect = [
            {"Rules": [{"ID": "Rule1", "Status": "Enabled"}]},
            ClientError(
                {"Error": {"Code": "NoSuchLifecycleConfiguration"}},
                "GetBucketLifecycleConfiguration",
            ),
        ]

        audit_results = audit_bucket_lifecycles()

        assert len(audit_results) == 2
        assert audit_results["hokusai-data"]["has_lifecycle"] is True
        assert audit_results["hokusai-models"]["has_lifecycle"] is False


class TestTerraformDriftDetector:
    """Test Terraform state drift detection."""

    def test_detect_drift_in_state(self):
        """Test detecting drift between Terraform state and actual resources."""
        from scripts.terraform_analyzer import detect_drift

        # Mock Terraform state
        tf_state = {
            "resources": [
                {
                    "type": "aws_db_instance",
                    "name": "main",
                    "instances": [
                        {"attributes": {"id": "hokusai-production", "engine_version": "13.7"}}
                    ],
                }
            ]
        }

        # Mock actual AWS state
        actual_state = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "hokusai-production",
                    "EngineVersion": "13.8",  # Different from Terraform
                }
            ]
        }

        drift = detect_drift(tf_state, actual_state)

        assert len(drift) == 1
        assert drift[0]["resource"] == "aws_db_instance.main"
        assert drift[0]["attribute"] == "engine_version"
        assert drift[0]["terraform_value"] == "13.7"
        assert drift[0]["actual_value"] == "13.8"


class TestInfrastructureMonitoring:
    """Test infrastructure monitoring setup."""

    @patch("boto3.client")
    def test_create_cloudwatch_alarm(self, mock_boto_client):
        """Test creating CloudWatch alarm for RDS changes."""
        from scripts.monitoring_setup import create_rds_change_alarm

        mock_cloudwatch = MagicMock()
        mock_boto_client.return_value = mock_cloudwatch

        alarm_name = create_rds_change_alarm(
            db_instance_id="hokusai-production",
            sns_topic_arn="arn:aws:sns:us-east-1:123456789:alerts",
        )

        mock_cloudwatch.put_metric_alarm.assert_called_once()
        assert alarm_name == "RDS-PasswordChange-hokusai-production"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
