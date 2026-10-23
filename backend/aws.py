"""Optional AWS features. Each one turns on only when its variable is set.

The Deploy tab binds S3_BUCKET and SQS_QUEUE_URL to the plan's S3 bucket and
SQS queue. No AWS keys are needed on AWS: the app's IAM role gives access.
"""
import json
import os
from datetime import datetime, timezone


def bucket() -> str:
    return os.environ.get("S3_BUCKET", "").strip()


def queue_url() -> str:
    return os.environ.get("SQS_QUEUE_URL", "").strip()


def _client(service: str):
    import boto3  # imported here so local runs without AWS start faster

    return boto3.client(service)


def export_tasks(rows: list) -> dict:
    """Writes every task to exports/tasks-<time>.json in the bucket."""
    key = "exports/tasks-%s.json" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _client("s3").put_object(Bucket=bucket(), Key=key, Body=json.dumps(rows, indent=2).encode(), ContentType="application/json")
    return {"bucket": bucket(), "key": key}


def publish(event: dict) -> bool:
    """Sends an event to the queue; False when no queue is configured."""
    if not queue_url():
        return False
    _client("sqs").send_message(QueueUrl=queue_url(), MessageBody=json.dumps(event))
    return True
