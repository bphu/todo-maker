from __future__ import annotations

import json
import os
from typing import Any
from typing import cast

import requests


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("LLM returned empty output")

    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    except json.JSONDecodeError:
        pass

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output")

    candidate = raw_text[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("LLM output JSON root must be an object")
    return cast(dict[str, Any], parsed)


def _build_prompt(transcript_segments: list[dict[str, Any]]) -> str:
    compact_segments = [
        {
            "segment_id": segment.get("segment_id"),
            "speaker_id": segment.get("speaker_id", "UNKNOWN"),
            "start_sec": segment.get("start_sec"),
            "end_sec": segment.get("end_sec"),
            "text": segment.get("text", ""),
        }
        for segment in transcript_segments
    ]

    transcript_json = json.dumps({"segments": compact_segments}, ensure_ascii=False)

    return (
        "You are an assistant that extracts action items from meeting transcripts. "
        "Return ONLY valid JSON with this schema: "
        "{\"todos\": [{\"todo_id\": string, \"text\": string, \"owner\": string, \"due\": string|null, \"confidence\": number, \"source_segment_ids\": string[]}]}. "
        "Rules: "
        "(1) owner must be one of the speaker_id values present in input, or UNKNOWN. "
        "(2) confidence between 0 and 1. "
        "(3) only include actionable items, do not include discussion-only statements. "
        "(4) preserve meaning and keep text concise. "
        "Input transcript JSON: "
        f"{transcript_json}"
    )


def _normalize_todos(payload: dict[str, Any], valid_speakers: set[str]) -> list[dict[str, Any]]:
    raw_todos = payload.get("todos", [])
    if not isinstance(raw_todos, list):
        raise ValueError("LLM payload field 'todos' must be a list")

    normalized: list[dict[str, Any]] = []
    for idx, raw_item in enumerate(raw_todos, start=1):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        owner = str(item.get("owner", "UNKNOWN")).strip() or "UNKNOWN"
        if owner not in valid_speakers:
            owner = "UNKNOWN"

        due = item.get("due")
        due_value = None if due in (None, "", "null") else str(due).strip()

        confidence_raw = item.get("confidence", 0.5)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        raw_source_segment_ids = item.get("source_segment_ids", [])
        if not isinstance(raw_source_segment_ids, list):
            raw_source_segment_ids = []
        source_segment_ids = [
            str(segment_id) for segment_id in raw_source_segment_ids if str(segment_id).strip()
        ]

        todo_id = str(item.get("todo_id", f"todo_{idx:04d}")).strip() or f"todo_{idx:04d}"

        normalized.append(
            {
                "todo_id": todo_id,
                "text": text,
                "owner": owner,
                "due": due_value,
                "confidence": confidence,
                "source_segment_ids": source_segment_ids,
            }
        )

    return normalized


def extract_todos_with_ollama(transcript_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not transcript_segments:
        return []

    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    timeout_sec = int(os.getenv("OLLAMA_TIMEOUT_SEC", "180"))

    prompt = _build_prompt(transcript_segments)

    response = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": "You extract actionable tasks and owner assignments from transcript segments."},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0.1,
            },
        },
        timeout=timeout_sec,
    )
    response.raise_for_status()

    payload = response.json()
    message = payload.get("message", {})
    content = message.get("content", "")

    llm_json = _extract_json_object(str(content))
    valid_speakers = {str(segment.get("speaker_id", "UNKNOWN")) for segment in transcript_segments}
    valid_speakers.add("UNKNOWN")

    return _normalize_todos(llm_json, valid_speakers)
