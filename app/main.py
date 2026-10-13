from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.worker import continue_task, run_task
from app.database.db import get_connection, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CentrAlign AI Task Worker",
    description="Autonomous invoice-processing prototype",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class TaskRequest(BaseModel):
    task: str = Field(min_length=5, max_length=1000)


class ReplyRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=1000)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "CentrAlign AI Task Worker",
    }


@app.post("/api/run-task")
def run_task_endpoint(request: TaskRequest):
    task = request.task.strip()

    if len(task) < 5:
        raise HTTPException(
            status_code=422,
            detail="Task must contain at least 5 non-whitespace characters.",
        )

    try:
        return run_task(task)
    except Exception as exc:
        import logging

        logging.exception("Task execution failed")

        raise HTTPException(
            status_code=500,
            detail=f"Task execution failed: {type(exc).__name__}: {exc}",
        ) from exc


@app.post("/api/runs/{run_id}/reply")
def reply_to_run_endpoint(run_id: str, request: ReplyRequest):
    reply = request.reply.strip()

    if not reply:
        raise HTTPException(status_code=422, detail="Reply cannot be empty.")

    try:
        return continue_task(run_id, reply)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Run not found. It may have expired after a server restart.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/invoices")
def list_invoices():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT invoice_id, supplier, invoice_date,
                   amount, due_date, description
            FROM invoices
            ORDER BY invoice_date DESC
            """
        ).fetchall()

    return {"invoices": [dict(row) for row in rows]}


@app.get("/api/records")
def list_internal_records():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT record_id, invoice_id, supplier,
                   amount, due_date, created_at
            FROM internal_records
            ORDER BY created_at DESC
            """
        ).fetchall()

    return {"records": [dict(row) for row in rows]}
