"""Answers an HTTP request (API Gateway HTTP API, payload format 2.0)."""
import json


def handler(event, context):
    method = event["requestContext"]["http"]["method"]
    name = (event.get("queryStringParameters") or {}).get("name", "world")
    body = json.loads(event["body"]) if event.get("body") else None
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"message": "Hello, %s" % name, "method": method, "path": event["rawPath"], "received": body}),
    }
