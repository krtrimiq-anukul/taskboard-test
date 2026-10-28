"""Runs when a file is uploaded (S3 ObjectCreated). The event names the file; read it with boto3 if needed.
Retried twice on failure; then the event is kept in its failed-events queue."""
from urllib.parse import unquote_plus


def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        print("New file: s3://%s/%s (%s bytes)" % (bucket, key, record["s3"]["object"].get("size")))
    return {"ok": True}
