from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests


def run_smoke_test(api_base_url: str, audio_file: Path, poll_interval_sec: float, timeout_sec: int) -> int:
    if not audio_file.exists() or not audio_file.is_file():
        print(f"Audio file not found: {audio_file}")
        return 2

    print(f"Uploading: {audio_file}")
    upload_url = f"{api_base_url.rstrip('/')}/jobs/upload"

    with audio_file.open("rb") as stream:
        upload_response = requests.post(
            upload_url,
            files={"file": (audio_file.name, stream, "audio/wav")},
            timeout=120,
        )

    if upload_response.status_code >= 400:
        print(f"Upload failed [{upload_response.status_code}]: {upload_response.text}")
        return 3

    payload = upload_response.json()
    job_id = payload.get("job_id")
    if not job_id:
        print(f"Unexpected upload response: {payload}")
        return 4

    print(f"Job queued: {job_id}")

    status_url = f"{api_base_url.rstrip('/')}/jobs/{job_id}"
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        status_response = requests.get(status_url, timeout=60)
        if status_response.status_code >= 400:
            print(f"Status check failed [{status_response.status_code}]: {status_response.text}")
            return 5

        status_payload = status_response.json()
        status = str(status_payload.get("status", "unknown"))
        print(f"Status: {status}")

        if status == "completed":
            break
        if status == "failed":
            print("Job failed:")
            print(status_payload)
            return 6

        time.sleep(poll_interval_sec)
    else:
        print(f"Timed out after {timeout_sec}s waiting for completion")
        return 7

    result_url = f"{api_base_url.rstrip('/')}/jobs/{job_id}/result"
    result_response = requests.get(result_url, timeout=60)
    if result_response.status_code >= 400:
        print(f"Result fetch failed [{result_response.status_code}]: {result_response.text}")
        return 8

    output_dir = Path("smoke-test-output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{job_id}_todos_by_person.txt"
    output_file.write_text(result_response.text, encoding="utf-8")

    print("\n=== Grouped To-Dos ===")
    print(result_response.text)
    print(f"Saved output: {output_file.resolve()}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="End-to-end smoke test for todo-maker API pipeline")
    parser.add_argument("--api", default="http://localhost:8000", help="Base URL of API service")
    parser.add_argument(
        "--audio",
        default="test-data/sample-multi-speaker.wav",
        help="Path to input audio file",
    )
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Seconds between status polls")
    parser.add_argument("--timeout", type=int, default=900, help="Total timeout in seconds")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit_code = run_smoke_test(
        api_base_url=args.api,
        audio_file=Path(args.audio),
        poll_interval_sec=args.poll_interval,
        timeout_sec=args.timeout,
    )
    sys.exit(exit_code)
