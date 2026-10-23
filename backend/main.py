"""Taskboard API: tasks kept in PostgreSQL, with an optional S3 export and SQS events.

Every route starts with /api, the path the Deploy tab gives the backend, so
the frontend calls it on the same address (Vite's proxy does the same locally).
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()  # backend/.env, for local runs only

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

import aws  # noqa: E402
from db import session  # noqa: E402
from models import STATUSES, Task  # noqa: E402

# Change this to see a new deploy (and a rollback) in the page header.
APP_VERSION = "1.0.0"

log = logging.getLogger("taskboard")
app = FastAPI(title="Taskboard API", version=APP_VERSION)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TaskUpdate(BaseModel):
    status: str


def as_dict(task: Task) -> dict:
    return {"id": task.id, "title": task.title, "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None}


def runtime_name() -> str:
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "AWS Lambda"
    if os.environ.get("ECS_CONTAINER_METADATA_URI_V4"):
        return "ECS on Fargate"
    return "local or server"


@app.get("/api/health")
def health():
    # HEALTH_FAIL=true (Deploy tab, step 3) makes deploys fail on purpose, to test rollbacks.
    if os.environ.get("HEALTH_FAIL", "").strip().lower() in ("1", "true", "yes"):
        raise HTTPException(500, "HEALTH_FAIL is set")
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/info")
def info():
    try:
        with session() as db:
            db.execute(text("SELECT 1"))
        database = "connected"
    except Exception as error:  # shown in the page, so the cause is visible after a deploy
        log.exception("Database check failed")
        database = "unavailable (%s)" % type(error).__name__
    return {"version": APP_VERSION, "runtime": runtime_name(), "database": database,
            "s3_export": bool(aws.bucket()), "sqs_events": bool(aws.queue_url())}


@app.get("/api/tasks")
def list_tasks():
    with session() as db:
        return [as_dict(task) for task in db.scalars(select(Task).order_by(Task.id))]


@app.post("/api/tasks", status_code=201)
def create_task(body: TaskIn):
    with session() as db:
        task = Task(title=body.title.strip())
        db.add(task)
        db.commit()
        db.refresh(task)
        result = as_dict(task)
    try:
        aws.publish({"event": "task.created", "task": result})
    except Exception:  # the task is saved either way
        log.exception("Could not send the task.created event to SQS")
    return result


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate):
    if body.status not in STATUSES:
        raise HTTPException(422, "status must be one of: " + ", ".join(STATUSES))
    with session() as db:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(404, "No such task")
        task.status = body.status
        db.commit()
        db.refresh(task)
        return as_dict(task)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    with session() as db:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(404, "No such task")
        db.delete(task)
        db.commit()


@app.post("/api/tasks/export")
def export_tasks():
    if not aws.bucket():
        raise HTTPException(503, "S3_BUCKET is not set: add an S3 bucket to the plan and bind it to the backend")
    return aws.export_tasks(list_tasks())
