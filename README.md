# todo-maker

Local-first AI pipeline for turning conversation audio into person-grouped to-do lists.

## What this project is designed to do
1. Accept an audio recording of a conversation.
2. Create a transcript with speaker labels.
3. Identify to-do items from the conversation.
4. Assign each to-do to the relevant person.
5. Export a text file grouped by person.

## Current scaffold in this repository
- `frontend/` Gradio UI for upload, status, and result download.
- `backend/` FastAPI API and Celery worker scaffold.
- `docker-compose.yml` local multi-service orchestration.
- `docs/ARCHITECTURE.md` system design and data contracts.
- `docs/CONTAINERIZATION.md` container strategy.
- `docs/CLOUD-ROADMAP.md` provider-agnostic cloud migration plan.

## Service outline
- `frontend`: Gradio app on port `7860`.
- `api`: FastAPI app on port `8000`.
- `worker`: Celery worker for async pipeline tasks.
- `redis`: queue broker and task backend.
- `ollama`: local LLM runtime for extraction/assignment stages.

## Quick start (local)
Prerequisites:
- Docker + Docker Compose
- NVIDIA driver + NVIDIA Container Toolkit (for GPU containers)

Run:
```bash
docker compose up --build
```

Then open:
- Frontend: `http://localhost:7860`
- API health: `http://localhost:8000/health`

## Notes about implementation stage
- The worker now performs real transcription with `faster-whisper` and attempts speaker diarization with `pyannote.audio`.
- If `HUGGINGFACE_TOKEN` is not set, transcription still runs and speakers default to `UNKNOWN`.
- To enable diarization, set `HUGGINGFACE_TOKEN` and ensure access to the selected `DIARIZATION_MODEL`.
- To tune runtime behavior, configure `ASR_MODEL`, `ASR_DEVICE`, `ASR_COMPUTE_TYPE`, and `ASR_BEAM_SIZE`.
- To-do extraction/assignment now uses Ollama by default and falls back to heuristic extraction when Ollama is unavailable or returns invalid output.

## Transcription and diarization configuration
Copy `.env.example` to `.env` and set values as needed.

Important environment variables:
- `TODO_USE_OLLAMA` (default `true`)
- `OLLAMA_BASE_URL` (default `http://ollama:11434`)
- `OLLAMA_MODEL` (default `qwen2.5:14b`)
- `OLLAMA_TIMEOUT_SEC` (default `180`)
- `ASR_MODEL` (default `large-v3`)
- `ASR_DEVICE` (`auto`, `cpu`, or `cuda`)
- `ASR_COMPUTE_TYPE` (`auto`, `float16`, `int8`, etc.)
- `ASR_BEAM_SIZE` (default `5`)
- `DIARIZATION_MODEL` (default `pyannote/speaker-diarization-3.1`)
- `HUGGINGFACE_TOKEN` (required for diarization)

When a job completes, status metadata now includes extraction mode and warnings (for example, fallback reason).

## Suggested production direction
- Keep the same service boundaries.
- Replace local storage with object storage.
- Replace local queue/cache with managed queue or managed Redis.
- Deploy containers to managed compute with autoscaling.

## Additional documentation
- [Architecture](docs/ARCHITECTURE.md)
- [Containerization](docs/CONTAINERIZATION.md)
- [Cloud Roadmap](docs/CLOUD-ROADMAP.md)

## Smoke test (end-to-end)
A ready-to-use multi-speaker sample file is included at:
- `test-data/sample-multi-speaker.wav`

Source:
- `https://raw.githubusercontent.com/pyannote/pyannote-audio/develop/tutorials/assets/sample.wav`

Run the stack:
```bash
docker compose up --build
```

Then run the smoke test from the repo root:
```bash
python scripts/smoke_test.py --api http://localhost:8000 --audio test-data/sample-multi-speaker.wav
```

Output is printed to terminal and saved under:
- `smoke-test-output/<job_id>_todos_by_person.txt`
