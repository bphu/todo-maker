from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import gradio as gr
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _format_api_error(prefix: str, response: requests.Response) -> str:
    details = response.text.strip()
    try:
        payload = response.json()
        if isinstance(payload, dict):
            details = str(payload.get("detail") or payload.get("error") or payload)
        else:
            details = str(payload)
    except ValueError:
        pass

    return (
        f"{prefix}\n"
        f"HTTP {response.status_code} from {response.request.method} {response.url}\n"
        f"Details: {details}"
    )


def _format_failed_job_message(job_id: str, status: dict[str, Any]) -> str:
    error_message = str(status.get("error", "No error details were provided by backend."))

    extraction = status.get("extraction", {})
    extraction_mode = extraction.get("mode") if isinstance(extraction, dict) else None
    extraction_warnings = extraction.get("warnings", []) if isinstance(extraction, dict) else []

    runtime = status.get("runtime", {})
    runtime_warnings = runtime.get("warnings", []) if isinstance(runtime, dict) else []

    lines = [
        f"Job {job_id} failed.",
        f"Error: {error_message}",
    ]

    if extraction_mode:
        lines.append(f"Extraction mode: {extraction_mode}")
    if extraction_warnings:
        lines.append(f"Extraction warnings: {' | '.join(str(w) for w in extraction_warnings)}")
    if runtime_warnings:
        lines.append(f"Runtime warnings: {' | '.join(str(w) for w in runtime_warnings)}")

    return "\n".join(lines)


def process_audio(audio_file: str):
    if not audio_file:
        return "No file selected.", "", None

    try:
        upload_url = f"{API_BASE_URL}/jobs/upload"
        with open(audio_file, "rb") as audio_stream:
            response = requests.post(upload_url, files={"file": (Path(audio_file).name, audio_stream)}, timeout=60)

        if response.status_code >= 400:
            return _format_api_error("Upload failed.", response), "", None

        job = response.json()
        job_id = str(job.get("job_id", "unknown"))

        status_text = "queued"
        status_payload: dict[str, Any] = {}
        for _ in range(60):
            status_response = requests.get(f"{API_BASE_URL}/jobs/{job_id}", timeout=30)
            if status_response.status_code >= 400:
                return _format_api_error(f"Status check failed for job {job_id}.", status_response), "", None

            payload = status_response.json()
            status_payload = payload if isinstance(payload, dict) else {}
            status_text = str(status_payload.get("status", "unknown"))
            if status_text == "completed":
                break
            if status_text == "failed":
                return _format_failed_job_message(job_id, status_payload), "", None
            time.sleep(2)

        if status_text != "completed":
            return (
                f"Job {job_id} is still processing after timeout.\n"
                "Try again in a minute and check backend logs for long-running model initialization."
            ), "", None

        result_response = requests.get(f"{API_BASE_URL}/jobs/{job_id}/result", timeout=30)
        if result_response.status_code >= 400:
            return _format_api_error(f"Result retrieval failed for job {job_id}.", result_response), "", None

        grouped_text = result_response.text
        output_path = Path("/tmp") / f"{job_id}_todos.txt"
        output_path.write_text(grouped_text, encoding="utf-8")

        return f"Job {job_id} completed.", grouped_text, str(output_path)
    except requests.RequestException as request_error:
        return (
            "Network/API request failed.\n"
            f"Error type: {type(request_error).__name__}\n"
            f"Details: {request_error}"
        ), "", None
    except Exception as unexpected_error:
        return (
            "Unexpected frontend processing error.\n"
            f"Error type: {type(unexpected_error).__name__}\n"
            f"Details: {unexpected_error}"
        ), "", None


with gr.Blocks(title="todo-maker") as demo:
    gr.Markdown("# todo-maker\nUpload a conversation recording to generate grouped to-do items.")

    audio_input = gr.Audio(type="filepath", label="Conversation Audio")
    run_btn = gr.Button("Process")

    status_output = gr.Textbox(label="Status")
    todos_output = gr.Textbox(label="To-Do Items by Person", lines=14)
    download_output = gr.File(label="Download Text File")

    run_btn.click(
        fn=process_audio,
        inputs=[audio_input],
        outputs=[status_output, todos_output, download_output],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
