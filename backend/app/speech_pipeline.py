from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PipelineRuntime:
    asr_device: str
    asr_compute_type: str
    diarization_enabled: bool
    warnings: list[str]


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _detect_runtime() -> PipelineRuntime:
    warnings: list[str] = []

    device_preference = os.getenv("ASR_DEVICE", "auto").lower()
    compute_type = os.getenv("ASR_COMPUTE_TYPE", "auto").lower()

    device = "cpu"
    if device_preference == "cuda":
        device = "cuda"
    elif device_preference == "cpu":
        device = "cpu"
    else:
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
            warnings.append("torch not available for device probing, defaulting ASR to CPU")

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    diarization_enabled = bool(os.getenv("HUGGINGFACE_TOKEN", "").strip())
    if not diarization_enabled:
        warnings.append("HUGGINGFACE_TOKEN is not set; diarization is disabled and speakers will be UNKNOWN")

    return PipelineRuntime(
        asr_device=device,
        asr_compute_type=compute_type,
        diarization_enabled=diarization_enabled,
        warnings=warnings,
    )


def _run_asr(audio_path: Path, runtime: PipelineRuntime) -> list[dict[str, Any]]:
    from faster_whisper import WhisperModel

    model_size = os.getenv("ASR_MODEL", "large-v3")
    beam_size = int(os.getenv("ASR_BEAM_SIZE", "5"))

    model = WhisperModel(model_size, device=runtime.asr_device, compute_type=runtime.asr_compute_type)
    segments_iter, _ = model.transcribe(
        str(audio_path),
        beam_size=beam_size,
        vad_filter=True,
        word_timestamps=True,
    )

    asr_segments: list[dict[str, Any]] = []
    for idx, segment in enumerate(segments_iter, start=1):
        asr_segments.append(
            {
                "segment_id": f"seg_{idx:04d}",
                "start_sec": float(segment.start),
                "end_sec": float(segment.end),
                "text": segment.text.strip(),
            }
        )
    return asr_segments


def _run_diarization(audio_path: Path, runtime: PipelineRuntime) -> list[dict[str, Any]]:
    if not runtime.diarization_enabled:
        return []

    diarization_model = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
    token = os.getenv("HUGGINGFACE_TOKEN", "")

    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(diarization_model, use_auth_token=token)

    if runtime.asr_device == "cuda":
        try:
            import torch

            pipeline.to(torch.device("cuda"))
        except Exception:
            runtime.warnings.append("Could not move diarization pipeline to CUDA; using CPU")

    diarization = pipeline(str(audio_path))

    diarization_segments: list[dict[str, Any]] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        diarization_segments.append(
            {
                "speaker": str(speaker),
                "start_sec": float(turn.start),
                "end_sec": float(turn.end),
            }
        )
    return diarization_segments


def _assign_speakers(
    asr_segments: list[dict[str, Any]], diarization_segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not diarization_segments:
        for segment in asr_segments:
            segment["speaker_id"] = "UNKNOWN"
        return asr_segments

    for segment in asr_segments:
        start_sec = float(segment["start_sec"])
        end_sec = float(segment["end_sec"])

        best_speaker = "UNKNOWN"
        best_overlap = 0.0

        for diarization_segment in diarization_segments:
            overlap = _overlap(
                start_sec,
                end_sec,
                float(diarization_segment["start_sec"]),
                float(diarization_segment["end_sec"]),
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = str(diarization_segment["speaker"])

        segment["speaker_id"] = best_speaker
    return asr_segments


def transcribe_and_diarize(audio_path: Path) -> dict[str, Any]:
    runtime = _detect_runtime()

    asr_segments = _run_asr(audio_path, runtime)

    diarization_segments: list[dict[str, Any]] = []
    if runtime.diarization_enabled:
        try:
            diarization_segments = _run_diarization(audio_path, runtime)
        except Exception as diarization_error:  # pragma: no cover - runtime/hardware dependent
            runtime.warnings.append(f"Diarization failed and was skipped: {diarization_error}")

    merged_segments = _assign_speakers(asr_segments, diarization_segments)

    return {
        "segments": merged_segments,
        "diarization_segments": diarization_segments,
        "metadata": {
            "asr_device": runtime.asr_device,
            "asr_compute_type": runtime.asr_compute_type,
            "asr_model": os.getenv("ASR_MODEL", "large-v3"),
            "diarization_model": os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1"),
            "diarization_enabled": runtime.diarization_enabled,
            "warnings": runtime.warnings,
        },
    }
