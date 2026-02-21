# Containerization Outline

## Recommendation
Containerize from day one. It adds small initial setup cost but reduces environment drift and simplifies cloud migration.

## Local Deployment Model
Use Docker Compose with these services:

- `frontend`: Gradio app
- `api`: FastAPI app
- `worker`: Celery worker for pipeline tasks
- `redis`: broker/backing store for queue state
- `ollama`: local LLM runtime for extraction/assignment

## GPU Notes
- Linux host is preferred for GPU stability.
- Install NVIDIA drivers and NVIDIA Container Toolkit.
- Run GPU workloads in services that need them (`worker`, optionally `ollama`).

## Proposed Compose Responsibilities
- `frontend` calls `api` over internal network.
- `api` writes files to shared volume and enqueues jobs.
- `worker` consumes queue, runs pipeline, writes artifacts.
- `redis` coordinates background tasks.
- `ollama` serves local model inference APIs.

## Volumes
- `./data` mounted into API/worker for persistent artifacts.
- `ollama_data` named volume for model files.

## Cloud Transition Mapping
Keep the same service boundaries and swap infrastructure:

- Local `./data` -> object storage (S3/Blob/GCS)
- Local Redis -> managed Redis or managed queue
- Compose services -> containers in Kubernetes / container apps / ECS
- Local secrets -> cloud secret manager

## CI/CD Direction
- Build images per service.
- Push to container registry.
- Deploy with environment-specific config.
- Run smoke tests on startup endpoints.
