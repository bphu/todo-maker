from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse

from .celery_app import celery_app

app = FastAPI(title="todo-maker API", version="0.1.0")


def _job_dir(job_id: str) -> Path:
    root = Path(os.getenv("DATA_ROOT", "/data"))
    return root / "jobs" / job_id


def _status_path(job_id: str) -> Path:
    return _job_dir(job_id) / "status.json"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs/upload")
async def upload_audio(file: UploadFile = File(...)) -> dict[str, str]:
    job_id = uuid.uuid4().hex
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "input_audio"
    target = job_dir / filename
    content = await file.read()
    target.write_bytes(content)

    status = {
        "job_id": job_id,
        "status": "queued",
        "uploaded_file": filename,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _status_path(job_id).write_text(json.dumps(status, indent=2), encoding="utf-8")

    celery_app.send_task("pipeline.run_pipeline", args=[job_id])

    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    status_file = _status_path(job_id)
    if not status_file.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(status_file.read_text(encoding="utf-8"))


@app.get("/jobs/{job_id}/result", response_class=PlainTextResponse)
def get_job_result(job_id: str) -> str:
    output_path = _job_dir(job_id) / "artifacts" / "todos_by_person.txt"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Result not ready")
    return output_path.read_text(encoding="utf-8")
