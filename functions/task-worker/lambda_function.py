"""Processes queue messages (SQS). A message whose processing fails is returned to the queue;
after five failures it moves to the queue's dead-letter queue."""
import json


def handler(event, context):
    failures = []
    for record in event["Records"]:
        try:
            message = json.loads(record["body"])
            print("Processing message %s: %s" % (record["messageId"], message))
        except Exception as error:  # Report only this message as failed; the others are done.
            print("Message %s failed: %s" % (record["messageId"], error))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
