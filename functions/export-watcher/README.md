# export-watcher

A Lambda function started by a file uploaded to S3. Its settings are in the repository's .sdlcforge/functions.json (the deployment tab's Function settings): packaging, runtime and handler, architecture, memory, timeout, triggers and managed-service bindings.

- **Test locally** (deployment tab) runs it in the official AWS Lambda image with Docker, with the sample event in events/. Edit the event to try other input.
- **Deploy** sends it with the environment's deploy; **Invoke**, **Logs** and **Roll back** work on the deployed function.

HTTP handlers return statusCode, headers and a string body (HTTP API payload format 2.0) and must answer within 30 seconds. SQS handlers return batchItemFailures for the messages that failed; those return to the queue and move to its dead-letter queue after five attempts. Scheduled and S3-triggered runs are retried twice, then kept in the function's failed-events queue. An S3 event names the uploaded file; it does not contain its bytes.

Use the function's IAM role for AWS clients (no keys in code). Keep passwords in the deployment tab's Secrets step.

Custom images: https://docs.aws.amazon.com/lambda/latest/dg/images-create.html
Custom runtimes: https://docs.aws.amazon.com/lambda/latest/dg/runtimes-custom.html
