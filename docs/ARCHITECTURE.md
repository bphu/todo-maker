# Architecture Outline

## Goal
Build a local-first AI tool that:
1. Accepts a conversation audio file.
2. Produces a timestamped transcript.
3. Detects speakers.
4. Extracts to-do items.
5. Assigns each to-do item to the correct person.
6. Exports a text file grouped by person.

## High-Level Design
Use an asynchronous pipeline with clear stage boundaries:

1. **Frontend (Gradio Web UI)**
   - Upload audio
   - View job status
   - Display transcript + speaker labels
   - Display grouped to-do list
   - Download output text file

2. **Backend API (FastAPI)**
   - Accept upload and create `job_id`
   - Persist job metadata and file paths
   - Expose status and result endpoints
   - Trigger background processing queue

3. **Workers (Celery)**
   - `transcription_worker`: speech-to-text + word timestamps
   - `diarization_worker`: speaker segmentation and labels
   - `extraction_worker`: to-do extraction from transcript segments
   - `assignment_worker`: map each to-do to responsible speaker/person
   - `export_worker`: build grouped text artifact

4. **Runtime Services**
   - Redis: queue + transient state
   - Local LLM runtime (Ollama): extraction/assignment prompts
   - GPU-enabled ML stack for ASR/diarization

5. **Storage**
   - Local volume for raw audio, intermediate JSON, final output files
   - Suggested path: `./data/jobs/<job_id>/`

## Data Contracts

### Transcript Segment
```json
{
  "segment_id": "seg_0001",
  "speaker_id": "SPEAKER_01",
  "start_sec": 12.4,
  "end_sec": 16.1,
  "text": "I'll send the draft by Friday."
}
```

### To-Do Item
```json
{
  "todo_id": "todo_0001",
  "text": "Send the draft",
  "owner": "SPEAKER_01",
  "due": "Friday",
  "confidence": 0.88,
  "source_segment_ids": ["seg_0001"]
}
```

### Exported Output Format
```text
SPEAKER_01
- Send the draft (due: Friday)

SPEAKER_02
- Review the draft
```

## Processing Flow
1. Upload audio to API.
2. API stores file and enqueues job.
3. Worker chain runs stage-by-stage.
4. Intermediate artifacts are written as JSON.
5. Final text file is written to job folder.
6. Frontend polls status and renders final outputs.

## Why This Architecture
- **Reliable retries:** each stage is independently retryable.
- **Scalable later:** worker counts can be increased in cloud.
- **Cloud-ready:** easy migration to managed queues/object storage.
- **Simple local start:** all components run with Docker Compose.
