# Taskboard

A small app for testing SDLCForge deployments: a React (Vite) frontend and a FastAPI backend that keeps tasks in PostgreSQL, with Alembic migrations.
It can also export tasks to S3 and send an event to SQS when a task is created; each of those turns on only when its variable is set.

```
frontend/   React + Vite. Calls the API at /api on the same address.
backend/    FastAPI. Routes under /api. DATABASE_URL (required), S3_BUCKET and SQS_QUEUE_URL (optional).
            alembic.ini + migrations/: run `alembic upgrade head` from this folder.
```

- Run it locally: TESTING-SERVERLESS.md, "Appendix: configure and run the app locally".
- Test the serverless deployment with it: TESTING-SERVERLESS.md.

API: `GET /api/health`, `GET /api/info`, `GET|POST /api/tasks`, `PATCH|DELETE /api/tasks/{id}`, `POST /api/tasks/export`.
Set `HEALTH_FAIL=true` to make `/api/health` fail on purpose (for testing failed deploys).
