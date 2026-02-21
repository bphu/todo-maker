from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .celery_app import celery_app
from .speech_pipeline import transcribe_and_diarize
from .todo_extractor import extract_todos_with_ollama

celery = celery_app


def _job_dir(job_id: str) -> Path:
    root = Path(os.getenv("DATA_ROOT", "/data"))
    return root / "jobs" / job_id


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _find_uploaded_audio(job_dir: Path) -> Path:
    allowed_suffixes = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".mp4", ".webm"}
    candidates: list[Path] = []

    for child in job_dir.iterdir():
        if not child.is_file():
            continue
        if child.name == "status.json" or child.suffix.lower() == ".json":
            continue
        if child.suffix.lower() in allowed_suffixes:
            candidates.append(child)

    if not candidates:
        raise FileNotFoundError(f"No supported audio file found in {job_dir}")

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _extract_todos(transcript_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trigger_phrases = ("i will", "i'll", "we need", "todo", "can you", "please", "action item")
    todos: list[dict[str, Any]] = []

    for index, segment in enumerate(transcript_segments, start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        lowered = text.lower()
        if not any(trigger in lowered for trigger in trigger_phrases):
            continue

        todos.append(
            {
                "todo_id": f"todo_{index:04d}",
                "text": text,
                "owner": str(segment.get("speaker_id", "UNKNOWN")),
                "due": None,
                "confidence": 0.6,
                "source_segment_ids": [str(segment.get("segment_id", f"seg_{index:04d}"))],
            }
        )

    if todos:
        return todos

    fallback_segments = transcript_segments[:5]
    for index, segment in enumerate(fallback_segments, start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        todos.append(
            {
                "todo_id": f"todo_{index:04d}",
                "text": f"Review discussion item: {text}",
                "owner": str(segment.get("speaker_id", "UNKNOWN")),
                "due": None,
                "confidence": 0.35,
                "source_segment_ids": [str(segment.get("segment_id", f"seg_{index:04d}"))],
            }
        )
    return todos


def _group_todos_by_owner(todos: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for todo in todos:
        owner = str(todo.get("owner", "UNKNOWN"))
        grouped.setdefault(owner, []).append(todo)

    lines: list[str] = []
    for owner in sorted(grouped.keys()):
        lines.append(owner)
        for item in grouped[owner]:
            due = item.get("due")
            due_suffix = f" (due: {due})" if due else ""
            lines.append(f"- {item.get('text', '')}{due_suffix}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


@celery_app.task(name="pipeline.run_pipeline")
def run_pipeline(job_id: str) -> dict[str, Any]:
    job_dir = _job_dir(job_id)
    artifacts_dir = job_dir / "artifacts"
    _write_json(
        job_dir / "status.json",
        {"job_id": job_id, "status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()},
    )

    try:
        audio_path = _find_uploaded_audio(job_dir)
        transcript = transcribe_and_diarize(audio_path)
        transcript_segments = transcript.get("segments", [])
        extraction_mode = "heuristic"
        extraction_warnings: list[str] = []

        if os.getenv("TODO_USE_OLLAMA", "true").lower() in {"1", "true", "yes", "on"}:
            try:
                llm_todos = extract_todos_with_ollama(transcript_segments)
                if llm_todos:
                    todos_payload = {"todos": llm_todos}
                    extraction_mode = "ollama"
                else:
                    todos_payload = {"todos": _extract_todos(transcript_segments)}
                    extraction_warnings.append("Ollama extraction returned no todos; used heuristic fallback")
            except Exception as extraction_error:
                todos_payload = {"todos": _extract_todos(transcript_segments)}
                extraction_warnings.append(f"Ollama extraction failed; used heuristic fallback: {extraction_error}")
        else:
            todos_payload = {"todos": _extract_todos(transcript_segments)}

        grouped_output = _group_todos_by_owner(todos_payload["todos"])

        _write_json(artifacts_dir / "transcript.json", transcript)
        _write_json(artifacts_dir / "todos.json", todos_payload)
        (artifacts_dir / "todos_by_person.txt").write_text(grouped_output, encoding="utf-8")

        status: dict[str, Any] = {
            "job_id": job_id,
            "status": "completed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {
                "transcript": str((artifacts_dir / "transcript.json").name),
                "todos": str((artifacts_dir / "todos.json").name),
                "grouped_text": str((artifacts_dir / "todos_by_person.txt").name),
            },
            "runtime": transcript.get("metadata", {}),
            "extraction": {
                "mode": extraction_mode,
                "warnings": extraction_warnings,
            },
        }
        _write_json(job_dir / "status.json", status)
        return status
    except Exception as pipeline_error:
        failed_status = {
            "job_id": job_id,
            "status": "failed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": str(pipeline_error),
        }
        _write_json(job_dir / "status.json", failed_status)
        raise
