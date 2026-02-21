from __future__ import annotations

import os
import time
from pathlib import Path

import gradio as gr
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def process_audio(audio_file: str):
    if not audio_file:
        return "No file selected.", "", None

    upload_url = f"{API_BASE_URL}/jobs/upload"
    with open(audio_file, "rb") as audio_stream:
        response = requests.post(upload_url, files={"file": (Path(audio_file).name, audio_stream)}, timeout=60)
    response.raise_for_status()
    job = response.json()
    job_id = job["job_id"]

    status_text = "queued"
    for _ in range(60):
        status_response = requests.get(f"{API_BASE_URL}/jobs/{job_id}", timeout=30)
        status_response.raise_for_status()
        status = status_response.json()
        status_text = status.get("status", "unknown")
        if status_text == "completed":
            break
        if status_text == "failed":
            return f"Job {job_id} failed.", "", None
        time.sleep(2)

    if status_text != "completed":
        return f"Job {job_id} still processing. Please retry shortly.", "", None

    result_response = requests.get(f"{API_BASE_URL}/jobs/{job_id}/result", timeout=30)
    result_response.raise_for_status()
    grouped_text = result_response.text

    output_path = Path("/tmp") / f"{job_id}_todos.txt"
    output_path.write_text(grouped_text, encoding="utf-8")

    return f"Job {job_id} completed.", grouped_text, str(output_path)


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
